import datetime
import logging
from typing import Union

import discord
from discord import Interaction, ui
from discord.ui import Modal
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.Meeting import MemberStatus, MeetingMember
from utils.Meetings.utils import find_member_in_meeting
from utils.logger import create_logger

logger = create_logger(__name__)


class KickBanModal(Modal):
    def __init__(self, bot, meeting, active_members, new_status, render_function) -> None:
        super().__init__(title='Исключение участника')
        self.bot = bot
        self.meeting = meeting
        self.active_members = active_members
        self.new_status = new_status
        self.render_meeting = render_function

        self.members_dict = {
            i + 1: member for i, member in enumerate(self.active_members)
        }
        self.members_dict.update({member: member for member in self.active_members})

        self.current_members = ui.TextInput(
            label='Текущие участники',
            style=discord.TextStyle.long,
            required=False,
            default='\n'.join([f"#{i + 1} ID: {member} - {self.active_members[member].discord_user.display_name}"
                               for i, member in enumerate(self.active_members)]))
        self.add_item(self.current_members)

        self.target = ui.TextInput(label='Укажите ID участника',
                                   style=discord.TextStyle.short,
                                   required=True)
        self.add_item(self.target)
        self.reason = ui.TextInput(label='Причина',
                                   style=discord.TextStyle.long,
                                   required=True,
                                   min_length=5,
                                   max_length=255)
        self.add_item(self.reason)

    async def on_submit(self, interaction: Interaction, /) -> None:
        # TODO: Поработать над оформлением сообщения
        try:
            self.target = int(self.target.value)
        except:
            return await interaction.response.send_message(f'Некорректно указан ID участника', ephemeral=True)
        self.target = self.members_dict[self.target]
        if self.target == self.meeting.author_id or self.target == interaction.user.id:
            return await interaction.response.send_message(f'Вы не можете исключить себя из сбора!', ephemeral=True)
        await interaction.response.defer()
        try:
            await self.active_members[self.target].discord_user.send(
                f'Вы были исключены из сбора {self.meeting.meeting_id} по причине: \n' + self.reason.value)
        except Exception as e:
            logger.exception(e)
            await interaction.followup.send('Участник не получил сообщение с причиной!', ephemeral=True)
        async with AsyncSession(self.bot.db_engine) as session:
            await session.execute(update(MeetingMember).
                                  where((MeetingMember.meeting_id == self.meeting.meeting_id) &
                                        (MeetingMember.discord_id == self.target)).
                                  values(status=self.new_status, last_update=datetime.datetime.now()))
            await session.commit()
        member = await find_member_in_meeting(self.meeting, self.target)
        self.meeting.meeting_members.remove(member)
        await self.render_meeting(bot=self.bot, meeting=self.meeting)
        await interaction.followup.send('Участник успешно исключен!', ephemeral=True)
