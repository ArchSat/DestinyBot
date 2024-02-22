import datetime
import logging

import discord
from discord import Interaction, ui
from discord.ui import Modal
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.Meeting import MemberStatus, Meeting, MeetingStatus
from utils.logger import create_logger

logger = create_logger(__name__)


class ChangeSizeModal(Modal):
    def __init__(self, bot, meeting, render_function, complete_event) -> None:
        super().__init__(title='Изменение размера сбора')
        self.bot = bot
        self.meeting = meeting
        self.render_meeting = render_function
        self.complete_event = complete_event

        self.new_size = ui.TextInput(label='Новый размер',
                                     style=discord.TextStyle.short,
                                     default=self.meeting.fireteam_max,
                                     required=True)
        self.add_item(self.new_size)

    async def on_submit(self, interaction: Interaction, /) -> None:
        await interaction.response.defer()
        try:
            current_members = [member for member in self.meeting.meeting_members
                               if member.status in [MemberStatus.MEMBER]]
            self.new_size = int(self.new_size.value)
            if len(current_members) > self.new_size:
                return await interaction.followup.send('Текущее количество участников превышает указанное значение!',
                                                       ephemeral=True)
            if self.new_size > self.meeting.meeting_channel.max_members_count:
                return await interaction.followup.send(f'Максимальное число участников для сборов в этом канале: '
                                                       f'{self.meeting.meeting_channel.max_members_count}!',
                                                       ephemeral=True)
        except:
            return await interaction.followup.send('При изменении размера сбора произошла ошибка!', ephemeral=True)
        async with AsyncSession(self.bot.db_engine) as session:
            self.meeting.fireteam_max = self.new_size
            if len(current_members) == self.new_size:
                self.meeting.status = MeetingStatus.COMPLETED
                self.meeting.complete_at = datetime.datetime.now()
                await self.complete_event(self.meeting)
            elif len(current_members) < self.new_size:
                self.meeting.status = MeetingStatus.ACTIVE
                self.meeting.complete_at = None
            await session.merge(self.meeting)
            await session.commit()
        await self.render_meeting(bot=self.bot, meeting=self.meeting)
        await interaction.followup.send('Размер сбора успешно обновлен!', ephemeral=True)
