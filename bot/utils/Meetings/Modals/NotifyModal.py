import logging
import os

import discord
from discord import Interaction, ui
from discord.ui import Modal
from dotenv import load_dotenv

from ORM.schemes.Meeting import Meeting, MemberStatus, MeetingMember, MeetingChannel
from utils.logger import create_logger
load_dotenv(override=True)

main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))
logger = create_logger(__name__)


class NotifyModal(Modal):
    def __init__(self, bot, meeting: Meeting, button_interaction: Interaction | None) -> None:
        super().__init__(title=f'Оповещение участников сбора')
        self.bot = bot
        self.meeting = meeting
        self.button_interaction = button_interaction
        self.notify_text = ui.TextInput(label='Текст оповещения',
                                        style=discord.TextStyle.long,
                                        required=True,
                                        min_length=5,
                                        max_length=255)
        self.add_item(self.notify_text)

    async def on_submit(self, interaction: Interaction, /) -> None:
        notify_embed = discord.Embed(title=f'Оповещение в сборе {self.meeting.meeting_channel.name}',
                                     description=f'{self.notify_text.value}\n'
                                                 f'\nСбор: {self.button_interaction.message.jump_url}')
        notify_embed.set_footer(text=f"ID: {self.meeting.meeting_id}")
        notify_embed.timestamp = self.meeting.start_at

        error_send = []
        success_send = []
        await interaction.response.defer()
        for member in self.meeting.meeting_members:
            if member.discord_id == interaction.user.id:
                continue
            if member.status in [MemberStatus.MEMBER, MemberStatus.LEADER]:
                member: MeetingMember
                try:
                    discord_member = await self.bot.fetch_user(member.discord_id)
                    await discord_member.send(embed=notify_embed)
                    success_send.append(member.discord_id)
                except Exception as e:
                    logger.exception(e)
                    error_send.append(member.discord_id)
        text = ''
        if success_send:
            text += 'Следующие участники получили уведомление: \n' + \
                    '\n'.join([f'<@{discord_id}>' for discord_id in success_send])
        else:
            text += 'Уведомление не было доставлено!\n'
        if error_send:
            text += '\nПри уведомлении следующих участников произошла ошибка: \n' + \
                    '\n'.join([f'<@{discord_id}>' for discord_id in error_send])
        await interaction.followup.send(text, ephemeral=True)
        meetings_notify_logs_channel_id = self.bot.config.get('meetings_notify_logs_channel')
        if meetings_notify_logs_channel_id:
            channel = self.bot.get_guild(main_guild_id).get_channel(meetings_notify_logs_channel_id)
            if channel:
                text = (f"From: {interaction.user.display_name}"
                        f"\n{text}")
                await channel.send(text, embed=notify_embed)
