import base64
import binascii
import hashlib
import html as _html
import io
import json
import os
import pathlib
import secrets
import shutil
import smtplib
import ssl
import threading
import urllib.parse
import uuid
from email.message import EmailMessage
from html import escape

import bcrypt
import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

# database.py import edilirken .env okunur; ortam değişkenlerini bundan SONRA okuyoruz
from database import VERI_DIR, get_db, tablolari_olustur
import models
import schemas
from datetime import date

import re
ALANLAR = ("kasinti", "buyume", "agri", "degisim", "kanama", "kabarik", "aile_gecmisi")

_TR = str.maketrans({
    "ı": "i", "İ": "i", "I": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
})


def _normalize(metin: str) -> str:
    return metin.translate(_TR).lower()


# Fiil olumsuzluk ekleri: kasinmiyor, buyumedi, kabarmamis, kanamayan, kasinmaz ...
_OLUMSUZ_EK = re.compile(r"(?:m[iu]yor(?:um)?|m[iu]yo|m[ae]di(?:m)?|m[ae]mis|m[ae]yan|m[ae]z)$")

_YOK = {"yok", "yoktur", "degil", "olmadi", "olmuyor", "olmamis", "bulunmuyor", "hayir"}
_VAR = {"var", "vardir", "vardi", "mevcut", "oluyor", "oldu", "olmus", "basladi", "evet",
        "gecirdi", "gecirmis", "gecirdiler", "teshis", "tedavi"}

_AYIRAC = {"ama", "fakat", "ancak", "lakin"}

_AKRABA = ("aile", "anne", "baba", "kardes", "dede", "nine", "teyze", "dayi", "amca", "akraba")
_HASTALIK = ("kanser", "melanom", "karsinom", "tumor", "lenfoma")


def _alan(tok: str) -> str | None:
    """Sözcük bir belirti ya da aile sözcüğü ise hangi alana ait olduğunu döner."""
    if tok.startswith("kasin"):
        return "kasinti"
    if (tok.startswith("buyu") and not tok.startswith("buyuk")) or tok.startswith(("irile", "genisle")):
        return "buyume"
    if tok.startswith(("agri", "sizla", "aciyor", "acisi")) or tok == "aci":
        return "agri"
    if tok.startswith("degis"):
        return "degisim"
    if tok.startswith(("kanam", "kanad", "kaniy", "kanay", "kanli", "kanl")) or tok == "kan":
        return "kanama"
    if tok.startswith(("kabar", "sisk", "sism", "yukselt")) or tok == "sis":
        return "kabarik"
    if tok.startswith(_AKRABA):
        return "aile_gecmisi"
    return None


def _belirtileri_cikar(metin: str) -> dict:
    sonuc = {a: None for a in ALANLAR}
    kesin = set()  # var/yok sözcüğüyle belirlenenler; bunlar sonradan "varsayılan"la ezilmez

    for cumle in re.split(r"[.!?;\n]+|,", _normalize(metin)):
        bekleyen: list[str] = []
        hastalik_gecti = False

        def bitir():
            """var/yok gelmeden biten bölüm: belirti anıldığı için "var" say."""
            for a in bekleyen:
                if a in kesin:
                    continue
                if a == "aile_gecmisi":
                    if hastalik_gecti:
                        sonuc[a] = True
                else:
                    sonuc[a] = True
            bekleyen.clear()

        for tok in re.findall(r"[a-z0-9]+", cumle):
            if tok in _AYIRAC:  # "ama", "fakat": önceki bölüm burada biter
                bitir()
                continue
            if tok.startswith(_HASTALIK):
                hastalik_gecti = True
                continue
            if tok in _YOK or tok in _VAR:
                deger = tok in _VAR
                for a in bekleyen:
                    sonuc[a] = deger
                    kesin.add(a)
                bekleyen = []
                continue
            alan = _alan(tok)
            if alan is None:
                continue
            if alan != "aile_gecmisi" and _OLUMSUZ_EK.search(tok):
                sonuc[alan] = False  # "kaşınmıyor", "büyümedi" ...
                kesin.add(alan)
            elif alan not in bekleyen:
                bekleyen.append(alan)
        bitir()  # cümle sonu
    return sonuc


def _bilgi_olustur(metin: str) -> dict:
    """lezyon_hakkinda.bilgi (JSONB) içine yazılacak nesne."""
    return {"metin": metin, "belirtiler": _belirtileri_cikar(metin)}


app = FastAPI(title="Dermavision API")

KOK = pathlib.Path(__file__).resolve().parent
UPLOAD_DIR = VERI_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = os.environ.get("DERMA_BASE_URL", "http://localhost:8000").rstrip("/")
# E-postalardaki bağlantılar için adres. Tanımlı değilse BASE_URL kullanılır.
# Yerelde localhost açılmıyorsa .env'e DERMA_LINK_URL=http://127.0.0.1:8000 yazın.
# (Google girişi BASE_URL'de kalır; ikisi birbirinden bağımsızdır.)
LINK_URL = os.environ.get("DERMA_LINK_URL", BASE_URL).rstrip("/")
# E-postadaki "Uygulamaya dön" düğmesi bu adresi açar (Google girişi bunu KULLANMAZ; uygulama kendi adresini gönderir).
# Expo Go: exp://<bilgisayarın-ip>:8081   |  Derlenmiş uygulama: dermavision://giris
APP_URL = os.environ.get("DERMA_APP_URL", "derma://giris")
SECRET = os.environ.get("DERMA_SECRET_KEY")
if not SECRET:
    SECRET = "gelistirme-icin-gecici-anahtar"
    print("[UYARI] DERMA_SECRET_KEY tanımlı değil, geçici anahtar kullanılıyor. Canlıda mutlaka tanımlayın.")
ser = URLSafeTimedSerializer(SECRET)

GOOGLE_CLIENT_ID = os.environ.get(
    "GOOGLE_CLIENT_ID",
    "680566286065-ben5ll4iju106tr3d99r77b6iactciob.apps.googleusercontent.com",
)
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
REDIRECT_URI = f"{BASE_URL}/api/auth/google/callback"

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").replace(" ", "")  # Gmail şifreyi boşluklu gösterir
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)

tablolari_olustur()  # tablolar yoksa oluşturur


# ---------------------------------------------------------------- E-posta
def eposta_gonder(kime: str, konu: str, aciklama: str, dugme: str, link: str):
    """SMTP ile e-posta yollar. SMTP ayarı yoksa bağlantıyı terminale yazar."""
    if not (SMTP_USER and SMTP_PASSWORD):
        print(f"[MAIL - SMTP ayarlı değil, gönderilmedi] {kime} | {konu} | {link}")
        return
    msg = EmailMessage()
    msg["Subject"] = konu
    msg["From"] = f"DermaVision <{SMTP_FROM}>"
    msg["To"] = kime
    msg.set_content(f"{aciklama}\n\n{link}\n\nBu e-postayı siz istemediyseniz dikkate almayın.")
    msg.add_alternative(
        f"""<div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;color:#14284B">
<h2 style="color:#1B3A6B">DermaVision</h2>
<p>{escape(aciklama)}</p>
<p><a href="{escape(link)}" style="display:inline-block;background:#1B3A6B;color:#ffffff;text-decoration:none;padding:12px 22px;border-radius:10px;font-weight:bold">{escape(dugme)}</a></p>
<p style="font-size:12px;color:#5B6B86">Düğme çalışmazsa bu adresi tarayıcınıza yapıştırın:<br>{escape(link)}</p>
<p style="font-size:12px;color:#5B6B86">Bu e-postayı siz istemediyseniz dikkate almayın. DermaVision bir tanı aracı değildir.</p>
</div>""",
        subtype="html",
    )
    try:
        if SMTP_PORT == 465:  # SSL ile doğrudan bağlantı
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15, context=ssl.create_default_context()) as s:
                s.login(SMTP_USER, SMTP_PASSWORD)
                s.send_message(msg)
        else:  # 587: STARTTLS
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(SMTP_USER, SMTP_PASSWORD)
                s.send_message(msg)
        print(f"[MAIL] gönderildi: {kime}")
    except Exception as ex:
        if isinstance(ex, smtplib.SMTPAuthenticationError):
            ipucu = "Gmail girişi reddedildi: SMTP_USER tam adres (...@gmail.com) ve SMTP_PASSWORD uygulama şifresi olmalı."
        elif isinstance(ex, OSError):
            ipucu = "Gmail sunucusuyla bağlantı kurulamadı: .env'e SMTP_PORT=465 yazıp deneyin; antivirüs veya ağ (okul/yurt Wi-Fi'si) engelliyor olabilir."
        else:
            ipucu = ""
        print(f"[MAIL HATA] {kime}: {type(ex).__name__}: {ex} {ipucu}")
        print(f"[MAIL] (yedek, yalnızca geliştirme için) bağlantı: {link}")


def aktivasyon_maili(eposta: str):
    t = ser.dumps(eposta.lower(), salt="aktivasyon")
    eposta_gonder(
        eposta,
        "DermaVision hesabınızı etkinleştirin",
        "Hesabınızı etkinleştirmek için aşağıdaki düğmeye tıklayın. Bağlantı 24 saat geçerlidir.",
        "Hesabımı etkinleştir",
        f"{LINK_URL}/aktivasyon?token={t}",
    )


def hash_izi(h: str | None) -> str:
    # Şifre değişince eski sıfırlama bağlantısı geçersiz olsun; hash'in kendisi bağlantıya girmez.
    return hashlib.sha256((h or "").encode()).hexdigest()[:16]


def sifirlama_maili(eposta: str, iz: str):
    t = ser.dumps([eposta, iz], salt="sifirlama")
    eposta_gonder(
        eposta,
        "DermaVision şifre sıfırlama",
        "Şifrenizi yenilemek için aşağıdaki düğmeye tıklayın. Bağlantı 30 dakika geçerlidir.",
        "Şifremi yenile",
        f"{LINK_URL}/sifirla?token={t}",
    )


# ---------------------------------------------------------------- Oturum
def oturum_cookie(resp: Response, uid: int, kalici: bool = True):
    resp.set_cookie(
        "oturum",
        ser.dumps(uid, salt="oturum"),
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600 if kalici else None,  # canlıda secure=True ekleyin
    )


def oturumdaki_kullanici(request: Request, db: Session = Depends(get_db)) -> models.Kullanici:
    # Mobil uygulama "Authorization: Bearer <token>" gönderir; web sayfası çerez kullanır.
    auth = request.headers.get("authorization", "")
    t = auth[7:] if auth.lower().startswith("bearer ") else request.cookies.get("oturum", "")
    try:
        uid = ser.loads(t, salt="oturum", max_age=7 * 24 * 3600)
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "Oturum yok.")
    u = db.get(models.Kullanici, uid)
    if not u or not u.is_active:
        raise HTTPException(401, "Oturum yok.")
    return u


# ---------------------------------------------------------------- Temel uçlar
@app.get("/saglik")
def saglik():
    return {"durum": "calisiyor"}


MAKS_BOYUT = 10 * 1024 * 1024
IMZA = {"jpg": b"\xff\xd8\xff", "png": b"\x89PNG\r\n\x1a\n"}


# ---------------------------------------------------------------- Yapay zekâ modeli (Xception + klinik veri)
# Kaggle'da eğitilen model "model" klasöründen yüklenir (Docker'da /model). Dosyalar yoksa tahmin kapalıdır,
# uygulamanın geri kalanı (kayıt, yükleme...) normal çalışır.
#   xception_klinik_model.keras  - model (girdiler: goruntu 299x299x3 [0-255], klinik vektör)
#   klinik_onisleme.json         - klinik verinin eğitimdeki ön işleme ayarları
#   uygulama_ayarlari.json       - sınıf listesi ve görüntü boyutu
MODEL_DIR = pathlib.Path(os.environ.get("DERMA_MODEL_DIZINI", str(KOK / "model")))
_ai = {"denendi": False, "model": None, "onisleme": None, "ayar": None}
_ai_kilit = threading.Lock()

SINIF_ADLARI = {
    "ACK": "Aktinik keratoz", "BCC": "Bazal hücreli karsinom", "MEL": "Melanom",
    "NEV": "Nevüs (ben)", "SCC": "Skuamöz hücreli karsinom", "SEK": "Seboreik keratoz",
}
# Uygulamadaki belirti alanı -> modelin klinik sütunu
BOLGELER = ("ABDOMEN", "ARM", "BACK", "CHEST", "EAR", "FACE", "FOOT", "FOREARM", "HAND", "LIP", "NECK", "NOSE", "SCALP", "THIGH")
BOLGE_ADI = {"ABDOMEN": "karın", "ARM": "kol", "BACK": "sırt", "CHEST": "göğüs", "EAR": "kulak", "FACE": "yüz", "FOOT": "ayak",
             "FOREARM": "ön kol", "HAND": "el", "LIP": "dudak", "NECK": "boyun", "NOSE": "burun", "SCALP": "saçlı deri", "THIGH": "uyluk"}
BELIRTI_KLINIK = {"kasinti": "itch", "buyume": "grew", "agri": "hurt",
                  "degisim": "changed", "kanama": "bleed", "kabarik": "elevation"}
BELIRTI_ADI = {"kasinti": "kaşıntı", "buyume": "büyüme", "agri": "ağrı",
               "degisim": "değişim", "kanama": "kanama", "kabarik": "kabarıklık"}


def _model_yukle():
    """Modeli ilk kullanımda bir kez yükler (sonraki çağrılarda bellekten verir)."""
    with _ai_kilit:
        if _ai["denendi"]:
            return _ai["model"]
        _ai["denendi"] = True
        yol = MODEL_DIR / "xception_klinik_model.keras"
        if not yol.exists():
            print(f"[MODEL] {yol} bulunamadı: yapay zekâ tahmini kapalı.")
            return None
        try:
            import tensorflow as tf
            _ai["model"] = tf.keras.models.load_model(yol, compile=False)
            _ai["onisleme"] = json.loads((MODEL_DIR / "klinik_onisleme.json").read_text(encoding="utf-8"))
            _ai["ayar"] = json.loads((MODEL_DIR / "uygulama_ayarlari.json").read_text(encoding="utf-8"))
            print(f"[MODEL] yüklendi: sınıflar={_ai['ayar']['siniflar']}")
        except Exception as ex:
            _ai["model"] = None
            print(f"[MODEL HATA] yüklenemedi: {type(ex).__name__}: {ex}")
        return _ai["model"]


def _sayi(v):
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _kategori_degeri(deger, kategoriler):
    """True/False/None ya da metni, eğitimdeki kategori yazımına (ör. 'True', 'UNK') çevirir."""
    if deger is None:
        adaylar = ("unknown", "unk", "nan", "none", "")
    elif deger is True:
        adaylar = ("true", "1", "yes")
    elif deger is False:
        adaylar = ("false", "0", "no")
    else:
        adaylar = (str(deger).lower(),)
    for k in kategoriler:
        if str(k).lower() in adaylar:
            return k
    return None  # eğitimde yok: tüm one-hot sütunları 0 kalır (eğitimdeki davranışla aynı)


def klinik_vektor(on: dict, ozellik: dict):
    """Klinik verinin eğitimdeki KlinikOnIsleme.transform işleminin birebir aynısı (tek satır için)."""
    import numpy as np
    parca = []
    for c in on["sayisal"]:
        v = _sayi(ozellik.get(c))
        parca.append(((on["medyan"][c] if v is None else v) - on["ort"][c]) / on["std"][c])
    for c in on["sayisal"]:
        parca.append(1.0 if _sayi(ozellik.get(c)) is None else 0.0)
    for c in on["kategorik"]:
        secilen = _kategori_degeri(ozellik.get(c), on["kategori"][c])
        parca.extend(1.0 if k == secilen else 0.0 for k in on["kategori"][c])
    return np.array([parca], dtype="float32")


def kullanici_ozellikleri(kullanici, belirtiler: dict | None, bolge: str | None = None) -> dict:
    """Uygulamada bilinen bilgiler -> modelin klinik sütunları. Bilinmeyenler None (=Unknown) kalır."""
    oz = {}
    if kullanici.dogum_tarihi:
        bugun = date.today()
        d = kullanici.dogum_tarihi
        oz["age"] = bugun.year - d.year - ((bugun.month, bugun.day) < (d.month, d.day))
    oz["gender"] = {"kadin": "female", "erkek": "male"}.get(kullanici.cinsiyet or "")
    for alan, sutun in BELIRTI_KLINIK.items():
        oz[sutun] = (belirtiler or {}).get(alan)  # True / False / None
    if bolge:
        oz["region"] = bolge.upper()
    return oz


def yapay_zeka_tahmin(veri: bytes, kullanici, belirtiler: dict | None, bolge: str | None = None) -> dict | None:
    """Fotoğraf + klinik bilgilerle sınıf olasılıklarını üretir. Model yoksa/hata olursa None döner."""
    model = _model_yukle()
    if model is None:
        return None
    try:
        import numpy as np
        import tensorflow as tf
        from PIL import Image
        ayar, on = _ai["ayar"], _ai["onisleme"]
        boyut = ayar["img_boyutu"]
        img = np.asarray(Image.open(io.BytesIO(veri)).convert("RGB"))
        # eğitimdeki okuma ile aynı: yeniden boyutlandır, yuvarla, 0-255 aralığında bırak
        a = tf.cast(tf.clip_by_value(tf.round(tf.image.resize(img, (boyut, boyut))), 0, 255), tf.float32)[None]
        oz = kullanici_ozellikleri(kullanici, belirtiler, bolge)
        k = tf.constant(klinik_vektor(on, oz))
        # TTA: orijinal + yatay ayna + dikey ayna ortalaması (eğitim notebook'undaki gibi)
        p = sum(model([g, k], training=False).numpy() for g in
                (a, tf.image.flip_left_right(a), tf.image.flip_up_down(a))) / 3
        p = p[0]
    except Exception as ex:
        print(f"[MODEL HATA] tahmin yapılamadı: {type(ex).__name__}: {ex}")
        return None
    siniflar = ayar["siniflar"]
    en = int(p.argmax())
    verilen = [BELIRTI_ADI[a] + (" var" if oz[BELIRTI_KLINIK[a]] else " yok")
               for a in BELIRTI_KLINIK if oz.get(BELIRTI_KLINIK[a]) is not None]
    if oz.get("region"):
        verilen.append("bölge: " + BOLGE_ADI.get(oz["region"], oz["region"]))
    return {
        "sinif": siniflar[en],
        "sinif_adi": SINIF_ADLARI.get(siniflar[en], siniflar[en]),
        "olasilik": round(float(p[en]), 4),
        "dagilim": {s: round(float(v), 4) for s, v in zip(siniflar, p)},
        "kullanilan_bilgiler": verilen,
    }


def tahmin_aciklamasi(t: dict) -> str:
    """analizler.xai_aciklama alanına yazılan okunabilir metin."""
    sirali = sorted(t["dagilim"].items(), key=lambda x: -x[1])
    diger = ", ".join(f"{SINIF_ADLARI.get(s, s)} %{v * 100:.0f}" for s, v in sirali[:3])
    bilgi = ", ".join(t["kullanilan_bilgiler"]) or "klinik bilgi girilmedi"
    return (f"Model tahmini: {t['sinif_adi']} (%{t['olasilik'] * 100:.0f}). "
            f"En olası sınıflar: {diger}. Kullanılan bilgiler: {bilgi}. "
            "Bu sonuç tanı değildir; bir dermatoloğa danışın.")


threading.Thread(target=_model_yukle, daemon=True).start()  # modeli açılışta arka planda yükle (ilk yükleme beklemesin)


def gorsel_kaydet(db: Session, kullanici: models.Kullanici, veri: bytes, mime: str,
                  onay: bool, bilgi: str, gorsel_kaynak: str, bolge: str | None = None) -> dict:
    """Görseli diske ve veritabanına kaydeder (iki yükleme ucu da bunu kullanır)."""
    if not onay:
        raise HTTPException(400, "Fotoğrafın işlenmesi için onay vermelisiniz.")
    if mime not in ("image/jpeg", "image/png"):
        raise HTTPException(400, "Sadece JPG veya PNG yüklenebilir")
    if len(veri) > MAKS_BOYUT:
        raise HTTPException(413, "Dosya 10 MB sınırını aşıyor")
    uzanti = "jpg" if mime == "image/jpeg" else "png"
    if not veri.startswith(IMZA[uzanti]):  # içerik gerçekten bir resim mi
        raise HTTPException(400, "Dosya geçerli bir JPG/PNG değil")
    if gorsel_kaynak not in ("kamera", "galeri"):
        gorsel_kaynak = "galeri"
    bolge = (bolge or "").strip().upper()
    if bolge not in BOLGELER:
        bolge = None

    klasor = UPLOAD_DIR / str(kullanici.kullanici_id)
    klasor.mkdir(exist_ok=True)
    dosya_adi = f"{uuid.uuid4()}.{uzanti}"
    yol = klasor / dosya_adi
    yol.write_bytes(veri)
    try:
        hakkinda = None
        if bilgi.strip():
            # metin + metinden çıkarılan belirtiler (kaşıntı var mı, aile geçmişi vb.) JSONB olarak saklanır
            hakkinda = models.LezyonHakkinda(
                kullanici_id=kullanici.kullanici_id,
                bilgi=_bilgi_olustur(bilgi.strip()[:5000]),
            )
            db.add(hakkinda)
            db.flush()
        gorsel = models.Gorsel(
            kullanici_id=kullanici.kullanici_id,
            dosya_yolu=f"{kullanici.kullanici_id}/{dosya_adi}",
            gorsel_kaynak=gorsel_kaynak,
            format=uzanti,
            boyut=len(veri),
        )
        db.add(gorsel)
        db.add(models.Onay(kullanici_id=kullanici.kullanici_id, onay_turu="fotograf_isleme"))
        db.flush()
        # Yapay zekâ tahmini (model yoksa ya da hata olursa yükleme yine de başarılı olur)
        tahmin = yapay_zeka_tahmin(veri, kullanici, hakkinda.bilgi["belirtiler"] if hakkinda else None, bolge)
        if tahmin:
            db.add(models.Analiz(gorsel_id=gorsel.gorsel_id,
                                 hakkinda_id=hakkinda.hakkinda_id if hakkinda else None,
                                 xai_aciklama=tahmin_aciklamasi(tahmin)))
        db.commit()
    except Exception:
        db.rollback()
        yol.unlink(missing_ok=True)  # veritabanına yazılamadıysa dosya da kalmasın
        raise
    return {
        "gorsel_id": gorsel.gorsel_id,
        "hakkinda_id": hakkinda.hakkinda_id if hakkinda else None,
        "belirtiler": hakkinda.bilgi["belirtiler"] if hakkinda else None,
        "tahmin": tahmin,
        "format": uzanti,
        "boyut": len(veri),
    }


@app.post("/api/gorseller", response_model=schemas.GorselOut)
def gorsel_yukle(
    dosya: UploadFile = File(...),
    onay: bool = Form(False),
    bilgi: str = Form(""),
    gorsel_kaynak: str = Form("galeri"),
    bolge: str = Form(""),
    kullanici: models.Kullanici = Depends(oturumdaki_kullanici),
    db: Session = Depends(get_db),
):
    """Dosya yükleme (multipart): web sayfası kullanır."""
    veri = dosya.file.read(MAKS_BOYUT + 1)
    return gorsel_kaydet(db, kullanici, veri, dosya.content_type, onay, bilgi, gorsel_kaynak, bolge)


@app.post("/api/gorseller/json", response_model=schemas.GorselOut)
def gorsel_yukle_json(
    g: schemas.GorselJson,
    kullanici: models.Kullanici = Depends(oturumdaki_kullanici),
    db: Session = Depends(get_db),
):
    """Fotoğraf base64 olarak JSON içinde gelir: mobil uygulama kullanır (FormData sorunlarını aşar)."""
    if len(g.dosya_base64) > MAKS_BOYUT * 4 // 3 + 1024:
        raise HTTPException(413, "Dosya 10 MB sınırını aşıyor")
    try:
        veri = base64.b64decode(g.dosya_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "Fotoğraf verisi okunamadı.")
    return gorsel_kaydet(db, kullanici, veri, g.mime, g.onay, g.bilgi, g.gorsel_kaynak, g.bolge)


@app.get("/api/hastaneler", response_model=list[schemas.HastaneOut])
def hastaneler(il: str | None = None, ilce: str | None = None,
               kullanici: models.Kullanici = Depends(oturumdaki_kullanici),
               db: Session = Depends(get_db)):
    q = select(models.Hastane).order_by(models.Hastane.ad).limit(200)
    if il:
        q = q.where(models.Hastane.il == il)
    if ilce:
        q = q.where(models.Hastane.ilce == ilce)
    return db.scalars(q).all()


# ---------------------------------------------------------------- Kimlik doğrulama
@app.post("/api/kayit", status_code=201)
def kayit_ol(k: schemas.Kayit, arka: BackgroundTasks, db: Session = Depends(get_db)):
    h = bcrypt.hashpw(k.sifre.encode(), bcrypt.gensalt()).decode()
    kul = models.Kullanici(
        ad=k.ad,
        soyad=k.soyad,
        eposta=k.eposta.lower(),
        sifre_hash=h,
        cinsiyet=k.cinsiyet,
        dogum_tarihi=date.fromisoformat(k.dogum_tarihi) if k.dogum_tarihi else None,
    )
    # KVKK: hangi onayın ne zaman verildiği kaydedilir
    for tur in ("yetiskin", "kvkk", "kullanim_kosullari"):
        kul.onaylar.append(models.Onay(onay_turu=tur))
    db.add(kul)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Bu e-posta ile zaten bir hesap var.")
    arka.add_task(aktivasyon_maili, k.eposta)
    return {"mesaj": "Kayıt alındı. Etkinleştirme bağlantısı e-postanıza gönderildi (gelmezse spam klasörüne bakın)."}


@app.post("/api/aktivasyon")
def aktive_et(token: str, db: Session = Depends(get_db)):
    try:
        e = ser.loads(token, salt="aktivasyon", max_age=24 * 3600)
    except (BadSignature, SignatureExpired):
        raise HTTPException(400, "Bağlantı geçersiz veya süresi dolmuş.")
    u = db.scalar(select(models.Kullanici).where(models.Kullanici.eposta == e))
    if u:
        u.is_active = True
        db.commit()
    return {"mesaj": "Hesabınız etkinleştirildi. Şimdi giriş yapabilirsiniz."}


@app.get("/sifirla", response_class=HTMLResponse)
def sifirla_sayfasi(token: str):
    """E-postadaki şifre sıfırlama bağlantısı (telefondaki tarayıcıda açılır): yeni şifre formu + uygulamaya dönüş."""
    html = """<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>DermaVision</title>
<style>body{font-family:system-ui,sans-serif;padding:32px 20px;max-width:420px;margin:auto;color:#222}
input{width:100%;box-sizing:border-box;padding:12px;margin:6px 0;font-size:16px;border:1px solid #bbb;border-radius:8px}
button,a.b{display:block;width:100%;box-sizing:border-box;text-align:center;margin-top:14px;padding:14px;background:#2563eb;color:#fff;
border:0;border-radius:10px;text-decoration:none;font-size:18px}#m{margin-top:14px;color:#b91c1c}#m.ok{color:#15803d}</style></head>
<body><h2>Yeni şifre belirleyin</h2>
<div id="f"><input id="s1" type="password" placeholder="Yeni şifre"><input id="s2" type="password" placeholder="Yeni şifre (tekrar)">
<small>En az 8 karakter, 1 büyük harf, 1 küçük harf, 1 rakam.</small><button id="g">Şifreyi yenile</button></div>
<p id="m"></p><div id="d" style="display:none"><a class="b" href="__APP__">Uygulamaya dön</a></div>
<script>
const T=__TOKEN__;
document.getElementById("g").onclick=async()=>{
 const a=document.getElementById("s1").value,b=document.getElementById("s2").value,m=document.getElementById("m");
 m.className="";if(a!==b){m.textContent="Şifreler eşleşmiyor.";return}
 try{const r=await fetch("/api/sifre-sifirla",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token:T,yeni_sifre:a})});
  const d=await r.json().catch(()=>({}));
  if(r.ok){m.className="ok";m.textContent=d.mesaj||"Şifreniz yenilendi.";document.getElementById("f").style.display="none";document.getElementById("d").style.display="block"}
  else{m.textContent=typeof d.detail==="string"?d.detail:((d.detail&&d.detail[0]&&d.detail[0].msg)||"Bir hata oluştu.").replace(/^Value error, /,"")}
 }catch(e){m.textContent="Sunucuya ulaşılamadı."}};
</script></body></html>"""
    return html.replace("__APP__", APP_URL).replace("__TOKEN__", json.dumps(token))


@app.get("/aktivasyon", response_class=HTMLResponse)
def aktive_et_link(token: str, db: Session = Depends(get_db)):
    """E-postadaki bağlantı (telefondaki tarayıcıda açılır): hesabı etkinleştirir, uygulamaya dönüş düğmesi gösterir."""
    try:
        mesaj = aktive_et(token, db)["mesaj"]
        baslik = "Hesabınız etkinleştirildi ✅"
    except HTTPException as ex:
        mesaj, baslik = ex.detail, "Bağlantı geçersiz"
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>DermaVision</title>
<style>body{{font-family:system-ui,sans-serif;text-align:center;padding:48px 20px;color:#222}}
a{{display:inline-block;margin-top:24px;padding:14px 28px;background:#2563eb;color:#fff;border-radius:10px;text-decoration:none;font-size:18px}}</style></head>
<body><h2>{baslik}</h2><p>{mesaj}</p><a href="{APP_URL}">Uygulamaya dön</a>
<script>setTimeout(function(){{location.href="{APP_URL}"}},800)</script></body></html>"""


@app.post("/api/giris")
def giris_yap(g: schemas.Giris, resp: Response, db: Session = Depends(get_db)):
    u = db.scalar(select(models.Kullanici).where(models.Kullanici.eposta == g.eposta.lower()))
    if u and u.sifre_hash:
        ok = bcrypt.checkpw(g.sifre.encode()[:72], u.sifre_hash.encode())
    else:  # kullanıcı yok ya da Google hesabı: zamanlama farkı olmasın
        bcrypt.checkpw(g.sifre.encode()[:72], bcrypt.hashpw(b"x", bcrypt.gensalt()))
        ok = False
    if not u or not ok:
        raise HTTPException(401, "E-posta veya şifre hatalı.")
    if not u.is_active:
        # Şifre doğru ama hesap etkin değil: bağlantıyı yeniden gönder
        return JSONResponse(
            {"detail": "Hesabınız henüz etkinleştirilmedi. Etkinleştirme bağlantısını e-postanıza yeniden gönderdik."},
            status_code=403,
            background=BackgroundTask(aktivasyon_maili, u.eposta),
        )
    oturum_cookie(resp, u.kullanici_id, kalici=g.beni_hatirla)  # web için çerez
    return {"mesaj": "Giriş başarılı", "token": ser.dumps(u.kullanici_id, salt="oturum")}  # mobil için token


@app.post("/api/cikis")
def cikis(resp: Response):
    resp.delete_cookie("oturum")
    return {"mesaj": "Çıkış yapıldı."}


@app.get("/api/ben", response_model=schemas.KullaniciOut)
def profil_getir(kullanici: models.Kullanici = Depends(oturumdaki_kullanici)):
    return kullanici


@app.delete("/api/hesabim")
def hesabi_sil(resp: Response, kullanici: models.Kullanici = Depends(oturumdaki_kullanici),
               db: Session = Depends(get_db)):
    """KVKK silme hakkı: kullanıcı, onayları, görselleri, notları ve analizleri silinir."""
    klasor = UPLOAD_DIR / str(kullanici.kullanici_id)
    db.delete(kullanici)
    db.commit()
    shutil.rmtree(klasor, ignore_errors=True)
    resp.delete_cookie("oturum")
    return {"mesaj": "Hesabınız ve verileriniz silindi."}


@app.post("/api/sifre-unuttum")
def sifre_unuttum(m: schemas.Unuttum, arka: BackgroundTasks, db: Session = Depends(get_db)):
    u = db.scalar(select(models.Kullanici).where(
        models.Kullanici.eposta == m.eposta.lower(), models.Kullanici.is_active.is_(True)))
    if u:
        arka.add_task(sifirlama_maili, u.eposta, hash_izi(u.sifre_hash))
    return {"mesaj": "Kayıtlı bir hesap varsa sıfırlama bağlantısı gönderildi."}


@app.post("/api/sifre-sifirla")
def sifre_sifirla(s: schemas.Sifirla, db: Session = Depends(get_db)):
    try:
        e, iz = ser.loads(s.token, salt="sifirlama", max_age=30 * 60)  # 30 dk
    except (BadSignature, SignatureExpired):
        raise HTTPException(400, "Bağlantı geçersiz veya süresi dolmuş.")
    u = db.scalar(select(models.Kullanici).where(models.Kullanici.eposta == e))
    if not u or hash_izi(u.sifre_hash) != iz:
        raise HTTPException(400, "Bağlantı daha önce kullanılmış.")
    u.sifre_hash = bcrypt.hashpw(s.yeni_sifre.encode(), bcrypt.gensalt()).decode()
    db.commit()
    return {"mesaj": "Şifreniz güncellendi."}


# ---------------------------------------------------------------- Google ile giriş
def google_kullanici(db: Session, b: dict) -> models.Kullanici:
    """Google hesabına karşılık gelen kullanıcıyı bulur, yoksa oluşturur.
    E-posta Google tarafından doğrulandığı için hesap doğrudan etkin olur."""
    eposta = b["email"].lower()
    u = db.scalar(select(models.Kullanici).where(models.Kullanici.eposta == eposta))
    if u:
        u.is_active = True
    else:
        tam = (b.get("name") or eposta).strip()
        ad = (b.get("given_name") or tam.split(" ")[0])[:50]
        soyad = (b.get("family_name") or " ".join(tam.split(" ")[1:]))[:50]
        u = models.Kullanici(ad=ad, soyad=soyad, eposta=eposta, sifre_hash=None, is_active=True)
        db.add(u)
    db.commit()
    return u


# --- Mobil uygulama: yerel Google girişi (tarayıcı açılmaz)
# Uygulama, telefondaki Google hesabıyla bir "id_token" alır ve buraya gönderir.
# Token'ın Google tarafından imzalandığını ve bizim client ID'mize ait olduğunu doğrularız.
@app.post("/api/auth/google/mobil")
def google_mobil(g: schemas.GoogleMobil, db: Session = Depends(get_db)):
    try:
        b = google_id_token.verify_oauth2_token(
            g.id_token, google_requests.Request(), GOOGLE_CLIENT_ID, clock_skew_in_seconds=10
        )
    except ValueError as ex:
        print(f"[Google] mobil jeton doğrulanamadı: {ex}")
        raise HTTPException(401, "Google kimlik doğrulaması başarısız oldu.")
    except google_exceptions.GoogleAuthError as ex:
        print(f"[Google] doğrulama sunucusuna ulaşılamadı: {ex}")
        raise HTTPException(503, "Google doğrulama sunucusuna ulaşılamadı. Biraz sonra tekrar deneyin.")
    if not b.get("email") or not b.get("email_verified"):
        raise HTTPException(401, "Google hesabınızın e-postası doğrulanmamış.")
    u = google_kullanici(db, b)
    return {"mesaj": "Giriş başarılı", "token": ser.dumps(u.kullanici_id, salt="oturum")}


# --- Tarayıcı üzerinden Google girişi (web sayfası ve mobil uygulama)
# Mobil: uygulama bu adresi ?donus=<uygulamanın geri dönüş adresi> ile bir tarayıcı penceresinde açar.
# Giriş bitince callback, oturum jetonunu bu adrese ?token=... olarak ekleyip uygulamaya geri yönlendirir.
DONUS_ONEKLERI = ("exp://", "exps://", "derma://", "dermavision://")  # yalnızca uygulama adreslerine dönülür


def donus_adresi(donus: str | None) -> str | None:
    return donus if donus and donus.startswith(DONUS_ONEKLERI) and len(donus) < 300 else None


def donus_yonlendir(donus: str, **param):
    """Uygulamaya dönüş sayfası. Android Chrome, kullanıcı dokunuşu olmadan yönlendirmeyle uygulama açmayı
    engelleyebildiği için hem otomatik yönlendirir hem de dokunulabilir bir düğme gösterir."""
    ayrac = "&" if "?" in donus else "?"
    adres = f"{donus}{ayrac}{urllib.parse.urlencode(param)}"
    basarili = "token" in param
    baslik = "Giriş başarılı ✅" if basarili else "Giriş tamamlanamadı"
    metin = "Uygulamaya dönmek için düğmeye dokunun." if basarili else "Uygulamaya dönüp tekrar deneyebilirsiniz."
    html = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>DermaVision</title>
<style>body{{font-family:system-ui,sans-serif;text-align:center;padding:48px 20px;color:#222}}
a{{display:inline-block;margin-top:24px;padding:16px 32px;background:#2563eb;color:#fff;border-radius:10px;text-decoration:none;font-size:20px}}</style></head>
<body><h2>{baslik}</h2><p>{metin}</p><a href="{_html.escape(adres)}">Uygulamaya dön</a>
<script>setTimeout(function(){{location.href={json.dumps(adres)}}},300)</script></body></html>"""
    return HTMLResponse(html)


@app.get("/api/auth/google")
async def google_ile_giris(donus: str | None = None):
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    resp = RedirectResponse(url=url)
    resp.set_cookie("g_state", state, httponly=True, samesite="lax", max_age=600)
    d = donus_adresi(donus)
    if d:
        resp.set_cookie("g_donus", d, httponly=True, samesite="lax", max_age=600)
    else:
        resp.delete_cookie("g_donus")
    return resp


def google_hata(neden: str, ayrinti: str = "", donus: str | None = None):
    print(f"[Google] giriş başarısız, neden={neden} {ayrinti}")
    if donus:
        return donus_yonlendir(donus, neden=neden)
    return RedirectResponse(f"/?hata=google&neden={neden}")


@app.get("/api/auth/google/callback")
async def google_callback(request: Request, code: str | None = None,
                          state: str | None = None, error: str | None = None,
                          db: Session = Depends(get_db)):
    donus = donus_adresi(request.cookies.get("g_donus"))
    if error:
        return google_hata("iptal", f"(google: {error})", donus)
    if not code or not state:
        return google_hata("durum", "(code veya state eksik)", donus)
    if state != request.cookies.get("g_state"):
        return google_hata("durum", "(state çerezi eşleşmedi; siteyi DERMA_BASE_URL adresinden açtığınızdan emin olun)", donus)
    if not GOOGLE_CLIENT_SECRET:
        return google_hata("anahtar", "(GOOGLE_CLIENT_SECRET tanımlı değil; .env dosyasına ekleyin)", donus)
    adim = "token"
    try:
        async with httpx.AsyncClient(timeout=10) as hc:
            t = await hc.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
            t.raise_for_status()
            tj = t.json()
            try:  # tercih: Google'ın imzaladığı kimlik jetonunu (id_token) doğrula
                adim = "id_token"
                b = await run_in_threadpool(
                    google_id_token.verify_oauth2_token,
                    tj["id_token"], google_requests.Request(), GOOGLE_CLIENT_ID, 10,
                )
            except Exception as ex:
                print(f"[Google] id_token doğrulanamadı ({ex}); userinfo deneniyor")
                adim = "userinfo"
                bilgi = await hc.get(
                    "https://openidconnect.googleapis.com/v1/userinfo",
                    headers={"Authorization": f"Bearer {tj['access_token']}"},
                )
                bilgi.raise_for_status()
                b = bilgi.json()
    except httpx.HTTPStatusError as ex:
        return google_hata("jeton", f"(adım={adim}, HTTP {ex.response.status_code}: {ex.response.text})", donus)
    except Exception as ex:
        return google_hata("jeton", f"(adım={adim}, {type(ex).__name__}: {ex})", donus)
    if not b.get("email") or not b.get("email_verified"):
        return google_hata("eposta", "(e-posta doğrulanmamış)", donus)

    u = google_kullanici(db, b)
    if donus:  # mobil uygulama: jeton uygulamaya geri dönüş adresiyle taşınır
        resp = donus_yonlendir(donus, token=ser.dumps(u.kullanici_id, salt="oturum"))
    else:      # web: çerezle giriş
        resp = RedirectResponse("/?giris=google")
        oturum_cookie(resp, u.kullanici_id)
    resp.delete_cookie("g_state")
    resp.delete_cookie("g_donus")
    return resp


# En sonda kalmalı, yoksa yukarıdaki adresleri gölgeler
app.mount("/", StaticFiles(directory=KOK / "static", html=True), name="static")
