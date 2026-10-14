import os

from sqlmodel import Session, create_engine

engine = create_engine(os.environ["DATABASE_URL"])


def get_session() -> Session:
    return Session(engine)
