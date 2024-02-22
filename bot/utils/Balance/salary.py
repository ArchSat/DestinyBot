import datetime
import logging
from typing import Dict

import discord
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.User import User, TransactionStatus, BalanceTransaction
from utils.Balance.balance import transform_float_to_decimal
from utils.clan_stats_utils import get_all_members_of_all_clans, get_registered_members_discord_ids, \
    get_discord_members, get_tokens_for_clan_members, ClanTableSalaryStats
from utils.logger import create_logger

logger = create_logger(__name__)


async def get_stats_for_salary(db_engine, guild: discord.Guild) -> Dict[int, ClanTableSalaryStats]:
    logger.info('Начало обновления статистики')
    timestamp = datetime.datetime.now()
    all_members_in_clans = await get_all_members_of_all_clans(db_engine)
    all_stats = {}
    for clan in all_members_in_clans:
        registered_admins = await get_tokens_for_clan_members(db_engine, all_members_in_clans[clan])
        all_registered_users = await get_registered_members_discord_ids(db_engine, all_members_in_clans[clan])
        discord_guild_members = await get_discord_members(guild, all_registered_users)
        clan_table_stats = ClanTableSalaryStats(members_list=all_members_in_clans[clan],
                                                timestamp=timestamp,
                                                total_discord_members=discord_guild_members,
                                                admins_tokens=registered_admins)
        all_stats[clan] = clan_table_stats
    return all_stats


def get_clear_salary_dict():
    new_balance = {
        'base': 0,
        'members': 0,
        'discord': 0,
        'inactive21': 0,
        'inactive31': 0,
        'summary': 0,
        'premium': 0
    }
    return new_balance


def calculate_salary(clan: ClanTableSalaryStats, bungie_id: int, salary_dict):
    new_balance = get_clear_salary_dict()
    if clan.total_members < 85:
        new_balance['members'] = -((85 - clan.total_members) * abs(salary_dict['less_than_85_members_each']))
    if bungie_id in [getattr(getattr(admin, 'bungie_net_user_info', None), 'membership_id', None)
                     for admin in clan.admins]:
        new_balance['base'] = salary_dict['base_admin']
    elif bungie_id == getattr(getattr(clan.leader_bungie_id, 'bungie_net_user_info', None), 'membership_id', None):
        new_balance['base'] = salary_dict['base_leader']
    else:
        new_balance['base'] = 0
    if len(clan.total_discord_members) > 50:
        new_balance['discord'] = (len(clan.total_discord_members) - 50) / 10 * salary_dict['each_10_over_50_discord']
    if clan.inactive_21d > 0:
        new_balance['inactive21'] = -abs((clan.inactive_21d - clan.inactive_31d) *
                                         salary_dict['each_inactive_more_than_21_day'])
    if clan.inactive_31d > 0:
        new_balance['inactive21'] = -abs(clan.inactive_31d * salary_dict['each_inactive_more_than_31_day'])
    new_balance['summary'] = max(0, sum(value for value in new_balance.values()))
    return new_balance


async def create_salary_list(db_engine, guild: discord.Guild, salary_dict: Dict):
    clan_stats = await get_stats_for_salary(db_engine=db_engine,
                                            guild=guild)
    # Словарь хранит Discord_ID + Salary_Dict

    result_salary: Dict[int, Dict] = {}
    missing_registration = []
    for clan_id in clan_stats:
        for admin in clan_stats[clan_id].admins + [clan_stats[clan_id].leader_bungie_id]:
            if admin.bungie_net_user_info:
                bungie_id = admin.bungie_net_user_info.membership_id
            else:
                missing_registration.append(admin.destiny_user_info.membership_id)
                continue
            discord_token_id = None
            for discord_id in clan_stats[clan_id].admins_tokens:
                if clan_stats[clan_id].admins_tokens[discord_id].bungie_id == bungie_id:
                    discord_token_id = clan_stats[clan_id].admins_tokens[discord_id].discord_id
                if not discord_token_id:
                    continue
            if not discord_token_id:
                missing_registration.append(bungie_id)
                continue

            result_salary_value = calculate_salary(clan=clan_stats[clan_id],
                                                   bungie_id=bungie_id,
                                                   salary_dict=salary_dict)
            current_salary_value = result_salary.get(discord_token_id, get_clear_salary_dict())
            if current_salary_value['summary'] >= result_salary_value['summary']:
                current_salary_value['premium'] += result_salary_value['summary'] * salary_dict['twin_clan_premium']
                current_salary_value['summary'] += result_salary_value['summary'] * salary_dict['twin_clan_premium']
                new_salary = current_salary_value
            else:
                result_salary_value['premium'] += current_salary_value['summary'] * salary_dict['twin_clan_premium']
                result_salary_value['summary'] += current_salary_value['summary'] * salary_dict['twin_clan_premium']
                new_salary = result_salary_value
            result_salary[discord_token_id] = new_salary
    return result_salary


async def pay_salary_in_database(db_engine, salary_dict) -> Dict[int, BalanceTransaction]:
    result_salary = {}
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        description = f"Выплата зарплаты от {datetime.datetime.now()}"
        for discord_id in salary_dict:
            print(f'К выплате: {discord_id} - {salary_dict[discord_id]}')
            amount = transform_float_to_decimal(salary_dict[discord_id]['summary'])
            if amount == transform_float_to_decimal(0.00):
                continue
            user = await session.get(User, discord_id)
            if not user:
                user = User(discord_id=discord_id)
                session.add(user)
                await session.flush()
                await session.refresh(user)
            user.balance += amount
            transaction = BalanceTransaction(discord_id=discord_id,
                                             amount=amount,
                                             description=description,
                                             status=TransactionStatus.SUCCESS)
            session.add(transaction)
            await session.flush([transaction])
            result_salary[discord_id] = transaction
        await session.commit()
        session.expunge_all()
        return result_salary
