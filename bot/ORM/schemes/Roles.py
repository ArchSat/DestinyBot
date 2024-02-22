import datetime
from collections import defaultdict
from enum import Enum

from sqlalchemy import Column, ForeignKey, select
from sqlalchemy.dialects.postgresql import BIGINT, INTEGER, TEXT, TIMESTAMP, BOOLEAN, ARRAY, ENUM, JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import relationship
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.sql.functions import now

from ORM.Base import Base


class RequirementStatement(Enum):
    LESS = '<'
    LESS_OR_EQUAL = '<='
    MORE = '>'
    MORE_OR_EQUAL = '>='
    EQUAL = '='
    NOT_EQUAL = '!='


class HistoricalStatsGroup(Enum):
    ALL_PVE = 'allPvE'
    ALL_PVP = 'allPvP'
    ALL_PVE_COMPETITIVE = 'allPvECompetitive'
    ALL_STRIKES = 'allStrikes'
    PATROL = 'patrol'
    RAID = 'raid'
    STORY = 'story'


# Для статистик - 3 вида - пве, пвп, все вместе
class RequirementRole(Base):
    __tablename__ = 'roles_role_requirements'
    requirement_id = Column(BIGINT, primary_key=True, autoincrement=True)
    group_id = Column(BIGINT, ForeignKey("roles.group_id",
                                         ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    custom_text = Column(TEXT, nullable=True, default=None)
    role_id = Column(BIGINT, nullable=False)
    group = relationship(
        'RoleRequirementGroup',
        back_populates='requirements_Role',
        innerjoin=True,
    )

    def __repr__(self):
        return f"{self.role_id}"


class RequirementTriumphScore(Base):
    __tablename__ = 'roles_triump_score_requirements'
    requirement_id = Column(BIGINT, primary_key=True, autoincrement=True)
    group_id = Column(BIGINT, ForeignKey("roles.group_id",
                                         ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    custom_text = Column(TEXT, nullable=True, default=None)
    statement = Column(ENUM(RequirementStatement), nullable=False)
    value = Column(BIGINT, nullable=False)
    group = relationship(
        'RoleRequirementGroup',
        back_populates='requirements_TriumphScore',
        innerjoin=True,
    )

    def __repr__(self):
        return f"Triumphs {self.statement} {self.value}"


class RequirementMetricScore(Base):
    __tablename__ = 'roles_metric_score_requirements'
    requirement_id = Column(BIGINT, primary_key=True, autoincrement=True)
    group_id = Column(BIGINT, ForeignKey("roles.group_id",
                                         ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    custom_text = Column(TEXT, nullable=True, server_default=None)
    metric_hash = Column(BIGINT, nullable=False)
    statement = Column(ENUM(RequirementStatement), nullable=False)
    value = Column(BIGINT, nullable=False)
    group = relationship(
        'RoleRequirementGroup',
        back_populates='requirements_MetricScore',
        innerjoin=True,
    )

    def __repr__(self):
        return f"{self.metric_hash} {self.statement} {self.value}"


class RequirementTriumphCompleted(Base):
    __tablename__ = 'roles_triump_completed_requirements'
    requirement_id = Column(BIGINT, primary_key=True, autoincrement=True)
    group_id = Column(BIGINT, ForeignKey("roles.group_id",
                                         ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    custom_text = Column(TEXT, nullable=True, default=None)
    record_hash = Column(BIGINT, nullable=False)
    completed = Column(BOOLEAN, nullable=False)
    group = relationship(
        'RoleRequirementGroup',
        back_populates='requirements_TriumphCompleted',
        innerjoin=True,
    )

    def __repr__(self):
        return f"{self.record_hash} {self.completed}"


class RequirementHistoricalStat(Base):
    __tablename__ = 'roles_historical_stats_requirements'
    requirement_id = Column(BIGINT, primary_key=True, autoincrement=True)
    group_id = Column(BIGINT, ForeignKey("roles.group_id",
                                         ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    custom_text = Column(TEXT, nullable=True, default=None)
    historical_stat_group = Column(ENUM(HistoricalStatsGroup), nullable=False)
    historical_stat_name = Column(TEXT, nullable=False)
    statement = Column(ENUM(RequirementStatement), nullable=False)
    value = Column(BIGINT, nullable=False)
    group = relationship(
        'RoleRequirementGroup',
        back_populates='requirements_HistoricalStat',
        innerjoin=True,
    )

    def __repr__(self):
        return f"{self.historical_stat_name} {self.statement} {self.value}"


class RequirementObjectivesCompleted(Base):
    __tablename__ = 'roles_objectives_requirements'
    requirement_id = Column(BIGINT, primary_key=True, autoincrement=True)
    group_id = Column(BIGINT, ForeignKey("roles.group_id",
                                         ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    custom_text = Column(TEXT, nullable=True, default=None)
    objective_hash = Column(BIGINT, nullable=False)
    completed = Column(BOOLEAN, nullable=False)
    group = relationship(
        'RoleRequirementGroup',
        back_populates='requirements_ObjectivesCompleted',
        innerjoin=True,
    )

    def __repr__(self):
        return f"{self.objective_hash} {self.completed}"


class RequirementObjectivesValues(Base):
    __tablename__ = 'roles_objectives_values_requirements'
    requirement_id = Column(BIGINT, primary_key=True, autoincrement=True)
    group_id = Column(BIGINT, ForeignKey("roles.group_id",
                                         ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    custom_text = Column(TEXT, nullable=True, default=None)
    objective_hash = Column(BIGINT, nullable=False)
    statement = Column(ENUM(RequirementStatement), nullable=False)
    value = Column(BIGINT, nullable=False)
    group = relationship(
        'RoleRequirementGroup',
        back_populates='requirements_ObjectivesValues',
        innerjoin=True,
    )

    def __repr__(self):
        return f"{self.objective_hash} {self.completed}"


class RoleRequirementGroup(Base):
    __tablename__ = "roles"

    # Фиктивный первичный ключ (на одну роль может быть несколько групп требований (Операция ИЛИ)
    group_id = Column(BIGINT, primary_key=True, autoincrement=True)

    role_id = Column(BIGINT, index=True, nullable=False)
    enabled = Column(BOOLEAN, nullable=False, server_default="True")
    sort_key = Column(INTEGER, nullable=False, server_default='0')

    requirements_HistoricalStat = relationship(
        'RequirementHistoricalStat',
        back_populates='group',
        cascade='save-update, merge, delete',
        passive_deletes=True,
    )
    requirements_TriumphCompleted = relationship(
        'RequirementTriumphCompleted',
        back_populates='group',
        cascade='save-update, merge, delete',
        passive_deletes=True,
    )
    requirements_MetricScore = relationship(
        'RequirementMetricScore',
        back_populates='group',
        cascade='save-update, merge, delete',
        passive_deletes=True,
    )
    requirements_TriumphScore = relationship(
        'RequirementTriumphScore',
        back_populates='group',
        cascade='save-update, merge, delete',
        passive_deletes=True,
    )
    requirements_Role = relationship(
        'RequirementRole',
        back_populates='group',
        cascade='save-update, merge, delete',
        passive_deletes=True,
    )
    requirements_ObjectivesCompleted = relationship(
        'RequirementObjectivesCompleted',
        back_populates='group',
        cascade='save-update, merge, delete',
        passive_deletes=True,
    )

    requirements_ObjectivesValues = relationship(
        'RequirementObjectivesValues',
        back_populates='group',
        cascade='save-update, merge, delete',
        passive_deletes=True,
    )

    def __repr__(self):
        desc = ""
        for req in self.requirements_Role + \
                   self.requirements_MetricScore + \
                   self.requirements_TriumphScore + \
                   self.requirements_HistoricalStat + \
                   self.requirements_TriumphCompleted + \
                   self.requirements_ObjectivesCompleted + \
                   self.requirements_ObjectivesValues:
            desc += f'{req}\n'
        return f"{self.group_id}: {self.role_id}\n{desc}"


class RequirementsType(Enum):
    REQUIREMENT_ROLE = RequirementRole
    REQUIREMENT_TRIUMPH_SCORE = RequirementTriumphScore
    REQUIREMENT_METRIC_SCORE = RequirementMetricScore
    REQUIREMENT_TRIUMPH_COMPLETED = RequirementTriumphCompleted
    REQUIREMENT_HISTORICAL_STAT = RequirementHistoricalStat
    REQUIREMENT_OBJECTIVES_COMPLETED = RequirementObjectivesCompleted
    REQUIREMENT_OBJECTIVES_VALUES = RequirementObjectivesValues


class RolesTree(Base):
    __tablename__ = 'roles_trees'

    role_id = Column(BIGINT, primary_key=True, autoincrement=False)
    parent_id = Column(BIGINT, ForeignKey(role_id, ondelete='SET NULL'), nullable=True, default=None)
    children = relationship("RolesTree", back_populates="parent")
    parent = relationship("RolesTree", back_populates="children", remote_side=[role_id])

    def __repr__(self):
        string = f'<@&{self.role_id}>'
        parent = self.parent
        while parent:
            string = f'<@&{parent.role_id}> -> {string}'
            parent = parent.parent
        return string

    def get_all_parents_list(self):
        result = []
        parent = self.parent
        while self.parent:
            result.append(parent.role_id)
            parent = parent.parent
        return result


async def get_all_nodes(engine):
    async with AsyncSession(engine, expire_on_commit=False) as session:
        nodes = list(await session.scalars(select(RolesTree)))
        children = defaultdict(list)
        for node in nodes:
            if node.parent:
                children[node.parent.role_id].append(node)
        for node in nodes:
            set_committed_value(node, 'children', children[node.role_id])
    return nodes
