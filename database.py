import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, func
from sqlalchemy.orm import declarative_base, sessionmaker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Base = declarative_base()

class Sentiment(Base):
    __tablename__ = "sentiments"

    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False, index=True)
    sentiment_score = Column(Float, nullable=False)
    delta_24h = Column(Float, nullable=False, default=0.0)
    catalyst = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

class Config(Base):
    __tablename__ = "config"

    key = Column(String(50), primary_key=True)
    value = Column(Text, nullable=False)

def get_db_url() -> str:
    user = os.getenv("POSTGRES_USER", "sentinel")
    password = os.getenv("POSTGRES_PASSWORD", "changeme")
    host = os.getenv("POSTGRES_HOST", "db")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "sentinel")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"

engine = create_engine(get_db_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_config(key: str, default: Optional[str] = None) -> Optional[str]:
    with SessionLocal() as session:
        row = session.query(Config).filter_by(key=key).first()
        return row.value if row else default

def set_config(key: str, value: str):
    with SessionLocal() as session:
        row = session.query(Config).filter_by(key=key).first()
        if row:
            row.value = value
        else:
            row = Config(key=key, value=value)
        session.add(row)
        session.commit()

def calculate_delta_24h(ticker: str, current_score: float) -> float:
    with SessionLocal() as session:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        avg = session.query(func.avg(Sentiment.sentiment_score)).filter(
            Sentiment.ticker == ticker,
            Sentiment.timestamp >= cutoff
        ).scalar()
        if avg is None:
            return 0.0
        return round(current_score - float(avg), 4)

def record_sentiment(ticker: str, score: float, catalyst: str, confidence: float):
    """Tool function invoked by the LLM (via Ollama tool calling)."""
    ticker = ticker.upper().strip()
    try:
        score_val = float(score)
    except (TypeError, ValueError):
        score_val = 0.0

    delta = calculate_delta_24h(ticker, score_val)
    with SessionLocal() as session:
        record = Sentiment(
            ticker=ticker,
            sentiment_score=score_val,
            delta_24h=delta,
            catalyst=str(catalyst)
        )
        session.add(record)
        session.commit()
        logger.info(f"Recorded sentiment for {ticker}: score={score_val}, delta={delta}, catalyst={catalyst}, confidence={confidence}")
        return record.id

def get_latest_sentiments(search: str = ""):
    with SessionLocal() as session:
        subq = session.query(
            Sentiment.ticker,
            func.max(Sentiment.timestamp).label("max_ts")
        ).group_by(Sentiment.ticker).subquery()

        query = session.query(Sentiment).join(
            subq,
            (Sentiment.ticker == subq.c.ticker) & (Sentiment.timestamp == subq.c.max_ts)
        )

        if search:
            query = query.filter(Sentiment.ticker.ilike(f"%{search}%"))

        return query.all()

def get_sentiment_history(ticker: str, days: int = 7):
    with SessionLocal() as session:
        cutoff = datetime.utcnow() - timedelta(days=days)
        return session.query(Sentiment).filter(
            Sentiment.ticker == ticker.upper(),
            Sentiment.timestamp >= cutoff
        ).order_by(Sentiment.timestamp).all()
