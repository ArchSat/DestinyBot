"""

    async with AsyncSession(ORM.engine) as session:
        q = select(RoleRequirementGroup).options(selectinload(RoleRequirementGroup.requirements_Role),
                                                 selectinload(RoleRequirementGroup.requirements_TriumphScore))
        test = await session.scalars(q)
        test: RoleRequirementGroup = list(test)[0]
        print(test.requirements_Role[0].role_id)
    return



    main_profile = await get_main_destiny_profile(bungie_id_list[1])
    metrics_and_records: DestinyProfileResponse = await main_profile.get_profile(components=
                                                                                 [DestinyComponentType.METRICS,
                                                                                  DestinyComponentType.RECORDS])
    historical_stats = await main_profile.get_historical_stats_for_account(groups=[DestinyStatsGroupType.GENERAL])
    print(historical_stats.merged_all_characters.results['allPvE'].all_time['totalActivityDurationSeconds'].basic.value)
    print(historical_stats.merged_all_characters)
    for stat in historical_stats.merged_all_characters.results['allPvE'].all_time:
        print(stat)


"""
import io
import logging
import os
import time
from copy import copy, deepcopy
from typing import Union, List

import bungio.models.base
import discord
from PIL import Image
from bungio.error import BungieException
from bungio.models import DestinyMetricDefinition, DestinyRecordDefinition, DestinyHistoricalStatsDefinition, \
    DestinyObjectiveDefinition
from discord import app_commands, Interaction, Permissions, WebhookMessage
from discord.ext import commands
from discord.webhook.async_ import MISSING
from dotenv import load_dotenv
from sqlalchemy import select, delete, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ORM.schemes.Roles import RoleRequirementGroup, RequirementHistoricalStat, RequirementRole, \
    RequirementTriumphScore, \
    RequirementMetricScore, RequirementTriumphCompleted, RequirementStatement, RequirementsType, HistoricalStatsGroup, \
    RequirementObjectivesCompleted, get_all_nodes, RolesTree, RequirementObjectivesValues
from utils.CustomCog import CustomCog
from utils.Roles.roles import get_roles_requirements, render_new_requirements_group, render_requirements_group, \
    render_requirements_group_image, \
    validate_requirements, RoleSelectorView
from utils.logger import create_logger
from utils.users_utils import get_user_stats, get_main_bungie_id_by_discord_id

load_dotenv(override=True)
logger = create_logger(__name__)
main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))


def create_reaction_roles_embed(roles_list):
    emb = discord.Embed(title=f'Доступные роли', colour=discord.Color.green())
    reactions = ''
    for role in roles_list:
        reactions += f'{role[1]} - {role[0].name}\n'
    emb.add_field(name='Для получения роли поставьте реакцию под этим сообщением:', value=reactions, inline=False)
    return emb


class RolesCog(CustomCog):
    """Тестовый модуль"""

    def __init__(self, bot):
        super().__init__(bot)
        self.roles_requirements = {}
        self.roles_trees = {}
        self.roles_list = []

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        emoji_list = {str(emoji): role for role, emoji in self.roles_list}
        emoji = str(payload.emoji)
        if emoji in emoji_list:
            if emoji_list[emoji] in payload.member.roles:
                await payload.member.remove_roles(emoji_list[emoji])
            else:
                await payload.member.add_roles(emoji_list[emoji])
            guild = self.bot.get_guild(payload.guild_id)
            channel = guild.get_channel(payload.channel_id)
            message: discord.Message = await channel.fetch_message(payload.message_id)
            await message.remove_reaction(payload.emoji, payload.member)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.update_roles_requirements()
        await self.update_roles_trees()
        while True:
            roles_list = []
            for role_id in self.config['reaction_roles']:
                role_emoji = self.config['reaction_roles'][role_id]
                if isinstance(role_emoji, int):
                    role_emoji = self.bot.get_emoji(role_emoji)
                role = self.bot.get_guild(main_guild_id).get_role(int(role_id))
                roles_list.append((role, role_emoji))
            self.roles_list = roles_list
            if self.roles_list:
                break

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        async with AsyncSession(self.bot.db_engine) as session:
            query = delete(RolesTree).where(RolesTree.role_id == role.id)
            await session.execute(query)
            await session.commit()
        await self.update_roles_trees()
        return role

    async def update_roles_trees(self):
        self.roles_trees = {node.role_id: node for node in await get_all_nodes(self.bot.db_engine)}

    async def update_roles_requirements(self):
        self.roles_requirements = await get_roles_requirements(self.bot.db_engine)

    async def init_config(self):
        self.config = {
            'roles_deny_unrole': [],
            'reaction_roles_channel_id': None,
            'reaction_roles_message_id': None,
            'reaction_roles': {
                '1128208142124191772': 1053322497254232104
            }
        }

    async def on_config_update(self):
        await self.load_config()
        if not self.config['reaction_roles_channel_id'] or not self.config['reaction_roles_message_id']:
            return
        roles_list = []
        for role_id in self.config['reaction_roles']:
            role_emoji = self.config['reaction_roles'][role_id]
            if isinstance(role_emoji, int):
                role_emoji = self.bot.get_emoji(role_emoji)
            role = self.bot.get_guild(main_guild_id).get_role(int(role_id))
            roles_list.append((role, role_emoji))
        channel = await self.bot.get_guild(main_guild_id).fetch_channel(self.config['reaction_roles_channel_id'])
        message: discord.Message = await channel.fetch_message(self.config['reaction_roles_message_id'])
        await message.clear_reactions()
        await message.edit(embed=create_reaction_roles_embed(roles_list=roles_list))
        for role, emoji in roles_list:
            await message.add_reaction(emoji)
        self.roles_list = roles_list

    @app_commands.command(name='post_other_games')
    @app_commands.default_permissions(administrator=True)
    @app_commands.guilds(main_guild_id)
    async def post_other_games_message(self, interaction: Interaction):
        roles_list = []
        for role_id in self.config['reaction_roles']:
            role_emoji = self.config['reaction_roles'][role_id]
            if isinstance(role_emoji, int):
                role_emoji = self.bot.get_emoji(role_emoji)
            role = self.bot.get_guild(main_guild_id).get_role(int(role_id))
            roles_list.append((role, role_emoji))
        message = await interaction.channel.send(embed=create_reaction_roles_embed(roles_list=roles_list))
        for role, emoji in roles_list:
            await message.add_reaction(emoji)
        self.config['reaction_roles_channel_id'] = message.channel.id
        self.config['reaction_roles_message_id'] = message.id
        await self.save_config()
        self.roles_list = roles_list

    @app_commands.command(name='unrole')
    @app_commands.default_permissions(administrator=True)
    @app_commands.guilds(main_guild_id)
    @app_commands.describe(role='Роль, которую необходимо снять',
                           limit='Роль, ограничивающая выборку всех пользователей до одной роли')
    async def unrole_command(self, interaction: Interaction, role: discord.Role, limit: Union[discord.Role, None]):
        """
        Снимает указанную роль со !!!всех!!! участников сервера
        """
        if role.id in self.config['roles_deny_unrole']:
            await interaction.response.send_message('Данную роль снимать нельзя!')
            return
        await interaction.response.defer(thinking=True)
        for user in interaction.guild.members:
            if role in user.roles:
                if limit is None or (limit and user.get_role(limit.id)):
                    await user.remove_roles(role, reason=f'Роль снята {interaction.user}')
        await interaction.followup.send(f'Роль {role.mention} снята со всех участников сервера!')

    roles_management_group = app_commands.Group(name="roles",
                                                description='Редактирование критериев выдачи ролей',
                                                guild_ids=[main_guild_id],
                                                default_permissions=Permissions(8),
                                                )

    roles_overrides_group = app_commands.Group(name='override',
                                               description='Создает ребро графа иерархии ролей '
                                                           'между двумя ролями',
                                               parent=roles_management_group)

    @roles_overrides_group.command(name='add', description='Создает ребро графа иерархии ролей '
                                                           'между двумя ролями')
    @app_commands.describe(master_role='Эта роль будет перезаписывать slave_role',
                           slave_role='Эта роль будет перезаписываться master_role')
    async def roles_override_add_command(self, interacion: Interaction,
                                         master_role: discord.Role,
                                         slave_role: discord.Role):
        await interacion.response.defer(thinking=True)
        await self.update_roles_trees()
        if master_role.id in self.roles_trees:
            parents = []
            parent = self.roles_trees[master_role.id].parent
            while parent:
                parents.append(parent.role_id)
                parent = parent.parent
            if slave_role.id in parents:
                return await interacion.followup.send('Найдена попытка создать цикл в иерархии ролей!\n'
                                                      'Связь не была создана!')

        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            master_role_tree = await session.scalar(select(RolesTree).options(selectinload(RolesTree.children)).
                                                    where(RolesTree.role_id == master_role.id))
            slave_role_tree = await session.scalar(select(RolesTree).options(selectinload(RolesTree.children)).
                                                   where(RolesTree.role_id == slave_role.id))
            if not master_role_tree:
                master_role_tree = RolesTree(role_id=master_role.id)
                session.add(master_role_tree)
                await session.merge(master_role_tree)
            if slave_role_tree:
                slave_role_tree.parent_id = master_role_tree.role_id
            else:
                slave_role_tree = RolesTree(role_id=slave_role.id, parent_id=master_role_tree.role_id)
                session.add(slave_role_tree)
            await session.merge(master_role_tree)
            await session.merge(slave_role_tree)
            await session.commit()
        await self.update_roles_trees()
        await interacion.followup.send(f'Роль {master_role} будет выдаваться вместо '
                                       f'{slave_role} при выполнении требований!')

    @roles_overrides_group.command(name='remove', description='Удаляет вершину графа иерархии ролей (роль)')
    @app_commands.describe(role='Роль для удаления из иерархии')
    async def roles_override_add_command(self, interacion: Interaction,
                                         role: discord.Role):
        await interacion.response.defer(thinking=True)
        deleted = await self.on_guild_role_delete(role)
        if deleted:
            await interacion.followup.send(f'Роль {deleted} удалена из иерархии ролей!')
        else:
            await interacion.followup.send(f'Роль не удалена!')

    @roles_overrides_group.command(name='list', description='Показывает все доступные в данный момент деревья ролей')
    async def roles_override_list_command(self, interacion: Interaction):
        await interacion.response.defer()
        for role_id in self.roles_trees:
            if not self.roles_trees[role_id].children:
                await interacion.channel.send(self.roles_trees[role_id])
        await interacion.followup.send('Все доступные деревья ролей:')

    roles_requirements_group = app_commands.Group(name="requirements",
                                                  description='Редактирование критериев выдачи ролей',
                                                  guild_ids=[main_guild_id],
                                                  default_permissions=Permissions(8),
                                                  parent=roles_management_group
                                                  )

    @roles_requirements_group.command(name="remove",
                                      description='Удаление конкретного требования к роли')
    @app_commands.describe(requirement_type='Тип требования',
                           requirement_id='Идентификатор требования')
    async def requirement_remove(self, interaction: Interaction,
                                 requirement_type: RequirementsType,
                                 requirement_id: int):
        async with AsyncSession(self.bot.db_engine) as session:
            query = delete(requirement_type.value).where(requirement_type.value.requirement_id == requirement_id)
            await session.execute(query)
            await session.commit()
            await interaction.response.send_message('Требование к роли удалено!')

    @roles_management_group.command(name='list', description='Список требований к ролям')
    @app_commands.describe(group_id='Идентификатор группы требований')
    async def show_requirements(self, interaction: Interaction, group_id: Union[int, None],
                                role: Union[discord.Role, None]):
        await interaction.response.defer()
        await self.update_roles_requirements()
        if not group_id and not role:
            new_image_x = []
            new_image_y = 0
            roles_images = []
            for group_id in self.roles_requirements:
                group: RoleRequirementGroup = self.roles_requirements[group_id]
                image = await render_requirements_group_image(group,
                                                              client=self.bot.bungio_client,
                                                              guild=interaction.guild,
                                                              need_id=True)
                if not image:
                    continue
                roles_images.append(image)
                new_image_x.append(image.size[0])
                new_image_y += image.size[1]
                new_image_y += 100
            result_image = Image.new('RGBA', (max(new_image_x), new_image_y), (0, 0, 0, 255))
            x, y = 0, 0
            for image in roles_images:
                result_image.paste(image, (x, y), mask=image)
                y += image.size[1]
                y += 100

            with io.BytesIO() as image_binary:
                result_image.save(image_binary, 'PNG')
                image_binary.seek(0)
                await interaction.followup.send(file=discord.File(fp=image_binary, filename='image.png'))

            return await interaction.followup.send(f'Список идентификаторов требований: '
                                                   f'{self.roles_requirements.keys()}')
        if group_id:
            result_image = await render_requirements_group_image(self.roles_requirements[group_id],
                                                                 client=self.bot.bungio_client,
                                                                 guild=interaction.guild,
                                                                 need_id=True)
            if not result_image:
                return await interaction.followup.send('Эта группа требований не содержит трабований!')
            with io.BytesIO() as image_binary:
                result_image.save(image_binary, 'PNG')
                image_binary.seek(0)
                return await interaction.followup.send(file=discord.File(fp=image_binary, filename='image.png'))
        if role:
            result = []
            for req in self.roles_requirements:
                if self.roles_requirements[req].role_id == role.id:
                    result.append(req)
            if not result:
                return await interaction.followup.send('С этой группой нет связанных требований!')
            else:
                return await interaction.followup.send('С этой группой связаны следующие требования: ' +
                                                       ', '.join([str(r) for r in result]))

    @roles_management_group.command(name='sort', description='Изменить значение для сортировки для группы')
    @app_commands.describe(group_id='Идентификатор группы требований',
                           sort_key='Значение для сортировки')
    async def sort_requirements(self, interaction: Interaction, group_id: int,
                                sort_key: int):
        await interaction.response.defer()
        async with AsyncSession(self.bot.db_engine) as session:
            await session.execute(update(RoleRequirementGroup).
                                  where(RoleRequirementGroup.group_id == group_id).
                                  values(sort_key=sort_key))
            await session.commit()
        await interaction.followup.send('Значение ключа сортировки обновлено')

    @roles_management_group.command(name='add', description='Создание группы требований к роли')
    @app_commands.describe(role='К какой роли создать группу требований',
                           sort_key='Порядок для сортировки')
    async def create_requirement_group(self, interaction: Interaction, role: discord.Role, sort_key: Union[int, None]):
        await interaction.response.defer()
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            new_group = RoleRequirementGroup(role_id=role.id,
                                             sort_key=sort_key)
            new_group = await session.merge(new_group)
            await session.commit()
        embed = render_new_requirements_group(new_group)
        await self.update_roles_requirements()
        await interaction.followup.send(embed=embed)

    @roles_management_group.command(name='remove', description='Удаление группы требований к роли')
    @app_commands.describe(group_id='Идентификатор группы требований')
    async def remove_requirement_group(self, interaction: Interaction, group_id: int):
        await interaction.response.defer()
        async with AsyncSession(self.bot.db_engine) as session:
            query = delete(RoleRequirementGroup).where(RoleRequirementGroup.group_id == group_id)
            await session.execute(query)
            await session.commit()
            await interaction.followup.send('Группа требований удалена!')
        await self.update_roles_requirements()

    @roles_requirements_group.command(name='add_triumph_score', description='Требование к количеству активных триумфов')
    @app_commands.describe(group_id='Идентификатор группы требований',
                           statement='Операция, применяемая к указанному значению',
                           value='Значение требования',
                           custom_text='Кастомный текст для отображения на изображениях')
    async def create_requirement_triumph_score(self, interaction: Interaction,
                                               group_id: int,
                                               statement: RequirementStatement,
                                               value: int,
                                               custom_text: Union[str, None]):
        await interaction.response.defer()
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            new_requirement = RequirementTriumphScore(group_id=group_id,
                                                      statement=statement,
                                                      value=value,
                                                      custom_text=custom_text)
            await session.merge(new_requirement)
            await session.commit()
        await self.update_roles_requirements()
        embed = await render_requirements_group(self.roles_requirements[group_id], client=self.bot.bungio_client)
        await interaction.followup.send(embed=embed)

    @roles_requirements_group.command(name='add_role', description='Требование к наличию других ролей')
    @app_commands.describe(group_id='Идентификатор группы требований',
                           role='Запрашиваемая роль',
                           custom_text='Кастомный текст для отображения на изображениях')
    async def create_requirement_role(self, interaction: Interaction,
                                      group_id: int,
                                      role: discord.Role,
                                      custom_text: Union[str, None]):
        await interaction.response.defer()
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            new_requirement = RequirementRole(group_id=group_id,
                                              role_id=role.id,
                                              custom_text=custom_text)
            await session.merge(new_requirement)
            await session.commit()
        await self.update_roles_requirements()
        embed = await render_requirements_group(self.roles_requirements[group_id], client=self.bot.bungio_client)
        await interaction.followup.send(embed=embed)

    @roles_requirements_group.command(name='add_metric_score', description='Требование к метрикам')
    @app_commands.describe(group_id='Идентификатор группы требований',
                           metric_hash='Хеш метрики',
                           statement='Операция, применяемая к указанному значению',
                           value='Значение требования',
                           custom_text='Кастомный текст для отображения на изображениях')
    async def create_requirement_metric_score(self, interaction: Interaction,
                                              group_id: int,
                                              metric_hash: int,
                                              statement: RequirementStatement,
                                              value: int,
                                              custom_text: Union[str, None]):
        await interaction.response.defer()

        metric_definition = await self.bot.bungio_client.manifest.fetch(DestinyMetricDefinition, metric_hash)
        if not metric_definition:
            return await interaction.followup.send('Метрика с таким хешем не найдена!')
        else:
            await metric_definition.fetch_manifest_information()
            metric_definition: DestinyMetricDefinition
            await interaction.followup.send(f'Выбранная метрика: {metric_definition.display_properties.name}\n'
                                            f'{metric_definition.display_properties.description}')

        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            new_requirement = RequirementMetricScore(group_id=group_id,
                                                     metric_hash=metric_hash,
                                                     statement=statement,
                                                     value=value,
                                                     custom_text=custom_text)
            await session.merge(new_requirement)
            await session.commit()
        await self.update_roles_requirements()
        embed = await render_requirements_group(self.roles_requirements[group_id], client=self.bot.bungio_client)
        await interaction.followup.send(embed=embed)

    @roles_requirements_group.command(name='add_triumph', description='Требование к триумфам')
    @app_commands.describe(group_id='Идентификатор группы требований',
                           record_hash='Хеш триумфа',
                           completed='Триумф должна быть получен / не должен быть получен',
                           custom_text='Кастомный текст для отображения на изображениях')
    async def create_requirement_triumph(self, interaction: Interaction,
                                         group_id: int,
                                         record_hash: int,
                                         completed: bool,
                                         custom_text: Union[str, None]):
        await interaction.response.defer()

        record_definition = await self.bot.bungio_client.manifest.fetch(DestinyRecordDefinition, record_hash)
        if not record_definition:
            return await interaction.followup.send('Метрика с таким хешем не найдена!')
        else:
            await record_definition.fetch_manifest_information()
            record_definition: DestinyRecordDefinition
            await interaction.followup.send(f'Выбранный триумф: {record_definition.display_properties.name}\n'
                                            f'{record_definition.display_properties.description}')

        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            new_requirement = RequirementTriumphCompleted(group_id=group_id,
                                                          record_hash=record_hash,
                                                          completed=completed,
                                                          custom_text=custom_text)
            await session.merge(new_requirement)
            await session.commit()
        await self.update_roles_requirements()
        embed = await render_requirements_group(self.roles_requirements[group_id], client=self.bot.bungio_client)
        await interaction.followup.send(embed=embed)

    @roles_requirements_group.command(name='add_hist_stat', description='Требование к метрикам')
    @app_commands.describe(group_id='Идентификатор группы требований',
                           historical_stat_group='Группа статистики',
                           historical_stat_name='Уникальное имя статистики',
                           statement='Операция, применяемая к указанному значению',
                           value='Значение требования',
                           custom_text='Кастомный текст для отображения на изображениях')
    async def create_requirement_hist_stat(self, interaction: Interaction,
                                           group_id: int,
                                           historical_stat_group: HistoricalStatsGroup,
                                           historical_stat_name: str,
                                           statement: RequirementStatement,
                                           value: int,
                                           custom_text: Union[str, None]):
        await interaction.response.defer()

        historical_stats_definition = await self.bot.bungio_client.api.get_historical_stats_definition()
        stat_definition: DestinyHistoricalStatsDefinition = \
            historical_stats_definition.get(historical_stat_name, None)
        if not stat_definition:
            return await interaction.followup.send('Статистика с указанным именем не найдена!')
        else:
            await stat_definition.fetch_manifest_information()
            await interaction.followup.send(f'Выбранная статистика: {stat_definition.stat_id}\n'
                                            f'{stat_definition.stat_description}')

        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            new_requirement = RequirementHistoricalStat(group_id=group_id,
                                                        historical_stat_group=historical_stat_group,
                                                        historical_stat_name=historical_stat_name,
                                                        statement=statement,
                                                        value=value,
                                                        custom_text=custom_text)
            await session.merge(new_requirement)
            await session.commit()
        await self.update_roles_requirements()
        embed = await render_requirements_group(self.roles_requirements[group_id], client=self.bot.bungio_client)
        await interaction.followup.send(embed=embed)

    @roles_requirements_group.command(name='add_objective_completed',
                                      description='Требование к составным элементам триумфов (ObjectiveDefinition)')
    @app_commands.describe(group_id='Идентификатор группы требований',
                           objective_hash='Хеш объекта (ObjectiveDefinition)',
                           completed='Триумф должна быть получен / не должен быть получен',
                           custom_text='Кастомный текст для отображения на изображениях')
    async def create_requirement_objective_completed(self, interaction: Interaction,
                                                     group_id: int,
                                                     objective_hash: int,
                                                     completed: bool,
                                                     custom_text: Union[str, None]):
        await interaction.response.defer()

        objective_definition = await self.bot.bungio_client.manifest.fetch(DestinyObjectiveDefinition, objective_hash)
        if not objective_definition:
            return await interaction.followup.send('Цель с таким хешем не найдена!')
        else:
            await objective_definition.fetch_manifest_information()
            await interaction.followup.send(f'Выбранная цель: {objective_definition.progress_description}')

        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            new_requirement = RequirementObjectivesCompleted(group_id=group_id,
                                                             objective_hash=objective_hash,
                                                             completed=completed,
                                                             custom_text=custom_text)
            await session.merge(new_requirement)
            await session.commit()
        await self.update_roles_requirements()
        embed = await render_requirements_group(self.roles_requirements[group_id], client=self.bot.bungio_client)
        await interaction.followup.send(embed=embed)

    @roles_requirements_group.command(name='add_objective_values',
                                      description='Требование к составным элементам триумфов (ObjectiveDefinition)')
    @app_commands.describe(group_id='Идентификатор группы требований',
                           objective_hash='Хеш объекта (ObjectiveDefinition)',
                           statement='Операция, применяемая к указанному значению',
                           value='Значение требования',
                           custom_text='Кастомный текст для отображения на изображениях')
    async def create_requirement_objective_values(self, interaction: Interaction,
                                                  group_id: int,
                                                  objective_hash: int,
                                                  statement: RequirementStatement,
                                                  value: int,
                                                  custom_text: Union[str, None]):
        await interaction.response.defer()

        objective_definition = await self.bot.bungio_client.manifest.fetch(DestinyObjectiveDefinition, objective_hash)
        if not objective_definition:
            return await interaction.followup.send('Цель с таким хешем не найдена!')
        else:
            await objective_definition.fetch_manifest_information()
            await interaction.followup.send(f'Выбранная цель: {objective_definition.progress_description}')

        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            new_requirement = RequirementObjectivesValues(group_id=group_id,
                                                          objective_hash=objective_hash,
                                                          statement=statement,
                                                          value=value,
                                                          custom_text=custom_text)
            await session.merge(new_requirement)
            await session.commit()
        await self.update_roles_requirements()
        embed = await render_requirements_group(self.roles_requirements[group_id], client=self.bot.bungio_client)
        await interaction.followup.send(embed=embed)

    game_group = app_commands.Group(name="game",
                                    description='Команды, взаимодействующие с внутриигровой статистикой',
                                    guild_ids=[main_guild_id],
                                    default_permissions=Permissions(8),
                                    )

    @game_group.command(name='roles')
    async def game_roles_command(self, interaction: Interaction):
        await interaction.response.defer()
        try:
            bungie_id = await get_main_bungie_id_by_discord_id(db_engine=self.bot.db_engine,
                                                               discord_id=interaction.user.id)
            if self.roles_requirements:
                metrics, records, stats = await get_user_stats(bungie_id, client=self.bot.bungio_client)
            else:
                return await interaction.followup.send('Нет ролей для выдачи!')
        except BungieException as e:
            # TODO: сделать глобальный обработчик ошибок с подобным эмбедом
            name_field = "Ошибка сервера Bungie!"
            value_field = f'Ошибка {e.code}: {e.error}\n' \
                          f'Описание: {e.message}\n'
            desc_text = f"**{name_field}**\n{value_field}\n"
            embed = discord.Embed(title=name_field, colour=discord.Colour.green())
            embed.description = desc_text
            return await interaction.followup.send(embed=embed)
        user_roles = [r.id for r in interaction.user.roles]

        while True:
            validated_groups = []
            user_roles = list(set(user_roles))
            user_roles_before_loop = copy(user_roles)
            for group in self.roles_requirements:
                validated, validated_group = await validate_requirements(metrics=metrics,
                                                                         records=records,
                                                                         stats=stats,
                                                                         requirement_group=deepcopy(
                                                                             self.roles_requirements[group]),
                                                                         user_roles_list=user_roles,
                                                                         client=self.bot.bungio_client)
                validated_groups.append(validated_group)
                if validated:
                    user_roles.append(validated_group.role_id)
                else:
                    try:
                        user_roles.remove(validated_group.role_id)
                    except Exception as e:
                        logger.exception(e)
                        pass
            if set(user_roles) == set(user_roles_before_loop):
                break

        new_image_x = []
        new_image_y = 0
        roles_for_user = []
        roles_for_clear = []
        roles_images = []
        validated_groups.sort(key=lambda r_group: getattr(r_group, 'sort_key', 0))
        for group in validated_groups:
            group: RoleRequirementGroup
            if getattr(group, 'completed', False):
                roles_for_user.append(group.role_id)
            else:
                roles_for_clear.append(group.role_id)
            image = await render_requirements_group_image(group,
                                                          client=self.bot.bungio_client,
                                                          guild=interaction.guild)
            if not image:
                continue
            roles_images.append(image)
            new_image_x.append(image.size[0])
            new_image_y += image.size[1]
            new_image_y += 100
        result_image = Image.new('RGBA', (max(new_image_x), new_image_y), (0, 0, 0, 255))
        x, y = 0, 0
        for image in roles_images:
            result_image.paste(image, (x, y), mask=image)
            y += image.size[1]
            y += 100

        result_roles_list = []
        upgrade_roles = []
        for role_id in roles_for_user:
            if role_id in self.roles_trees:
                current_role_id = role_id
                while self.roles_trees[current_role_id].parent and \
                        self.roles_trees[current_role_id].parent.role_id in roles_for_user:
                    upgrade_roles.append(current_role_id)
                    current_role_id = self.roles_trees[current_role_id].parent.role_id
                result_roles_list.append(current_role_id)
            else:
                result_roles_list.append(role_id)

        for group_id in self.roles_requirements:
            role_id = self.roles_requirements[group_id].role_id
            role = interaction.user.get_role(role_id)
            if role:
                try:
                    await interaction.user.remove_roles(role, reason='/game roles')
                except:
                    pass

        # for role_id in list(set(result_roles_list)):
        #     try:
        #         await interaction.user.add_roles(interaction.guild.get_role(role_id),
        #                                          reason='Соответствует требованиям')
        #     except Exception as e:
        #         logger.exception(e)
        if result_roles_list:
            view = RoleSelectorView(member=interaction.user,
                                    roles_ids_for_user=list(set(result_roles_list)))
        else:
            view = MISSING
        with io.BytesIO() as image_binary:
            result_image.save(image_binary, 'PNG')
            image_binary.seek(0)
            result: WebhookMessage = await interaction.followup.send(
                file=discord.File(fp=image_binary, filename='image.png'),
                view=view)
        if view is not MISSING:
            await view.wait()
            for item in view.children:
                item.disabled = True
            await result.edit(view=view)


async def setup(bot):
    await bot.add_cog(RolesCog(bot))
    logger.info(f'Расширение {RolesCog} загружено!')
