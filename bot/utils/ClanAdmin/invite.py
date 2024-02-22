from typing import List

import discord
from bungio.error import BungieException
from bungio.models import DestinyUser, GroupApplicationRequest, BungieMembershipType, GroupApplicationResponse, \
    GroupBanRequest


async def invite_to_clan_by_bungie_next_id(auth, clan_id, bungie_id):
    memberships = await DestinyUser(membership_id=bungie_id, membership_type=254). \
        get_membership_data_by_id()
    invite_result_list = []
    for destiny_membership in memberships.destiny_memberships:
        try:
            inv = await destiny_membership.individual_group_invite(auth=auth,
                                                                   group_id=clan_id,
                                                                   data=GroupApplicationRequest(message='Invite'))
            invite_result_list.append(inv)
        except BungieException as e:
            invite_result_list.append(e)
    return invite_result_list


async def invite_to_clan_by_destiny_id(auth, clan_id, membership_id, membership_type):
    assert membership_type != 254
    assert membership_type != BungieMembershipType.BUNGIE_NEXT
    try:
        invite = await DestinyUser(membership_id=membership_id,
                                   membership_type=membership_type). \
            individual_group_invite(auth=auth,
                                    group_id=clan_id,
                                    data=GroupApplicationRequest(message='Invite'))
    except BungieException as e:
        return e
    return invite


def render_invite_result(bungie_tag,
                         invite_results: List[GroupApplicationResponse | BungieException],
                         clan_name: str | None = None):
    title_text = f'Результаты приглашения участника {bungie_tag}'
    if clan_name:
        title_text += f'\nКлан: {clan_name}'
    embed = discord.Embed(title=title_text, colour=discord.Colour.green())
    desc_text = ""
    for group_app_res in invite_results:
        if isinstance(group_app_res, GroupApplicationResponse):
            name_field = "Участник успешно приглашен!"
            value_field = ""
        else:
            name_field = "Ошибка приглашения участника!"
            value_field = f'Ошибка {group_app_res.code}: {group_app_res.error}\n' \
                          f'Описание: {group_app_res.message}\n'
        desc_text += f"**{name_field}**\n{value_field}\n"
    embed.description = desc_text
    return embed


async def ban_in_clan_by_destiny_id(auth, clan_id, membership_id, membership_type):
    assert membership_type != 254
    assert membership_type != BungieMembershipType.BUNGIE_NEXT
    try:
        ban = await DestinyUser(membership_id=membership_id,
                                membership_type=membership_type).ban_member(group_id=clan_id,
                                                                            auth=auth,
                                                                            data=GroupBanRequest(comment='Banned',
                                                                                                 length=0))
    except BungieException as e:
        return e
    return ban
