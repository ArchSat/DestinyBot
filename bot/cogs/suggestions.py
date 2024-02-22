import asyncio
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.Vote import Voting
from utils.CustomCog import CustomCog
from utils.Suggestions.ui import create_embed, SuggestionView
from utils.logger import create_logger

logger = create_logger(__name__)

load_dotenv(override=True)
main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))


class Suggestions(CustomCog):
    """Голосования в предложениях."""

    def __init__(self, bot):
        super().__init__(bot)

    async def init_config(self):
        self.config = {
            'suggestions_channel': 1128208145542565983
        }

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(SuggestionView(bot=self.bot))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.channel.id != self.config['suggestions_channel']:
            return
        if message.author.bot:
            return
        if not message.content and not message.attachments:
            return
        description = message.content
        for attachment in message.attachments:
            description += f'\n{attachment.url}'
        embed = create_embed(message.author, description)
        view = SuggestionView(bot=self.bot)
        new_suggestion = await message.channel.send(embed=embed, view=view)
        await message.delete()
        async with AsyncSession(self.bot.db_engine) as session:
            new_voting = Voting(message_id=new_suggestion.id,
                                author_id=message.author.id,
                                description=description)
            await session.merge(new_voting)
            await session.commit()
        await new_suggestion.create_thread(name='Обсуждение предложения')


async def setup(bot):
    await bot.add_cog(Suggestions(bot))
    logger.info(f'Расширение {Suggestions} загружено!')
