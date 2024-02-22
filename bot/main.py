import asyncio
import logging
import os

from discord.ext import commands
from dotenv import load_dotenv

from ElderLyBot import ElderLyBot
from utils.error_handlers import *
from utils.logger import create_logger

load_dotenv(override=True)
main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))


async def run_bot():
    bot = ElderLyBot(INITIAL_EXTENSIONS)

    @bot.command()
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def sync(ctx):
        synced = await bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} commands!")
        synced = await bot.tree.sync(guild=bot.get_guild(main_guild_id))
        await ctx.send(f"Synced {len(synced)} commands!")
        bot.tree.copy_global_to(guild=bot.get_guild(main_guild_id))
        synced = await bot.tree.sync(guild=bot.get_guild(main_guild_id))
        await ctx.send(f"Synced {len(synced)} commands!")

    await bot.start(os.getenv('BOT_TOKEN', ''))


if __name__ == '__main__':
    import sentry_sdk

    sentry_sdk.init(
        dsn=os.environ['SENTRYIO_SDN'],
        traces_sample_rate=1.0
    )

    logger = create_logger('discord', log_level=logging.INFO)
    create_logger('sqlalchemy.engine', need_stdout=False).setLevel(logging.INFO)
    create_logger('utils')
    create_logger('CustomCogs')

    INITIAL_EXTENSIONS = [
        'cogs.config',
        'cogs.auth',
        'cogs.balance',
        'cogs.clans',
        'cogs.meetings',
        'cogs.moderation',
        'cogs.voices',
        'cogs.clan_administration',
        'cogs.resets',
        'cogs.roles',
        'cogs.tickets',
        'cogs.suggestions',
        'cogs.audit',
        'cogs.test',
    ]

    asyncio.run(run_bot())
