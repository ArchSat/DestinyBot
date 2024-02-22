import logging
import os
from typing import Optional, List

import discord
from discord import app_commands, Interaction, Permissions
from discord.ext import commands, tasks
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from tabulate import tabulate
from utils.logger import create_logger
from ORM.schemes.Clan import Clan
from utils.clan_stats_utils import create_stats_table, update_stats_in_google_sheets
from utils.db_utils import get_full_clans

logger = create_logger(__name__)

main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))


class ClanCog(commands.Cog):
    """Модуль, добавляющий функционал управления кланами"""

    def __init__(self, bot):
        self.bot = bot
        self.auto_update.start()

    clan_group = app_commands.Group(name="clan",
                                    description="Команды управления кланами в БД",
                                    guild_ids=[main_guild_id],
                                    default_permissions=Permissions(8)
                                    )

    @clan_group.command(name='add', description='Добавляет или изменяет клан в БД')
    async def clan_add_command(self, interaction: Interaction,
                               clan_id: int,
                               clan_tag:
                               Optional[str],
                               visible: Optional[bool]):
        if visible is None:
            visible = True
        new_clan = Clan(clan_id=clan_id, clan_tag=clan_tag, visible=visible)
        async with AsyncSession(self.bot.db_engine) as session:
            await session.merge(new_clan)
            try:
                await session.commit()
                error = False
            except Exception as e:
                error = True
                logger.exception(e)
                await session.rollback()
        if not error:
            await interaction.response.send_message(f'Клан {clan_id} добавлен в БД')
        else:
            await interaction.response.send_message(f'При добавлении клана в БД произошла ошибка')

    @clan_group.command(name='list', description='Выводит список кланов в БД')
    async def clan_list_command(self, interaction: Interaction):
        clan_table = [['ID', 'Tag', 'Visible']]
        clan_list = await get_full_clans(self.bot.db_engine)
        clan_table += [[clan.clan_id, clan.clan_tag, clan.visible] for clan in clan_list]
        await interaction.response.send_message("```" + tabulate(clan_table) + "```")

    async def clan_list_autocomplete(self,
                                     interaction: discord.Interaction,
                                     current: str,
                                     ) -> List[app_commands.Choice[str]]:
        clan_list = await get_full_clans(self.bot.db_engine)
        result_list = []
        for clan in clan_list:
            if clan.clan_tag:
                if current.lower() in clan.clan_tag.lower():
                    result_list.append(app_commands.Choice(name=f'Клан {clan.clan_tag} - {clan.clan_id}',
                                                           value=clan.clan_id))
            else:
                if current.lower() in str(clan.clan_id):
                    result_list.append(app_commands.Choice(name=f'Клан {clan.clan_tag} - {clan.clan_id}',
                                                           value=clan.clan_id))
        return result_list[:25]

    @clan_group.command(name='remove', description='Удаляет клан из БД')
    @app_commands.autocomplete(clan_id=clan_list_autocomplete)
    async def clan_remove_command(self, interaction: Interaction, clan_id: int):
        async with AsyncSession(self.bot.db_engine) as session:
            await session.execute(delete(Clan).where(Clan.clan_id == clan_id))
            await session.commit()
        await interaction.response.send_message(f'Клан {clan_id} удален из БД')

    stats_group = app_commands.Group(name="stats",
                                     description="Команды управления статистикой",
                                     guild_ids=[main_guild_id],
                                     default_permissions=Permissions(administrator=True)
                                     )

    @tasks.loop(minutes=5)
    async def auto_update(self):
        logger.debug('auto_update')
        await self.bot.wait_until_ready()
        logger.info('Начало обновления статистики')
        try:
            table = await create_stats_table(self.bot.db_engine, await self.bot.fetch_guild(main_guild_id))
            await update_stats_in_google_sheets(table)
        except Exception as e:
            logger.exception(e)

    @stats_group.command(name='update', description='Обновляет таблицу статистики')
    async def stats_update_command(self, interaction: Interaction):
        self.auto_update.restart()
        await interaction.response.send_message('Задача обновления статистики перезапущена')


async def setup(bot):
    await bot.add_cog(ClanCog(bot))
    logger.info(f'Расширение {ClanCog} загружено!')
