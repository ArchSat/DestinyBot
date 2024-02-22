import datetime
import logging
import os
from typing import Optional

import bungio
import discord
from bungio.models import AuthData
from discord.ext import commands, tasks
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ORM import engine, Base
from ORM.schemes.CogConfig import CogConfig
from ORM.schemes.Token import Token, TokenType
from utils.bungio_client import CustomClient
from utils.error_handlers import on_command_error, on_application_command_error
from utils.logger import create_logger
from utils.tokens import get_encode_key, encode_key, sym_encrypt, sym_decrypt

load_dotenv(override=True)

logger = create_logger('ElderLyBot')


# TODO:
# raise NotImplementedError('Добавить Alembic в CI/CD: alembic upgrade head при обновлении кода')

class ElderLyBot(commands.Bot):
    def __init__(self, INITIAL_EXTENSIONS, **kwargs):
        super().__init__(command_prefix='*',
                         case_insensitive=True,
                         intents=discord.Intents.all(),
                         help_command=None,
                         **kwargs)
        self.INITIAL_EXTENSIONS = INITIAL_EXTENSIONS
        self.main_guild_id = os.getenv('DISCORD_GUILD_ID', None)
        self.db_engine = engine
        self.bungio_client = self.BungioClient(self.db_engine)
        self.auth_data = {}

        self.tree.on_error = on_application_command_error
        self.on_command_error = on_command_error

    async def get_valid_auth(self, bungie_id):
        if bungie_id in self.auth_data:
            return self.auth_data[bungie_id]
        async with AsyncSession(self.db_engine) as session:
            token = await session.scalars(select(Token).where(Token.bungie_id == bungie_id))
            try:
                token = list(token)[0]
            except IndexError:
                return None
        encode_key_value = await get_encode_key(token.bungie_id)
        key = encode_key(key_value=encode_key_value)
        refresh_token = sym_decrypt(token.token, key)
        # Работает
        ad = AuthData(refresh_token=refresh_token,
                      refresh_token_expiry=bungio.utils.get_now_with_tz(),
                      membership_type=254,
                      membership_id=token.bungie_id,
                      token='',
                      token_expiry=bungio.utils.get_now_with_tz() - datetime.timedelta(minutes=10),
                      bungie_name=None
                      )

        await ad.refresh()
        self.auth_data[ad.membership_id] = ad
        return ad

    class BungioClient(CustomClient):
        def __init__(self, db_engine, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.db_engine = db_engine

        async def on_token_update(self, before: Optional[AuthData], after: AuthData) -> None:
            await super().on_token_update(before=before, after=after)
            encode_key_value = await get_encode_key(after.membership_id)
            key = encode_key(key_value=encode_key_value)
            refresh_token = sym_encrypt(after.refresh_token, key)
            token = Token(bungie_id=int(after.membership_id),
                          token=refresh_token,
                          token_expire=after.refresh_token_expiry.replace(tzinfo=None),
                          token_type=TokenType.EXTENDED)
            async with AsyncSession(self.db_engine) as session:
                try:
                    await session.merge(token)
                    await session.commit()
                except Exception as e:
                    await session.rollback()
                    logger.exception(e)

    async def init_config(self):
        self.config = {
            'trusted_roles': [1128208142271000619, 1128208142271000618],
            'can_notify_meetings': [],
            'meetings_logs_channel': 965990163165638666,
            'meetings_notify_logs_channel': 977637466800554054,
        }

    async def save_config(self):
        if not hasattr(self, 'config'):
            await self.init_config()
        config = CogConfig(cog_name='MAIN', cog_config=self.config)
        async with AsyncSession(self.db_engine) as session:
            await session.merge(config)
            await session.commit()

    async def load_config(self):
        # Инициализация конфига БОТА (доступен из любого cog файла)
        try:
            async with AsyncSession(self.db_engine) as session:
                config = await session.scalars(select(CogConfig).where(CogConfig.cog_name == 'MAIN'))
            self.config = list(config)[0].cog_config
        except IndexError:
            await self.save_config()
        except Exception as e:
            logger.exception(e)
            raise e

    async def on_ready(self):
        logger.info('Ready!')
        logger.info(f'Logged in as ----> {self.user}')
        logger.info(f'ID: {self.user.id}')
        self.clear_old_auth.start()
        logger.info('Tasks started!')

    async def setup_hook(self) -> None:
        async with self.db_engine.begin() as conn:
            # await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        for ext in self.INITIAL_EXTENSIONS:
            await self.load_extension(ext)

        await self.load_config()

        # if self.main_guild_id:
        #     guild = discord.Object(self.main_guild_id)
        #     self.tree.copy_global_to(guild=guild)
        #     await self.tree.sync(guild=guild)

    @tasks.loop(minutes=10)
    async def clear_old_auth(self):
        new_auth_data = {}
        for bungie_id in self.auth_data:
            t: AuthData = self.auth_data[bungie_id]
            if t.token_expiry > bungio.utils.get_now_with_tz():
                new_auth_data[bungie_id] = t
        self.auth_data = new_auth_data
