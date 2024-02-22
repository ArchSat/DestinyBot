import os

import discord
from discord import app_commands, Interaction
from discord.ext import commands
from dotenv import load_dotenv
from utils.Tickets.CreateTicketModal import CreateTicketModal
from utils.logger import create_logger

logger = create_logger('test')

load_dotenv(override=True)
main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))


class TestCog(commands.Cog):
    """Тестовый модуль"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(guild=discord.Object(id=main_guild_id))
    async def test(self, ctx):
        pass


async def setup(bot):
    await bot.add_cog(TestCog(bot))
