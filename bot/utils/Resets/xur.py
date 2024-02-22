import PIL
import requests
from PIL import Image, ImageFont, ImageDraw
from PIL.Image import Resampling
from bungio.models import DestinyVendorSaleItemComponent, DestinyInventoryItemDefinition, AuthData, \
    DestinyVendorDefinition, GroupUserInfoCard, DestinyProfileResponse, DestinyComponentType, DestinyCharacterComponent

from utils.Resets.resets_utils import open_image
from utils.bungio_client import CustomClient
from utils.users_utils import get_main_destiny_profile


async def render_resource(client: CustomClient, item: DestinyVendorSaleItemComponent):
    im = Image.new('RGBA', (100, 100), color=(0, 0, 0, 0))
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


async def get_xur(client: CustomClient, auth: AuthData):
    xur_hash = 2190858386
    xur_definition: DestinyVendorDefinition = await client.manifest.fetch(DestinyVendorDefinition, xur_hash)
    await xur_definition.fetch_manifest_information()
    # Поиск необходимых индексов категорий
    required_indexes_names = ['category_black_market_exotics', 'category.weapons_past', 'category.armor_past',
                              'category_exotic_weapons']
    required_indexes = {}

    for index in xur_definition.display_categories:
        if index.identifier in required_indexes_names:
            required_indexes[index.index] = index.identifier
    required_indexes = dict(sorted(required_indexes.items()))

    member_main_profile: GroupUserInfoCard = await get_main_destiny_profile(bungie_id=auth.membership_id,
                                                                            membership_type=auth.membership_type)
    character_list: DestinyProfileResponse = await (member_main_profile.
                                                    get_profile(components=[DestinyComponentType.CHARACTERS],
                                                                auth=auth))
    character_list: dict[int, DestinyCharacterComponent] = character_list.characters.data
    xur_items = {}

    for category_index in required_indexes:
        xur_items[category_index] = []
    items_hashes = []
    for character in character_list:
        tess_everis = await (character_list[character].
                             get_vendor(xur_hash,
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
                    if items[item] not in xur_items[category_index]:
                        if items[item].item_hash not in items_hashes:
                            items_hashes.append(items[item].item_hash)
                            xur_items[category_index].append(items[item])
                xur_items[category_index].sort(key=lambda item: item.vendor_item_index)
    return xur_items


def render_xur_exotic_weapon(item_hash, itemComponents_vendor):
    if item_hash == 3856705927:
        # Для хоукмуна добавляем слот магазина (Контора не может)
        itemComponents_vendor['2'] = [{'plugItemHash': 1431678320, 'canInsert': True, 'enabled': True}]
        itemComponents_vendor = dict(sorted(itemComponents_vendor.items()))
    item = get_item_by_hash(item_hash, 'DestinyInventoryItemDefinition')

    r = requests.get(f'https://www.bungie.net/{item["displayProperties"]["icon"]}', stream=True,
                     headers=head).raw
    image = Image.open(r).convert('RGBA')
    temp_image = Image.new('RGBA', (100, 100), color='#dddddd')
    temp_image.paste(image, (2, 2))
    maxsize = (96, 96)
    temp_image.thumbnail(maxsize, Resampling.LANCZOS)
    image = temp_image
    image = image.resize((96, 96), Resampling.LANCZOS)
    perk_max_count = 0
    for pos in itemComponents_vendor:
        if perk_max_count < len(itemComponents_vendor[pos]):
            perk_max_count = len(itemComponents_vendor[pos])

    background = Image.new('RGBA', (400, 96), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(background)
    draw.rectangle((0, 0, *background.size), outline='#ffffff', width=2)
    background.paste(image, (0, 0))
    x = 96
    y = 10
    perk_list = []
    for column in itemComponents_vendor:
        for perk in itemComponents_vendor[str(column)]:
            perk_list.append((int(perk['plugItemHash'])))
            perk_info = get_item_by_hash(perk['plugItemHash'],
                                         'DestinyInventoryItemDefinition')['displayProperties']
            perk_ico = requests.get(f'https://www.bungie.net/{perk_info["icon"]}', stream=True,
                                    headers=head).raw
            ico = Image.open(perk_ico).convert('RGBA')
            maxsize = (75, 75)
            ico.thumbnail(maxsize, Resampling.LANCZOS)
            background.paste(ico, (x, y), mask=ico)
        x += 75

    return background


def create_xur_items_box(xur_items: dict, xur_items_components: dict):
    xur_box = Image.new('RGBA', (950, 1200), (0, 0, 0, 0))
    x, y = 5, 5

    category_black_market_exotics = xur_items['category_black_market_exotics']
    for item in category_black_market_exotics:
        item_image = render_resource(item)
        xur_box.paste(item_image, (x, y), mask=item_image)
        x += item_image.width + 5
    x -= (96 + 5) * len(category_black_market_exotics)
    y += 96 + 30

    category_armor_past = xur_items['category.armor_past']
    for i, item in enumerate(category_armor_past):
        item_image = render_resource(item)
        xur_box.paste(item_image, (x, y), mask=item_image)
        x += item_image.width + 5
        if (i + 1) % 5 == 0:
            y += 96 + 30
            x -= 5 * (96 + 5)

    category_weapons_past = xur_items['category.weapons_past']
    for item in category_weapons_past:
        item_image = render_resource(item)
        xur_box.paste(item_image, (x, y), mask=item_image)
        x += item_image.width + 5
    x -= (96 + 5) * len(category_weapons_past)
    y += 96 + 30

    category_exotic_weapons = xur_items['category_exotic_weapons']
    for item in category_exotic_weapons:
        weapon_components = xur_items_components[str(item['vendorItemIndex'])]['plugs']
        item_image = render_xur_exotic_weapon(item['itemHash'], weapon_components)
        xur_box.paste(item_image, (x, y), mask=item_image)
        y += 96 + 10
    x -= (96 + 5) * len(category_weapons_past)

    return xur_box


def create_xur_image(bungie_id, headers):
    xur, xur_info, xur_items_components = get_xur(bungie_id, headers)
    xur_items_box = create_xur_items_box(xur, xur_items_components)

    xur_locations = {
        0: ['Башня, Ангар', 'resets/xur/tower.png'],
        1: ['ЕМЗ, Извилистая бухта', 'resets/xur/edz.png'],
        2: ['Несс, Могила Смотрителя', 'resets/xur/ness.png'],
    }
    xur_location = xur_locations[xur_info['vendorLocationIndex']]
    background = Image.open('resets/xur/xur.png')
    location_image = Image.open(xur_location[1]).convert('RGBA')
    location_text = xur_location[0]
    draw = ImageDraw.Draw(background)
    background.paste(location_image, (1050, 238), mask=location_image)
    font = ImageFont.truetype('events/Montserrat/Montserrat-Bold.ttf', size=48)
    draw.text((1050, 170), location_text, font=font)
    background.paste(xur_items_box, (1050, 821), mask=xur_items_box)
    return background
