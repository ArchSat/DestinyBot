import logging

import discord
from discord import ButtonStyle, app_commands, SelectOption
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.operators import is_

from ORM import MeetingChannel
from utils.Meetings.Modals.CreateActivity import CreateActivity
from utils.logger import create_logger

logger = create_logger(__name__)


class SelectActivityView(discord.ui.View):
    def __init__(self, bot, public_channels):
        super().__init__(timeout=None)
        self.bot = bot
        self.public_channels = {ch.channel_id: ch for ch in public_channels}
        options = [SelectOption(label=ch.name,
                                value=str(ch.channel_id),
                                emoji=ch.emoji if ch.emoji else None) for ch in public_channels]

        self.select_menu = discord.ui.Select(options=options,
                                             min_values=1,
                                             max_values=1,
                                             placeholder='Выбор активности')
        self.add_item(self.select_menu)
        self.select_menu.callback = self.select_activity

    async def select_activity(self, interaction: discord.Interaction):
        try:
            selected_channel = int(self.select_menu.values[0])
            channel = self.public_channels[selected_channel]
        except:
            return interaction.response.send_message('Произошла ошибка при создании сбора', ephemeral=True)
        modal = CreateActivity(self.bot, channel)
        await interaction.response.send_modal(modal)
        for item in self.children:
            item.disabled = True
        self.stop()
        await interaction.edit_original_response(view=self)


class CreateMeetingView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(style=ButtonStyle.gray, label='Создать сбор', custom_id='create_meeting')
    async def create_meeting(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            channel = (await session.scalar(select(MeetingChannel).
                                            where(MeetingChannel.channel_id == interaction.channel_id)))
            if not channel:
                return await interaction.response.send_message('Данный канал не предназначен для сборов!',
                                                               ephemeral=True)
        modal = CreateActivity(self.bot, channel)
        await interaction.response.send_modal(modal)
