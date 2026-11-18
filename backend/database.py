"""Veritabanı bağlantısı (PostgreSQL).

Bağlantı adresi DATABASE_URL ortam değişkeninden okunur:
    postgresql+psycopg://kullanici:sifre@sunucu:5432/veritabani

Docker Compose bunu otomatik tanımlar (sunucu adı: db).
Docker'sız çalışacaksanız .env dosyasına kendi adresinizi yazın.

Yüklenen fotoğraflar veritabanında değil, dosya olarak VERI_DIR/uploads altında tutulur
(Docker'da VERI_DIR=/data, kalıcı bir volume'dur). Veritabanında yalnızca dosya yolu durur.
"""
import os
import pathlib

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

KOK = pathlib.Path(__file__).resolve().parent
load_dotenv(KOK.parent / ".env", override=True)  # Docker'da .env imajda yok, ortam değişkenleri geçerli

# Fotoğrafların kaydedileceği klasör
VERI_DIR = pathlib.Path(os.environ.get("DERMA_VERI_DIZINI", KOK.parent))
VERI_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL tanımlı değil. Docker Compose ile çalıştırın (docker compose up -d --build) "
        "ya da .env dosyasına şunu ekleyin: "
        "DATABASE_URL=postgresql+psycopg://derma:SIFRE@127.0.0.1:5432/dermavision"
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # kopmuş bağlantıyı kullanmadan önce yeniler
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """Her istek için bir oturum açar, iş bitince kapatır."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def tablolari_olustur():
    """Tablolar yoksa oluşturur (models.py import edilmiş olmalı)."""
    Base.metadata.create_all(bind=engine)
