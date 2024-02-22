import os

from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.asyncio import create_async_engine

from .schemes.User import *
from .schemes.Token import *
from .schemes.Clan import *
from .schemes.CogConfig import *
from .schemes.Meeting import *
from .schemes.Voice import *
from .schemes.Roles import *
from .schemes.Tikets import *
from .schemes.Vote import *

from .Base import Base

from dotenv import load_dotenv

load_dotenv(override=True)

engine = create_async_engine(os.getenv('DATABASE_URL'),
                             isolation_level="SERIALIZABLE",
                             pool_size=20)


async def init_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
