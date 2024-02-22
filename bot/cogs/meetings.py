import asyncio
import datetime
import os
from asyncio import sleep
from typing import Union, List

import discord
from discord import app_commands, Permissions, Interaction, RawMessageDeleteEvent
from discord.app_commands import Choice
from discord.ext import commands, tasks
from dotenv import load_dotenv
from sqlalchemy import update, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ORM import MeetingChannel
from ORM.schemes.Meeting import Meeting, MeetingStatus
from utils.CustomCog import CustomCog
from utils.Meetings.Embeds import init_channel_embed, create_embed
from utils.Meetings.Views.CreateMeetingView import CreateMeetingView
from utils.Meetings.Views.MeetingView import MeetingView, delete_meeting
from utils.ResourseConverters import ResourseType

from utils.logger import create_logger

logger = create_logger('Meetings')

load_dotenv(override=True)
main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))

check_expire_meetings_interval = 10


async def activity_autocomplete(interaction: Interaction, current: str):
    t = [Choice(name=DAM.name, value=DAM.name) for DAM in ResourseType if current.lower() in DAM.name.lower()][:25]
    return t


class MeetingsCog(commands.Cog):
    """Модуль сборов"""

    def __init__(self, bot):
        self.bot = bot
        self.check_expire_meetings.start()

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: RawMessageDeleteEvent):
        # Меняет статус сбора на удаленный
        if payload.cached_message and not payload.cached_message.author.bot:
            return
        async with AsyncSession(self.bot.db_engine) as session:
            await session.execute(update(Meeting).
                                  where((Meeting.meeting_id == payload.message_id) &
                                        (Meeting.status == MeetingStatus.ACTIVE)).
                                  values(status=MeetingStatus.DELETED_BY_OTHER_USER))
            await session.commit()

    @tasks.loop(minutes=check_expire_meetings_interval)
    async def check_expire_meetings(self):
        await self.bot.wait_until_ready()
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            query = select(Meeting).options(
                selectinload(Meeting.meeting_channel)
            ).where(and_(Meeting.actual_until <= datetime.datetime.now() +
                         datetime.timedelta(minutes=check_expire_meetings_interval),
                         Meeting.status.in_([MeetingStatus.ACTIVE, MeetingStatus.COMPLETED])))
            expired_meetings = list((await session.execute(query)).unique().scalars())
        asyncio.create_task(self.process_expired_meetings(expired_meetings=expired_meetings))

    async def process_expired_meetings(self, expired_meetings: List[Meeting]):
        while True:
            for meeting in expired_meetings:
                if meeting.actual_until <= datetime.datetime.now():
                    async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
                        if meeting.status == MeetingStatus.ACTIVE:
                            meeting.status = MeetingStatus.DELETED_BY_OVERDUE
                        if meeting.status == MeetingStatus.COMPLETED:
                            meeting.status = MeetingStatus.DELETED_BY_COMPLETED
                        logger.info(f"Changed status {meeting.meeting_id}: {meeting.status}")
                        await session.merge(meeting)
                        await session.commit()
                else:
                    continue
                try:
                    await delete_meeting(self.bot, meeting)
                except:
                    pass
                try:
                    log_channel_id = self.bot.config.get('meetings_logs_channel', None)
                    if log_channel_id:
                        log_channel = await self.bot.get_guild(main_guild_id).fetch_channel(log_channel_id)
                        if log_channel:
                            embed = create_embed(meeting)
                            await log_channel.send('Удаление сбора', embed=embed)
                except:
                    pass
            await sleep(1)
            if all([True if meeting.status in [MeetingStatus.DELETED_BY_COMPLETED,
                                               MeetingStatus.DELETED_BY_OVERDUE,
                                               MeetingStatus.DELETED_BY_OTHER_USER] else False
                    for meeting in expired_meetings]):
                break

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(CreateMeetingView(self.bot))
        self.bot.add_view(MeetingView(self.bot))

    meetings_group = app_commands.Group(name="meetings",
                                        description="Команды модуля сборов",
                                        guild_ids=[main_guild_id],
                                        default_permissions=Permissions(8),
                                        )

    meetings_category_group = app_commands.Group(name="category",
                                                 description="Команды управления конфигурацией модуля сборов",
                                                 guild_ids=[main_guild_id],
                                                 parent=meetings_group
                                                 )

    @meetings_category_group.command(name='add', description='Создает категорию сборов')
    @app_commands.autocomplete(activity_type=activity_autocomplete)
    @app_commands.describe(channel='Канал, для которого определяются настройки',
                           planned_channel='Канал для запланированных сборов',
                           name='Название категории',
                           description='Описание категории',
                           custom_meeting_text='Текст, отправляемый при создании сбора (может быть упоминание роли)',
                           icon='Иконка в оформлении сборов',
                           default_members_count='Число участников по умолчанию',
                           max_members_count='Максимальное число участников',
                           activity_type='Тип активностей (BungieManifest)',
                           metric_hashes='Хеши метрик для отображения статистики (через запятую, будут суммироваться)',
                           voices_category='Категория для создания голосовых каналов'
                           )
    async def add_category_command(self,
                                   interaction: Interaction,
                                   channel: discord.TextChannel,
                                   planned_channel: Union[discord.TextChannel, None],
                                   name: str,
                                   description: Union[str, None],
                                   custom_meeting_text: Union[str, None],
                                   icon: Union[str, None],
                                   default_members_count: int,
                                   max_members_count: int,
                                   activity_type: Union[str, None],
                                   metric_hashes: Union[str, None],
                                   voices_category: Union[discord.CategoryChannel, None]
                                   ):
        new_category = MeetingChannel(channel_id=channel.id,
                                      planned_channel_id=planned_channel.id if planned_channel else channel.id,
                                      name=name,
                                      custom_meeting_text=custom_meeting_text,
                                      description=description,
                                      icon_url=icon,
                                      default_members_count=default_members_count,
                                      max_members_count=max_members_count,
                                      activity_type=activity_type,
                                      metric_hash=[int(metric_hash) for metric_hash in metric_hashes.split(',')]
                                      if metric_hashes else None,
                                      voices_category_id=voices_category.id if voices_category else None,
                                      )
        async with AsyncSession(self.bot.db_engine) as session:
            await session.merge(new_category)
            await session.commit()
        await interaction.response.send_message(f'Новая категория создана для канала: {channel.jump_url}',
                                                ephemeral=True)

        init_message = await channel.send(embed=init_channel_embed(new_category.name, new_category.description),
                                          view=CreateMeetingView(self.bot))
        new_category.create_meeting_message_id = init_message.id

        async with AsyncSession(self.bot.db_engine) as session:
            await session.merge(new_category)
            await session.commit()

        await interaction.followup.send(content=f'Сообщение для создания сборов опубликовано: {init_message.jump_url}',
                                        ephemeral=True)


async def setup(bot):
    await bot.add_cog(MeetingsCog(bot))
    logger.info(f'Расширение {MeetingsCog} загружено!')
