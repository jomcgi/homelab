import os
from functools import lru_cache

from sqlmodel import Session, create_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://app:app@localhost:5432/monolith"
)


@lru_cache(maxsize=1)
def get_engine():
    return create_engine(DATABASE_URL)


def get_session():
    with Session(get_engine()) as session:
        yield session
