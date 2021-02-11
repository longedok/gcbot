from __future__ import annotations

import os

from sqlalchemy import create_engine, Integer, BigInteger, Column, DateTime, Boolean
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

pg_user = os.environ["POSTGRES_USERNAME"]
pg_pass = os.environ["POSTGRES_PASSWORD"]
pg_db = os.environ["POSTGRES_DB"]
pg_host = os.environ.get("POSTGRES_HOST", "postgres")
engine = create_engine(f"postgresql://{pg_user}:{pg_pass}@{pg_host}/{pg_db}")

session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)
session = Session()

Base = declarative_base()


class MessageRecord(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    date = Column(Integer, nullable=False)
    delete_after = Column(Integer)
    deleted = Column(Boolean, default=False)
    delete_cancelled = Column(Boolean, default=False)
    delete_failed = Column(Boolean, default=False)
    delete_attempt = Column(Integer, default=0, nullable=False)
    should_delete = Column(Boolean, default=False)

    def __str__(self) -> str:
        return f"MessageRecord(mid={self.message_id}, delete_after={self.delete_after})"

    def __repr__(self) -> str:
        return str(self)


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, nullable=False)
    gc_enabled = Column(Boolean, default=False)
    gc_ttl = Column(Integer, default=0)


def init_storage() -> None:
    Base.metadata.create_all(engine)

