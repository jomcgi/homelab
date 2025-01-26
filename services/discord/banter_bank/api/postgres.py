from sqlalchemy.ext.asyncio import create_async_engine

CONNECTION_STRING = "postgresql+asyncpg://postgres@banter-bank-postgres:5432/postgres"

async_engine = create_async_engine(CONNECTION_STRING)
