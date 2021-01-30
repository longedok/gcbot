import os

from sqlalchemy import create_engine, Integer, Column, DateTime, Boolean
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

ROOT_DIR = os.path.dirname(os.path.realpath(__file__))
DB_PATH = os.path.join(ROOT_DIR, "bot.db")

engine = create_engine(f"sqlite:///{DB_PATH}")

session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)
session = Session()

Base = declarative_base()


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    message_id = Column(Integer)
    chat_id = Column(Integer)
    delete_after = Column(Integer)
    deleted = Column(Boolean, default=False)

    def __str__(self) -> str:
        return f"Message(mid={self.message_id}, delete_after={self.delete_after})"

    def __repr__(self) -> str:
        return str(self)


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
    gc_enabled = Column(Boolean, default=False)
    gc_ttl = Column(Integer, default=0)


def init_storage() -> None:
    Base.metadata.create_all(engine)

    settings = session.query(Settings).first()
    if not settings:
        settings = Settings()
        session.add(settings)
    session.commit()
