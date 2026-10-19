"""API'nin aldığı ve döndüğü veri biçimleri (Pydantic)."""
import re
from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator


def sifre_kontrol(s: str) -> str:
    if len(s) < 8:
        raise ValueError("Şifre en az 8 karakter olmalı.")
    if not re.search(r"[A-Z]", s) or not re.search(r"[a-z]", s) or not re.search(r"\d", s):
        raise ValueError("Şifre en az 1 büyük harf, 1 küçük harf ve 1 rakam içermeli.")
    if len(s.encode()) > 72:  # bcrypt sınırı
        raise ValueError("Şifre çok uzun.")
    return s


# ---------------------------------------------------------------- İstekler
class Kayit(BaseModel):
    ad: str
    soyad: str
    eposta: EmailStr
    sifre: str
    sifre_tekrar: str
    dogum_tarihi: str | None = None
    cinsiyet: str | None = None
    yetiskin_onay: bool
    kvkk_onay: bool
    kosul_onay: bool

    @field_validator("ad", "soyad")
    @classmethod
    def _isim(cls, v):
        v = " ".join(v.split())
        if len(v) > 50 or not re.fullmatch(r"[^\W\d_]+(?:[ '\-][^\W\d_]+)*", v):
            raise ValueError("Ad ve soyad yalnızca harf içermeli.")
        return v

    @field_validator("dogum_tarihi")
    @classmethod
    def _dogum(cls, v):
        if not v:
            return None
        try:
            d = date.fromisoformat(v)
        except ValueError:
            raise ValueError("Geçerli bir doğum tarihi girin.")
        bugun = date.today()
        if d > bugun or d.year < 1900:
            raise ValueError("Geçerli bir doğum tarihi girin.")
        yas = bugun.year - d.year - ((bugun.month, bugun.day) < (d.month, d.day))
        if yas < 18:
            raise ValueError("Bu uygulamayı yalnızca 18 yaşından büyükler kullanabilir.")
        return d.isoformat()

    @field_validator("cinsiyet")
    @classmethod
    def _cinsiyet(cls, v):
        return v if v in ("kadin", "erkek", "diger") else None

    @field_validator("sifre")
    @classmethod
    def _sifre(cls, v):
        return sifre_kontrol(v)

    @model_validator(mode="after")
    def _genel(self):
        if self.sifre != self.sifre_tekrar:
            raise ValueError("Şifreler eşleşmiyor.")
        if not (self.yetiskin_onay and self.kvkk_onay and self.kosul_onay):
            raise ValueError("Zorunlu onay kutularını işaretleyin.")
        return self


class Giris(BaseModel):
    eposta: EmailStr
    sifre: str
    beni_hatirla: bool = False


class Unuttum(BaseModel):
    eposta: EmailStr


class Sifirla(BaseModel):
    token: str
    yeni_sifre: str

    @field_validator("yeni_sifre")
    @classmethod
    def _s(cls, v):
        return sifre_kontrol(v)


class GorselJson(BaseModel):
    dosya_base64: str
    mime: str
    onay: bool = False
    bilgi: str = ""
    gorsel_kaynak: str = "galeri"


class GoogleMobil(BaseModel):
    id_token: str


# ---------------------------------------------------------------- Yanıtlar
class KullaniciOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    kullanici_id: int
    ad: str
    soyad: str
    eposta: str


class GorselOut(BaseModel):
    gorsel_id: int
    hakkinda_id: int | None = None
    format: str
    boyut: int


class HastaneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    hastane_id: int
    ad: str
    tur: str | None = None
    il: str | None = None
    ilce: str | None = None
    enlem: float | None = None
    boylam: float | None = None
    mhrs_url: str | None = None
