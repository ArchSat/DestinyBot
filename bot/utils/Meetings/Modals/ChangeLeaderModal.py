import datetime
import logging
from typing import Union

import discord
from discord import Interaction, ui
from discord.ui import Modal
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.Meeting import MemberStatus, MeetingMember
from utils.logger import create_logger

logger = create_logger(__name__)


class ChangeLeaderModal(Modal):
    def __init__(self, bot, meeting, active_members, render_function) -> None:
        super().__init__(title='Изменение лидера')
        self.bot = bot
        self.meeting = meeting
        self.active_members = active_members
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

    async def on_submit(self, interaction: Interaction, /) -> None:
        # TODO: Поработать над оформлением сообщения
        try:
            self.target = int(self.target.value)
        except:
            return await interaction.response.send_message(f'Некорректно указан ID участника', ephemeral=True)
        self.target = self.members_dict[self.target]
        await interaction.response.defer()
        async with AsyncSession(self.bot.db_engine) as session:
            try:
                update_time = datetime.datetime.now()
                result = await session.execute(update(MeetingMember).returning(MeetingMember).
                                               where((MeetingMember.meeting_id == self.meeting.meeting_id) &
                                                     (MeetingMember.discord_id == interaction.user.id)).
                                               values(status=MemberStatus.MEMBER, last_update=update_time))
                result.one()
                result = await session.execute(update(MeetingMember).returning(MeetingMember).
                                               where((MeetingMember.meeting_id == self.meeting.meeting_id) &
                                                     (MeetingMember.discord_id == self.target)).
                                               values(status=MemberStatus.LEADER, last_update=update_time))
                result.one()
                await session.commit()
                for member in self.meeting.meeting_members:
                    member: MeetingMember
                    if member.discord_id == self.target:
                        member.status = MemberStatus.LEADER
                    if member.discord_id == interaction.user.id:
                        member.status = MemberStatus.MEMBER

            except Exception as e:
                await session.rollback()
                return await interaction.followup.send(f'При передаче сбора произошла ошибка!\n{e}', ephemeral=True)
        try:
            await self.active_members[self.target].discord_user.send(
                f'Вы были назначены лидером в сборе {self.meeting.meeting_id}')
        except Exception as e:
            logger.exception(e)
            await interaction.followup.send('Участник не получил оповещение о передаче сбора!', ephemeral=True)
        await self.render_meeting(bot=self.bot, meeting=self.meeting)
        await interaction.followup.send('Участник успешно назначен лидером сбора!', ephemeral=True)
