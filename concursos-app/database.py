import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Local: lê o arquivo .env (se existir). Em produção (Render) não há .env e as variáveis vêm do painel.
# load_dotenv NÃO sobrescreve variáveis já definidas no ambiente, então o Render sempre tem prioridade.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

url = os.getenv("DATABASE_URL", "").strip()

if url.startswith(("postgres://", "postgresql://")):
    # Produção (Render + Neon). "postgres://" não é aceito pelo SQLAlchemy 2, então normalizamos.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    engine = create_engine(url, pool_pre_ping=True, pool_recycle=300)  # Neon suspende conexões ociosas
elif os.getenv("RENDER"):
    # No Render o disco é efêmero: cair no SQLite aqui apagaria os dados a cada deploy (o bug original).
    raise RuntimeError("DATABASE_URL não está definida (Render > Environment). Cole a connection string do Neon.")
else:
    # Desenvolvimento local sem .env: SQLite
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
