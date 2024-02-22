import logging
from typing import Union

import discord
from discord import Interaction, ui
from discord.ui import Modal
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.Meeting import MemberStatus, MeetingMember, Meeting
from utils.logger import create_logger

logger = create_logger(__name__)


class ChangeDescriptionModal(Modal):
    def __init__(self, bot, meeting, render_function) -> None:
        super().__init__(title='Изменение описания сбора')
        self.bot = bot
        self.meeting = meeting
        self.render_meeting = render_function

        self.comment = ui.TextInput(label='Описание',
                                    style=discord.TextStyle.long,
                                    default=self.meeting.comment,
                                    max_length=255,
                                    required=False)
        self.add_item(self.comment)

    async def on_submit(self, interaction: Interaction, /) -> None:
        await interaction.response.defer()
        async with AsyncSession(self.bot.db_engine) as session:
            await session.execute(update(Meeting).
                                  where(Meeting.meeting_id == self.meeting.meeting_id).
                                  values(comment=self.comment.value))
            await session.commit()
        self.meeting.comment = self.comment.value
        await self.render_meeting(bot=self.bot, meeting=self.meeting)
        await interaction.followup.send('Описание успешно изменено!', ephemeral=True)
