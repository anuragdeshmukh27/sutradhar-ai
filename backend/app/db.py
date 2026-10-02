import os
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import BACKEND_DIR

DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'sutradhar.db'}")
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()


class LedgerRow(Base):
    __tablename__ = "ledger"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow)
    run_id = Column(String, index=True)
    node_id = Column(String)
    agent = Column(String)
    tool = Column(String)
    args = Column(JSON)
    result = Column(JSON)
    reversible = Column(Boolean)
    undo_payload = Column(JSON)
    status = Column(String)  # done | undone | failed


class Email(Base):
    __tablename__ = "outbox"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow)
    run_id = Column(String, index=True)
    to = Column(String)
    subject = Column(String)
    body = Column(Text)
    status = Column(String, default="sent")  # sent | recalled


class CalendarEvent(Base):
    __tablename__ = "calendar"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, index=True)
    title = Column(String)
    date = Column(String)
    details = Column(Text)
    status = Column(String, default="scheduled")  # scheduled | deleted


def init_db():
    Base.metadata.create_all(engine)


@contextmanager
def session():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def row_dict(row) -> dict:
    d = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    if d.get("ts"):
        d["ts"] = d["ts"].isoformat()
    return d
