import datetime
from typing import List

from bungio.models import DestinyUser, GroupType, DestinyClan, GroupMember, DestinyHistoricalStatsAccountResult, \
    DestinyRecordComponent, DestinyMetricComponent, DestinyComponentType, DestinyProfileResponse, DestinyStatsGroupType, \
    SingleComponentResponseOfDestinyMetricsComponent, SingleComponentResponseOfDestinyProfileRecordsComponent, GroupV2, \
    GroupUserInfoCard, GroupMembership
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.Token import Token
from ORM.schemes.User import User
from utils.ResourseConverters import get_raid_report_link, get_dungeon_report_link, get_crusible_report_link, \
    get_trials_report_link, get_nightfall_report_link, get_destiny_tracker_link, get_triump_report_link
from utils.bungio_client import CustomClient
from utils.db_utils import get_full_clans_ids


async def get_group_list_by_bungie_id(membership_id, membership_type=254, auth=None) -> List[GroupMembership]:
    user_group_list = []
    user = DestinyUser(membership_id=membership_id, membership_type=membership_type)
    memberships = (await user.get_membership_data_by_id()).destiny_memberships
    for membership in memberships:
        groups = await membership.get_groups_for_member(filter=0, group_type=1, auth=auth)
        for group in groups.results:
            if group.group.group_type == GroupType.CLAN:
                user_group_list.append(group)
    return user_group_list


async def get_clan_list_by_bungie_id(membership_id, membership_type=254, auth=None) -> List[GroupV2]:
    user_group_list = []
    user = DestinyUser(membership_id=membership_id, membership_type=membership_type)
    memberships = (await user.get_membership_data_by_id()).destiny_memberships
    for membership in memberships:
        groups = await membership.get_groups_for_member(filter=0, group_type=1, auth=auth)
        for group in groups.results:
            if group.group.group_type == GroupType.CLAN:
                user_group_list.append(group.group)
    return user_group_list


async def get_admins_and_founder_for_clan(clan_id) -> List[GroupMember]:
    clan = DestinyClan(group_id=clan_id)
    result = []
    clan_admins = await clan.get_admins_and_founder_of_group(currentpage=0)
    result += clan_admins.results
    if clan_admins.has_more:
        result += await clan.get_admins_and_founder_of_group(currentpage=1)
    return result


async def check_user_in_local_clans(db_engine, membership_id, membership_type=254) -> bool:
    member_clans_list = await get_clan_list_by_bungie_id(membership_id, membership_type)
    local_clan_ids_list = await get_full_clans_ids(db_engine)
    return bool(set([clan.group_id for clan in member_clans_list]) & set(local_clan_ids_list))


async def get_main_bungie_id_by_discord_id(db_engine, discord_id):
    async with AsyncSession(db_engine) as session:
        query = select(User.bungie_id).where(User.discord_id == discord_id)
        bungie_id = (await session.execute(query)).scalar()
    if not bungie_id:
        return None
    return bungie_id


async def get_all_tokens_bungie_id_by_discord_id(db_engine, discord_id):
    async with AsyncSession(db_engine) as session:
        query = select(Token.bungie_id).where(Token.discord_id == discord_id)
        bungie_id_list = list(await session.scalars(query))
    return bungie_id_list


async def get_bungie_name_by_bungie_id(membership_id, membership_type):
    bungie_name = (await DestinyUser(membership_id=membership_id,
                                     membership_type=membership_type).get_linked_profiles(
        get_all_memberships=False)).bnet_membership
    return bungie_name.full_bungie_name if bungie_name.bungie_global_display_name else None


async def get_bungie_name_by_discord_id(db_engine, discord_id):
    bungie_id = await get_main_bungie_id_by_discord_id(db_engine, discord_id)
    if not bungie_id:
        return None
    bungie_name = await get_bungie_name_by_bungie_id(bungie_id, 254)
    return bungie_name


async def get_main_destiny_profile(bungie_id, membership_type=254):
    member_main_profile = None
    member_profiles = await \
        DestinyUser(membership_id=bungie_id, membership_type=membership_type).get_membership_data_by_id()
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
    return member_main_profile


async def get_user_stats(bungie_id, client: CustomClient) -> (SingleComponentResponseOfDestinyMetricsComponent,
                                                              SingleComponentResponseOfDestinyProfileRecordsComponent,
                                                              DestinyHistoricalStatsAccountResult):
    main_profile = await get_main_destiny_profile(bungie_id)
    metrics_and_records: DestinyProfileResponse = await main_profile.get_profile(components=
                                                                                 [DestinyComponentType.METRICS,
                                                                                  DestinyComponentType.RECORDS])
    historical_stats = await client.api.get_historical_stats(character_id=0,
                                                             destiny_membership_id=main_profile.membership_id,
                                                             membership_type=main_profile.membership_type,
                                                             groups=[DestinyStatsGroupType.NONE,
                                                                     DestinyStatsGroupType.GENERAL,
                                                                     DestinyStatsGroupType.WEAPONS,
                                                                     DestinyStatsGroupType.MEDALS,
                                                                     DestinyStatsGroupType.RESERVED_GROUPS,
                                                                     DestinyStatsGroupType.LEADERBOARD,
                                                                     DestinyStatsGroupType.ACTIVITY,
                                                                     DestinyStatsGroupType.UNIQUE_WEAPON,
                                                                     DestinyStatsGroupType.INTERNAL],
                                                             )
    # historical_stats = await main_profile.get_historical_stats_for_account(
    #     groups=[DestinyStatsGroupType.NONE,
    #             DestinyStatsGroupType.GENERAL,
    #             DestinyStatsGroupType.WEAPONS,
    #             DestinyStatsGroupType.MEDALS,
    #             DestinyStatsGroupType.RESERVED_GROUPS,
    #             DestinyStatsGroupType.LEADERBOARD,
    #             DestinyStatsGroupType.ACTIVITY,
    #             DestinyStatsGroupType.UNIQUE_WEAPON,
    #             DestinyStatsGroupType.INTERNAL])
    metrics = metrics_and_records.metrics
    records = metrics_and_records.profile_records
    return metrics, records, historical_stats


async def search_all_bungie_ids_by_discord(db_engine, discord_id):
    user_bungie_ids = []
    async with AsyncSession(db_engine) as session:
        q1 = await session.scalar(select(User.bungie_id).where(User.discord_id == discord_id))
        if q1:
            user_bungie_ids.append(q1)
        q2 = await session.scalars(select(Token.bungie_id).where(Token.discord_id == discord_id))
        if q2:
            user_bungie_ids += list(q2)
    return list(set(user_bungie_ids))


async def get_info_for_bungie_id(bungie_id):
    result = []
    hyperlinks = [f'[Bungie.net](https://www.bungie.net/ru/Profile/254/{bungie_id})']
    main_profile = await get_main_destiny_profile(bungie_id=bungie_id)
    clans = await get_group_list_by_bungie_id(membership_id=bungie_id)
    for clan in clans:
        join_clan_date = clan.member.join_date.strftime('%H:%M %d.%m.%Y')
        last_online = clan.member.last_online_status_change
        if int(last_online) == 0:
            last_online = int(clan.member.join_date.timestamp())

        last_online = datetime.datetime.fromtimestamp(last_online).strftime('%H:%M %d.%m.%Y')

        result.append(f'**{clan.group.name}**\n'
                      f'Дата вступления в клан: {join_clan_date}\n'
                      f'Последний онлайн: {last_online}\n')
    if not main_profile:
        return result + hyperlinks
    main_profile: GroupUserInfoCard
    membership_id = main_profile.membership_id
    membership_type = main_profile.membership_type.value
    link = get_raid_report_link(membership_type=membership_type,
                                membership_id=membership_id)
    hyperlinks.append(f'[RaidReport]({link})')

    link = get_dungeon_report_link(membership_type=membership_type,
                                   membership_id=membership_id)
    hyperlinks.append(f'[DungeonReport]({link})')

    link = get_crusible_report_link(membership_type=membership_type,
                                    membership_id=membership_id)
    hyperlinks.append(f'[CrusibleReport]({link})')

    link = get_trials_report_link(membership_type=membership_type,
                                  membership_id=membership_id)
    hyperlinks.append(f'[TrialsReport]({link})')

    link = get_nightfall_report_link(membership_type=membership_type,
                                     membership_id=membership_id)
    hyperlinks.append(f'[NightfallReport]({link})')

    link = get_triump_report_link(membership_type=membership_type,
                                  membership_id=membership_id)
    hyperlinks.append(f'[TriumphReport]({link})')

    link = get_destiny_tracker_link(membership_type=membership_type,
                                    membership_id=membership_id)
    hyperlinks.append(f'[DestinyTracker]({link})')
    return result + hyperlinks
