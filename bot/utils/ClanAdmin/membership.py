from typing import List

import discord
from bungio.error import BungieException
from bungio.models import GroupMember, DestinyUser

from utils.ClanAdmin.share import search_destiny_players_by_full_tag
from utils.clan_stats_utils import get_clan_members


async def search_user_by_bungie_id_in_clan(bungie_id, clan_id):
    memberships = await DestinyUser(membership_id=bungie_id, membership_type=254). \
        get_membership_data_by_id()
    memberships = memberships.destiny_memberships
    clan_members = await get_clan_members(clan_id=clan_id)
    user_memberships = [membership.membership_id for membership in memberships]
    result = []
    for member in clan_members:
        if member.destiny_user_info.membership_id in user_memberships:
            result.append(member)
    return result


async def search_user_by_bungie_tag_in_clan(bungie_tag, clan_id, client):
    memberships = await search_destiny_players_by_full_tag(client=client, bungie_tag=bungie_tag)
    clan_members = await get_clan_members(clan_id=clan_id)
    user_memberships = [membership.membership_id for membership in memberships]
    result = []
    for member in clan_members:
        if member.destiny_user_info.membership_id in user_memberships:
            result.append(member)
    return result


async def change_members_type(members_list, new_member_type, clan_id, auth):
    result_list = []
    for member in members_list:
        member: GroupMember
        try:
            result = await member.destiny_user_info.edit_group_membership(member_type=new_member_type,
                                                                          group_id=clan_id,
                                                                          auth=auth)
        except BungieException as e:
            result = e
        result_list.append(result)
    return result_list


def render_result(result_list, member: str):
    result_list: List[BungieException | int]
    if len(result_list) == 0:
        embed = discord.Embed(title=f'Результат изменения статуса {member}', colour=discord.Colour.red())
        embed.description = 'Участник не найден в клане!'
        return embed
    embed = discord.Embed(title=f'Результаты изменения статуса {member}', colour=discord.Colour.green())
    desc_text = ""
    for res in result_list:
        if isinstance(res, int):
            name_field = "Тип участника успешно изменен!"
            value_field = f"{res}"
        else:
            name_field = "Ошибка приглашения участника!"
            value_field = f'Ошибка {res.code}: {res.error}\n' \
                          f'Описание: {res.message}\n'
        desc_text += f"**{name_field}**\n{value_field}\n"
    embed.description = desc_text
    return embed
