import uuid
from enum import Enum

from sqlalchemy import Column, NUMERIC, TEXT, ForeignKey, INTEGER
from sqlalchemy.dialects.postgresql import BIGINT, UUID, TIMESTAMP, ENUM, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql.functions import now

from ORM.Base import Base


class VoiceChannelType(Enum):
    CREATOR = 'Канал создания новых каналов'
    PERMANENT = 'Перманентный канал'
    TEMPORARY = 'Временный канал'
    DELETED = 'Канал удален'


class VoiceCategory(Base):
    __tablename__ = "voice_categories"
    category_id = Column(BIGINT, primary_key=True, autoincrement=False)
    create_voice_channel_id = Column(BIGINT, nullable=False, unique=True)
    default_channel_name = Column(TEXT, nullable=False)
    user_limit = Column(INTEGER, nullable=True)
    default_overwrites = Column(JSONB, nullable=False, server_default='{}')
    voices = relationship(
        'Voice',
        back_populates='category',
        passive_deletes=True,
    )


class Voice(Base):
    __tablename__ = "voices"
    channel_id = Column(BIGINT, primary_key=True, autoincrement=False)
    category_id = Column(BIGINT, ForeignKey("voice_categories.category_id",
                                            ondelete=None, onupdate=None), nullable=False)
    channel_type = Column(ENUM(VoiceChannelType),
                          nullable=False,
                          server_default=str(VoiceChannelType.TEMPORARY.name),
                          index=True)
    author_id = Column(BIGINT, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=now())

    category = relationship(
        'VoiceCategory',
        back_populates='voices',
        innerjoin=True,
    )
