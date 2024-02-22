import logging

from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.CogConfig import CogConfig
from utils.logger import create_logger

logger = create_logger(__name__)


class CustomCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.config = {}

    async def on_config_update(self):
        await self.load_config()

    async def save_config(self):
        logger.info(f'Сохранение конфигурации {self.__cog_name__}')
        config = CogConfig(cog_name=self.__cog_name__, cog_config=self.config)
        async with AsyncSession(self.bot.db_engine) as session:
            await session.merge(config)
            await session.commit()

    async def load_config(self):
        try:
            async with AsyncSession(self.bot.db_engine) as session:
                config = await session.scalars(select(CogConfig).where(CogConfig.cog_name == self.__cog_name__))
            self.config = list(config)[0].cog_config
        except IndexError:
            await self.cog_config_save()
        except Exception as e:
            logger.exception(e)
            raise e

    async def cog_config_save(self):
        await self.init_config()
        config = CogConfig(cog_name=self.__cog_name__, cog_config=self.config)
        async with AsyncSession(self.bot.db_engine) as session:
            await session.merge(config)
            await session.commit()

    async def cog_load(self) -> None:
        await self.load_config()

    async def init_config(self):
        if not hasattr(self, 'config'):
            self.config = {}
