import os
import textwrap
from typing import List

import PIL
from PIL import Image, ImageDraw, ImageFont
from bungio.models import AuthData, DestinyVendorDefinition, DestinyDisplayCategoryDefinition, GroupUserInfoCard, \
    DestinyComponentType, DestinyProfileResponse, DestinyCharacterComponent, DestinyVendorCategory, \
    DestinyVendorSaleItemComponent, DestinyInventoryItemDefinition

from utils.Resets.resets_utils import open_image
from utils.bungio_client import CustomClient
from utils.users_utils import get_main_destiny_profile


async def get_ada_1(client: CustomClient, auth: AuthData) -> dict[int, List[DestinyVendorSaleItemComponent]]:
    ada_1 = 350061650
    ada_1_definition = await client.manifest.fetch(DestinyVendorDefinition, ada_1)
    await ada_1_definition.fetch_manifest_information()
    ada_1_definition: DestinyVendorDefinition
    # Поиск необходимых индексов категорий (Яркая пыль и Предметы)
    required_indexes = []
    for index in ada_1_definition.display_categories:
        index: DestinyDisplayCategoryDefinition
        if index.identifier in ['category_materials_exchange']:
            required_indexes.append(index.index)
    member_main_profile: GroupUserInfoCard = await get_main_destiny_profile(bungie_id=auth.membership_id,
                                                                            membership_type=auth.membership_type)
    character_list: DestinyProfileResponse = await (member_main_profile.
                                                    get_profile(components=[DestinyComponentType.CHARACTERS],
                                                                auth=auth))
    character_list: dict[int, DestinyCharacterComponent] = character_list.characters.data
    ada_1 = await (character_list[list(character_list.keys())[0]].
                   get_vendor(ada_1,
                              components=[DestinyComponentType.VENDORS,
                                          DestinyComponentType.VENDOR_CATEGORIES,
                                          DestinyComponentType.VENDOR_SALES],
                              auth=auth))

    ada_1_items = {}
    for category_index in required_indexes:
        ada_1_items[category_index] = []

    items_hashes = []

    categories: List[DestinyVendorCategory] = ada_1.categories.data.categories
    items: dict[int, DestinyVendorSaleItemComponent] = ada_1.sales.data
    for category in categories:
        category_index = category.display_category_index
        if category_index in required_indexes:
            for item in category.item_indexes:
                if items[item] not in ada_1_items[category_index]:
                    if items[item].item_hash not in items_hashes:
                        # Шейдеры
                        for resource in items[item].costs:
                            if resource.item_hash == 3159615086 and resource.quantity == 10000:
                                items_hashes.append(items[item].item_hash)
                                ada_1_items[category_index].append(items[item])
                                continue
            ada_1_items[category_index].sort(key=lambda item: item.vendor_item_index)
    return ada_1_items


async def render_resource(client: CustomClient, item_hash: int):
    item = await client.manifest.fetch(DestinyInventoryItemDefinition, item_hash)
    await item.fetch_manifest_information()
    item: DestinyInventoryItemDefinition

    im = Image.new('RGBA', (980, 250), color=(0, 0, 0, 0))

    image = (await open_image(item.display_properties.icon)).convert('RGBA')
    mod_background = Image.new('RGBA', (96, 96), color='#252525')
    mod_background.paste(image, mask=image)
    image = mod_background
    draw = ImageDraw.Draw(im)
    temp_image = Image.new('RGB', (100, 100), color='#d2d2d2')
    temp_image.paste(image, (2, 2))
    maxsize = (96, 96)
    temp_image.thumbnail(maxsize, PIL.Image.Resampling.LANCZOS)

    mod_name = item.display_properties.name
    mod_type = item.item_type_display_name
    if textwrap.fill(mod_name, 60).count('\n') > 1:
        mod_name_len = len(mod_name)
        while textwrap.fill(mod_name, 60).count('\n') > 1:
            mod_name_len -= 1
            mod_name = mod_name[:mod_name_len]
        mod_name = mod_name[:len(mod_name) - 3]
        mod_name += '...'

    if len(mod_type) >= 30:
        mod_type = mod_type[:27]
        mod_type += '...'

    mod_font_name = ImageFont.truetype(f'{os.path.dirname(__file__)}/../assets/'
                                       f'/fonts/Montserrat/Montserrat-Bold.ttf', size=48)
    mod_font_type = ImageFont.truetype(f'{os.path.dirname(__file__)}/../assets/'
                                       f'/fonts/Montserrat/Montserrat-Medium.ttf', size=38)
    x, y = 116, 10
    draw.text((x, y), textwrap.fill(mod_name, 60), font=mod_font_name)
    mod_name_bbox = mod_font_name.getbbox(mod_name)
    y += (textwrap.fill(mod_name, 60).count('\n') + 1) * (mod_name_bbox[3] - mod_name_bbox[1])
    draw.text((x, y), mod_type, font=mod_font_type)
    im.paste(temp_image, (10, 10))
    return im


async def create_ada_1_box(ada_1_items: dict[int, List[DestinyVendorSaleItemComponent]], client: CustomClient):
    ada_1_picture = Image.new('RGBA', (1100, 1000), (0, 0, 0, 0))
    x, y = 2, 2
    for category in ada_1_items:
        for item in ada_1_items[category]:
            item_image = await render_resource(item_hash=item.item_hash, client=client)
            ada_1_picture.paste(item_image, (x, y), mask=item_image)
            y += 120 + 4

    return ada_1_picture
