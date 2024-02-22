import datetime
import io
import os

import discord
from discord import app_commands, Permissions, Interaction
from discord.ext import commands, tasks

from utils.CustomCog import CustomCog

from dotenv import load_dotenv

from utils.Resets.lost_sectors import create_lost_sector_image
from utils.Resets.resets_utils import LostSectorDrop, LostSector, get_current_rotation_day
from utils.Resets.weekly import create_weekly_picture
from utils.get_last_reset import get_last_reset, get_last_reset_day
from utils.logger import create_logger

load_dotenv(override=True)

main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))

logger = create_logger(__name__)


class ResetsCog(CustomCog):
    """Работает с игровыми ресетами."""

    def __init__(self, bot):
        super().__init__(bot)
        self.drop = {
            'legs': None,
            'hands': None,
            'chest': None,
            'head': None
        }

    async def init_config(self):
        self.config = {
            'bungie_id_for_resets': 21667205,
            'resets_channel': 1128208145542565981,

            'last_weekly_post': 1690909500,
            'last_weekly_message': None,

            'last_friday_post': None,
            'last_friday_message': None,

            'last_daily_post': 1691255100,
            'last_daily_message': None,

            'lost_sector_items': {
                'legs': [1624882687,
                         511888814,
                         1702288800,
                         3045642045,
                         1453120846,
                         1001356380,
                         2463947681,
                         2390471904,
                         3637722482],
                'hands': [1703598057,
                          1443166262,
                          3453042252,
                          3259193988,
                          2169905051,
                          300502917,
                          3267996858,
                          2780717641,
                          1467044898,
                          2415768376,
                          3831935023,
                          3093309525],
                'chest': [461841403,
                          1322544481,
                          3301944824,
                          2321120637,
                          1935198785,
                          90009855],
                'head': [1619425569,
                         3974038291,
                         2316914168,
                         1703551922,
                         3316517958,
                         1849149215,
                         3574051505,
                         192896783,
                         2374129871],
            },
            'lost_sector_rotation': {
                '0': 2571435846,
                '1': 457172845,
                '2': 628527323,
                '3': 2310698352,
                '4': 2504276276,
                '5': 1174061505,
                '6': 1525311377,
                '7': 3229581104,
                '8': 1956131625,
                '9': 212477858,
                '10': 1509764575,
            },
            'lost_sector_drop_rotation': {
                0: 'legs',
                1: 'hands',
                2: 'chest',
                3: 'head',
            }
        }

    async def send_weekly(self):
        logger.info('Формируется недельный ресет')
        if self.config['resets_channel']:
            try:
                channel = await self.bot.get_guild(main_guild_id).fetch_channel(self.config['resets_channel'])
                auth = await self.bot.get_valid_auth(self.config['bungie_id_for_resets'])
                image = await create_weekly_picture(client=self.bot.bungio_client, auth=auth)
                with io.BytesIO() as image_binary:
                    image.save(image_binary, 'PNG')
                    image_binary.seek(0)
                    new_weekly: discord.Message = await channel.send(file=discord.File(fp=image_binary,
                                                                                       filename='weekly.png'))
                if self.config['last_weekly_message']:
                    try:
                        weekly_message: discord.Message = await channel.fetch_message(self.config['last_weekly_message'])
                        await weekly_message.delete()
                    except Exception as e:
                        logger.exception(e)
                self.config['last_weekly_message'] = new_weekly.id
                self.config['last_weekly_post'] = new_weekly.created_at.replace(microsecond=0).timestamp()
                await self.save_config()
            except Exception as e:
                logger.exception(e)

    async def send_daily(self):
        logger.info('Формируется дневной ресет')
        if self.config['resets_channel']:
            try:
                channel = await self.bot.get_guild(main_guild_id).fetch_channel(self.config['resets_channel'])
                image = await self.get_lost_sector_image()
                with io.BytesIO() as image_binary:
                    image.save(image_binary, 'PNG')
                    image_binary.seek(0)
                    sectors: discord.Message = await channel.send(file=discord.File(fp=image_binary,
                                                                                    filename='image.png'))
                if self.config['last_daily_message']:
                    try:
                        sectors_message: discord.Message = await channel.fetch_message(self.config['last_daily_message'])
                        await sectors_message.delete()
                    except Exception as e:
                        logger.exception(e)
                self.config['last_daily_message'] = sectors.id
                self.config['last_daily_post'] = sectors.created_at.replace(microsecond=0).timestamp()
                await self.save_config()
            except Exception as e:
                logger.exception(e)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.init_sectors_drop()
        self.check_resets.start()

    @tasks.loop(minutes=1)
    async def check_resets(self):
        last_post = datetime.datetime.fromtimestamp(self.config['last_weekly_post'])
        current_message_last_reset = get_last_reset(date=last_post)
        current_last_reset = get_last_reset()
        if current_last_reset - current_message_last_reset >= datetime.timedelta(days=7):
            await self.send_weekly()

        last_post = datetime.datetime.fromtimestamp(self.config['last_daily_post'])
        current_message_last_reset = get_last_reset_day(date=last_post)
        current_last_reset = get_last_reset_day()
        if current_last_reset - current_message_last_reset >= datetime.timedelta(days=1):
            await self.send_daily()

    async def on_config_update(self):
        await self.load_config()
        await self.init_sectors_drop()

    async def init_sectors_drop(self):
        legs = LostSectorDrop(client=self.bot.bungio_client,
                              name='Экзотическая броня для ног',
                              icon_path='utils/assets/lost_sectors/armor/legs.png',
                              items=self.config.get('lost_sector_items', {}).get('legs', [])
                              )
        await legs.init()
        self.drop['legs'] = legs
        hands = LostSectorDrop(client=self.bot.bungio_client,
                               name='Экзотическая рукавицы',
                               icon_path='utils/assets/lost_sectors/armor/hands.png',
                               items=self.config.get('lost_sector_items', {}).get('hands', [])
                               )
        await hands.init()
        self.drop['hands'] = hands
        chest = LostSectorDrop(client=self.bot.bungio_client,
                               name='Экзотический нагрудник',
                               icon_path='utils/assets/lost_sectors/armor/chest.png',
                               items=self.config.get('lost_sector_items', {}).get('chest', [])
                               )
        await chest.init()
        self.drop['chest'] = chest
        head = LostSectorDrop(client=self.bot.bungio_client,
                              name='Экзотический шлем',
                              icon_path='utils/assets/lost_sectors/armor/head.png',
                              items=self.config.get('lost_sector_items', {}).get('head', [])
                              )
        await head.init()
        self.drop['head'] = head

    async def get_lost_sector_image(self):
        lost_sectors_to_render = {}
        # На 4 дня (сегодня + 3 дня вперед)
        for i in range(4):
            sector_rotation = get_current_rotation_day(count=len(self.config.get('lost_sector_rotation', [])),
                                                       delta=i * 86400)
            sector_drop = get_current_rotation_day(count=len(self.config.get('lost_sector_drop_rotation', [])),
                                                   delta=i * 86400)
            sector_drop_obj = self.drop[self.config.get('lost_sector_drop_rotation')[str(sector_drop)]]
            lost_sectors_to_render[i] = LostSector(client=self.bot.bungio_client,
                                                   activity_hash=
                                                   self.config.get('lost_sector_rotation')[str(sector_rotation)],
                                                   drop=
                                                   sector_drop_obj
                                                   )
            await lost_sectors_to_render[i].init()
        image = await create_lost_sector_image(client=self.bot.bungio_client,
                                               date=datetime.datetime.now(),
                                               lost_sectors=lost_sectors_to_render)
        return image

    resets_group = app_commands.Group(name="resets",
                                      description="Команды для игровых ресетов",
                                      guild_ids=[main_guild_id],
                                      default_permissions=Permissions(8))

    @resets_group.command(name='sectors')
    async def lost_sector_test(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.send_daily()
        await interaction.followup.send('Изображение секторов отправлено!')

    @resets_group.command(name='weekly')
    async def create_weekly_picture(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.send_weekly()
        await interaction.followup.send('Изображение недельного ресета отправлено!')


async def setup(bot):
    await bot.add_cog(ResetsCog(bot))
    logger.info(f'Расширение {ResetsCog} загружено!')
