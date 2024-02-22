import os
import textwrap
from typing import List

import PIL
from PIL import Image, ImageDraw, ImageFont
from PIL.Image import Resampling
from bungio.models import AuthData, DestinyVendorDefinition, DestinyDisplayCategoryDefinition, GroupUserInfoCard, \
    DestinyComponentType, DestinyProfileResponse, DestinyCharacterComponent, DestinyVendorCategory, \
    DestinyVendorSaleItemComponent, DestinyInventoryItemDefinition

from utils.Resets.resets_utils import open_image
from utils.bungio_client import CustomClient
from utils.users_utils import get_main_destiny_profile


async def get_eververse(client: CustomClient, auth: AuthData) -> dict[int, List[DestinyVendorSaleItemComponent]]:
    tess_everis_hash = 3361454721

    tess_everis_definition = await client.manifest.fetch(DestinyVendorDefinition, tess_everis_hash)
    await tess_everis_definition.fetch_manifest_information()
    tess_everis_definition: DestinyVendorDefinition

    # Поиск необходимых индексов категорий (Яркая пыль и Предметы)
    required_indexes = []
    for index in tess_everis_definition.display_categories:
        if index.identifier in ['categories.featured.bright_dust', 'categories.bright_dust.items',
                                'categories.bright_dust.flair']:
            required_indexes.append(index.index)

    member_main_profile: GroupUserInfoCard = await get_main_destiny_profile(bungie_id=auth.membership_id,
                                                                            membership_type=auth.membership_type)
    character_list: DestinyProfileResponse = await (member_main_profile.
                                                    get_profile(components=[DestinyComponentType.CHARACTERS],
                                                                auth=auth))
    character_list: dict[int, DestinyCharacterComponent] = character_list.characters.data
    tess_everis_items = {}

    for category_index in required_indexes:
        tess_everis_items[category_index] = []
    items_hashes = []
    for character in character_list:
        tess_everis = await (character_list[character].
                             get_vendor(tess_everis_hash,
                                        components=[DestinyComponentType.VENDORS,
                                                    DestinyComponentType.VENDOR_CATEGORIES,
                                                    DestinyComponentType.VENDOR_SALES],
                                        auth=auth))
        categories = tess_everis.categories.data.categories
        items = tess_everis.sales.data
        for category in categories:
            category_index = category.display_category_index
            if category_index in required_indexes:
                for item in category.item_indexes:
                    if items[item] not in tess_everis_items[category_index]:
                        if items[item].item_hash not in items_hashes:
                            items_hashes.append(items[item].item_hash)
                            tess_everis_items[category_index].append(items[item])
                tess_everis_items[category_index].sort(key=lambda item: item.vendor_item_index)
    return tess_everis_items


async def render_resource(client: CustomClient, item: DestinyVendorSaleItemComponent):
    im = Image.new('RGBA', (96, 96), color=(0, 0, 0, 0))
    await item.fetch_manifest_information()
    resource = item.manifest_item_hash
    await resource.fetch_manifest_information()
    resource: DestinyInventoryItemDefinition

    temp_image = Image.new('RGBA', (100, 100), color='#dddddd')
    temp_image.paste(await open_image(resource.display_properties.icon), (2, 2))
    maxsize = (87, 87)
    temp_image.thumbnail(maxsize, Resampling.LANCZOS)
    im.paste(temp_image)
    return im


async def render_eververse(client, eververse_items: dict):
    eververse_picture = Image.new('RGBA', (1100, 300), (0, 0, 0, 0))
    x, y = 2, 2
    for category in eververse_items:
        for item in eververse_items[category]:
            item_image = await render_resource(client=client, item=item)
            eververse_picture.paste(item_image, (x, y), mask=item_image)
            x += 87 + 4
        x = 2
        y += 87 + 4
    return eververse_picture
