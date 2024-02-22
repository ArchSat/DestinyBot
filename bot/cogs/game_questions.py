import json
import os
from typing import List

import discord.ui
from discord import app_commands, SelectOption, Interaction
from discord.ext import commands
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.CogConfig import CogConfig
from utils.CustomCog import CustomCog
from utils.logger import create_logger

logger = create_logger(__name__)

load_dotenv(override=True)
main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))


class GameQuestionsCog(CustomCog):
    """Модуль для управления конфигурациями"""

    def __init__(self, bot):
        super().__init__(bot)

    async def init_config(self):
        self.config = {
            'questions_forum_channel_id': 1139265961116045392,
            'close_tag_id': 1141051603521126611,
        }

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        if thread.parent_id != self.config['questions_forum_channel_id']:
            return
        print(thread.applied_tags)
        await thread.add_tags(thread.parent.get_tag(self.config['close_tag_id']))
        await thread.edit(locked=True)

    @app_commands.command(name='forum_tag_list')
    @app_commands.default_permissions(administrator=True)
    @app_commands.guilds(main_guild_id)
    async def get_forum_tags_ids_command(self, interaction: Interaction):
        text = ''
        if (isinstance(interaction.channel, discord.Thread) and
                isinstance(interaction.channel.parent, discord.ForumChannel)):
            for tag in interaction.channel.parent.available_tags:
                text += f'{tag.name} - {tag.id}\n'
            await interaction.response.send_message(text, ephemeral=True)
        else:
            await interaction.response.send_message('Данный канал не является форумом!', ephemeral=True)


async def setup(bot):
    await bot.add_cog(GameQuestionsCog(bot))
    logger.info(f'Расширение {GameQuestionsCog} загружено!')
