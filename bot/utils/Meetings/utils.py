import datetime
import logging
import time

import discord
from bungio.error import BungIOException
from bungio.models import DestinyUser, DestinyComponentType, DestinyMetricComponent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ORM.schemes.Meeting import MeetingMember, MeetingChannel, MemberStatus, Meeting, MeetingStatus
from utils.logger import create_logger
from utils.users_utils import get_main_bungie_id_by_discord_id, get_bungie_name_by_bungie_id, get_main_destiny_profile

logger = create_logger(__name__)


def parse_date(date: str):
    date = datetime.datetime.strptime(date, "%d.%m-%H:%M").replace(year=datetime.datetime.now().year)
    # date = pytz.timezone('Europe/Moscow').localize(date)
    if date <= datetime.datetime.now():
        date = date.replace(year=(datetime.datetime.now().year + 1))
    return date


async def check_many_meetings_of_member(db_engine, discord_id: int, timestamp: datetime.datetime):
    async with AsyncSession(db_engine) as session:
        query = select(MeetingMember).join(Meeting) \
            .where((MeetingMember.status.in_([MemberStatus.MEMBER, MemberStatus.LEADER])) &
                   (MeetingMember.discord_id == discord_id) &
                   (Meeting.start_at.between(timestamp - datetime.timedelta(hours=2),
                                             timestamp + datetime.timedelta(hours=2))) &
                   (Meeting.status.in_([MeetingStatus.ACTIVE, MeetingStatus.COMPLETED])))
        result = (await session.execute(query)).scalars()
    return list(result.unique())


async def create_meeting_member(db_engine, meeting: Meeting, discord_member: discord.Member) -> MeetingMember:
    for meeting_member in meeting.meeting_members:
        meeting_member: MeetingMember
        if meeting_member.discord_id == discord_member.id:
            return meeting_member

    async with AsyncSession(db_engine) as session:
        query = select(MeetingChannel.metric_hash).where(meeting.category_id == MeetingChannel.channel_id)
        metric_hashes = (await session.execute(query)).scalar()

    bungie_id = await get_main_bungie_id_by_discord_id(db_engine, discord_member.id)
    bungie_name, metric_value, main_membership_id, main_membership_type = None, None, None, None
    if bungie_id:
        try:
            bungie_name = await get_bungie_name_by_bungie_id(membership_id=bungie_id, membership_type=254)
            member_main_profile = None
            member_profiles = await \
                DestinyUser(membership_id=bungie_id, membership_type=254).get_membership_data_by_id()
            if member_profiles.primary_membership_id:
                for profile in member_profiles.destiny_memberships:
                    if member_profiles.primary_membership_id == profile.membership_id:
                        member_main_profile = profile
            elif len(member_profiles.destiny_memberships) == 1:
                member_main_profile = member_profiles.destiny_memberships[0]
            elif len(member_profiles.destiny_memberships) > 1:
                for profile in member_profiles.destiny_memberships:
                    if profile.membership_type == 3:
                        member_main_profile = profile
            if member_main_profile:
                main_membership_id, main_membership_type = \
                    member_main_profile.membership_id, member_main_profile.membership_type.value
            if metric_hashes and member_main_profile:
                member_metrics = await member_main_profile.get_profile(components=[DestinyComponentType.METRICS])
                if member_metrics:
                    for metric_hash in metric_hashes:
                        metric: DestinyMetricComponent | None = member_metrics.metrics.data.metrics.get(metric_hash, None)
                        if metric:
                            if metric_value is None:
                                metric_value = 0
                            metric_value += metric.objective_progress.progress
                        else:
                            continue
        except BungIOException as e:
            logger.exception(e)
    meeting_member = MeetingMember(
        meeting_id=meeting.meeting_id,
        discord_id=discord_member.id,
        bungie_name=bungie_name,
        other_data={'metric_value': metric_value,
                    'membership_id': main_membership_id,
                    'membership_type': main_membership_type}
    )
    return meeting_member


async def get_full_meeting(db_engine, meeting_id):
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        meeting = await session.scalar(
            select(Meeting).options(joinedload(Meeting.meeting_members), joinedload(Meeting.meeting_channel)).
            where(Meeting.meeting_id == meeting_id))
        session.expunge(meeting)
    return meeting


async def find_member_in_meeting(meeting: Meeting, discord_member_id: int) -> MeetingMember | None:
    existed_user = None
    for meeting_member in meeting.meeting_members:
        meeting_member: MeetingMember
        if meeting_member.discord_id == discord_member_id:
            existed_user = meeting_member
    return existed_user


async def create_meeting_member_fast(meeting: Meeting, discord_member: discord.Member) -> MeetingMember:
    for meeting_member in meeting.meeting_members:
        meeting_member: MeetingMember
        if meeting_member.discord_id == discord_member.id:
            return meeting_member
    meeting_member = MeetingMember(
        meeting_id=meeting.meeting_id,
        discord_id=discord_member.id,
        other_data={'metric_value': None,
                    'membership_id': None,
                    'membership_type': None})
    return meeting_member


async def update_meeting_member(db_engine,
                                meeting: Meeting,
                                discord_member: discord.Member,
                                render_meeting_func) -> None | MeetingMember:
    bungie_id = await get_main_bungie_id_by_discord_id(db_engine, discord_member.id)
    bungie_name, metric_value, main_membership_id, main_membership_type, metric_value = None, None, None, None, None
    meeting_member = None
    for member in meeting.meeting_members:
        if member.discord_id == discord_member.id:
            meeting_member = member
    if not meeting_member:
        meeting_member = MeetingMember(
            meeting_id=meeting.meeting_id,
            discord_id=discord_member.id
        )
    if bungie_id:
        try:
            bungie_name = await get_bungie_name_by_bungie_id(membership_id=bungie_id, membership_type=254)
            member_main_profile = None
            member_profiles = await \
                DestinyUser(membership_id=bungie_id, membership_type=254).get_membership_data_by_id()
            if member_profiles.primary_membership_id:
                for profile in member_profiles.destiny_memberships:
                    if member_profiles.primary_membership_id == profile.membership_id:
                        member_main_profile = profile
            elif len(member_profiles.destiny_memberships) == 1:
                member_main_profile = member_profiles.destiny_memberships[0]
            elif len(member_profiles.destiny_memberships) > 1:
                for profile in member_profiles.destiny_memberships:
                    if profile.membership_type == 3:
                        member_main_profile = profile
            if member_main_profile:
                main_membership_id, main_membership_type = \
                    member_main_profile.membership_id, member_main_profile.membership_type.value
            if meeting.meeting_channel.metric_hash and member_main_profile:
                member_metrics = await member_main_profile.get_profile(components=[DestinyComponentType.METRICS])
                for metric_hash in meeting.meeting_channel.metric_hash:
                    metric: DestinyMetricComponent | None = member_metrics.metrics.data.metrics.get(metric_hash, None)
                    if metric:
                        if metric_value is None:
                            metric_value = 0
                        metric_value += metric.objective_progress.progress
                    else:
                        continue
        except BungIOException as e:
            logger.exception(e)
        meeting_member.last_update = datetime.datetime.now()
        meeting_member.bungie_name = bungie_name
        meeting_member.other_data = {'metric_value': metric_value,
                                     'membership_id': main_membership_id,
                                     'membership_type': main_membership_type}
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            await session.merge(meeting_member)
            await session.commit()
        await render_meeting_func(meeting)
    return meeting_member
