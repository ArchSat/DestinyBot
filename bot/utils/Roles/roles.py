import os
from typing import Union, List

import bungio
import discord
from PIL import Image, ImageFont, ImageDraw
from PIL.ImageFont import FreeTypeFont
from bungio.models import DestinyMetricDefinition, DestinyRecordDefinition, DestinyHistoricalStatsDefinition, \
    DestinyMetricComponent, DestinyRecordComponent, \
    DestinyHistoricalStatsAccountResult, SingleComponentResponseOfDestinyMetricsComponent, \
    SingleComponentResponseOfDestinyProfileRecordsComponent, DestinyHistoricalStatsValue, \
    DestinyObjectiveDefinition, DestinyUnlockValueUIStyle, DestinyHistoricalStatsByPeriod
from discord import Interaction, SelectOption, ButtonStyle
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ORM.schemes.Roles import RoleRequirementGroup, RequirementTriumphScore, RequirementMetricScore, \
    RequirementTriumphCompleted, RequirementHistoricalStat, RequirementRole, RequirementStatement, \
    HistoricalStatsGroup, RequirementObjectivesCompleted, RequirementObjectivesValues
from utils.bungio_client import CustomClient
from utils.logger import create_logger

logger = create_logger(__name__)


class RoleSelectorView(discord.ui.View):
    def __init__(self,
                 member: discord.Member,
                 roles_ids_for_user: List[int]):
        super().__init__(timeout=300)
        self.member = member
        self.roles_ids = roles_ids_for_user
        self.roles = [member.guild.get_role(role_id) for role_id in self.roles_ids]
        try:
            self.roles.remove(None)
        except:
            pass
        self.roles_pages = list(bungio.utils.split_list(self.roles, 25))
        self.roles_options_pages = [[SelectOption(label=f'{role.name}',
                                                  value=f'{role.id}')
                                     for role in page] for page in self.roles_pages]
        self.current_page = 0

        self.select_role = discord.ui.Select(min_values=0, max_values=min(len(self.roles_ids), 25),
                                             placeholder='Выбор ролей для выдачи',
                                             options=self.roles_options_pages[self.current_page], row=0)
        self.update_list()

        self.select_role.callback = self.select_callback

        self.prev_button: discord.ui.Button = discord.ui.Button(emoji=discord.PartialEmoji(name="\U000025c0"), row=0)
        self.prev_button.callback = self.prev_button_callback
        self.next_button: discord.ui.Button = discord.ui.Button(emoji=discord.PartialEmoji(name="\U000025b6"), row=0)
        self.next_button.callback = self.next_button_callback

        if len(roles_ids_for_user) > 25:
            self.add_item(self.prev_button)
            self.add_item(self.select_role)
            self.add_item(self.next_button)
        else:
            self.add_item(self.select_role)

        self.all_roles_button: discord.ui.Button = discord.ui.Button(label='Выдать все роли',
                                                                     style=ButtonStyle.green,
                                                                     row=1)
        self.all_roles_button.callback = self.all_roles_button_callback
        self.add_item(self.all_roles_button)

    def update_list(self):
        self.select_role.options = self.roles_options_pages[self.current_page]

    async def prev_button_callback(self, interaction: Interaction):
        if interaction.user.id != self.member.id:
            embed = discord.Embed(description="Вы не можете использовать это!",
                                  color=discord.Colour.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if self.current_page == 0:
            self.current_page = len(self.roles_options_pages) - 1
        else:
            self.current_page -= 1
        self.update_list()
        await interaction.message.edit(view=self)

    async def next_button_callback(self, interaction: Interaction):
        if interaction.user.id != self.member.id:
            embed = discord.Embed(description="Вы не можете использовать это!",
                                  color=discord.Colour.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if self.current_page == len(self.roles_options_pages) - 1:
            self.current_page = 0
        else:
            self.current_page += 1
        self.update_list()
        await interaction.message.edit(view=self)

    async def all_roles_button_callback(self, interaction: Interaction):
        if interaction.user.id != self.member.id:
            embed = discord.Embed(description="Вы не можете использовать это!",
                                  color=discord.Colour.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        await interaction.response.defer(thinking=True, ephemeral=True)
        for role_id in self.roles_ids:
            try:
                role = interaction.guild.get_role(role_id)
                if not interaction.user.get_role(role_id):
                    await interaction.user.add_roles(role, reason='/game roles')
            except Exception as e:
                logger.exception(e)
        await interaction.followup.send('Все роли выданы!')

    async def select_callback(self, interaction: Interaction):
        if interaction.user.id != self.member.id:
            embed = discord.Embed(description="Вы не можете использовать это!",
                                  color=discord.Colour.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        await interaction.response.defer(thinking=True, ephemeral=True)
        for role_id_str in self.select_role.values:
            role_id = int(role_id_str)
            try:
                await interaction.user.add_roles(interaction.guild.get_role(role_id), reason='/game roles')
            except Exception as e:
                logger.exception(e)
        await interaction.followup.send('Выбранные роли выданы!')


def render_new_requirements_group(new_group: RoleRequirementGroup):
    embed = discord.Embed(colour=discord.Colour.green(), title='Новая группа требований')
    embed.description = f'ID: {new_group.group_id}\n' \
                        f'Роль: <@&{new_group.role_id}>'
    return embed


async def render_requirements_group(requirement_group: RoleRequirementGroup, client: CustomClient | None):
    embed = discord.Embed(colour=discord.Colour.green(), title=f'Группа требований {requirement_group.group_id}')
    description = f'ID: {requirement_group.group_id}\n' \
                  f'Роль: <@&{requirement_group.role_id}>\n\n'

    if requirement_group.requirements_TriumphScore:
        description += 'Требования к счету триумфов (REQUIREMENT_TRIUMPH_SCORE)\n'
    for req in requirement_group.requirements_TriumphScore:
        req: RequirementTriumphScore
        description += f'ID: {req.requirement_id} Счет триумфов {req.statement.value} {req.value}\n'
    if requirement_group.requirements_TriumphScore:
        description += '\n'

    if requirement_group.requirements_MetricScore:
        description += 'Требования к датчикам статистики (REQUIREMENT_METRIC_SCORE)\n'
    for req in requirement_group.requirements_MetricScore:
        req: RequirementMetricScore
        if client:
            metric_definition = await client.manifest.fetch(DestinyMetricDefinition, req.metric_hash)
            await metric_definition.fetch_manifest_information()
            metric_definition: DestinyMetricDefinition
            metric_description = f"{metric_definition.display_properties.description}"
        else:
            metric_description = f"{req.metric_hash}"
        description += f'ID: {req.requirement_id} Счет метрики: {metric_description} {req.statement.value} {req.value}\n'
    if requirement_group.requirements_MetricScore:
        description += '\n'

    if requirement_group.requirements_TriumphCompleted:
        description += 'Требования к триумфам (REQUIREMENT_TRIUMPH_COMPLETED)\n'
    for req in requirement_group.requirements_TriumphCompleted:
        req: RequirementTriumphCompleted
        if client:
            record_definition = await client.manifest.fetch(DestinyRecordDefinition, req.record_hash)
            await record_definition.fetch_manifest_information()
            record_definition: DestinyRecordDefinition
            record_description = f"{record_definition.display_properties.description}"
        else:
            record_description = f"{req.record_hash}"
        description += f'ID: {req.requirement_id} Триумф {record_description} выполнен: {req.completed}\n'
    if requirement_group.requirements_TriumphCompleted:
        description += '\n'

    if requirement_group.requirements_HistoricalStat:
        historical_stats_definition = await client.api.get_historical_stats_definition()
        description += 'Требования к агрегированной статистике (REQUIREMENT_HISTORICAL_STAT)\n'
    else:
        historical_stats_definition = {}
    for req in requirement_group.requirements_HistoricalStat:
        req: RequirementHistoricalStat
        stat_definition: DestinyHistoricalStatsDefinition = \
            historical_stats_definition.get(req.historical_stat_name, None)
        if stat_definition:
            stat_description = stat_definition.stat_name
        else:
            stat_description = req.historical_stat_name
        description += f'ID: {req.requirement_id} Stat {stat_description} в {req.historical_stat_group} ' \
                       f'{req.statement.value} {req.value}\n'
    if requirement_group.requirements_HistoricalStat:
        description += '\n'

    if requirement_group.requirements_ObjectivesCompleted:
        description += 'Требования к частям триумфов (REQUIREMENT_OBJECTIVES)\n'
    for req in requirement_group.requirements_ObjectivesCompleted:
        req: RequirementObjectivesCompleted
        if client:
            objective_definition = await client.manifest.fetch(DestinyObjectiveDefinition, req.objective_hash)
            await objective_definition.fetch_manifest_information()
            objective_definition: DestinyObjectiveDefinition
            objective_description = f"{objective_definition.progress_description}"
        else:
            objective_description = f"{req.objective_hash}"
        description += f'ID: {req.requirement_id} Цель {objective_description} выполнена: {req.completed}\n'
    if requirement_group.requirements_ObjectivesCompleted:
        description += '\n'

    if requirement_group.requirements_Role:
        description += 'Требования к другим ролям (REQUIREMENT_ROLE)\n'
    for req in requirement_group.requirements_Role:
        req: RequirementRole
        description += f'ID: {req.requirement_id} Иметь роль <@&{req.role_id}>\n'

    embed.description = description
    return embed


async def render_requirements_group_image(requirement_group: RoleRequirementGroup, client: CustomClient | None,
                                          guild: discord.Guild, need_id=False):
    path = f'{os.path.dirname(__file__)}/../assets'
    title_font = ImageFont.truetype(f'{path}/fonts/Montserrat/Montserrat-Black.ttf', size=30)
    sub_title_font = ImageFont.truetype(f'{path}/fonts/OpenSans/OpenSans-Light.ttf', size=30)
    text_font = ImageFont.truetype(f'{path}/fonts/OpenSans/OpenSans-Light.ttf', size=30)
    text_colour = '#FFFFFF'
    historical_stats_definition = await client.api.get_historical_stats_definition()

    requirement_role = guild.get_role(requirement_group.role_id)
    if not requirement_role:
        requirement_role = requirement_group.role_id
    requirement_role = str(requirement_role)
    if getattr(requirement_group, 'completed', None) is not None:
        requirement_role = f"{requirement_group.completed} {requirement_role}"
    if need_id:
        requirement_role = f"ID: {requirement_group.group_id} (sort: {requirement_group.sort_key}) {requirement_role}"

    requirements_images = {}
    all_requirements = requirement_group.requirements_ObjectivesCompleted + requirement_group.requirements_Role + \
                       requirement_group.requirements_MetricScore + requirement_group.requirements_TriumphScore + \
                       requirement_group.requirements_HistoricalStat + \
                       requirement_group.requirements_TriumphCompleted + \
                       requirement_group.requirements_ObjectivesValues
    if not all_requirements:
        return
    for requirement in all_requirements:
        requirement_image = await render_requirement(requirement,
                                                     client=client,
                                                     text_font=text_font,
                                                     text_colour=text_colour,
                                                     guild=guild,
                                                     historical_stats_definition=historical_stats_definition,
                                                     need_id=need_id)
        requirement_class_name = requirement.__class__.__name__
        if requirement_class_name in requirements_images:
            requirements_images[requirement_class_name][requirement.requirement_id] = requirement_image
        else:
            requirements_images[requirement_class_name] = {requirement.requirement_id: requirement_image}

    background_x = []
    background_y = 0
    role_box = title_font.getbbox(requirement_role)
    background_x.append(role_box[2] - role_box[0])
    background_y += role_box[3] - role_box[1]
    for requirement_class_name in requirements_images:
        for requirement_id in requirements_images[requirement_class_name]:
            req_im_size = requirements_images[requirement_class_name][requirement_id].size
            background_x.append(req_im_size[0])
            background_y += req_im_size[1]

    background = Image.new('RGBA', (max(background_x), background_y), (0, 0, 0, 255))
    draw = ImageDraw.Draw(background)

    x, y = 0, 0
    draw.text((x, y), requirement_role, font=title_font, fill=text_colour)
    y += role_box[3] - role_box[1]

    for requirement_class_name in requirements_images:
        for requirement_id in requirements_images[requirement_class_name]:
            background.paste(requirements_images[requirement_class_name][requirement_id], (x, y),
                             mask=requirements_images[requirement_class_name][requirement_id])
            req_im_size = requirements_images[requirement_class_name][requirement_id].size
            y += req_im_size[1]

    return background


async def render_requirement(requirement: Union[
    RequirementRole,
    RequirementTriumphScore,
    RequirementMetricScore,
    RequirementTriumphCompleted,
    RequirementHistoricalStat,
    RequirementObjectivesCompleted,
    RequirementObjectivesValues],
                             text_font: FreeTypeFont,
                             text_colour: str,
                             guild: discord.Guild,
                             client: CustomClient | None,
                             historical_stats_definition: dict[str, DestinyHistoricalStatsDefinition] = None,
                             need_id: bool = True):
    if historical_stats_definition is None:
        historical_stats_definition = {}
    background_x = []
    background_y = 0

    if need_id:
        requirement_text = f'ID: {requirement.requirement_id} '
    else:
        requirement_text = ''
    if not requirement.custom_text:
        if isinstance(requirement, RequirementTriumphScore):
            requirement_text += f'Счет триумфов {requirement.statement.value} {requirement.value}\n'
        elif isinstance(requirement, RequirementRole):
            role = guild.get_role(requirement.role_id)
            requirement_text += f'Иметь роль {role.name}\n'
        elif isinstance(requirement, RequirementMetricScore):
            if client:
                metric_definition = await client.manifest.fetch(DestinyMetricDefinition, requirement.metric_hash)
                await metric_definition.fetch_manifest_information()
                metric_definition: DestinyMetricDefinition
                metric_description = f"{metric_definition.display_properties.description}"
            else:
                metric_description = f"{requirement.metric_hash}"
            requirement_text += f'Счет метрики: ' \
                                f'«{metric_description}» {requirement.statement.value} {requirement.value}\n'
        elif isinstance(requirement, RequirementTriumphCompleted):
            if client:
                record_definition = await client.manifest.fetch(DestinyRecordDefinition, requirement.record_hash)
                await record_definition.fetch_manifest_information()
                record_definition: DestinyRecordDefinition
                record_description = f"{record_definition.display_properties.description}"
            else:
                record_description = f"{requirement.record_hash}"
            requirement_text += f'Триумф «{record_description}» выполнен: {requirement.completed}\n'
        elif isinstance(requirement, RequirementHistoricalStat):
            stat_definition: DestinyHistoricalStatsDefinition = \
                historical_stats_definition.get(requirement.historical_stat_name, None)
            if stat_definition:
                stat_description = stat_definition.stat_name
            else:
                stat_description = requirement.historical_stat_name
            requirement_text += f'Статистика «{stat_description}» в {requirement.historical_stat_group.value} ' \
                                f'{requirement.statement.value} {requirement.value}\n'
        elif isinstance(requirement, RequirementObjectivesCompleted):
            if client:
                objective_definition = await client.manifest.fetch(DestinyObjectiveDefinition,
                                                                   requirement.objective_hash)
                await objective_definition.fetch_manifest_information()
                objective_definition: DestinyObjectiveDefinition
                objective_description = f"{objective_definition.progress_description}"
            else:
                objective_description = f"{requirement.objective_hash}"
            requirement_text += f'Цель «{objective_description}» выполнена: {requirement.completed}\n'

        elif isinstance(requirement, RequirementObjectivesValues):
            if client:
                objective_definition = await client.manifest.fetch(DestinyObjectiveDefinition,
                                                                   requirement.objective_hash)
                await objective_definition.fetch_manifest_information()
                objective_definition: DestinyObjectiveDefinition
                objective_description = f"{objective_definition.progress_description}"
            else:
                objective_description = f"{requirement.objective_hash}"
            requirement_text += f'Цель «{objective_description}» {requirement.statement.value}: {requirement.value}\n'

        else:
            requirement_text += '?'
    else:
        requirement_text = requirement.custom_text
        if need_id:
            requirement_text = f'ID: {requirement.requirement_id} {requirement.custom_text}'

    completed = getattr(requirement, 'fact_completed', None)
    current = getattr(requirement, 'current', None)
    require = getattr(requirement, 'require', None)
    if require is None:
        require = getattr(requirement, 'value', None)
    current_text = ''
    if completed is not None and current is not None:
        completed_emojis = ['[Не выполнено]', '[Выполнено]']
        requirement_text = f'{completed_emojis[completed]} {requirement_text}'
        current_text = f'Текущее значение: {current}'
        if require is not None:
            current_text += f' (Нужно {require})'

        box = text_font.getbbox(current_text)
        background_x.append(box[2] - box[0])
        background_y += (box[3] - box[1]) * 1.5

    requirement_text_box = text_font.getbbox(requirement_text)
    background_x.append(requirement_text_box[2] - requirement_text_box[0])
    background_y += (requirement_text_box[3] - requirement_text_box[1]) * 1.5

    background = Image.new('RGBA', (max(background_x), int(background_y)))
    draw = ImageDraw.Draw(background)
    x, y = 0, 0

    draw.text((x, y), requirement_text, font=text_font, fill=text_colour)
    y += requirement_text_box[3] - requirement_text_box[1]

    if current_text:
        draw.text((x, y), current_text, font=text_font, fill=text_colour)

    return background


async def get_roles_requirements(db_engine):
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        # Добавить сортировку в запрос
        query = select(RoleRequirementGroup).options(joinedload(RoleRequirementGroup.requirements_HistoricalStat),
                                                     joinedload(RoleRequirementGroup.requirements_MetricScore),
                                                     joinedload(RoleRequirementGroup.requirements_Role),
                                                     joinedload(RoleRequirementGroup.requirements_TriumphCompleted),
                                                     joinedload(RoleRequirementGroup.requirements_TriumphScore),
                                                     joinedload(RoleRequirementGroup.requirements_ObjectivesCompleted),
                                                     joinedload(RoleRequirementGroup.requirements_ObjectivesValues)
                                                     ).where(RoleRequirementGroup.enabled == True).order_by(
            RoleRequirementGroup.sort_key)

        all_roles_requirements = (
            await session.execute(query)).unique().scalars()
    return {req.group_id: req for req in all_roles_requirements}


async def validate_triumph_score(records: SingleComponentResponseOfDestinyProfileRecordsComponent,
                                 requirement: RequirementTriumphScore):
    triump_score = records.data.active_score
    if requirement.statement == RequirementStatement.LESS:
        return triump_score < requirement.value, triump_score
    elif requirement.statement == RequirementStatement.LESS_OR_EQUAL:
        return triump_score <= requirement.value, triump_score
    elif requirement.statement == RequirementStatement.MORE:
        return triump_score > requirement.value, triump_score
    elif requirement.statement == RequirementStatement.MORE_OR_EQUAL:
        return triump_score >= requirement.value, triump_score
    elif requirement.statement == RequirementStatement.EQUAL:
        return triump_score == requirement.value, triump_score
    elif requirement.statement == RequirementStatement.NOT_EQUAL:
        return triump_score != requirement.value, triump_score
    return False, triump_score


async def validate_metric_score(metrics: SingleComponentResponseOfDestinyMetricsComponent,
                                requirement: RequirementMetricScore):
    metric = metrics.data.metrics.get(requirement.metric_hash, None)
    if not isinstance(metric, DestinyMetricComponent):
        return False, None
    metric_value = metric.objective_progress.progress
    if requirement.statement == RequirementStatement.LESS:
        return metric_value < requirement.value, metric_value
    elif requirement.statement == RequirementStatement.LESS_OR_EQUAL:
        return metric_value <= requirement.value, metric_value
    elif requirement.statement == RequirementStatement.MORE:
        return metric_value > requirement.value, metric_value
    elif requirement.statement == RequirementStatement.MORE_OR_EQUAL:
        return metric_value >= requirement.value, metric_value
    elif requirement.statement == RequirementStatement.EQUAL:
        return metric_value == requirement.value, metric_value
    elif requirement.statement == RequirementStatement.NOT_EQUAL:
        return metric_value != requirement.value, metric_value
    return False, metric_value


async def validate_historical_stat(stats: dict[str, DestinyHistoricalStatsByPeriod],
                                   requirement: RequirementHistoricalStat):
    value = stats[requirement.historical_stat_group.value].all_time[requirement.historical_stat_name].basic.value
    if requirement.statement == RequirementStatement.LESS:
        return value < requirement.value, value
    elif requirement.statement == RequirementStatement.LESS_OR_EQUAL:
        return value <= requirement.value, value
    elif requirement.statement == RequirementStatement.MORE:
        return value > requirement.value, value
    elif requirement.statement == RequirementStatement.MORE_OR_EQUAL:
        return value >= requirement.value, value
    elif requirement.statement == RequirementStatement.EQUAL:
        return value == requirement.value, value
    elif requirement.statement == RequirementStatement.NOT_EQUAL:
        return value != requirement.value, value
    return False, value


async def validate_triump_completed(records: SingleComponentResponseOfDestinyProfileRecordsComponent,
                                    requirement: RequirementTriumphCompleted):
    triump = records.data.records.get(requirement.record_hash, None)
    if not isinstance(triump, DestinyRecordComponent):
        return False, None
    triump: DestinyRecordComponent
    objectives_completed = True
    interval_objectives_completed = True
    if triump.objectives:
        objectives_completed = all([obj.complete for obj in triump.objectives])
    if triump.interval_objectives:
        interval_objectives_completed = all([obj.complete for obj in triump.interval_objectives])
    triump_completed = objectives_completed and interval_objectives_completed
    return triump_completed == requirement.completed, triump_completed


async def validate_role(member: discord.Member, requirement: RequirementRole):
    role = member.get_role(requirement.role_id)
    return bool(role)


async def validate_objective_complete(records: SingleComponentResponseOfDestinyProfileRecordsComponent,
                                      metrics: SingleComponentResponseOfDestinyMetricsComponent,
                                      requirement: RequirementObjectivesCompleted,
                                      client):
    for metric in metrics.data.metrics:
        if metrics.data.metrics[metric].objective_progress.objective_hash == requirement.objective_hash:
            completed = requirement.completed == metrics.data.metrics[metric].objective_progress.complete
            value = metrics.data.metrics[metric].objective_progress.progress
            completion_value = metrics.data.metrics[metric].objective_progress.completion_value

            obj: DestinyObjectiveDefinition = await client.manifest.fetch(DestinyObjectiveDefinition,
                                                                          requirement.objective_hash)
            await obj.fetch_manifest_information()
            if obj.value_style == DestinyUnlockValueUIStyle.RAW_FLOAT:
                value = value / 100
                completion_value = completion_value / 100

            return completed, value, completion_value
    for record in records.data.records:
        if records.data.records[record].objectives:
            for obj in records.data.records[record].objectives:
                if obj.objective_hash == requirement.objective_hash:
                    completed = requirement.completed == obj.complete
                    value = obj.progress
                    completion_value = obj.completion_value

                    obj: DestinyObjectiveDefinition = await client.manifest.fetch(DestinyObjectiveDefinition,
                                                                                  requirement.objective_hash)
                    await obj.fetch_manifest_information()
                    if obj.value_style == DestinyUnlockValueUIStyle.RAW_FLOAT:
                        value = value / 100
                        completion_value = completion_value / 100

                    return completed, value, completion_value
        if records.data.records[record].interval_objectives:
            for obj in records.data.records[record].interval_objectives:
                if obj.objective_hash == requirement.objective_hash:
                    completed = requirement.completed == obj.complete
                    value = obj.progress
                    completion_value = obj.completion_value
                    obj: DestinyObjectiveDefinition = await client.manifest.fetch(DestinyObjectiveDefinition,
                                                                                  requirement.objective_hash)
                    await obj.fetch_manifest_information()
                    if obj.value_style == DestinyUnlockValueUIStyle.RAW_FLOAT:
                        value = value / 100
                        completion_value = completion_value / 100

                    return completed, value, completion_value

    obj: DestinyObjectiveDefinition = await client.manifest.fetch(DestinyObjectiveDefinition,
                                                                  requirement.objective_hash)
    await obj.fetch_manifest_information()
    completed, value, completion_value = False, 0, obj.completion_value
    if obj.value_style == DestinyUnlockValueUIStyle.RAW_FLOAT:
        value = value / 100
        completion_value = completion_value / 100

    return completed, value, completion_value


async def validate_objective_values(records: SingleComponentResponseOfDestinyProfileRecordsComponent,
                                    metrics: SingleComponentResponseOfDestinyMetricsComponent,
                                    requirement: RequirementObjectivesValues):
    value = 0
    for metric in metrics.data.metrics:
        if metrics.data.metrics[metric].objective_progress.objective_hash == requirement.objective_hash:
            value = metrics.data.metrics[metric].objective_progress.progress

    for record in records.data.records:
        if records.data.records[record].objectives:
            for obj in records.data.records[record].objectives:
                if obj.objective_hash == requirement.objective_hash:
                    value = obj.progress

        if records.data.records[record].interval_objectives:
            for obj in records.data.records[record].interval_objectives:
                if obj.objective_hash == requirement.objective_hash:
                    value = obj.progress

    if requirement.statement == RequirementStatement.LESS:
        return value < requirement.value, value
    elif requirement.statement == RequirementStatement.LESS_OR_EQUAL:
        return value <= requirement.value, value
    elif requirement.statement == RequirementStatement.MORE:
        return value > requirement.value, value
    elif requirement.statement == RequirementStatement.MORE_OR_EQUAL:
        return value >= requirement.value, value
    elif requirement.statement == RequirementStatement.EQUAL:
        return value == requirement.value, value
    elif requirement.statement == RequirementStatement.NOT_EQUAL:
        return value != requirement.value, value
    return False, value


async def validate_role_by_roles_list(roles_ids_list: List[int], requirement: RequirementRole):
    return requirement.role_id in roles_ids_list


async def validate_requirements(requirement_group: RoleRequirementGroup,
                                metrics: SingleComponentResponseOfDestinyMetricsComponent,
                                records: SingleComponentResponseOfDestinyProfileRecordsComponent,
                                stats: dict[str, DestinyHistoricalStatsByPeriod],
                                user_roles_list: List[int],
                                client
                                ) -> (bool, RoleRequirementGroup):
    for requirement in requirement_group.requirements_TriumphScore:
        completed, current = await validate_triumph_score(records=records, requirement=requirement)
        setattr(requirement, 'fact_completed', completed)
        setattr(requirement, 'current', current)

    for requirement in requirement_group.requirements_MetricScore:
        completed, current = await validate_metric_score(metrics=metrics, requirement=requirement)
        setattr(requirement, 'fact_completed', completed)
        setattr(requirement, 'current', current)

    for requirement in requirement_group.requirements_HistoricalStat:
        completed, current = await validate_historical_stat(stats=stats, requirement=requirement)
        setattr(requirement, 'fact_completed', completed)
        setattr(requirement, 'current', current)

    for requirement in requirement_group.requirements_TriumphCompleted:
        completed, current = await validate_triump_completed(records=records, requirement=requirement)
        setattr(requirement, 'fact_completed', completed)
        setattr(requirement, 'current', current)

    for requirement in requirement_group.requirements_ObjectivesCompleted:
        completed, current, require = await validate_objective_complete(records=records,
                                                                        metrics=metrics,
                                                                        requirement=requirement,
                                                                        client=client)
        setattr(requirement, 'fact_completed', completed)
        setattr(requirement, 'current', current)
        setattr(requirement, 'require', require)

    for requirement in requirement_group.requirements_ObjectivesValues:
        completed, current = await validate_objective_values(records=records,
                                                             metrics=metrics,
                                                             requirement=requirement)
        setattr(requirement, 'fact_completed', completed)
        setattr(requirement, 'current', current)

    for requirement in requirement_group.requirements_Role:
        completed = await validate_role_by_roles_list(roles_ids_list=user_roles_list,
                                                      requirement=requirement)
        setattr(requirement, 'fact_completed', completed)
        setattr(requirement, 'current', completed)

    completed = all(r.fact_completed for r in requirement_group.requirements_TriumphScore +
                    requirement_group.requirements_TriumphCompleted +
                    requirement_group.requirements_HistoricalStat +
                    requirement_group.requirements_MetricScore +
                    requirement_group.requirements_ObjectivesCompleted +
                    requirement_group.requirements_ObjectivesValues +
                    requirement_group.requirements_Role)
    setattr(requirement_group, 'completed', completed)
    return completed, requirement_group
