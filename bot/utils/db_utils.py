import datetime
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.Clan import Clan


def parse_time(date_string: str) -> datetime.timedelta:
    seconds = 0
    for interval in re.findall(r'[\d*]*[\D*]*', date_string):
        if not interval:
            continue
        if 'mo' in interval:
            seconds += int(re.findall(r'[\d]*', interval)[0]) * 30 * 24 * 60 * 60
            continue
        elif 'w' in interval:
            seconds += int(re.findall(r'[\d]*', interval)[0]) * 7 * 24 * 60 * 60
            continue
        elif 'd' in interval:
            seconds += int(re.findall(r'[\d]*', interval)[0]) * 24 * 60 * 60
            continue
        elif 'h' in interval:
            seconds += int(re.findall(r'[\d]*', interval)[0]) * 60 * 60
            continue
        elif 'm' in interval:
            seconds += int(re.findall(r'[\d]*', interval)[0]) * 60
            continue
        elif 's' in interval:
            seconds += int(re.findall(r'[\d]*', interval)[0])
            continue
        else:
            # По умолчанию - без указания единиц измерения - в днях
            seconds += int(interval) * 24 * 60 * 60
    return datetime.timedelta(seconds=seconds)


async def get_visible_clans_ids(db_engine):
    async with AsyncSession(db_engine) as session:
        clan_ids = list(await session.scalars(select(Clan.clan_id).where(Clan.visible).order_by(Clan.clan_tag.asc())))
    return clan_ids


async def get_visible_clans(db_engine):
    async with AsyncSession(db_engine) as session:
        clans = list(await session.scalars(select(Clan).where(Clan.visible).order_by(Clan.clan_tag.asc())))
    return clans


async def get_full_clans_ids(db_engine):
    query = select(Clan.clan_id).order_by(Clan.visible.desc(), Clan.clan_tag.asc())
    async with AsyncSession(db_engine) as session:
        clan_list = list(await session.scalars(query))
    return clan_list


async def get_full_clans(db_engine):
    query = select(Clan).order_by(Clan.visible.desc(), Clan.clan_tag.asc())
    async with AsyncSession(db_engine) as session:
        clan_list = list(await session.scalars(query))
    return clan_list
