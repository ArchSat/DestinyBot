from typing import List

import discord
from bungio.models import UserInfoCard, BungieMembershipType, ExactSearchRequest
from discord import ButtonStyle

from utils.ClanAdmin.exceptions import InvalidBungieTag
from utils.bungio_client import CustomClient


class InviteButton(discord.ui.Button):
    def __init__(self, membership_id, disabled=False):
        super().__init__(label='Пригласить в клан',
                         style=ButtonStyle.green,
                         custom_id=f'invite_to_clan_{membership_id}',
                         disabled=disabled)


async def search_destiny_players_by_full_tag(bungie_tag: str,
                                             client: CustomClient,
                                             membership_type: BungieMembershipType = BungieMembershipType.ALL) -> \
        List[UserInfoCard]:
    if '#' not in bungie_tag:
        raise InvalidBungieTag('Некорректно указан BungieTag')
    try:
        bungie_name = bungie_tag.split('#')[0]
        bungie_code = bungie_tag.split('#')[1]
        assert 0 < len(bungie_code) <= 4
    except (IndexError, AssertionError):
        raise InvalidBungieTag('Некорректно указан BungieTag')
    users_info_cards = await client.api.search_destiny_player_by_bungie_name(
        ExactSearchRequest(display_name=bungie_name,
                           display_name_code=bungie_code),
        membership_type=membership_type)
    return users_info_cards
