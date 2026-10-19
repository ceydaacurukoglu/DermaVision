import base64
import binascii
import hashlib
import os
import pathlib
import secrets
import shutil
import smtplib
import ssl
import urllib.parse
import uuid
from email.message import EmailMessage
from html import escape

import bcrypt
import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

# database.py import edilirken .env okunur; ortam değişkenlerini bundan SONRA okuyoruz
from database import VERI_DIR, get_db, tablolari_olustur
import models
import schemas
from datetime import date

# Kurulum (Docker'sız yerel çalışma):
#   pip install -r requirements.txt
#   uvicorn main:app --host 0.0.0.0 --port 8000
# Veritabanı SQLite dosyasıdır (dermavision.db), tablolar ilk açılışta oluşur.
# SQLite tek dosya olduğu için uvicorn'u tek işçiyle (varsayılan) çalıştırın; --workers kullanmayın.
#
# Gizli ayarlar .env dosyasından okunur (GitHub'a yüklenmemeli):
#   DERMA_SECRET_KEY, DERMA_BASE_URL, GOOGLE_CLIENT_SECRET, SMTP_USER, SMTP_PASSWORD

app = FastAPI(title="Dermavision API")

KOK = pathlib.Path(__file__).resolve().parent
UPLOAD_DIR = VERI_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = os.environ.get("DERMA_BASE_URL", "http://localhost:8000").rstrip("/")
# E-postalardaki bağlantılar için adres. Tanımlı değilse BASE_URL kullanılır.
# Yerelde localhost açılmıyorsa .env'e DERMA_LINK_URL=http://127.0.0.1:8000 yazın.
# (Google girişi BASE_URL'de kalır; ikisi birbirinden bağımsızdır.)
LINK_URL = os.environ.get("DERMA_LINK_URL", BASE_URL).rstrip("/")
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
        f"{LINK_URL}/?aktivasyon={t}",
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
        f"{LINK_URL}/?sifirla={t}",
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


def gorsel_kaydet(db: Session, kullanici: models.Kullanici, veri: bytes, mime: str,
                  onay: bool, bilgi: str, gorsel_kaynak: str) -> dict:
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

    klasor = UPLOAD_DIR / str(kullanici.kullanici_id)
    klasor.mkdir(exist_ok=True)
    dosya_adi = f"{uuid.uuid4()}.{uzanti}"
    yol = klasor / dosya_adi
    yol.write_bytes(veri)
    try:
        hakkinda = None
        if bilgi.strip():
            hakkinda = models.LezyonHakkinda(kullanici_id=kullanici.kullanici_id, bilgi=bilgi.strip()[:5000])
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
        db.commit()
    except Exception:
        db.rollback()
        yol.unlink(missing_ok=True)  # veritabanına yazılamadıysa dosya da kalmasın
        raise
    return {
        "gorsel_id": gorsel.gorsel_id,
        "hakkinda_id": hakkinda.hakkinda_id if hakkinda else None,
        "format": uzanti,
        "boyut": len(veri),
    }


@app.post("/api/gorseller", response_model=schemas.GorselOut)
def gorsel_yukle(
    dosya: UploadFile = File(...),
    onay: bool = Form(False),
    bilgi: str = Form(""),
    gorsel_kaynak: str = Form("galeri"),
    kullanici: models.Kullanici = Depends(oturumdaki_kullanici),
    db: Session = Depends(get_db),
):
    """Dosya yükleme (multipart): web sayfası kullanır."""
    veri = dosya.file.read(MAKS_BOYUT + 1)
    return gorsel_kaydet(db, kullanici, veri, dosya.content_type, onay, bilgi, gorsel_kaynak)


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
    return gorsel_kaydet(db, kullanici, veri, g.mime, g.onay, g.bilgi, g.gorsel_kaynak)


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


# --- Web sayfası: tarayıcı üzerinden Google girişi (static/index.html kullanır)
@app.get("/api/auth/google")
async def google_ile_giris():
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
    return resp


def google_hata(neden: str, ayrinti: str = ""):
    print(f"[Google] giriş başarısız, neden={neden} {ayrinti}")
    return RedirectResponse(f"/?hata=google&neden={neden}")


@app.get("/api/auth/google/callback")
async def google_callback(request: Request, code: str | None = None,
                          state: str | None = None, error: str | None = None,
                          db: Session = Depends(get_db)):
    if error:
        return google_hata("iptal", f"(google: {error})")
    if not code or not state:
        return google_hata("durum", "(code veya state eksik)")
    if state != request.cookies.get("g_state"):
        return google_hata("durum", "(state çerezi eşleşmedi; siteyi DERMA_BASE_URL adresinden açtığınızdan emin olun)")
    if not GOOGLE_CLIENT_SECRET:
        return google_hata("anahtar", "(GOOGLE_CLIENT_SECRET tanımlı değil; .env dosyasına ekleyin)")
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
            bilgi = await hc.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {t.json()['access_token']}"},
            )
            bilgi.raise_for_status()
            b = bilgi.json()
    except httpx.HTTPStatusError as ex:
        return google_hata("jeton", f"(HTTP {ex.response.status_code}: {ex.response.text})")
    except Exception as ex:
        return google_hata("jeton", f"({ex})")
    if not b.get("email") or not b.get("email_verified"):
        return google_hata("eposta", "(e-posta doğrulanmamış)")

    u = google_kullanici(db, b)
    resp = RedirectResponse("/?giris=google")
    oturum_cookie(resp, u.kullanici_id)
    resp.delete_cookie("g_state")
    return resp


# En sonda kalmalı, yoksa yukarıdaki adresleri gölgeler
app.mount("/", StaticFiles(directory=KOK / "static", html=True), name="static")
