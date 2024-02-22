import asyncio
import time
from typing import List
from urllib.request import urlopen

from PIL import Image
from bungio.models import DestinyInventoryItemDefinition, DestinyActivityDefinition, \
    DestinyActivityModifierReferenceDefinition, DestinyActivityModifierDefinition

from utils.bungio_client import CustomClient


class LostSectorModifiers:
    def __init__(self, client, sector: DestinyActivityDefinition):
        self._sector = sector
        self._client: CustomClient = client
        self.champions: List[DestinyActivityModifierReferenceDefinition] = []
        self.surge: List[DestinyActivityModifierReferenceDefinition] = []
        self.overcharged: List[DestinyActivityModifierReferenceDefinition] = []

    def __repr__(self):
        return f"{self._sector}> Champions: {self.champions}; Surge: {self.surge}; Overcharged: {self.overcharged}"

    async def init(self):
        champions_dict = {
            '[Дестабилизация]': await self._client.manifest.fetch(DestinyActivityModifierDefinition, str(1201462052)),
            '[Оглушение]': await self._client.manifest.fetch(DestinyActivityModifierDefinition, str(4218937993)),
            '[Пробивание щитов]': await self._client.manifest.fetch(DestinyActivityModifierDefinition, str(1974619026)),
        }
        for k in champions_dict:
            await champions_dict[k].fetch_manifest_information()

        await self._sector.fetch_manifest_information()
        for modifier in self._sector.modifiers:
            await modifier.fetch_manifest_information()
            if not modifier.manifest_activity_modifier_hash.display_in_nav_mode:
                continue
            mod_name = modifier.manifest_activity_modifier_hash.display_properties.name.lower()
            mod_desc = modifier.manifest_activity_modifier_hash.display_properties.description

            if 'воители' in mod_name:
                for champion_type in champions_dict:
                    if champion_type in mod_desc:
                        self.champions.append(champions_dict[champion_type])

            elif 'мощь' in mod_name:
                self.surge.append(modifier)

            elif 'сверхзаря' in mod_name and 'var' in mod_desc:
                self.overcharged.append(modifier)


class LostSectorDrop:
    def __init__(self, client, name, icon_path, items):
        self._client = client
        self.name = name
        self.icon = icon_path
        self._items_hashes = items
        self.items = None

    async def init(self):
        self.icon = Image.open(self.icon).convert('RGBA')
        self.items = [await self._client.manifest.fetch(DestinyInventoryItemDefinition, item)
                      for item in self._items_hashes]
        for item in self.items:
            await item.fetch_manifest_information()


class LostSector:
    def __init__(self, client, activity_hash, drop: LostSectorDrop):
        self._client = client
        self._activity_hash = activity_hash
        self.activity = None
        self.drop = drop

    async def init(self):
        self.activity = await self._client.manifest.fetch(DestinyActivityDefinition, self._activity_hash)
        await self.activity.fetch_manifest_information()


def get_current_rotation_day(count, delta=0):
    day = 86400
    current_time = int(time.time()) + abs(delta)
    return (abs(current_time - 1600794000) // day) % count


async def open_image(link) -> Image:
    if link[0] == '/':
        link = f'https://www.bungie.net{link}'
    image_raw = await asyncio.get_event_loop().run_in_executor(None, urlopen, link)
    image = await asyncio.get_event_loop().run_in_executor(None, Image.open, image_raw)
    return image
