import asyncio
import datetime
import logging
import os
import time
from copy import copy
from typing import Optional, List, Union

import discord
from discord import app_commands, Interaction, Permissions, ChannelType
from discord.abc import GuildChannel
from discord.app_commands import Choice
from discord.ext import commands, tasks
from sqlalchemy import select, delete, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tabulate import tabulate

from ORM.schemes.Meeting import Meeting
from ORM.schemes.Voice import VoiceCategory, Voice, VoiceChannelType
from utils.CustomCog import CustomCog
from utils.logger import create_logger
from ORM.schemes.Clan import Clan

# logger = logging.getLogger('discord')

logger = create_logger(__name__)

main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))


async def return_user(member: discord.Member, before=None, reason=None, message_text: str | None = None):
    if member.voice:
        if before and before.channel:
            await member.move_to(before.channel, reason=reason)
        else:
            await member.move_to(None, reason=reason)
        if reason and message_text:
            try:
                await member.send(message_text)
            except:
                pass


class Voices(CustomCog):
    """Модуль для управления голосовыми каналами"""

    def __init__(self, bot):
        super().__init__(bot)
        self.delete_voices_tasks = {

        }

    async def init_config(self):
        self.config = {
            'roles_can_connect_create_voices': [1128208142124191773],
            'other_games_category_id': None,
            'other_games_deny_applications': [372438022647578634, 726090012877258762],
            'create_voice_cooldown': 10,
            'delete_delay': 30
        }

    def check_other_games(self, member: discord.Member):
        result = True
        for activity in member.activities:
            if getattr(activity, 'application_id', None) in self.config['other_games_deny_applications']:
                result = False
            if 'destiny' in activity.name.lower():
                result = False
        return result

    async def create_overwrites(self, member: discord.Member, voice_category: VoiceCategory):
        overwrites = {}
        guild = member.guild
        for ov in voice_category.default_overwrites:
            if guild.get_role(int(ov)):
                overwrites[guild.get_role(int(ov))] = discord.PermissionOverwrite(
                    **voice_category.default_overwrites[ov])
            else:
                overwrites[guild.get_member(int(ov))] = discord.PermissionOverwrite(
                    **voice_category.default_overwrites[ov])
        overwrites.pop(None, None)
        return overwrites

    async def create_voice(self, member: discord.Member, voice_category: VoiceCategory):
        logger.info(f'Создается голосовой канал для {member}')
        guild = member.guild
        category = await guild.fetch_channel(voice_category.category_id)
        overwrites = await self.create_overwrites(member=member, voice_category=voice_category)
        new_voice = await category.create_voice_channel(
            name=f"{voice_category.default_channel_name} - {member.display_name}",
            user_limit=voice_category.user_limit,
            bitrate=guild.bitrate_limit,
            overwrites=overwrites)
        async with AsyncSession(self.bot.db_engine) as session:
            voice = Voice(channel_id=new_voice.id,
                          category_id=voice_category.category_id,
                          author_id=member.id)
            await session.merge(voice)
            await session.commit()
        await member.move_to(new_voice)

    async def delete_voice_over_time(self, voice: discord.VoiceChannel):
        await asyncio.sleep(self.config.get('delete_delay', 0))
        if not voice.members:
            await voice.delete()
            self.delete_voices_tasks.pop(voice.id, None)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: GuildChannel):
        if channel.type != ChannelType.voice:
            return
        async with AsyncSession(self.bot.db_engine) as session:
            query = update(Voice).where(Voice.channel_id == channel.id).values(channel_type=VoiceChannelType.DELETED)
            await session.execute(query)
            await session.commit()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before, after):
        if member.bot:
            return

        # Если канал находится в очереди на удаление - задача отменяется и удаляется
        if getattr(getattr(after, 'channel', None), 'id', None):
            if after.channel.id in self.delete_voices_tasks:
                logger.debug(
                    f'{member} зашел в канал {after.channel}, который готовится к удалению. Удаление отменено!')
                self.delete_voices_tasks[after.channel.id].cancel()
                self.delete_voices_tasks.pop(after.channel.id, None)

        after_category_id = getattr(getattr(getattr(after, 'channel', None), 'category', None), 'id', None)

        if after_category_id == self.config.get('other_games_category_id', 0):
            if not self.check_other_games(member):
                await return_user(member=member,
                                  before=before,
                                  reason='Destiny 2 в других играх',
                                  message_text='В данной категории запрещено играть в Destiny 2!\n'
                                               'Используйте тематические каналы!')

        if after_category_id:
            async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
                select_category_query = select(VoiceCategory). \
                    where(VoiceCategory.category_id == after_category_id)
                category = await session.scalar(select_category_query)
                if category:
                    select_creators_query = select(Voice). \
                        where(and_(Voice.channel_type == VoiceChannelType.CREATOR,
                                   Voice.category_id == category.category_id))
                    creators = list(await session.scalars(select_creators_query))
                    if after.channel.id in [creator.channel_id for creator in creators]:
                        select_last_created_user_channel = select(Voice). \
                            where(Voice.author_id == member.id). \
                            order_by(Voice.created_at.desc()). \
                            limit(1)
                        last_created_voice: Voice | None = await session.scalar(select_last_created_user_channel)
                        if last_created_voice and \
                                datetime.datetime.now() - last_created_voice.created_at <= \
                                datetime.timedelta(seconds=self.config.get('create_voice_cooldown', 0)):
                            logger.info(f"Кулдаун создания голосового канала для {member}")
                            await return_user(member=member,
                                              before=before,
                                              reason='Кулдаун создания голосовых каналов!',
                                              message_text=f'Создавать голосовые каналы можно не чаще чем раз в '
                                                           f'{self.config.get("create_voice_cooldown", 0)} секунд!')
                        else:
                            session.expunge_all()
                            await session.rollback()
                            await session.close()
                            await self.create_voice(member=member, voice_category=category)

        if before.channel:
            if not before.channel.members:
                await self.check_and_delete_if_require(before.channel)

    async def check_and_delete_if_require(self, channel: discord.VoiceChannel):
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            select_category_query = select(Voice). \
                where(Voice.channel_id == channel.id)
            voice: Voice | None = await session.scalar(select_category_query)
        if voice and voice.channel_type == VoiceChannelType.TEMPORARY:
            logger.debug(f'Канал {channel} пуст. Создана задача на удаление.')
            task = asyncio.create_task(self.delete_voice_over_time(channel))
            self.delete_voices_tasks[channel.id] = task
            return True
        else:
            return False

    @commands.Cog.listener()
    async def on_ready(self):
        pass
        # guild: discord.Guild = await self.bot.fetch_guild(main_guild_id)
        # all_channels = {channel.id: channel for channel in await guild.fetch_channels()}
        # Удаление пустых каналов после перезагрузки
        # for channel in all_channels:
        #     if all_channels[channel].type == ChannelType.voice:
        #         if not all_channels[channel].members:
        #             await self.check_and_delete_if_require(all_channels[channel])

    voices_group = app_commands.Group(name="voice",
                                      description="Команды управления голосовыми каналами",
                                      guild_ids=[main_guild_id],
                                      default_permissions=Permissions(8),
                                      )
    voices_category_group = app_commands.Group(name="category",
                                               description="Команды управления категориями голосовых каналов",
                                               guild_ids=[main_guild_id],
                                               parent=voices_group
                                               )

    @voices_category_group.command(name='add', description='Создает категорию голосовых каналов')
    @app_commands.describe(voices_category='Категория для создания голосовых каналов',
                           create_voice='Канал, который будет создавать новые каналы '
                                        '(если не указать - команда создаст новый)',
                           default_channel_name='Имя каналов по умолчанию',
                           user_limit='Лимит пользователей в каналах по умолчанию',
                           delete_current_voices='Добавлять ли текущие голосовые каналы в '
                                                 'исключения для удаления (False)',
                           overwrites='Канал, с которого скопировать права для создания будущих войсов')
    async def add_category_command(self,
                                   interaction: Interaction,
                                   voices_category: discord.CategoryChannel,
                                   create_voice: Union[discord.VoiceChannel, None],
                                   default_channel_name: str,
                                   user_limit: Union[int, None],
                                   delete_current_voices: bool = True,
                                   overwrites: Union[discord.VoiceChannel, None] = None
                                   ):
        if not create_voice:
            new_overwrites = {
                voices_category.guild.default_role: discord.PermissionOverwrite.from_pair(discord.Permissions.none(),
                                                                                          discord.Permissions.all()),

            }
            new_overwrites.update({voices_category.guild.get_role(role):
                                       discord.PermissionOverwrite(view_channel=True,
                                                                   connect=True,
                                                                   create_instant_invite=True,
                                                                   speak=False)
                                   for role in self.config.get('roles_can_connect_create_voices', [])})
            new_overwrites.pop(None, None)
            create_voice = await voices_category.create_voice_channel(name='🔊 Создать Войс 🔊',
                                                                      overwrites=new_overwrites)

        overwrites_obj = {}
        if overwrites:
            for ov in overwrites.overwrites:
                overwrites_obj[ov.id] = overwrites.overwrites[ov]._values

        new_category = VoiceCategory(
            category_id=voices_category.id,
            create_voice_channel_id=create_voice.id if create_voice else None,
            default_channel_name=default_channel_name,
            user_limit=user_limit,
            default_overwrites=overwrites_obj
        )
        new_voice = Voice(
            channel_id=create_voice.id,
            channel_type=VoiceChannelType.CREATOR,
            category_id=new_category.category_id
        )

        async with AsyncSession(self.bot.db_engine) as session:
            await session.merge(new_category)
            if not delete_current_voices:
                for channel in voices_category.voice_channels:
                    voice = Voice(
                        channel_id=channel.id,
                        channel_type=VoiceChannelType.PERMANENT,
                        category_id=voices_category.id
                    )
                    await session.merge(voice)
            await session.merge(new_voice)
            await session.commit()
        await interaction.response.send_message('Новая категория создана!')


async def setup(bot):
    await bot.add_cog(Voices(bot))
    logger.info(f'Расширение {Voices} загружено!')
