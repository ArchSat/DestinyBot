import asyncio
import datetime
import logging
import os
from asyncio import sleep
from copy import copy
from functools import partial
from typing import Optional, Union, List

import discord
from discord import app_commands, Interaction, Permissions
from discord.ext import commands, tasks
from discord.ext.commands import Context
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.User import SanctionStatus, SanctionType, Sanction
from utils.CustomCog import CustomCog
from utils.Moderation.moderation_utils import SanctionModal, WarnListView
from utils.logger import create_logger

logger = create_logger('Moderation')

main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))

minimal_sanction_interval_minutes = 10


class ModerationCog(CustomCog):
    """Команды модераторов Discord"""

    def __init__(self, bot):
        super().__init__(bot)
        self.persistent_warns_update = None
        self.check_expire_sanctions.start()

        self.warn_context = app_commands.ContextMenu(guild_ids=[main_guild_id], name='Предупреждение',
                                                     callback=self.warn_user_callback)
        self.bot.tree.add_command(self.warn_context)

        self.ban_context = app_commands.ContextMenu(guild_ids=[main_guild_id], name='Бан',
                                                    callback=self.ban_user_callback)
        self.bot.tree.add_command(self.ban_context)

    async def init_config(self):
        self.config = {
            'warn_list_channel_id': None,
            'warn_list_message_id': None
        }

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_config()
        message = None
        if self.config.get('warn_list_channel_id', None):
            if self.config.get('warn_list_message_id', None):
                guild = self.bot.get_guild(main_guild_id)
                try:
                    channel = await guild.fetch_channel(self.config['warn_list_channel_id'])
                    message = await channel.fetch_message(self.config['warn_list_message_id'])
                except:
                    pass
        await self.add_persistant_view(message)

    async def add_persistant_view(self, message):
        warns_view = WarnListView(update_warns_func=self.get_active_warns, message=message, persistence=True)
        await warns_view.init()
        await warns_view.update()
        self.bot.add_view(warns_view)
        self.persistent_warns_update = warns_view.update

    warnlist_group = app_commands.Group(name="warnlist",
                                        description="Команды работы с предупреждениями",
                                        guild_ids=[main_guild_id],
                                        default_permissions=Permissions(8),
                                        )

    @warnlist_group.command(name='persistent', description='Создает постоянное меню с списком предупреждений '
                                                           '(может быть только одно)')
    @app_commands.default_permissions(administrator=True)
    async def warnlist_command(self, interaction: Interaction):
        warns_view = WarnListView(update_warns_func=self.get_active_warns, persistence=True)
        await warns_view.init()
        await warns_view.send_message(ctx=interaction, text=None)
        self.config['warn_list_channel_id'] = warns_view.message.channel.id
        self.config['warn_list_message_id'] = warns_view.message.id
        await self.save_config()
        await self.add_persistant_view(warns_view.message)

    @warnlist_group.command(name='user', description='Список всех примененных к пользователю санкций')
    @app_commands.describe(user='Пользователь для просмотра списка')
    async def user_warnlist_command(self, interaction: Interaction, user: discord.Member):
        warns_view = WarnListView(update_warns_func=partial(self.get_user_sanctions, user=user), persistence=False)
        await warns_view.init()
        await warns_view.send_message(ctx=interaction, text=None)

    async def get_user_sanctions(self, user: discord.Member):
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            query = select(Sanction).where(Sanction.member_id == user.id)
            actual_warns = list(await session.scalars(query))
        return actual_warns

    async def get_active_warns(self):
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            query = select(Sanction).where(and_(
                Sanction.status == SanctionStatus.ACTIVE),
                (Sanction.type == SanctionType.WARN)
            )
            actual_warns = list(await session.scalars(query))
        return actual_warns

    # Реализация кэширования конечно так себе, но лучше лезть в БД раз в 10 минут, чем каждую минуту
    @tasks.loop(minutes=minimal_sanction_interval_minutes)
    async def check_expire_sanctions(self):
        await self.bot.wait_until_ready()
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            query = select(Sanction).where(
                and_(Sanction.expire <= datetime.datetime.now() +
                     datetime.timedelta(minutes=minimal_sanction_interval_minutes),
                     Sanction.status == SanctionStatus.ACTIVE)
            )
            expired_sanctions = list(await session.scalars(query))
        asyncio.create_task(self.process_expired_sanctions(expired_sanctions=expired_sanctions))

    async def process_expired_sanctions(self, expired_sanctions: List[Sanction]):
        while True:
            for sanction in expired_sanctions:
                if sanction.expire <= datetime.datetime.now():
                    sanction.status = SanctionStatus.EXPIRE
                else:
                    continue
                async with AsyncSession(self.bot.db_engine) as session:
                    await session.merge(sanction)
                    await session.commit()
                await self.remove_sanction_from_user(sanction.member_id, sanction.type)
            await sleep(1)
            if all([True if sanction.status == SanctionStatus.EXPIRE else False for sanction in expired_sanctions]):
                break

    async def remove_sanction_from_user(self, discord_id: int, sanction_type: SanctionType):
        if sanction_type == SanctionType.BAN:
            try:
                user = await self.bot.fetch_user(discord_id)
                if user:
                    guild: discord.Guild = self.bot.get_guild(main_guild_id)
                    ban = await guild.fetch_ban(user)
                    await guild.unban(user, reason='Срок бана истек')
                    logger.info(f'{user} срок бана истек!')
            except Exception as e:
                logger.exception(e)
        if sanction_type == SanctionType.WARN:
            if self.persistent_warns_update:
                await self.persistent_warns_update()

    @app_commands.command(name='warn')
    @app_commands.default_permissions(administrator=True)
    @app_commands.guilds(main_guild_id)
    @app_commands.describe(user='Пользователь для выдачи предупреждения')
    async def warn_command(self, interaction, user: discord.Member):
        modal = SanctionModal(title=f'Предупреждение пользователю {user.display_name}',
                              target=user,
                              duration='14d',
                              sanction_type=SanctionType.WARN,
                              bot=self.bot,
                              sanction_function=partial(self.warn_callback_function, user=user))
        await interaction.response.send_modal(modal)

    @app_commands.default_permissions(administrator=True)
    async def warn_user_callback(self, interaction, user: discord.Member):
        modal = SanctionModal(title=f'Предупреждение пользователю {user.display_name}',
                              target=user,
                              duration='14d',
                              sanction_type=SanctionType.WARN,
                              bot=self.bot,
                              sanction_function=partial(self.warn_callback_function, user=user))
        await interaction.response.send_modal(modal)

    async def warn_callback_function(self, user: discord.Member, sanction_embed, **kwargs):
        try:
            await user.send(embed=sanction_embed)
        except Exception as e:
            logger.exception(e)
        if self.persistent_warns_update:
            await self.persistent_warns_update()

    @app_commands.command(name='unwarn')
    @app_commands.default_permissions(administrator=True)
    @app_commands.guilds(main_guild_id)
    async def unwarn_command(self, interaction, warn_id: int):
        await interaction.response.defer()
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            query = select(Sanction).where(and_(Sanction.id == warn_id, Sanction.type == SanctionType.WARN))
            warn: Union[Sanction | None] = await session.scalar(query)
            if warn:
                if warn.status == SanctionStatus.ACTIVE:
                    warn.status = SanctionStatus.REMOVED
                    await session.merge(warn)
                    await session.commit()
                    if self.persistent_warns_update:
                        await self.persistent_warns_update()
                    return await interaction.followup.send(f'Предупреждение удалено!')
                else:
                    return await interaction.followup.send(f'Предупреждение имеет статус {warn.status} '
                                                           f'и не подлежит редактированию!')
            else:
                return await interaction.followup.send(f'Предупреждение с таким идентификатором не найдено!')

    @app_commands.command(name='ban')
    @app_commands.default_permissions(administrator=True)
    @app_commands.guilds(main_guild_id)
    @app_commands.describe(user='Пользователь для выдачи бана')
    async def ban_command(self, interaction, user: discord.Member):
        modal = SanctionModal(title=f'Бан {user.display_name}',
                              target=user,
                              duration='14d',
                              sanction_type=SanctionType.BAN,
                              bot=self.bot,
                              sanction_function=partial(self.ban_callback_function, user=user, author=interaction.user))
        await interaction.response.send_modal(modal)

    @app_commands.default_permissions(administrator=True)
    async def ban_user_callback(self, interaction, user: discord.Member):
        modal = SanctionModal(title=f'Бан {user.display_name}',
                              target=user,
                              duration='14d',
                              sanction_type=SanctionType.BAN,
                              bot=self.bot,
                              sanction_function=partial(self.ban_callback_function, user=user, author=interaction.user))
        await interaction.response.send_modal(modal)

    async def ban_callback_function(self, sanction: Sanction, user: discord.Member, sanction_embed, **kwargs):
        if sanction.expire and sanction.expire <= \
                datetime.datetime.now() + datetime.timedelta(minutes=minimal_sanction_interval_minutes):
            asyncio.create_task(self.process_expired_sanctions([sanction]))
        reason = kwargs.get('reason', 'Без указания причины')
        author = kwargs.get('author', None)
        try:
            await user.send(embed=sanction_embed)
        except:
            pass
        try:
            await user.ban(reason=f"{author}: {reason}" if author else reason)
        except Exception as e:
            logger.exception(e)
            raise e

    async def cog_command_error(self, context: Context, exception: Exception):
        command = context.command
        if command and command.has_error_handler():
            return

        cog = context.cog
        if cog and cog.has_error_handler():
            return

        logger.error('Ignoring exception in command %s', command, exc_info=exception)

        await context.reply(f'При выполнении команды произошла ошибка: {exception}')

    @app_commands.command(name='clear', description='Удаляет сообщения в канале')
    @app_commands.guilds(main_guild_id)
    @app_commands.default_permissions(administrator=True)
    async def clear_command(self, interaction: Interaction,
                            count: Optional[int] = 5):
        await interaction.response.defer(thinking=True, ephemeral=True)
        deleted_messages = await interaction.channel.purge(limit=count)
        await interaction.followup.send(f'Удалено {len(deleted_messages)} сообщений!', ephemeral=True)

    @commands.command(hidden=False)
    @commands.has_permissions(administrator=True)
    async def sudo(self, ctx, victim: Union[discord.Member, int, str], *, command):
        if isinstance(victim, str):
            await ctx.reply('Можно указать либо DiscordID, либо тег пользователя!')
            return
        if isinstance(victim, int):
            try:
                new_id = (await self.bot.fetch_user(victim)).id
            except discord.errors.NotFound:
                return await ctx.reply('Пользователь не найден!')
            victim = copy(ctx.message.author)
            victim._user = copy(victim._user)
            victim._user.id = new_id
        new_message = copy(ctx.message)
        new_message.author = victim
        new_message.content = ctx.prefix + command
        try:
            await self.bot.process_commands(new_message)
        except Exception as e:
            await ctx.reply(e)


async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
    logger.info(f'Расширение {ModerationCog} загружено!')
