import datetime
import re
from typing import List, Union

import bungio.utils
import discord
from bungio.error import BungieException
from bungio.models import DestinyClan, GroupMemberApplication, GroupApplicationResponse, GroupResponse, AuthData, \
    GroupMember, GroupMemberLeaveResult
from itertools import islice

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.Token import Token
from ORM.schemes.User import User
from utils.clan_stats_utils import get_clan_members

ON_PAGE = 10


def chunks_dict(data, chunk_size):
    it = iter(data)
    for i in range(0, len(data), chunk_size):
        yield {k: data[k] for k in islice(it, chunk_size)}


async def clear_invites(clan_id, auth_data):
    group = DestinyClan(group_id=clan_id)
    invites = []
    search_result_of_group_member_application = await group.get_invited_individuals(currentpage=0, auth=auth_data)
    invites += search_result_of_group_member_application.results
    if search_result_of_group_member_application.has_more:
        search_result_of_group_member_application = await group.get_invited_individuals(currentpage=1, auth=auth_data)
        invites += search_result_of_group_member_application.results
    result = {}
    for invite in invites:
        invite: GroupMemberApplication
        cancel: GroupApplicationResponse = await invite.destiny_user_info.individual_group_invite_cancel(
            group_id=clan_id, auth=auth_data)
        if invite.bungie_net_user_info:
            result[invite.bungie_net_user_info.membership_id] = (invite, cancel)
        else:
            result[invite.destiny_user_info.membership_id] = (invite, cancel)
    return result


def create_cls_inv_result_pages(result, clan: GroupResponse, on_page=ON_PAGE):
    rendered_pages = []
    pages = list(chunks_dict(result, on_page))
    for page_number, page in enumerate(pages):
        embed = discord.Embed(title='Отмена приглашений\n'
                                    f'{clan.detail.name}', colour=discord.Color.green())
        embed.set_footer(text=f'Итого: {len(result)} • Страница {page_number + 1}/{len(pages)}')
        for res in page:
            user_info: GroupMemberApplication = page[res][0]
            kick_result: GroupApplicationResponse = page[res][1]
            if user_info.bungie_net_user_info:
                field_name = f"{user_info.bungie_net_user_info.full_bungie_name}"
            else:
                field_name = f"{user_info.destiny_user_info.display_name}"
            field_value = f"{kick_result.resolution.name}"
            embed.add_field(name=discord.utils.escape_markdown(field_name), value=field_value, inline=False)
        rendered_pages.append(embed)
    return rendered_pages


async def get_inactives(clan_id, inactive_time: datetime.timedelta) -> List[GroupMember]:
    members: List[GroupMember] = await get_clan_members(clan_id)
    inactive_list = []
    for member in members:
        if member.is_online:
            continue
        if not member.last_online_status_change:
            member.last_online_status_change = int(member.join_date.timestamp())
        if datetime.datetime.fromtimestamp(member.last_online_status_change, tz=datetime.timezone.utc) + inactive_time \
                < bungio.utils.get_now_with_tz():
            inactive_list.append(member)
    return inactive_list


def create_inactives_result_pages(time: datetime.timedelta,
                                  result: List[GroupMember], clan: GroupResponse, on_page=ON_PAGE):
    rendered_pages = []
    for member in result:
        member.join_date = int(member.join_date.timestamp())

    result.sort(key=lambda r: r.last_online_status_change)
    pages = list(bungio.utils.split_list(result, on_page))
    for page_number, page in enumerate(pages):
        embed = discord.Embed(title=f'Инактив более {time}\n'
                                    f'{clan.detail.name}', colour=discord.Color.red())
        embed.set_footer(text=f'Итого: {len(result)} • Страница {page_number + 1}/{len(pages)}')
        for user_info in page:
            user_info: GroupMember
            if user_info.bungie_net_user_info and user_info.bungie_net_user_info.bungie_global_display_name:
                field_name = f"{user_info.bungie_net_user_info.full_bungie_name}"
            else:
                name = user_info.destiny_user_info.bungie_global_display_name
                code = str(user_info.destiny_user_info.bungie_global_display_name_code).zfill(4)
                field_name = f"{name}#{code}"
            last_online = f"<t:{user_info.last_online_status_change}:f>"
            join_date = f"<t:{user_info.join_date}:f>"
            field_value = f"Последний онлайн: {last_online}\n" \
                          f"Дата вступления: {join_date}\n" \
                          f"[Профиль](https://www.bungie.net/ru/Profile/" \
                          f"{user_info.destiny_user_info.membership_type.value}/" \
                          f"{user_info.destiny_user_info.membership_id})"
            embed.add_field(name=discord.utils.escape_markdown(field_name), value=field_value, inline=False)
        rendered_pages.append(embed)
    return rendered_pages


async def clear_inactives(inactive_list: List[GroupMember], auth_data: AuthData):
    result = {}
    for member in inactive_list:
        try:
            kick_member = await member.destiny_user_info.kick_member(group_id=member.group_id, auth=auth_data)
        except BungieException as e:
            kick_member = e
        result[member.destiny_user_info.membership_id] = (member, kick_member)
    return result


def create_cls_inac_result_pages(result, clan: GroupResponse, time: datetime.timedelta, on_page=ON_PAGE):
    rendered_pages = []

    pages = list(chunks_dict(result, on_page))
    for page_number, page in enumerate(pages):
        embed = discord.Embed(title=f'Инактив более {time}\n'
                                    f'{clan.detail.name}', colour=discord.Color.red())
        embed.set_footer(text=f'Итого: {len(result)} • Страница {page_number + 1}/{len(pages)}')
        for r in page:
            user_info: GroupMember = page[r][0]
            kick_result: GroupMemberLeaveResult | BungieException = page[r][1]

            if user_info.bungie_net_user_info and user_info.bungie_net_user_info.bungie_global_display_name:
                field_name = f"{user_info.bungie_net_user_info.full_bungie_name}"
            else:
                name = user_info.destiny_user_info.bungie_global_display_name
                code = str(user_info.destiny_user_info.bungie_global_display_name_code).zfill(4)
                field_name = f"{name}#{code}"
            if isinstance(kick_result, GroupMemberLeaveResult):
                field_value = 'Участник исключен'
            else:
                field_value = f'Ошибка при исключении участника:\n' \
                              f'Ошибка {kick_result.code}: {kick_result.error}\n' \
                              f'Описание: {kick_result.message}\n'

            embed.add_field(name=discord.utils.escape_markdown(field_name), value=field_value, inline=False)
        rendered_pages.append(embed)
    return rendered_pages


class UnitedMember:
    def __init__(self, destiny_member: GroupMember, discord_member: Union[discord.Member, int, None]):
        self.destiny_member = destiny_member
        self.discord_member = discord_member


async def check_discord_members(bungie_id_list: List[int], guild: discord.Guild, db_engine):
    async with AsyncSession(db_engine) as session:
        query = select(User.discord_id, User.bungie_id).where(User.bungie_id.in_(bungie_id_list))
        users = await session.execute(query)
        query = select(Token.discord_id, Token.bungie_id).where(Token.bungie_id.in_(bungie_id_list))
        tokens = await session.execute(query)
        registered = list(users) + list(tokens)
    registered = list(set(registered))
    result = {}
    for reg in registered:
        print(reg)
        try:
            member = await guild.fetch_member(reg[0])
        except discord.errors.NotFound:
            member = reg[0]
        result[reg[1]] = member
    return result


async def get_inactives_discord(clan_members: List[UnitedMember], time: datetime.timedelta) -> List[UnitedMember]:
    cls_result = []
    for member in clan_members:
        if not member.destiny_member.last_online_status_change:
            member.destiny_member.last_online_status_change = int(member.destiny_member.join_date.timestamp())
        if isinstance(member.discord_member, discord.Member) or isinstance(member.discord_member, int):
            continue
        if datetime.datetime.now(tz=None) - member.destiny_member.join_date.replace(tzinfo=None) >= time:
            cls_result.append(member)
    cls_result.sort(key=lambda m: m.destiny_member.join_date)
    return cls_result


def create_discord_pages(time, input_result: List[UnitedMember], clan, on_page=ON_PAGE):
    rendered_pages = []
    for member in input_result:
        member.destiny_member.join_date = int(member.destiny_member.join_date.timestamp())

    def sort_func(m: UnitedMember):
        if m.discord_member is None:
            return 2, m.destiny_member.join_date
        elif isinstance(m.discord_member, int):
            return 1, m.destiny_member.join_date
        else:
            return 0, m.destiny_member.join_date

    input_result.sort(key=sort_func)

    pages = list(bungio.utils.split_list(input_result, on_page))
    for page_number, page in enumerate(pages):
        embed = discord.Embed(title=f'Результат выполнения Discord ({time})\n'
                                    f'{clan.detail.name}', colour=discord.Color.red())
        embed.set_footer(text=f'Итого: {len(input_result)} • Страница {page_number + 1}/{len(pages)}')
        for res in page:
            res: UnitedMember
            result = res.destiny_member
            if result.bungie_net_user_info and result.bungie_net_user_info.bungie_global_display_name:
                field_name = f"{result.bungie_net_user_info.full_bungie_name}"
            else:
                name = result.destiny_user_info.bungie_global_display_name
                code = str(result.destiny_user_info.bungie_global_display_name_code).zfill(4)
                field_name = f"{name}#{code}"
            if res.discord_member is None:
                discord_text = "Участник не зарегистрирован"
            elif isinstance(res.discord_member, int):
                discord_text = f"Покинул сервер (<@{res.discord_member}> - {res.discord_member})\n"
            else:
                discord_text = f"На сервере: {res.discord_member.mention} ({res.discord_member.display_name})"
            last_online = f"<t:{result.last_online_status_change}:f>"
            join_date = f"<t:{result.join_date}:f>"
            field_value = f"Discord: {discord_text}\n" \
                          f"Последний онлайн: {last_online}\n" \
                          f"Дата вступления: {join_date}\n" \
                          f"[Профиль](https://www.bungie.net/ru/Profile/" \
                          f"{result.destiny_user_info.membership_type.value}/" \
                          f"{result.destiny_user_info.membership_id})"

            embed.add_field(name=discord.utils.escape_markdown(field_name), value=field_value, inline=False)
        rendered_pages.append(embed)
    return rendered_pages


async def clear_discord(inactive_list: List[UnitedMember], auth_data: AuthData):
    result = {}
    for member in inactive_list:
        try:
            kick_member = await member.destiny_member.destiny_user_info.kick_member(
                group_id=member.destiny_member.group_id, auth=auth_data)
        except BungieException as e:
            kick_member = e
        result[member.destiny_member.destiny_user_info.membership_id] = (member, kick_member)
    return result
