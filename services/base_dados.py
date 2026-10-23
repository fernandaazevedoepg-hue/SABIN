import os

from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL não encontrada no ficheiro .env")


# Ligação única partilhada por toda a aplicação. Antes, cada módulo criava a
# sua e ficavam várias ligações paradas no Supabase, que o Power BI também usa.
# Cada processo fica com no máximo 5 ligações e só 2 se mantêm abertas.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=2,
    max_overflow=3,
    pool_recycle=300,
)