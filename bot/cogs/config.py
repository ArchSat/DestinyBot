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

logger = create_logger('test')

load_dotenv(override=True)
main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))


class EditConfigModal(discord.ui.Modal):
    def __init__(self, config, save_config, on_config_update):
        super().__init__(title='Изменение конфигурации', timeout=None)
        self.config: CogConfig = config
        self.save_config = save_config
        self.on_config_update = on_config_update
        self.config_value = discord.ui.TextInput(label=f'Конфигурация {self.config.cog_name}',
                                                 style=discord.TextStyle.long,
                                                 default=f'{json.dumps(self.config.cog_config)}',
                                                 required=True)
        self.add_item(self.config_value)

    async def on_submit(self, interaction: Interaction, /) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        new_value = json.loads(self.config_value.value)
        new_config = CogConfig(cog_name=self.config.cog_name,
                               cog_config=new_value)
        await self.save_config(new_config)
        await self.on_config_update()
        await interaction.followup.send('Конфигурация обновлена!')


class ConfigSelectView(discord.ui.View):
    def __init__(self, options, save_config, on_config_update):
        super().__init__(timeout=None)
        self.options = {
            opt.cog_name: opt for opt in options
        }
        self.save_config = save_config
        self.on_config_update = on_config_update
        self.selected = None

        self.select_cog = discord.ui.Select(min_values=1, max_values=1, options=self.get_options())
        self.select_cog.callback = self.select_cog_callback
        self.add_item(self.select_cog)

    def get_options(self):
        options = [
            SelectOption(label=f'{self.options[opt].cog_name}', value=f'{self.options[opt].cog_name}')
            for opt in self.options
        ]
        return options

    async def select_cog_callback(self, interaction: discord.Interaction):
        selected = self.options[self.select_cog.values[0]]
        await interaction.response.send_modal(EditConfigModal(selected, self.save_config, self.on_config_update))


class ConfigCog(commands.Cog):
    """Модуль для управления конфигурациями"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='config')
    @app_commands.guilds(main_guild_id)
    @app_commands.default_permissions(administrator=True)
    async def edit_config(self, interaction):
        async with AsyncSession(self.bot.db_engine) as session:
            options = list(await session.scalars(select(CogConfig)))
        await interaction.response.send_message(view=ConfigSelectView(options=options,
                                                                      save_config=self.save_config,
                                                                      on_config_update=self.on_config_update),
                                                ephemeral=True)

    async def on_config_update(self):
        await self.bot.load_config()
        for cog in self.bot.cogs:
            cog_obj = self.bot.get_cog(cog)
            if isinstance(cog_obj, CustomCog):
                await cog_obj.on_config_update()

    async def save_config(self, config: CogConfig):
        async with AsyncSession(self.bot.db_engine) as session:
            await session.merge(config)
            await session.commit()


async def setup(bot):
    await bot.add_cog(ConfigCog(bot))
    logger.info(f'Расширение {ConfigCog} загружено!')
