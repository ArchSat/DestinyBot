import logging
import os
from typing import Union

import discord
from discord import Interaction, ui
from discord.ui import Modal
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.Meeting import MemberStatus, MeetingMember, Meeting, MeetingStatus
from utils.Meetings.Embeds import create_embed
from utils.logger import create_logger

logger = create_logger(__name__)

main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))


class CancelMeetingModal(Modal):
    def __init__(self, bot, meeting, delete_func) -> None:
        super().__init__(title='Отмена сбора')
        self.bot = bot
        self.meeting = meeting
        self.delete = delete_func

        self.comment = ui.TextInput(label='Причина отмены',
                                    style=discord.TextStyle.long,
                                    max_length=255,
                                    required=False)
        self.add_item(self.comment)

    async def on_submit(self, interaction: Interaction, /) -> None:
        # TODO: Поработать над оформлением
        await interaction.response.defer()
        async with AsyncSession(self.bot.db_engine) as session:
            await session.execute(update(Meeting).
                                  where(Meeting.meeting_id == self.meeting.meeting_id).
                                  values(status=MeetingStatus.CANCELED))
            await session.commit()
        error_send = []
        success_send = []
        for member in self.meeting.meeting_members:
            if member.discord_id == interaction.user.id:
                continue
            if member.status in [MemberStatus.MEMBER, MemberStatus.LEADER]:
                member: MeetingMember
                try:
                    discord_member = await self.bot.fetch_user(member.discord_id)
                    await discord_member.send(f'Сбор {self.meeting.meeting_id} отменен!\n'
                                              f'{self.comment.value}')
                    success_send.append(member.discord_id)
                except Exception as e:
                    logger.exception(e)
                    error_send.append(member.discord_id)
        try:
            await self.delete(bot=self.bot, meeting=self.meeting)
        except discord.errors.NotFound as e:
            logger.exception(e)
        await interaction.followup.send('Сбор отменен!', ephemeral=True)
        try:
            log_channel_id = self.bot.config.get('meetings_logs_channel', None)
            if log_channel_id:
                log_channel = await self.bot.get_guild(main_guild_id).fetch_channel(log_channel_id)
                if log_channel:
                    embed = create_embed(self.meeting)
                    await log_channel.send('Удаление сбора', embed=embed)
        except:
            pass
