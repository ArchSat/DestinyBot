import asyncio
import datetime
import logging
import os
from typing import List, Dict, Any

import discord
import pygsheets
from bungio.models import DestinyClan, GroupMember, RuntimeGroupMemberType
from discord import NotFound
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.Clan import Clan
from ORM.schemes.Token import Token
from ORM.schemes.User import User
from utils.db_utils import get_visible_clans_ids
from utils.logger import create_logger

logger = create_logger(__name__)


async def get_clan_members(clan_id) -> List[GroupMember]:
    clan_members = []
    has_more = True
    page = 0
    while has_more:
        members = await DestinyClan(group_id=clan_id).get_members_of_group(currentpage=page,
                                                                           member_type=None,
                                                                           name_search=None)
        has_more = members.has_more
        page += 1
        clan_members += members.results
    return clan_members


async def get_all_members_of_all_clans(db_engine) -> dict[int:List[GroupMember]]:
    clan_ids = await get_visible_clans_ids(db_engine)
    members_tasks = [get_clan_members(clan_id) for clan_id in clan_ids]
    logger.debug('Начало сбора статистики участников кланов')
    members_result = await asyncio.gather(*members_tasks)
    logger.debug('Статистика участников кланов собрана')
    result = {}
    for i, members in enumerate(members_result):
        result[clan_ids[i]] = members_result[i]
    return result


async def get_registered_members_discord_ids(db_engine, members_list: List[GroupMember]) -> List[int]:
    async with AsyncSession(db_engine) as session:
        not_null_bungie_ids = [member.bungie_net_user_info.membership_id
                               for member in members_list
                               if member.bungie_net_user_info]
        query = select(User.discord_id).where(User.bungie_id.in_(not_null_bungie_ids))
        members_ids = list(await session.scalars(query))
    return members_ids


async def get_tokens_for_clan_members(db_engine, members_list: List[GroupMember]) -> Dict[int, Token]:
    async with AsyncSession(db_engine) as session:
        not_null_bungie_ids = [member.bungie_net_user_info.membership_id
                               for member in members_list
                               if member.bungie_net_user_info]
        query = select(Token).where(Token.bungie_id.in_(not_null_bungie_ids))
        tokens = list(await session.scalars(query))
    members = {token.discord_id: token for token in tokens}
    return members


async def get_discord_members(guild, members_ids) -> List[discord.Member]:
    members = []
    if not guild:
        return members
    for discord_id in members_ids:
        try:
            members.append(guild.get_member(discord_id))
        except NotFound:
            pass
    return members


class ClanTableStats:
    def __init__(self, members_list: List[GroupMember], timestamp: datetime.datetime):
        self.total_members: int = len(members_list)
        self.inactive_10d: int = 0
        self.inactive_14d: int = 0
        self.inactive_21d: int = 0
        self.inactive_31d: int = 0
        self.leader_bungie_id: GroupMember | None = None
        self.admins: List[GroupMember] = []
        timestamp = int(timestamp.timestamp())
        for member in members_list:

            if abs(timestamp - int(member.last_online_status_change)) > 864000:
                self.inactive_10d += 1
            if abs(timestamp - int(member.last_online_status_change)) > 1209600:
                self.inactive_14d += 1
            if abs(timestamp - int(member.last_online_status_change)) > 1814400:
                self.inactive_21d += 1
            if abs(timestamp - int(member.last_online_status_change)) > 2678400:
                self.inactive_31d += 1

            if member.member_type == RuntimeGroupMemberType.ADMIN:
                self.admins.append(member)

            if member.member_type == RuntimeGroupMemberType.FOUNDER:
                self.leader_bungie_id = member

    def __repr__(self):
        return f"Leader: {self.leader_bungie_id}, Admins: {self.admins}, total: {self.total_members}, " \
               f"10-14-21-31: {self.inactive_10d}-{self.inactive_14d}-{self.inactive_21d}-{self.inactive_31d}"


class ClanTableSalaryStats(ClanTableStats):
    def __init__(self, members_list: List[GroupMember],
                 timestamp: datetime.datetime,
                 total_discord_members: List[discord.Member],
                 admins_tokens: Dict[int, Token]):
        super().__init__(members_list, timestamp)
        self.total_discord_members = total_discord_members
        self.admins_tokens = admins_tokens


async def get_names_of_all_clans(db_engine):
    clan_ids = await get_visible_clans_ids(db_engine)
    clan_names = [DestinyClan(group_id=clan_id).get_group() for clan_id in clan_ids]
    logger.debug('Начало сбора названий кланов')
    names_result = await asyncio.gather(*clan_names)
    logger.debug('Названия кланов собраны')
    result = {}
    for i, members in enumerate(names_result):
        result[clan_ids[i]] = names_result[i]
    return result


async def update_stats_in_db(db_engine, all_groups_table_stats, all_groups_discord_stats):
    timestamp = datetime.datetime.now()
    async with AsyncSession(db_engine) as session:
        for clan in all_groups_discord_stats:
            if all_groups_table_stats[clan].leader_bungie_id:
                leader_bungie_id = all_groups_table_stats[clan].leader_bungie_id.bungie_net_user_info.membership_id
            else:
                leader_bungie_id = None

            admins = []
            for admin in all_groups_table_stats[clan].admins:
                if admin.bungie_net_user_info:
                    admins.append(str(admin.bungie_net_user_info.membership_id))

            clan_obj = Clan(
                clan_id=clan,
                total_members=all_groups_table_stats[clan].total_members,
                discord_members=len(all_groups_discord_stats[clan]),
                inactive_10d=all_groups_table_stats[clan].inactive_10d,
                inactive_14d=all_groups_table_stats[clan].inactive_14d,
                inactive_21d=all_groups_table_stats[clan].inactive_21d,
                inactive_31d=all_groups_table_stats[clan].inactive_31d,
                leader_bungie_id=leader_bungie_id,
                last_update=timestamp,
                admins=', '.join(admins) if admins else None
            )
            await session.merge(clan_obj)
        await session.commit()


async def create_stats_table(db_engine, guild):
    logger.info('Начало обновления статистики')
    timestamp = datetime.datetime.now()
    result = []
    all_members_in_clans = await get_all_members_of_all_clans(db_engine)
    all_groups_names = await get_names_of_all_clans(db_engine)

    assert len(all_members_in_clans) == len(all_groups_names)

    all_groups_table_stats = {}
    all_groups_discord_stats = {}

    for clan in all_members_in_clans:
        registered_users = await get_registered_members_discord_ids(db_engine, all_members_in_clans[clan])

        discord_guild_members = await get_discord_members(guild, registered_users)
        all_groups_discord_stats[clan] = discord_guild_members

        clan_table_stats = ClanTableStats(all_members_in_clans[clan], timestamp)
        all_groups_table_stats[clan] = clan_table_stats
        result.append([
            f'=ГИПЕРССЫЛКА("https://www.bungie.net/ru/ClanV2?groupId={clan}", "{all_groups_names[clan].detail.name}")',
            f"'{clan_table_stats.leader_bungie_id.bungie_net_user_info.full_bungie_name if clan_table_stats.leader_bungie_id.bungie_net_user_info else None}",
            "'" + ', '.join([admin.bungie_net_user_info.full_bungie_name
                             for admin in clan_table_stats.admins if admin.bungie_net_user_info]),
            f'{clan_table_stats.total_members}',
            f'{len(discord_guild_members)}',
            f'{clan_table_stats.inactive_10d}',
            f'{clan_table_stats.inactive_14d}',
            f'{clan_table_stats.inactive_21d}',
            f'{clan_table_stats.inactive_31d}',
        ])
    await update_stats_in_db(db_engine, all_groups_table_stats, all_groups_discord_stats)
    logger.info('Информация в БД обновлена')
    return result


async def update_stats_in_google_sheets(new_table):
    try:
        gc = pygsheets.authorize(service_account_env_var='google_credentials')
    except KeyError:
        gc = pygsheets.authorize(service_account_file='config/google_credentials.json')

    sh = gc.open_by_key(os.getenv('GOOGLE_SHEET_ID'))
    wks = sh.worksheet('index', 0)
    if wks.rows != 2:
        wks.delete_rows(3, wks.rows - 1)
    first_row = [['Название клана', 'Основатель', 'Администраторы', 'Всего участников', 'Discord',
                  'Инактив 10 дней+',
                  'Инактив 14 дней+',
                  'Инактив 21 день+',
                  'Инактив 31 день+']]
    wks.update_values('A1', first_row)
    wks.add_rows(len(new_table) - 1)
    wks.update_values('A2', new_table)
    wks.add_rows(2)
    current_date = str(datetime.datetime.now().strftime('%H:%M %d.%m.%Y'))

    wks.update_values(f'A{wks.rows}', [['Итог',
                                        'на',
                                        current_date,
                                        f'=sum(D2:D{wks.rows - 1})',
                                        f'=sum(E2:E{wks.rows - 1})',
                                        f'=sum(F2:F{wks.rows - 1})',
                                        f'=sum(G2:G{wks.rows - 1})',
                                        f'=sum(H2:H{wks.rows - 1})',
                                        f'=sum(I2:I{wks.rows - 1})']])
    pygsheets.datarange.DataRange(start='A1', end=f'I{wks.rows}', worksheet=wks).update_borders(top=True,
                                                                                                right=True,
                                                                                                bottom=True,
                                                                                                left=True,
                                                                                                inner_horizontal=True,
                                                                                                inner_vertical=True,
                                                                                                style='SOLID')
    return sh
