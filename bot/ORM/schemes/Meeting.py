import datetime
from enum import Enum

from sqlalchemy import Column, ForeignKey, desc, asc
from sqlalchemy.dialects.postgresql import BIGINT, INTEGER, TEXT, TIMESTAMP, BOOLEAN, ARRAY, ENUM, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql.functions import now

from ORM.Base import Base
from utils.ResourseConverters import ResourseType


class MeetingStatus(Enum):
    ACTIVE = 'Активный сбор'
    COMPLETED = 'Сбор завершен'
    CANCELED = 'Сбор отменен'
    DELETED_BY_OTHER_USER = 'Сбор удален'
    DELETED_BY_COMPLETED = 'Сбор удален после завершения'
    DELETED_BY_OVERDUE = 'Сбор удален по истечении срока'


class MemberStatus(Enum):
    LEADER = 'Лидер'
    MEMBER = 'Участник'
    LEFT = 'Покинул'
    KICKED = 'Исключен'
    BANNED = 'Забанен'


class MeetingMember(Base):
    __tablename__ = "meetings_members"

    meeting_id = Column(BIGINT, ForeignKey("meetings.meeting_id", ondelete='CASCADE', onupdate='CASCADE'),
                        primary_key=True, autoincrement=False)
    discord_id = Column(BIGINT, primary_key=True, autoincrement=False)
    status = Column(ENUM(MemberStatus), nullable=False, index=True, server_default=str(MemberStatus.MEMBER.name))
    last_update = Column(TIMESTAMP, server_default=now(), server_onupdate=now(), onupdate=datetime.datetime.now())
    bungie_name = Column(TEXT, nullable=True)
    other_data = Column(JSONB, nullable=True)
    meeting = relationship(
        'Meeting',
        back_populates='meeting_members',
        cascade='delete',
        innerjoin=True,
    )


class Meeting(Base):
    __tablename__ = "meetings"

    # ID сообщения в канале сборов
    meeting_id = Column(BIGINT, primary_key=True, autoincrement=False)
    # Атрибут для сопоставления КУДА этот сбор - channel_id PK для таблицы каналов
    category_id = Column(BIGINT, ForeignKey("meetings_channels.channel_id",
                                            ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    status = Column(ENUM(MeetingStatus), nullable=False, server_default=str(MeetingStatus.ACTIVE.name))

    binded_voice = Column(BIGINT, nullable=True)
    # Для определения где опубликован сбор
    # Если не запланирован, то в meetings_channels.channel_id, иначе - meetings_channels.planned_channel_id
    planned = Column(BOOLEAN, nullable=False)
    author_id = Column(BIGINT, nullable=False, index=True)
    fireteam_max = Column(INTEGER, nullable=False)
    comment = Column(TEXT, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=now())
    start_at = Column(TIMESTAMP, nullable=True)
    complete_at = Column(TIMESTAMP, nullable=True)
    actual_until = Column(TIMESTAMP, nullable=False)
    meeting_channel = relationship(
        'MeetingChannel',
        back_populates='meetings',
        cascade='merge, delete',
        innerjoin=True,
        lazy='joined'
    )
    meeting_members = relationship(
        'MeetingMember',
        back_populates='meeting',
        cascade='delete, delete-orphan',
        passive_deletes=True,
        order_by=(asc(MeetingMember.status), desc(MeetingMember.last_update)),
        lazy='joined'
    )


class MeetingChannel(Base):
    __tablename__ = "meetings_channels"

    channel_id = Column(BIGINT, primary_key=True, autoincrement=False)
    planned_channel_id = Column(BIGINT, nullable=True)
    name = Column(TEXT, nullable=False)
    description = Column(TEXT, nullable=True)
    custom_meeting_text = Column(TEXT, nullable=True)
    icon_url = Column(TEXT, nullable=True)
    default_members_count = Column(INTEGER, nullable=False)
    max_members_count = Column(INTEGER, nullable=False)
    activity_type = Column(ENUM(ResourseType), nullable=True)
    metric_hash = Column(ARRAY(BIGINT), nullable=True)
    voices_category_id = Column(BIGINT, nullable=True)
    create_meeting_message_id = Column(BIGINT, nullable=True)
    meetings = relationship(
        'Meeting',
        back_populates='meeting_channel',
        cascade='save-update, merge, delete',
        passive_deletes=True
    )
