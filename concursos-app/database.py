import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

url = os.getenv("DATABASE_URL", "").strip()

if url.startswith(("postgres://", "postgresql://")):
    # Produção (Render + Neon). O Render/Heroku usam "postgres://", que o SQLAlchemy 2 não aceita.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    engine = create_engine(url, pool_pre_ping=True, pool_recycle=300)  # Neon suspende conexões ociosas
else:
    # Desenvolvimento local
    url = "sqlite:///./banco.db"
    engine = create_engine(url, connect_args={"check_same_thread": False})  # só vale para SQLite

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
