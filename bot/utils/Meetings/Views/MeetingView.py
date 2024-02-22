import asyncio
import dataclasses
import datetime
import logging
import os
from functools import partial

import discord
from discord import ButtonStyle, NotFound, Interaction
from discord.ui import Item
from sqlalchemy import select, insert, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ORM.schemes.Meeting import Meeting, MemberStatus, MeetingStatus, MeetingMember
from main import ElderLyBot
from utils.Meetings.Embeds import create_embed
from utils.Meetings.Modals.CancelMeetingModal import CancelMeetingModal
from utils.Meetings.Modals.ChangeDescriptionModal import ChangeDescriptionModal
from utils.Meetings.Modals.ChangeLeaderModal import ChangeLeaderModal
from utils.Meetings.Modals.KickBanModals import KickBanModal
from utils.Meetings.Modals.NotifyModal import NotifyModal
from utils.Meetings.Modals.SizeModal import ChangeSizeModal
from utils.Meetings.utils import create_meeting_member, get_full_meeting, create_meeting_member_fast, \
    update_meeting_member, find_member_in_meeting
from utils.logger import create_logger

main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))

logger = create_logger(__name__)


class MeetingView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot: ElderLyBot = bot

    async def on_error(self, interaction: Interaction, error: Exception, item: Item, /) -> None:
        logger.error('Ошибка при управлении сбором')
        logger.error(error, exc_info=error)
        if interaction.response.is_done():
            answer = interaction.followup.send
        else:
            answer = interaction.response.send_message
        await answer(f'При выполнении действия произошла ошибка: {error.__class__}\n{error}'
                     f'\nПовторите попытку позже или сообщите об этом администрации!', ephemeral=True)

    async def on_meeting_complete(self, meeting):
        channel = await self.bot.get_guild(main_guild_id). \
            fetch_channel(meeting.meeting_channel.channel_id
                          if not meeting.planned
                          else meeting.meeting_channel.planned_channel_id)
        message = await channel.fetch_message(meeting.meeting_id)
        embed = discord.Embed(title=f'Сбор {meeting.meeting_channel.name} завершен!',
                              description=f'{message.jump_url}')
        embed.set_footer(text=f'ID: {meeting.meeting_id}')

        for member in meeting.meeting_members:
            if member.status == MemberStatus.LEADER:
                try:
                    user = await self.bot.fetch_user(member.discord_id)
                    user_message = await user.send(f'Сбор завершен: {message.jump_url}',
                                                   embed=embed)
                    logger.info(f'Отправлено сообщение пользователю {user}: {user_message}')
                except Exception as e:
                    logger.exception(e)
                    pass

        meetings_logs_channel_id = self.bot.config.get('meetings_logs_channel', None)
        if meetings_logs_channel_id:
            channel = self.bot.get_guild(main_guild_id).get_channel(meetings_logs_channel_id)
            if channel:
                text = f"Сбор завершен!"
                embed.description += '\n'
                embed.description += '\n'.join([f'<@{member.discord_id}> - {member.status.value} ({member.last_update})'
                                                for member in meeting.meeting_members])
                await channel.send(text, embed=embed)

    @discord.ui.button(label='Вступить/Покинуть', custom_id=f'join_meeting', style=ButtonStyle.green)
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        meeting = await get_full_meeting(self.bot.db_engine, interaction.message.id)
        meeting: Meeting
        meeting_active_members = [member for member in meeting.meeting_members
                                  if member.status in [MemberStatus.MEMBER]]
        await interaction.response.defer()

        old_member = await find_member_in_meeting(meeting, interaction.user.id)
        if not old_member:
            old_member = False
        else:
            old_member = True

        new_member = await create_meeting_member_fast(meeting, interaction.user)

        if old_member:
            if new_member.status == MemberStatus.LEADER:
                return await interaction.followup.send('Вы являетесь лидером этого сбора!',
                                                       ephemeral=True)
            if new_member.status == MemberStatus.BANNED:
                return await interaction.followup.send('Вы не можете присоединиться к этому сбору!',
                                                       ephemeral=True)
        if new_member.status == MemberStatus.MEMBER:
            new_member.status = MemberStatus.LEFT
            meeting.status = MeetingStatus.ACTIVE
            meeting.complete_at = None
        else:
            if meeting.status == MeetingStatus.COMPLETED or len(meeting_active_members) >= meeting.fireteam_max:
                return await interaction.followup.send('Этот сбор закончен!',
                                                       ephemeral=True)
            new_member.status = MemberStatus.MEMBER
            meeting_active_members.append(new_member)

        new_member.last_update = datetime.datetime.now()

        if new_member.status == MemberStatus.MEMBER and meeting.fireteam_max == len(meeting_active_members):
            meeting.status = MeetingStatus.COMPLETED
            meeting.complete_at = datetime.datetime.now()

        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            if old_member:
                await session.merge(new_member)
            else:
                session.add(new_member)
            await session.commit()
        if not old_member:
            meeting.meeting_members.append(new_member)
            new_member.meeting = meeting
            meeting = new_member.meeting
        try:
            if meeting.status == MeetingStatus.COMPLETED:
                asyncio.create_task(self.on_meeting_complete(meeting))
            else:
                # Уведомление о выходе одного из участников из сбора
                try:
                    meetings_logs_channel_id = self.bot.config.get('meetings_logs_channel', None)
                    if meetings_logs_channel_id:
                        channel = self.bot.get_guild(main_guild_id).get_channel(meetings_logs_channel_id)
                        if channel:
                            text = f"Участник покинул завершенный сбор!"
                            embed = discord.Embed(title=f'Сбор {meeting.meeting_channel.name} не завершен!',
                                                  description=f'{interaction.message.jump_url}')
                            embed.set_footer(text=f'ID: {meeting.meeting_id}')
                            embed.description += '\n'
                            embed.description += '\n'.join(
                                [f'<@{member.discord_id}> - {member.status.value} ({member.last_update})'
                                 for member in meeting.meeting_members])
                            await channel.send(text, embed=embed)
                except:
                    pass
            await render_meeting(self.bot, meeting)
        except Exception as e:
            logger.exception(e)
        if not old_member:
            asyncio.create_task(update_meeting_member(
                db_engine=self.bot.db_engine,
                meeting=meeting,
                discord_member=interaction.user,
                render_meeting_func=partial(render_meeting, self.bot)
            )
            )

    @discord.ui.button(label='Оповестить', custom_id=f'notify_meeting')
    async def notify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        meeting = await get_full_meeting(self.bot.db_engine, interaction.message.id)
        access = False
        for member in meeting.meeting_members:
            if member.status == MemberStatus.LEADER and member.discord_id == interaction.user.id:
                access = True
                break
        can_notify_meetings = self.bot.config.get('can_notify_meetings', [])
        for role_id in can_notify_meetings:
            if interaction.user.get_role(role_id):
                access = True
                break
        if access:
            modal = NotifyModal(self.bot, meeting, button_interaction=interaction)
            return await interaction.response.send_modal(modal)
        await interaction.response.defer()

    @discord.ui.button(label='Исключить', custom_id=f'kick_member_meeting')
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        meeting = await get_full_meeting(self.bot.db_engine, interaction.message.id)
        access = False
        for member in meeting.meeting_members:
            if member.status == MemberStatus.LEADER and member.discord_id == interaction.user.id:
                access = True
                break
        if access:
            active_members = {}
            for member in meeting.meeting_members:
                if member.status in [MemberStatus.LEADER, MemberStatus.MEMBER]:
                    try:
                        member.discord_user = await self.bot.get_guild(main_guild_id). \
                            fetch_member(member.discord_id)
                    except NotFound:
                        member.discord_user = await self.bot.fetch_user(member.discord_id)
                    active_members[member.discord_id] = member

            modal = KickBanModal(bot=self.bot,
                                 meeting=meeting,
                                 active_members=active_members,
                                 new_status=MemberStatus.KICKED,
                                 render_function=render_meeting)
            return await interaction.response.send_modal(modal)
        await interaction.response.defer()

    @discord.ui.button(label='Описание', custom_id='description_meeting')
    async def description_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        meeting = await get_full_meeting(self.bot.db_engine, interaction.message.id)
        meeting: Meeting
        access = False
        for member in meeting.meeting_members:
            if member.status == MemberStatus.LEADER and member.discord_id == interaction.user.id:
                access = True
                break
        if access:
            modal = ChangeDescriptionModal(bot=self.bot,
                                           meeting=meeting,
                                           render_function=render_meeting)
            return await interaction.response.send_modal(modal)
        await interaction.response.defer()

    @discord.ui.button(label='Размер', custom_id='size_meeting')
    async def size_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        meeting = await get_full_meeting(self.bot.db_engine, interaction.message.id)
        meeting: Meeting
        access = False
        for member in meeting.meeting_members:
            if member.status == MemberStatus.LEADER and member.discord_id == interaction.user.id:
                access = True
                break
        if access:
            modal = ChangeSizeModal(bot=self.bot,
                                    meeting=meeting,
                                    render_function=render_meeting,
                                    complete_event=self.on_meeting_complete)
            return await interaction.response.send_modal(modal)
        await interaction.response.defer()

    @discord.ui.button(label='Лидер', custom_id='leader_meeting')
    async def leader_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        meeting = await get_full_meeting(self.bot.db_engine, interaction.message.id)
        meeting: Meeting
        access = False
        for member in meeting.meeting_members:
            if member.status == MemberStatus.LEADER and member.discord_id == interaction.user.id:
                access = True
                break
        if access:
            active_members = {}
            for member in meeting.meeting_members:
                if member.status in [MemberStatus.LEADER, MemberStatus.MEMBER]:
                    try:
                        member.discord_user = await self.bot.get_guild(main_guild_id). \
                            fetch_member(member.discord_id)
                    except NotFound:
                        member.discord_user = await self.bot.fetch_user(member.discord_id)
                    active_members[member.discord_id] = member
            modal = ChangeLeaderModal(bot=self.bot,
                                      meeting=meeting,
                                      active_members=active_members,
                                      render_function=render_meeting)
            return await interaction.response.send_modal(modal)
        await interaction.response.defer()

    # TODO: Перспектива на большой дистанции
    # @discord.ui.button(label='Voice', custom_id='create_voice_meeting')
    # async def voice_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    #     raise NotImplementedError()

    @discord.ui.button(label='Бан', custom_id='ban_member_meeting', style=ButtonStyle.red)
    async def ban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        meeting = await get_full_meeting(self.bot.db_engine, interaction.message.id)
        meeting: Meeting
        access = False
        for member in meeting.meeting_members:
            if member.status == MemberStatus.LEADER and member.discord_id == interaction.user.id:
                access = True
                break
        if access:
            active_members = {}
            for member in meeting.meeting_members:
                if member.status in [MemberStatus.LEADER, MemberStatus.MEMBER]:
                    try:
                        member.discord_user = await self.bot.get_guild(main_guild_id). \
                            fetch_member(member.discord_id)
                    except NotFound:
                        member.discord_user = await self.bot.fetch_user(member.discord_id)
                    active_members[member.discord_id] = member

            modal = KickBanModal(bot=self.bot,
                                 meeting=meeting,
                                 active_members=active_members,
                                 new_status=MemberStatus.BANNED,
                                 render_function=render_meeting)
            return await interaction.response.send_modal(modal)
        await interaction.response.defer()

    @discord.ui.button(label='Удалить', custom_id=f'cancel_meeting', style=ButtonStyle.red)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        meeting = await get_full_meeting(self.bot.db_engine, interaction.message.id)
        meeting: Meeting
        access = False
        for member in meeting.meeting_members:
            if member.status == MemberStatus.LEADER and member.discord_id == interaction.user.id:
                access = True
                break
        if access:
            modal = CancelMeetingModal(bot=self.bot, meeting=meeting, delete_func=delete_meeting)
            return await interaction.response.send_modal(modal)
        await interaction.response.defer()


async def render_meeting(bot, meeting: Meeting):
    discord_channel = await bot.get_guild(main_guild_id).fetch_channel(
        meeting.meeting_channel.channel_id
        if not meeting.planned
        else meeting.meeting_channel.planned_channel_id)
    meeting_message = await discord_channel.fetch_message(meeting.meeting_id)
    embed = create_embed(meeting)
    await meeting_message.edit(content=f'{meeting.meeting_channel.custom_meeting_text}',
                               embed=embed,
                               view=MeetingView(bot))


async def delete_meeting(bot, meeting: Meeting):
    if meeting.planned:
        channel = await bot.get_guild(main_guild_id).fetch_channel(meeting.meeting_channel.planned_channel_id)
    else:
        channel = await bot.get_guild(main_guild_id).fetch_channel(meeting.meeting_channel.channel_id)
    message = await channel.fetch_message(meeting.meeting_id)
    await message.delete()
