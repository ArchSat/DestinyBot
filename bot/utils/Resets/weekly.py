import os
import textwrap
import time

from PIL import Image, ImageFont, ImageDraw
from PIL.Image import Resampling
from bungio.models import AuthData, DestinyPublicMilestone, DestinyActivityModifierDefinition, DestinyActivityDefinition

from utils.Resets.ada1 import get_ada_1, create_ada_1_box
from utils.Resets.eververse import get_eververse, render_eververse
from utils.Resets.resets_utils import open_image
from utils.bungio_client import CustomClient
from utils.logger import create_logger

logger = create_logger('resets')

raids = {
    1191701339: {
        'name': 'Источник кошмаров',
        'icon': '/common/destiny2_content/icons/7ddce334fe8391848f408227439c1d7a.png',
        'challenges': {
            3: ['Освещенное мучение', 'Продливать таймер (убивать мучителя) только под баффом "Поле света"'],
            0: ['Перекрестный огонь', 'Активировать трамплин можно только с противоположной стороны'],
            1: ['Космический баланс', 'Менять планеты так, чтобы справа были светлые, а слева темные'],
            2: ['Мы одна команда', 'REDACTED'],
        }
    },

    1374392663: {
        'name': 'Гибель короля',
        'icon': '/common/destiny2_content/icons/0e515c7cf25a2f2350b788e6f5b7f8eb.png',
        'challenges': {
            4: ['Трава всегда зеленее', 'Игроку нельзя два раза подряд стоять на одном и том же тотеме'],
            0: ['Коварная кража', 'После подбора клейма, забрать купол в течение 5 секунд'],
            1: ['Изумленный взгляд',
                'Игрок с бафом "Взгляд Голгорота" должен передавать его, стоя в луже'],
            2: ['Строительные работы',
                'Каждому игроку нельзя вставать на одну и ту же платформу дважды (за одну фазу урона)'],
            3: ['Руки прочь',
                'Каждому игроку нельзя убивать одного и того же огра и рыцаря (на протяжении всего этапа)'],
        }
    },

    1441982566: {
        'name': 'Клятва послушника',
        'icon': '/common/destiny2_content/icons/f2b6ec58e14244e4972705897667c246.png',
        'challenges': {
            2: ['Стремительное разрушение', 'Убивать неудержимых огров одновременно или'
                                            ' не убивать их вообще'],
            3: ['Основная информация', 'Из комнаты выносить не более одного символа'],
            0: ['Прорыв обороны', 'Каждый игрок должен убить не более одного рыцаря в щите'],
            1: ['Зацикленный катализатор', 'Игрокам нельзя терять бафф "Иссушающая сила" до начала фазы урона'],
        }
    },

    3711931140: {
        'name': 'Хрустальный чертог',
        'icon': '/common/destiny2_content/icons/6d2ba4628f33a6884b5d32d62eac6a32.png',
        'challenges': {
            3: ['Погодите-ка...', 'Не убивать виверн, пока они не начнут сливаться со слияниями'],
            4: ['Оракула мне дай ответ', 'Каждый игрок не должен разрушать один и тот же оракул '
                                         'более одного раза'],
            0: ['По ту сторону', 'Не позволить Храмовнику телепортироваться'],
            1: ['Странники во времени', 'Виверна и минотавр в порталах должны быть уничтожены одновременно'],
            2: ['Стройный хор', 'Каждый игрок в порталах (Марс/Венера) должен сломать по одному из трех оракулов'],
        }
    },

    910380154: {
        'name': 'Склеп глубокого камня',
        'icon': '/common/destiny2_content/icons/9d6744eed9fa9b55f8190ce975f1872d.png',
        'challenges': {
            0: ['Красный бродяга', 'Каждый игрок должен отстрелить по 2 консоли в нижней части,'
                                   ' не умирая от "красного пола"'],
            1: ['Копии копий', 'Необходимо удерживать дебафф "Репликация Атракс" до окончания этапа,'
                               ' не сбрасывая их и не умирая'],
            2: ['На все руки', 'Каждый игрок должен использовать каждый баф'],
            3: ['Ядерная четверка', 'Сбивать по 4 двигателя боссу за раз']
        }
    },

    2497200493: {
        'name': 'Сад спасения',
        'icon': '/common/destiny2_content/icons/e48d301e674a19f17c5cb249a2da0173.png',
        'challenges': {
            2: ['Остатки', 'Не убивать циклопов, которых спавнит гарпия'],
            3: ['Звено в цепочке', 'Необходимо обновлять бафф на всех членах команды одновременно'],
            0: ['К вершине', 'Вносить в шпиль только по 10 частиц'],
            1: ['От одного до ста', 'Заполнить шпиль за 10 секунд с первого внесения частиц'],
        }
    },

    1661734046: {
        'name': 'Последнее желание',
        'icon': '/common/destiny2_content/icons/597d5fe665eeb011ec0d74a5d9d8137e.png',
        'challenges': {
            4: ['Ритуал призыва', 'Активировать все платформы'],
            0: ['Шабаш ведьм', 'Необходимо не получить урона от снайперского выстрела Шуро Чи'],
            1: ['Вечная война', 'Не убивать огров кроме Моргета'],
            2: ['Не влезать', ' Не дать рыцарям выйти из комнат'],
            3: ['Сила памяти', 'Каждому игроку не отстреливать один и тот же глаз за фазу урона'],
        }
    },
}


def get_current_rotation(count_rotations):
    week = 604800
    current_time = int(time.time())
    return (abs(current_time - 1600794000) // week) % count_rotations


def get_current_raid_rotation():
    rotations = {
        2: 2497200493,  # 'garden_of_salvation',
        3: 910380154,  # 'deep_stone_crypt',
        4: 3711931140,  # 'vault_of_glass',
        5: 1441982566,  # 'vow_of_the_disciple',
        0: 1374392663,  # 'kings_fall',
        1: 1661734046,  # 'last_wish',
    }
    return rotations[get_current_rotation(len(rotations))]


async def create_weekly_picture(client: CustomClient, auth: AuthData):
    logger.info('Формирую недельный ресет')

    milestones: dict[str, DestinyPublicMilestone] = await client.api.get_public_milestones(auth=auth)

    background = Image.open(f'{os.path.dirname(__file__)}/../assets/resets/weekly_reset.png')
    x, y = 50, 1660
    left_info_box = await create_left_info_box(client=client, milestones=milestones)
    background.paste(left_info_box, (x, y), mask=left_info_box)

    x, y = 1075, 190
    raid_box = await create_raid_box(client=client)
    background.paste(raid_box, (x, y), mask=raid_box)

    x, y = 1075, 860
    dungeon_box = await create_dungeon_box(client=client)
    background.paste(dungeon_box, (x, y), mask=dungeon_box)

    x, y = 2125, 190
    nightfall_box = await create_nightfall_box(client=client,
                                               milestones=milestones)  # get_nightfall_box_with_weapon(milestones)
    background.paste(nightfall_box, (x, y), mask=nightfall_box)

    x, y = 1075, 1540
    witch_queen_box = await get_current_comp_box(client=client)
    background.paste(witch_queen_box, (x, y), mask=witch_queen_box)

    x, y = 2125, 860
    dares_box = get_dares_box()
    background.paste(dares_box, (x, y), mask=dares_box)

    x, y = 1075, 2160
    nightmares_box = await create_nightmares_box()
    background.paste(nightmares_box, (x, y), mask=nightmares_box)

    x, y = 2125, 1530
    # season_box = create_season_box()
    ada_1 = await get_ada_1(client=client, auth=auth)
    ada_1_box = await create_ada_1_box(ada_1_items=ada_1, client=client)
    background.paste(ada_1_box, (x, y + 50), mask=ada_1_box)

    x, y = 2125, 2310
    eververse = await get_eververse(client=client, auth=auth)
    eververse_box = await render_eververse(client=client, eververse_items=eververse)
    background.paste(eververse_box, (x, y), mask=eververse_box)

    x, y = 3175, 180
    raids_box = await create_all_raids_box()
    background.paste(raids_box, (x, y), mask=raids_box)
    logger.info('Недельный ресет сформирован!')
    return background


async def create_left_info_box(client: CustomClient, milestones: dict[str, DestinyPublicMilestone]):
    background = Image.new('RGBA', (760, 1000), (0, 0, 0, 0))
    font_bold = ImageFont.truetype(f'{os.path.dirname(__file__)}/../'
                                   f'assets/fonts/Montserrat/Montserrat-Bold.ttf', size=41)
    font_normal = ImageFont.truetype(f'{os.path.dirname(__file__)}/../'
                                     f'assets/fonts/Montserrat/Montserrat-Medium.ttf', size=35)
    draw = ImageDraw.Draw(background)
    x, y = 0, 0
    weekly_burn = get_current_singe(milestones)
    draw.text((x, y), 'Стихийное горение', font=font_bold)
    y += 40
    for burn in weekly_burn:
        burn_desc = await client.manifest.fetch(DestinyActivityModifierDefinition, burn)
        if burn_desc:
            await burn_desc.fetch_manifest_information()
            burn_desc: DestinyActivityModifierDefinition
        if burn_desc:
            draw.text((x, y), f"{burn_desc.display_properties.name}", font=font_normal, fill='#888888')
        y += 35
    y += 50
    draw.text((x, y), 'Бонус активностей', font=font_bold)
    y += 40
    weekly_bonus = get_current_double_modifiers(milestones)
    for modifier in weekly_bonus:
        modifier_desc = await client.manifest.fetch(DestinyActivityModifierDefinition, modifier)
        if modifier_desc:
            await modifier_desc.fetch_manifest_information()
            modifier_desc: DestinyActivityModifierDefinition
        if modifier_desc:
            draw.text((x, y), f"{modifier_desc.display_properties.name}", font=font_normal, fill='#888888')
        y += 35
    y += 50

    draw.text((x, y), 'Горнило', font=font_bold)
    y += 40
    crusible = get_current_crucible_mode(milestones)
    for activity in crusible:
        activity_desc = await client.manifest.fetch(DestinyActivityDefinition, activity.activity_hash)
        if activity_desc:
            await activity_desc.fetch_manifest_information()
            activity_desc: DestinyActivityDefinition
        draw.text((x, y), f"{activity_desc.display_properties.name}", font=font_normal, fill='#888888')
        y += 35
    y += 50

    draw.text((x, y), 'Город грез', font=font_bold)
    y += 40
    curse = get_current_curse()
    challenge = get_current_ascendant_challenge()
    draw.text((x, y), f"{curse}", font=font_normal, fill='#888888')
    y += 35
    draw.text((x, y), f"Высшее испытание:", font=font_normal, fill='#888888')
    y += 35
    draw.multiline_text((x, y), f"{textwrap.fill(challenge, 25)}", font=font_normal, fill='#888888')
    y += 50
    return background


def get_current_singe(milestones: dict[str, DestinyPublicMilestone]):
    strikes_playlist: DestinyPublicMilestone = milestones.get('1942283261', None)  # 1437935813
    if not strikes_playlist:
        return []
    all_singes = {426976067, 3196075844, 2691200658, 3809788899, 3810297122}
    strike_nightfall_modifiers = []
    for activity in strikes_playlist.activities:
        strike_nightfall_modifiers += activity.modifier_hashes
    return list(set(strike_nightfall_modifiers) & all_singes)


def get_current_double_modifiers(milestones: dict[str, DestinyPublicMilestone]):
    # Increased Vanguard Rank, Increased Trials Rank, Increased Gambit Rank,
    # Increased Crucible Rank, Double Nightfall Drops
    all_double_modifiers = {745014575, 1361609633, 3228023383, 3874605433, 1171597537}
    current_modifiers = []
    # 100k, Gambit, Crusible, Trials
    check_milestones = [1437935813, 2029743966, 3448738070, 3312774044, 3007559996, 1942283261]
    for milestone_hash in check_milestones:
        if not milestones.get(str(milestone_hash), None):
            continue
        for activity in milestones[str(milestone_hash)].activities:
            activity_modifiers = activity.modifier_hashes
            if set(activity_modifiers) & all_double_modifiers:
                current_modifiers += list(set(activity_modifiers) & all_double_modifiers)
    return list(set(current_modifiers))


def get_current_crucible_mode(milestones: dict[str, DestinyPublicMilestone]):
    crucible = milestones.get('3312774044', None)
    if not crucible:
        return []
    crucible_modes = []
    for activity in crucible.activities:
        if activity.activity_hash in [2696116787, 2259621230, 2754695317, 2607135461, 1113451448, 4150051058]:
            continue
        crucible_modes.append(activity)
    return crucible_modes


def get_current_curse():
    rotations = {
        0: 'Среднее проклятие (2 неделя)',
        1: 'Сильное проклятие (3 неделя)',
        2: 'Слабое проклятие (1 неделя)',
    }
    return rotations[get_current_rotation(3)]


def get_current_ascendant_challenge():
    rotations = {
        0: 'Зал звездного света (Кимер. гарнизон)',
        1: 'Могила Афелия (Уроборея)',
        2: 'Сады Эсилы (Потерянное святилище)',
        3: 'Хребет Керы  (Расколотые руины)',
        4: 'Закоулок  посланника (Крепость отточенной кромки)',
        5: 'Залив утонувших желаний (Бездна Агонарха)'
    }
    return rotations[get_current_rotation(6)]


async def create_raid_box(client: CustomClient):
    raid_desc = await client.manifest.fetch(DestinyActivityDefinition, str(get_current_raid_rotation()))
    await raid_desc.fetch_manifest_information()
    raid_desc: DestinyActivityDefinition
    raid_image = await open_image(raid_desc.pgcr_image)

    background = Image.new('RGBA', (977, 570))
    raid_box = Image.open(f'{os.path.dirname(__file__)}/../assets/resets/raid.png')
    box_for_crop_temp = (0, 0, *raid_box.size)
    box_for_crop = []
    for i, coord in enumerate(box_for_crop_temp):
        if i % 2 == 0:
            box_for_crop.append(coord + 100)
        else:
            box_for_crop.append(coord + 400)
    cropped_image = raid_image.crop(box_for_crop)
    ellipsed_raid_image = raid_box.copy()
    ellipsed_raid_image.paste(cropped_image, mask=raid_box)
    cropped_ellipsed_raid_image = ellipsed_raid_image.crop((150, 0, *ellipsed_raid_image.size))
    raid_box.paste(cropped_ellipsed_raid_image, (150, 0), mask=cropped_ellipsed_raid_image)
    background.paste(raid_box, (90, 146), mask=raid_box)
    draw = ImageDraw.Draw(background)
    font = ImageFont.truetype(f'{os.path.dirname(__file__)}/../assets/'
                              f'fonts/Montserrat/Montserrat-Bold.ttf', size=48)
    raid_name = (raid_desc.display_properties.name.lower().
                 replace(': легенда', '').
                 replace(': мастер', '').
                 replace(': нормальный', '').title())
    draw.text((90, 65), f"{raid_name}", font=font)
    return background


async def create_dungeon_box(client: CustomClient):
    dungeon_desc = await client.manifest.fetch(DestinyActivityDefinition, str(get_current_dungeon_rotation()))
    await dungeon_desc.fetch_manifest_information()
    dungeon_desc: DestinyActivityDefinition
    dungeon_image = await open_image(dungeon_desc.pgcr_image)

    background = Image.new('RGBA', (977, 570))
    dungeon_box = Image.open(f'{os.path.dirname(__file__)}/../assets/resets/dungeon.png')
    box_for_crop_temp = (0, 0, *dungeon_box.size)
    box_for_crop = []
    for i, coord in enumerate(box_for_crop_temp):
        if i % 2 == 0:
            box_for_crop.append(coord + 100)
        else:
            box_for_crop.append(coord + 400)
    cropped_image = dungeon_image.crop(box_for_crop)
    ellipsed_dungeon_image = dungeon_box.copy()
    ellipsed_dungeon_image.paste(cropped_image, mask=dungeon_box)
    cropped_ellipsed_dungeon_image = ellipsed_dungeon_image.crop((150, 0, *ellipsed_dungeon_image.size))
    dungeon_box.paste(cropped_ellipsed_dungeon_image, (150, 0), mask=cropped_ellipsed_dungeon_image)
    background.paste(dungeon_box, (90, 146), mask=dungeon_box)
    draw = ImageDraw.Draw(background)
    font = ImageFont.truetype(f'{os.path.dirname(__file__)}/../assets/'
                              f'fonts/Montserrat/Montserrat-Bold.ttf', size=48)
    name = (dungeon_desc.display_properties.name.lower()
            .replace(': легенда', '')
            .replace(': мастер', '')
            .replace(': нормальный', '').title())
    draw.text((90, 65), f"{name}", font=font)
    return background


def get_current_dungeon_rotation():
    rotations = {
        1: 1375089621,  # 'Яма ереси',
        2: 1077850348,  # 'Откровение',
        3: 4078656646,  # 'Тиски алчности',
        4: 2823159265,  # 'Дуальность',
        0: 2032534090,  # 'Расколотый трон',
    }
    return rotations[get_current_rotation(5)]


async def create_nightfall_box(client: CustomClient, milestones: dict[str, DestinyPublicMilestone]):
    background = Image.new('RGBA', (977, 570))
    nightfall_box = Image.open(f'{os.path.dirname(__file__)}/../assets/resets/nightfall.png')
    strike_nightfall, current_burn, current_weapons, current_shields, current_champions = \
        await get_current_nightfall(client=client, milestones=milestones)

    icons = {
        'void': '/common/destiny2_content/icons/DestinyDamageTypeDefinition_ceb2f6197dccf3958bb31cc783eb97a0.png',
        'solar': '/common/destiny2_content/icons/DestinyDamageTypeDefinition_2a1773e10968f2d088b97c22b22bba9e.png',
        'arc': '/common/destiny2_content/icons/DestinyDamageTypeDefinition_092d066688b879c807c3b460afdd61e6.png',
        'barrier': '/common/destiny2_content/icons/DestinyBreakerTypeDefinition_07b9ba0194e85e46b258b04783e93d5d.png',
        'unstoppable': '/common/destiny2_content/icons/DestinyBreakerTypeDefinition_825a438c85404efd6472ff9e97fc7251'
                       '.png',
        'overload': '/common/destiny2_content/icons/DestinyBreakerTypeDefinition_da558352b624d799cf50de14d7cb9565.png'
    }

    nightfall_desc = await client.manifest.fetch(DestinyActivityDefinition, strike_nightfall)
    await nightfall_desc.fetch_manifest_information()
    nightfall_desc: DestinyActivityDefinition
    nightfall_image = await open_image(nightfall_desc.pgcr_image)
    box_for_crop_temp = (0, 0, *nightfall_box.size)
    box_for_crop = []
    for i, coord in enumerate(box_for_crop_temp):
        if i % 2 == 0:
            box_for_crop.append(coord + 100)
        else:
            box_for_crop.append(coord + 400)
    cropped_image = nightfall_image.crop(box_for_crop)
    ellipsed_nightfall_image = nightfall_box.copy()
    ellipsed_nightfall_image.paste(cropped_image, mask=nightfall_box)
    cropped_ellipsed_nightfall_image = ellipsed_nightfall_image.crop((150, 0, *ellipsed_nightfall_image.size))

    nightfall_box.paste(cropped_ellipsed_nightfall_image, (150, 0), mask=cropped_ellipsed_nightfall_image)

    x, y = 715, 100
    for shield in current_shields:
        shield_image = Image.new('RGBA', (600, 600))
        draw = ImageDraw.Draw(shield_image)
        draw.ellipse((0, 0, 600, 600), fill='white')
        shield_image = shield_image.resize((60, 60), Resampling.LANCZOS)

        shield_icon = (await open_image(icons[shield])).convert("RGBA")
        shield_icon = shield_icon.resize((36, 36), Resampling.LANCZOS)
        shield_image.paste(shield_icon, (12, 12), mask=shield_icon)
        nightfall_box.paste(shield_image, (x, y), mask=shield_image)
        x -= 75

    x, y = 715, 175
    for champion in current_champions:
        champion_image = (await open_image(icons[champion])).convert("RGBA")
        champion_image = champion_image.resize((60, 60), Resampling.LANCZOS)
        nightfall_box.paste(champion_image, (x, y), mask=champion_image)
        x -= 75

    x, y = 160, 0
    burn_x, burn_y = x, y
    for burn in current_burn:
        burn_def = await client.manifest.fetch(DestinyActivityModifierDefinition, burn)
        await burn_def.fetch_manifest_information()
        burn_def: DestinyActivityModifierDefinition
        burn_name = burn_def.display_properties.name
        draw = ImageDraw.Draw(nightfall_box)
        font = ImageFont.truetype(f'{os.path.dirname(__file__)}/../assets/'
                                  f'/fonts/Montserrat/Montserrat-Bold.ttf', size=30)
        draw.text((burn_x + 2, burn_y + 2), burn_name, font=font, fill='#000000')
        draw.text((burn_x, burn_y), burn_name, font=font, fill='#ffffff')
        burn_y += 40

    burn_x, burn_y = x, 175
    for weapon in current_weapons:
        weapon_mod = await client.manifest.fetch(DestinyActivityModifierDefinition, weapon)
        await weapon_mod.fetch_manifest_information()
        weapon_mod: DestinyActivityModifierDefinition

        weapon_mod_image = (await open_image(weapon_mod.display_properties.icon)).convert("RGBA")
        weapon_mod_image = weapon_mod_image.resize((60, 60), Resampling.LANCZOS)
        nightfall_box.paste(weapon_mod_image, (burn_x, burn_y), mask=weapon_mod_image)
        burn_x += 75

    background.paste(nightfall_box, (90, 146), mask=nightfall_box)
    draw = ImageDraw.Draw(background)
    font = ImageFont.truetype(f'{os.path.dirname(__file__)}/../assets/'
                              f'/fonts/Montserrat/Montserrat-Bold.ttf', size=48)
    draw.text((90, 65), f"{nightfall_desc.display_properties.description.title()}", font=font)
    return background


async def get_current_nightfall(client: CustomClient, milestones: dict[str, DestinyPublicMilestone]):
    all_burns = [426976067, 3196075844, 2691200658, 3809788899, 3810297122]
    all_weapons = [2178457119, 2626834038, 2743796883, 3132780533, 3320777106, 3758645512, 95459596, 795009574,
                   1282934989, 1326581064]
    strike_nightfall = milestones[str(2029743966)].activities[-1]
    strike_nightfall_modifiers = strike_nightfall.modifier_hashes
    current_burn = []
    current_weapons = []
    current_shields = []
    current_champions = []
    for modif in strike_nightfall_modifiers:
        if modif in all_burns:
            current_burn.append(modif)
            continue
        if modif in all_weapons:
            current_weapons.append(modif)
            continue
        modifier_definition = await client.manifest.fetch(DestinyActivityModifierDefinition, str(modif))
        await modifier_definition.fetch_manifest_information()
        modifier_definition: DestinyActivityModifierDefinition
        if '[Пустота]' in modifier_definition.display_properties.description:
            current_shields.append('void')
        if '[Солнце]' in modifier_definition.display_properties.description:
            current_shields.append('solar')
        if '[Молния]' in modifier_definition.display_properties.description:
            current_shields.append('arc')

        if '[Пробивание щитов]' in modifier_definition.display_properties.description:
            current_champions.append('barrier')
        if '[Оглушение]' in modifier_definition.display_properties.description:
            current_champions.append('unstoppable')
        if '[Дестабилизация]' in modifier_definition.display_properties.description:
            current_champions.append('overload')

    return strike_nightfall.activity_hash, current_burn, current_weapons, \
        list(set(current_shields)), list(set(current_champions))


async def get_current_comp_box(client: CustomClient):
    mission_desc = await client.manifest.fetch(DestinyActivityDefinition, str(get_current_comp_mission()))
    await mission_desc.fetch_manifest_information()
    mission_desc: DestinyActivityDefinition

    background = Image.new('RGBA', (977, 570))
    draw = ImageDraw.Draw(background)
    font = ImageFont.truetype(f'{os.path.dirname(__file__)}/../assets/'
                              f'/fonts/Montserrat/Montserrat-Bold.ttf', size=48)
    name = mission_desc.display_properties.name.lower().replace(': классика', '').title()
    draw.text((90, 65), f"{name}", font=font)
    return background


def get_current_comp_mission():
    missions = {
        7: 2101866276,
        0: 2879686618,
        1: 2314609324,
        2: 4024253728,
        3: 2466996414,
        4: 1266868740,
        5: 264882961,
        6: 1152906386,
    }
    return missions[get_current_rotation(8)]


def get_dares_box():
    background = Image.new('RGBA', (977, 570))
    dares_rotation = get_current_dares_of_eternity()
    draw = ImageDraw.Draw(background)
    font = ImageFont.truetype(f'{os.path.dirname(__file__)}/../assets/'
                              f'/fonts/Montserrat/Montserrat-Bold.ttf', size=48)
    name = f"{dares_rotation[0]} > {dares_rotation[1]} > {dares_rotation[2]}"
    draw.text((90, 65), f"{name}", font=font)
    return background


def get_current_dares_of_eternity():
    dares = {
        2: ['Вексы', 'Кабал', 'Улей'],
        1: ['Улей', 'Падшие', 'Кабал'],
        0: ['Одержимые', 'Кабал', 'Вексы'],
        5: ['Кабал', 'Одержимые', 'Улей'],
        4: ['Улей', 'Вексы', 'Кабал'],
        3: ['Падшие', 'Улей', 'Вексы'],
    }
    return dares[get_current_rotation(6)]


async def create_nightmares_box():
    nightmares = get_current_nightmares()
    nightmares_box = Image.new('RGBA', (2160, 720))
    x, y = 0, 0
    for nightmare in nightmares:
        image = await open_image(nightmare[3])
        image = image.crop((280, 0, 1000, 720))
        nightmares_box.paste(image, (x, y))
        x += 720

    background = Image.open(f'{os.path.dirname(__file__)}/../assets/resets/raid.png')
    background_size = background.size
    background = background.resize(nightmares_box.size)
    background.paste(nightmares_box, mask=background)
    nightmares_box = background.resize(background_size)

    background = Image.new('RGBA', (977, 570))
    background.paste(nightmares_box, (90, 146), mask=nightmares_box)
    draw = ImageDraw.Draw(background)
    font_bold = ImageFont.truetype(f'{os.path.dirname(__file__)}/../assets/'
                                   f'/fonts/Montserrat/Montserrat-Bold.ttf', size=36)
    font_medium = ImageFont.truetype(f'{os.path.dirname(__file__)}/../assets/'
                                     f'/fonts/Montserrat/Montserrat-Medium.ttf', size=28)
    x, y = 90, 400
    for nightmare in nightmares:
        draw.text((x, y), f"{nightmare[0]}", font=font_bold)
        y += 40
        draw.text((x, y), f"{nightmare[1]}", font=font_medium, fill='#888888')
        y += 25
        draw.text((x, y), f"{nightmare[2]}", font=font_medium, fill='#888888')
        y -= 65
        x += 265

    return background


def get_current_nightmares():
    rotations = {
        0: [1342492675, 2450170731, 2639701103],
        1: [4098556693, 3205253945, 1188363426],
        2: [2639701103, 571058904, 1907493625],
        3: [2450170731, 1342492675, 4098556693],
        4: [1188363426, 1907493625, 3205253945],
        5: [2450170731, 2639701103, 571058904],
        6: [3205253945, 4098556693, 1342492675],
        7: [1907493625, 1188363426, 571058904]
    }
    nightmares_names = {
        2639701103: ['Безумие', 'Фанатик', '11 минут',
                     '/img/destiny_content/pgcr/nightmare_hunt_insanity.jpg'],
        571058904: ['Боль', 'Омнигул', '10 минут',
                    '/img/destiny_content/pgcr/nightmare_hunt_anguish.jpg'],
        2450170731: ['Отчаяние', 'Крота', '15 минут',
                     '/img/destiny_content/pgcr/nightmare_hunt_despair.jpg'],
        1342492675: ['Страх', 'Фогот', '10 минут',
                     '/img/destiny_content/pgcr/nightmare_hunt_fear.jpg'],
        3205253945: ['Одиночество', 'Таникс', '7 минут',
                     '/img/destiny_content/pgcr/nightmare_hunt_isolation.jpg'],
        1907493625: ['Гордыня', 'Сколас', '8 минут',
                     '/img/destiny_content/pgcr/nightmare_hunt_pride.jpg'],
        4098556693: ['Гнев', 'Гоул', '9 минут',
                     '/img/destiny_content/pgcr/nightmare_hunt_rage.jpg'],
        1188363426: ['Неволя', 'Зидрон', '12 минут',
                     '/img/destiny_content/pgcr/nightmare_hunt_servitude.jpg'],
    }
    result = []
    hashes = rotations[get_current_rotation(8)]
    for hash_id in hashes:
        result.append(nightmares_names[hash_id])
    return result


async def create_all_raids_box():
    raids_interval = 380
    background = Image.new('RGBA', (975, len(raids) * (300 + raids_interval)), (0, 0, 0, 0))
    current_raid = get_current_raid_rotation()
    x, y = 0, 0
    for raid in raids:
        if raid == current_raid:
            all_challenges = True
        else:
            all_challenges = False
        raid_box = await create_one_raid_box(raids[raid], all_challenges)
        background.paste(raid_box, (x, y), mask=raid_box)
        y += raids_interval
    return background


async def create_one_raid_box(raid, all_challenges=False):
    background = Image.new('RGBA', (975, 300), (0, 0, 0, 0))
    encounter_box = Image.new('RGBA', (42, 42), (0, 0, 0, 0))
    draw = ImageDraw.Draw(encounter_box)
    draw.rectangle((0, 0, 41, 41), outline='#999999', width=4)

    challenge_box = encounter_box.copy()
    draw = ImageDraw.Draw(challenge_box)
    draw.rectangle((7, 7, 34, 34), fill='#f0ff00')

    current_challenge = get_current_rotation(len(raid['challenges']))

    raid_icon = (await open_image(raid['icon'])).convert('RGBA')
    raid_icon_size = (96, 96)
    raid_icon = raid_icon.resize(raid_icon_size, Resampling.LANCZOS)

    background.paste(raid_icon, (0, 0), mask=raid_icon)
    x, y = 96 + 15, 0
    for challenge in raid['challenges']:
        if challenge == current_challenge or all_challenges:
            background.paste(challenge_box, (x, y), mask=challenge_box)
        else:
            background.paste(encounter_box, (x, y), mask=encounter_box)
        x += 42 + 6

    raid_name_font = ImageFont.truetype(f'{os.path.dirname(__file__)}/../assets/'
                                        f'/fonts/Montserrat/Montserrat-Bold.ttf', size=60)
    raid_desc_font = ImageFont.truetype(f'{os.path.dirname(__file__)}/../assets/'
                                        f'/fonts/Montserrat/Montserrat-Medium.ttf', size=30)
    x, y = 96 + 10, 42
    draw = ImageDraw.Draw(background)
    draw.text((x, y), raid['name'], font=raid_name_font)

    x, y = 96 + 15, 128
    draw.line((x, y, x + 880, y), fill='#424242', width=5)
    draw.line((x, y + 56, x + 880, y + 56), fill='#424242', width=5)
    if all_challenges:
        draw.text((x, y + 7), 'Недельная ротация', font=raid_desc_font, fill='#6ca0dc')
    else:
        draw.text((x, y + 7), raid['challenges'][current_challenge][0], font=raid_desc_font, fill='#6ca0dc')

    x, y = x, 190
    if all_challenges:
        draw.text((x, y), 'Доступны все испытания рейда', font=raid_desc_font, fill='#88898a')
    else:
        draw.multiline_text((x, y), textwrap.fill(raid['challenges'][current_challenge][1], 45),
                            font=raid_desc_font, fill='#88898a')

    return background
