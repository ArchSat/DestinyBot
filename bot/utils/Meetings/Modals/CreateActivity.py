import datetime
import os

import logging

import discord
from discord import ui
from discord.ui import Modal, Item
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.Meeting import MeetingChannel, Meeting, MeetingMember, MemberStatus
from utils.Meetings.Embeds import create_meeting_embed
from utils.Meetings.Views.ConfirmView import ConfirmView
from utils.Meetings.Views.MeetingView import render_meeting
from utils.Meetings.utils import parse_date, create_meeting_member, check_many_meetings_of_member, get_full_meeting

from dotenv import load_dotenv

from utils.logger import create_logger

load_dotenv(override=True)

logger = create_logger(__name__)

main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))


class CreateActivity(Modal):
    def __init__(self, bot, meeting_channel: MeetingChannel) -> None:
        super().__init__(title=f'Создание сбора в {meeting_channel.name}'[:45])
        self.bot = bot
        self.meeting_channel = meeting_channel
        self.new_meeting_message = None
        self.description = ui.TextInput(label='Описание сбора',
                                        style=discord.TextStyle.long,
                                        required=False,
                                        max_length=255)
        self.add_item(self.description)
        self.fireteam_max = ui.TextInput(label='Количество участников сбора',
                                         style=discord.TextStyle.short,
                                         default=self.meeting_channel.default_members_count,
                                         required=True,
                                         max_length=len(str(self.meeting_channel.max_members_count)))
        self.add_item(self.fireteam_max)
        self.start_time = ui.TextInput(label='Время начала по МСК (Не обязательно)',
                                       style=discord.TextStyle.short,
                                       placeholder='01.01-12:00',
                                       required=False,
                                       min_length=11,
                                       max_length=11)
        self.add_item(self.start_time)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            start_time = parse_date(self.start_time.value) if self.start_time.value else datetime.datetime.now()
        except Exception as e:
            logger.exception(e)
            return await interaction.response.send_message(f'Некорректно указана дата!', ephemeral=True)
        try: 
            int(self.fireteam_max.value) 
        except ValueError:
            return await interaction.response.send_message(f'Некорректно указано число участников для сбора!',
                                                            ephemeral=True)
        if int(self.fireteam_max.value) > self.meeting_channel.max_members_count:
            return await interaction.response.send_message(f'Максимальное число участников '
                                                           f'для сбора в эту активность '
                                                           f'{self.meeting_channel.max_members_count}!', ephemeral=True)
        if int(self.fireteam_max.value) < 1:
            return await interaction.response.send_message(f'Указано некорректное число участников для сбора!',
                                                           ephemeral=True)
        new_meeting = Meeting(meeting_id=None,
                              category_id=self.meeting_channel.channel_id,
                              planned=bool(self.start_time.value),
                              author_id=interaction.user.id,
                              fireteam_max=int(self.fireteam_max.value),
                              comment=self.description.value,
                              start_at=start_time,
                              actual_until=start_time + datetime.timedelta(hours=6))

        await interaction.response.defer()

        channel_id = self.meeting_channel.channel_id \
            if not new_meeting.planned else self.meeting_channel.planned_channel_id

        many_meetings = await check_many_meetings_of_member(self.bot.db_engine, interaction.user.id, start_time)

        if many_meetings:
            confirm_view = ConfirmView()
            confirm_message = await interaction.followup.send("Вы пытаетесь создать или вступить в сбор, "
                                                              "записавшись или организовав другой сбор с "
                                                              "близким временем.\n"
                                                              "Неявка на сбор может повлечь выдачу штрафа!",
                                                              view=confirm_view,
                                                              ephemeral=True)
            await confirm_view.wait()
            if not confirm_view.confirmed:
                return await confirm_message.edit(content='Создание сбора отменено!', view=None)
        self.new_meeting_message: discord.Message = await (
            await self.bot.get_guild(main_guild_id).fetch_channel(channel_id)). \
            send(content=f'{self.meeting_channel.custom_meeting_text}', embed=create_meeting_embed())
        new_meeting.meeting_id = self.new_meeting_message.id
        meeting_leader: MeetingMember = await create_meeting_member(db_engine=self.bot.db_engine,
                                                                    meeting=new_meeting,
                                                                    discord_member=interaction.user)
        meeting_leader.status = MemberStatus.LEADER
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            session.add(new_meeting)
            session.add(meeting_leader)
            await session.commit()

        new_meeting = await get_full_meeting(self.bot.db_engine, self.new_meeting_message.id)
        await render_meeting(self.bot, new_meeting)
        if self.new_meeting_message.channel.id != interaction.channel_id:
            self.new_meeting_message: discord.Message
            return await interaction.followup.send(f'Сбор создан:\n'
                                                   f'{self.new_meeting_message.jump_url}', ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception, /):
        logger.error('Ошибка при создании сбора')
        logger.error(error, exc_info=error)
        if interaction.response.is_done():
            answer = interaction.followup.send
        else:
            answer = interaction.response.send_message

        await answer(f'При создании сбора произошла ошибка: {error}!', ephemeral=True)
        if self.new_meeting_message:
            await self.new_meeting_message.delete()
            async with AsyncSession(self.bot.db_engine) as session:
                await session.execute(delete(Meeting).where(Meeting.meeting_id == self.new_meeting_message.id))
