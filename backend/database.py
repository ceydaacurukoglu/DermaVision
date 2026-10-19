"""Veritabanı bağlantısı (SQLite).

Veritabanı tek bir dosyadır: <VERI_DIR>/dermavision.db
Docker'da VERI_DIR=/data olduğundan dosya volume içinde durur ve konteyner silinse de kalır.
"""
import os
import pathlib

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

KOK = pathlib.Path(__file__).resolve().parent
load_dotenv(KOK.parent / ".env", override=True)  # Docker'da .env imajda yok, ortam değişkenleri geçerli

# Veritabanı dosyası ve yüklenen fotoğraflar burada durur
VERI_DIR = pathlib.Path(os.environ.get("DERMA_VERI_DIZINI", KOK.parent))
VERI_DIR.mkdir(parents=True, exist_ok=True)
DB_DOSYASI = VERI_DIR / "dermavision.db"

engine = create_engine(
    f"sqlite:///{DB_DOSYASI.as_posix()}",
    connect_args={"check_same_thread": False, "timeout": 15},  # FastAPI isteklerini birden çok iş parçacığında çalıştırır
)


@event.listens_for(engine, "connect")
def _fk_ac(dbapi_conn, _):
    # SQLite'ta yabancı anahtarlar varsayılan olarak kapalıdır; silme zincirleri için açıyoruz
    dbapi_conn.execute("PRAGMA foreign_keys=ON")


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
