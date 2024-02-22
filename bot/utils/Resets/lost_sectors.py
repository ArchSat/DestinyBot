import datetime
import os
import re
import textwrap
from typing import List

import bungio
from PIL import Image, ImageDraw, ImageFont
from bungio.models import DestinyActivityDefinition, DestinyDestinationDefinition, \
    DestinyActivityModifierReferenceDefinition, DestinyActivityModifierDefinition, DestinyInventoryItemDefinition

from utils.Resets.resets_utils import open_image, get_current_rotation_day, LostSector, LostSectorModifiers
from utils.bungio_client import CustomClient


async def create_lost_sector_big_box(client, sector: DestinyActivityDefinition):
    location: DestinyDestinationDefinition = sector.manifest_destination_hash

    sector_pgcr_image = (await open_image(sector.pgcr_image)).convert('RGBA')

    # Затенение изображения
    shadow = Image.new('RGBA', sector_pgcr_image.size, (0, 0, 0, 0))
    sector_pgcr_image.paste(shadow, (0, 0), mask=shadow)
    sector_pgcr_image.putalpha(255)

    # Обраборка изображения под маску
    sector_big_box_mask = Image.open(f'{os.path.dirname(__file__)}/../assets/lost_sectors/sector_big_box_mask.png')
    sector_pgcr_image = sector_pgcr_image.resize(sector_big_box_mask.size)
    sector_pgcr_image = sector_pgcr_image.crop((0, 0, *sector_big_box_mask.size))
    background = Image.new('RGBA', sector_pgcr_image.size, (0, 0, 0, 0))
    background.paste(sector_pgcr_image, (0, 0), mask=sector_big_box_mask)
    # background содержит изображение фона

    # TEXT
    font = ImageFont.truetype(f'{os.path.dirname(__file__)}/../assets/fonts/Montserrat/Montserrat-Black.ttf', size=60)
    font_colour = '#FDFEFE'
    draw = ImageDraw.Draw(background)

    draw.text((815, 60), location.display_properties.name.upper(), font=font, fill=font_colour)
    draw.text((815, 120), sector.original_display_properties.name, font=font, fill=font_colour)

    sector_modifiers = LostSectorModifiers(client, sector)
    await sector_modifiers.init()
    sector_descrition_box = await create_lost_sector_big_box_description(sector_modifiers)
    background.paste(sector_descrition_box, (50, 50), mask=sector_descrition_box)
    return background


async def create_lost_sector_big_box_description(lost_sector_modifiers: LostSectorModifiers):
    path = f'{os.path.dirname(__file__)}/../assets'
    background = Image.open(f'{path}/lost_sectors/sector_big_box_description_mask.png')

    draw = ImageDraw.Draw(background)
    category_font = ImageFont.truetype(f'{path}/fonts/Montserrat/Montserrat-Black.ttf', size=30)
    font_colour = '#FDFEFE'
    x, y = 30, 20

    category_name = 'ВОИТЕЛИ:'
    draw.text((x, y), category_name, font=category_font, fill=font_colour)
    box = category_font.getbbox(category_name)
    y += box[3] + 20
    for mod in lost_sector_modifiers.champions:
        champ_box = await create_sector_modifier_without_description_box(mod)
        background.paste(champ_box, (x, y), mask=champ_box)
        y += champ_box.height + 15

    y += 25

    category_name = 'МОЩЬ:'
    draw.text((x, y), category_name, font=category_font, fill=font_colour)
    box = category_font.getbbox(category_name)
    y += box[3] + 20
    for mod in lost_sector_modifiers.surge:
        surge_box = await create_sector_modifier_with_description_box(mod)
        background.paste(surge_box, (x, y), surge_box)
        y += surge_box.height + 15

    y += 25

    category_name = 'ОРУЖИЕ:'
    draw.text((x, y), category_name, font=category_font, fill=font_colour)
    box = category_font.getbbox(category_name)
    y += box[3] + 20
    for mod in lost_sector_modifiers.overcharged:
        mod_box = await create_sector_modifier_with_description_box(mod)
        background.paste(mod_box, (x, y), mod_box)
        y += mod_box.height + 15

    return background


async def create_sector_modifier_with_description_box(modifier: DestinyActivityModifierDefinition |
                                                                DestinyActivityModifierReferenceDefinition):
    if isinstance(modifier, DestinyActivityModifierReferenceDefinition):
        await modifier.fetch_manifest_information()
        modifier = modifier.manifest_activity_modifier_hash
    modifier: DestinyActivityModifierDefinition

    path = f'{os.path.dirname(__file__)}/../assets'
    name_font = ImageFont.truetype(f'{path}/fonts/Montserrat/Montserrat-Black.ttf', size=30)
    description_font = ImageFont.truetype(f'{path}/fonts/Montserrat/Montserrat-Black.ttf', size=30)
    icons_size = 60
    font_colour = '#FDFEFE'

    modifier_name = modifier.display_properties.name
    modifier_name: str = modifier_name.replace('Сверхзаряженная ', '').replace('Сверхзаряженный ', '')
    modifier_name = modifier_name.capitalize()
    name_box = name_font.getbbox(modifier_name)
    modifier_desc = modifier.display_properties.description
    vars_in_desc = re.findall('{var:\d*}', modifier_desc)
    for var in vars_in_desc:
        var_value = 25
        modifier_desc = modifier_desc.replace(var, str(var_value))

    modifier_icon = await open_image(modifier.display_properties.icon)

    modifier_desc = modifier_desc + '.'
    modifier_desc = modifier_desc.replace('\n\n\n', '\n\n').replace('\n\n', '\n').replace('\n', '.')
    modifier_desc = modifier_desc.replace('....', '...').replace('...', '..').replace('..', '.')
    modifier_desc = modifier_desc.replace('. ', '.')
    modifier_desc = modifier_desc.replace('.', '.\n')
    string_len = 28

    name_h = name_box[3] - name_box[1]

    description_h = 0
    for row in modifier_desc.split('\n'):
        wrap_row = textwrap.fill(row, string_len)
        wrap_row_box = description_font.getbbox(wrap_row)
        description_h += (wrap_row_box[3] - wrap_row_box[1]) * (wrap_row.count('\n') + 1) + 10

    background_h = max(icons_size, description_h + name_h + 10)
    background_w = 650

    background = Image.new('RGBA', (background_w, background_h), (0, 0, 0, 0))
    background.paste(modifier_icon, (0, 0), mask=modifier_icon)
    draw = ImageDraw.Draw(background)
    draw.text((modifier_icon.width + 10, 0), modifier_name, font=name_font, fill=font_colour)
    x, y = modifier_icon.width + 10, name_h + 10
    for row in modifier_desc.split('\n'):
        wrap_row = textwrap.fill(row, string_len)
        wrap_row_box = description_font.getbbox(wrap_row)
        draw.multiline_text((x, y), wrap_row,
                            font=description_font,
                            fill=font_colour)
        y += (wrap_row_box[3] - wrap_row_box[1]) * (wrap_row.count('\n') + 1) + 10

    return background


async def create_sector_modifier_without_description_box(modifier: DestinyActivityModifierDefinition |
                                                                   DestinyActivityModifierReferenceDefinition):
    if isinstance(modifier, DestinyActivityModifierReferenceDefinition):
        await modifier.fetch_manifest_information()
        modifier = modifier.manifest_activity_modifier_hash
    modifier: DestinyActivityModifierDefinition

    path = f'{os.path.dirname(__file__)}/../assets'
    name_font = ImageFont.truetype(f'{path}/fonts/Montserrat/Montserrat-Black.ttf', size=30)
    icons_size = 60
    font_colour = '#FDFEFE'

    modifier_name = modifier.display_properties.name
    name_box = name_font.getbbox(modifier_name)

    modifier_icon = (await open_image(modifier.display_properties.icon)).resize((icons_size, icons_size))

    name_h = name_box[3] - name_box[1]
    background_h = max(icons_size, name_h)
    background_w = 650

    background = Image.new('RGBA', (background_w, background_h), (0, 0, 0, 0))
    background.paste(modifier_icon, (0, 0), mask=modifier_icon)
    draw = ImageDraw.Draw(background)
    modifier_name_box = name_font.getbbox(modifier_name)
    draw.text((modifier_icon.width + 10, (background.height // 2 - modifier_name_box[3] // 2)),
              modifier_name,
              font=name_font,
              fill=font_colour)
    return background


async def create_drop_box(item_list):
    chunk_size = 10
    item_list = list(bungio.utils.split_list(item_list, chunk_size))
    item_size = 107
    x, y = 10, 10
    box_size = (x + chunk_size * (item_size + 15), y + len(item_list) * (item_size + 15))
    background = Image.new('RGBA', box_size, (0, 0, 0, 0))
    for row in item_list:
        for item in row:
            item: DestinyInventoryItemDefinition
            item_image = (await open_image(item.display_properties.icon)).convert('RGBA').resize((item_size, item_size))

            # item_image = Image.open(item_req).convert('RGBA').resize((96, 96))
            # drop_mask = Image.open('resets/sectors/drop_mask.png')
            # drop_image = Image.new('RGBA', item_image.size, (0, 0, 0, 0))
            # drop_image.paste(item_image, (0, 0), mask=drop_mask)
            # item_image = drop_image.resize((item_size, item_size))

            background.paste(item_image, (x, y), mask=item_image)
            x += item_size + 15
        x -= len(row) * (item_size + 15)
        y += item_size + 15
    return background


async def create_small_sector_box(sector: LostSector, date):
    icon_size = 107

    location: DestinyDestinationDefinition = sector.activity.manifest_destination_hash
    pgcr_image = (await open_image(sector.activity.pgcr_image)).convert('RGBA').resize((900, 500))

    path = f'{os.path.dirname(__file__)}/../assets'
    small_sector_mask = Image.open(f'{path}/lost_sectors/small_sector_mask.png')
    shadow = Image.new('RGBA', pgcr_image.size, (0, 0, 0, 75))
    pgcr_image.paste(shadow, (0, 0), mask=shadow)
    pgcr_image.putalpha(255)
    pgcr_image = pgcr_image.crop((0, 0, *small_sector_mask.size))
    background = Image.new('RGBA', pgcr_image.size, (255, 255, 255, 0))
    background.paste(pgcr_image, (0, 0), mask=small_sector_mask)

    font = ImageFont.truetype(f'{path}/fonts/Montserrat/Montserrat-Black.ttf', size=30)
    date_font = ImageFont.truetype(f'{path}/fonts/Montserrat/Montserrat-Black.ttf', size=30)
    date_string = date.strftime('%d.%m')
    sector_name = sector.activity.original_display_properties.name  # sector.activity.display_properties.name
    sector_location = location.display_properties.name

    draw = ImageDraw.Draw(background)
    draw.text((50, 45), date_string, font=date_font, fill='#FDFEFE')

    draw.text((50, 100), sector_location.upper(), font=font, fill='#FDFEFE')
    draw.text((50, 135), sector_name, font=font, fill='#FDFEFE')

    drop_icon = sector.drop.icon.convert('RGBA').\
        resize((icon_size, icon_size))
    drop_mask = Image.open(f'{path}/lost_sectors/drop_mask.png').resize((icon_size, icon_size))
    drop_image = Image.new('RGBA', drop_icon.size, (0, 0, 0, 0))
    drop_image.paste(drop_icon, (0, 0), mask=drop_mask)
    drop_image = drop_image.resize((icon_size, icon_size))

    background.paste(drop_image, (50, 345), mask=drop_image)

    return background


async def create_lost_sector_image(client: CustomClient,
                                   date: datetime.datetime,
                                   lost_sectors: dict[int: LostSector]):
    """
    lost_sectors: словарь в формате:
    {
    0: LostSector() - сегодня
    1: LostSector() - завтра
    2: LostSector() - послезавтра
    3: LostSector() - после послезавтра
    }
    """
    path = f'{os.path.dirname(__file__)}/../assets'
    background = Image.open(f'{path}/lost_sectors/background.png')
    draw = ImageDraw.Draw(background)

    date_font = ImageFont.truetype(f'{path}/fonts/Montserrat/Montserrat-Black.ttf', size=160)
    date_string = date.strftime('%d.%m')
    draw.text((315, 45), date_string, font=date_font, fill='#FDFEFE')

    drop_box = await create_drop_box(lost_sectors[0].drop.items)
    background.paste(drop_box, (870, 230), mask=drop_box)

    current_sector_box = await create_lost_sector_big_box(client, lost_sectors[0].activity)
    background.paste(current_sector_box, (50, 550), mask=current_sector_box)

    x, y = 50, 1610
    for i in range(3):
        sector = lost_sectors[i + 1]
        small_sector_box = await create_small_sector_box(sector, date + datetime.timedelta(days=i + 1))
        background.paste(small_sector_box, (x, y), mask=small_sector_box)
        x += small_sector_box.width + 50

    return background
