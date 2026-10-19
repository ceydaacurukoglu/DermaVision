"""Tablolar (ER diyagramına göre)."""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Kullanici(Base):
    __tablename__ = "kullanicilar"

    kullanici_id: Mapped[int] = mapped_column(primary_key=True)
    ad: Mapped[str] = mapped_column(String(50))
    soyad: Mapped[str] = mapped_column(String(50), default="")
    eposta: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    sifre_hash: Mapped[str | None] = mapped_column(String(100))  # Google ile kayıt olanlarda boş
    dogum_tarihi: Mapped[date | None] = mapped_column(Date)
    cinsiyet: Mapped[str | None] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(default=False)  # e-posta onaylandı mı
    kayit_tarihi: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Kullanıcı silinince bağlı kayıtlar da silinir (KVKK: silme hakkı)
    onaylar: Mapped[list["Onay"]] = relationship(back_populates="kullanici", cascade="all")
    gorseller: Mapped[list["Gorsel"]] = relationship(back_populates="kullanici", cascade="all")
    hakkindalar: Mapped[list["LezyonHakkinda"]] = relationship(back_populates="kullanici", cascade="all")


class Onay(Base):
    __tablename__ = "onaylar"

    onay_id: Mapped[int] = mapped_column(primary_key=True)
    kullanici_id: Mapped[int] = mapped_column(ForeignKey("kullanicilar.kullanici_id", ondelete="CASCADE"), index=True)
    onay_turu: Mapped[str] = mapped_column(String(40))  # yetiskin, kvkk, kullanim_kosullari, fotograf_isleme
    onay_tarihi: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    kullanici: Mapped[Kullanici] = relationship(back_populates="onaylar")


class Gorsel(Base):
    __tablename__ = "gorseller"

    gorsel_id: Mapped[int] = mapped_column(primary_key=True)
    kullanici_id: Mapped[int] = mapped_column(ForeignKey("kullanicilar.kullanici_id", ondelete="CASCADE"), index=True)
    dosya_yolu: Mapped[str] = mapped_column(String(300))  # uploads klasörüne göre: "<kullanici_id>/<uuid>.jpg"
    gorsel_kaynak: Mapped[str] = mapped_column(String(20), default="galeri")  # kamera / galeri
    format: Mapped[str] = mapped_column(String(10))
    boyut: Mapped[int] = mapped_column(Integer)

    kullanici: Mapped[Kullanici] = relationship(back_populates="gorseller")
    analizler: Mapped[list["Analiz"]] = relationship(back_populates="gorsel", cascade="all")


class LezyonHakkinda(Base):
    __tablename__ = "lezyon_hakkinda"

    hakkinda_id: Mapped[int] = mapped_column(primary_key=True)
    kullanici_id: Mapped[int] = mapped_column(ForeignKey("kullanicilar.kullanici_id", ondelete="CASCADE"), index=True)
    bilgi: Mapped[str] = mapped_column(Text)

    kullanici: Mapped[Kullanici] = relationship(back_populates="hakkindalar")
    analizler: Mapped[list["Analiz"]] = relationship(back_populates="hakkinda", cascade="all")


class VeriSeti(Base):
    """Referans veri seti (PAD-UFES-20 benzeri). CSV'den bir kez yüklenir."""
    __tablename__ = "verisetleri"

    veriseti_id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[str | None] = mapped_column(String(50))
    lesion_id: Mapped[str | None] = mapped_column(String(50))
    img_id: Mapped[str | None] = mapped_column(String(100))
    diagnostic: Mapped[str | None] = mapped_column(String(20))
    region: Mapped[str | None] = mapped_column(String(50))
    age: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(String(20))
    fitspatrick: Mapped[int | None] = mapped_column(Integer)
    diameter_1: Mapped[float | None] = mapped_column(Float)
    diameter_2: Mapped[float | None] = mapped_column(Float)
    itch: Mapped[str | None] = mapped_column(String(10))
    grew: Mapped[str | None] = mapped_column(String(10))
    hurt: Mapped[str | None] = mapped_column(String(10))
    changed: Mapped[str | None] = mapped_column(String(10))
    bleed: Mapped[str | None] = mapped_column(String(10))
    elevation: Mapped[str | None] = mapped_column(String(10))
    biopsed: Mapped[str | None] = mapped_column(String(10))


class Analiz(Base):
    __tablename__ = "analizler"

    analiz_id: Mapped[int] = mapped_column(primary_key=True)
    gorsel_id: Mapped[int] = mapped_column(ForeignKey("gorseller.gorsel_id", ondelete="CASCADE"), index=True)
    hakkinda_id: Mapped[int | None] = mapped_column(ForeignKey("lezyon_hakkinda.hakkinda_id", ondelete="CASCADE"))
    veriseti_id: Mapped[int | None] = mapped_column(ForeignKey("verisetleri.veriseti_id", ondelete="SET NULL"))
    xai_aciklama: Mapped[str | None] = mapped_column(Text)
    olusturma_tarihi: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    gorsel: Mapped[Gorsel] = relationship(back_populates="analizler")
    hakkinda: Mapped[LezyonHakkinda | None] = relationship(back_populates="analizler")


class Hastane(Base):
    __tablename__ = "hastaneler"

    hastane_id: Mapped[int] = mapped_column(primary_key=True)
    ad: Mapped[str] = mapped_column(String(200))
    tur: Mapped[str | None] = mapped_column(String(50))
    il: Mapped[str | None] = mapped_column(String(50), index=True)
    ilce: Mapped[str | None] = mapped_column(String(50))
    enlem: Mapped[float | None] = mapped_column(Float)
    boylam: Mapped[float | None] = mapped_column(Float)
    mhrs_url: Mapped[str | None] = mapped_column(String(300))
