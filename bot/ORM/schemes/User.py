import uuid
from enum import Enum

from sqlalchemy import Column, NUMERIC, TEXT, ForeignKey, BOOLEAN, ARRAY
from sqlalchemy.dialects.postgresql import BIGINT, UUID, TIMESTAMP, ENUM, INTERVAL
from sqlalchemy.orm import relationship
from sqlalchemy.sql.functions import now

from ORM.Base import Base


class SanctionType(Enum):
    WARN = 'Предупреждение'
    BAN = 'Бан'
    TEXT_MUTE = 'Текстовый мут'
    VOICE_MUTE = 'Голосовой мут'


class SanctionStatus(Enum):
    ACTIVE = 'Активный'
    EXPIRE = 'Истекший'
    REMOVED = 'Удаленный'


class Sanction(Base):
    __tablename__ = "sanctions"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    type = Column(ENUM(SanctionType), nullable=False, index=True)
    author_id = Column(BIGINT, nullable=False)
    member_id = Column(BIGINT, nullable=False, index=True)
    reason = Column(TEXT, nullable=False)
    expire = Column(TIMESTAMP, nullable=True, index=True)
    channel_id = Column(BIGINT, nullable=True)
    message_id = Column(BIGINT, nullable=True)
    status = Column(ENUM(SanctionStatus), nullable=False,
                    server_default=str(SanctionStatus.ACTIVE.name), index=True)


class TransactionStatus(Enum):
    SUCCESS = 'Операция выполнена'
    REJECTED = 'Операция отклонена'
    ERROR = 'Операция завершена с ошибкой'


class BalanceTransaction(Base):
    __tablename__ = "balance_transactions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    discord_id = Column(BIGINT, ForeignKey("users.discord_id",
                                           ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    amount = Column(NUMERIC(precision=1000, scale=2), nullable=False)
    description = Column(TEXT, nullable=True)
    pair_transaction = Column(UUID(as_uuid=True), index=True, nullable=True)
    status = Column(ENUM(TransactionStatus), nullable=False, server_default=str(TransactionStatus.ERROR.name))
    timestamp = Column(TIMESTAMP, server_default=now())
    user = relationship(
        'User',
        back_populates='transactions',
        innerjoin=True,
    )


class User(Base):
    __tablename__ = "users"
    discord_id = Column(BIGINT, primary_key=True, autoincrement=False)
    balance = Column(NUMERIC(precision=1000, scale=2), nullable=False, server_default='0')
    bungie_id = Column(BIGINT, nullable=True, index=True, unique=True)
    leave_server_date = Column(TIMESTAMP, nullable=True)
    transactions = relationship(
        'BalanceTransaction',
        back_populates='user',
        cascade='save-update, merge, delete',
        passive_deletes=True,
        order_by=BalanceTransaction.timestamp
    )

    def __repr__(self):
        return "<User(discord_id='%s', bungie_id='%s', balance='%s')>" % (
            self.discord_id,
            self.bungie_id,
            self.balance,
        )


class Subscribe(Base):
    __tablename__ = 'subscriptions'

    discord_id = Column(BIGINT, ForeignKey("users.discord_id",
                                           onupdate='CASCADE'), nullable=False, primary_key=True)

    auto_renewal = Column(BOOLEAN, nullable=False, server_default='True', index=True)
    end_date = Column(TIMESTAMP, nullable=False, index=True)
    role_removed = Column(BOOLEAN, nullable=False, index=True, server_default='False')
    transactions = Column(ARRAY(UUID(as_uuid=True)), nullable=False)

    user = relationship(
        'User',
        uselist=False
    )
