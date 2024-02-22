from enum import Enum

from sqlalchemy import Column, TEXT, ForeignKey, INTEGER, BOOLEAN
from sqlalchemy.dialects.postgresql import BIGINT, TIMESTAMP, JSONB, ARRAY, ENUM
from sqlalchemy.orm import relationship
from sqlalchemy.sql.functions import now

from ORM.Base import Base


class TicketMessage(Base):
    __tablename__ = "tickets_messages"

    ticket_id = Column(BIGINT, ForeignKey("tickets.channel_id",
                                          ondelete='CASCADE', onupdate='CASCADE'), primary_key=True, autoincrement=True)
    message_id = Column(BIGINT, primary_key=True, autoincrement=False)
    author_id = Column(BIGINT, nullable=False)
    message_content = Column(TEXT, nullable=True)
    embed_json = Column(ARRAY(JSONB), nullable=True)
    attachments = Column(ARRAY(TEXT), nullable=True)
    created_at = Column(TIMESTAMP, nullable=False)

    ticket = relationship(
        'Ticket',
        back_populates='messages',
        innerjoin=True,
    )


class TicketType(Base):
    __tablename__ = "ticket_types"

    type_id = Column(INTEGER, primary_key=True, autoincrement=True)
    display_name = Column(TEXT, nullable=False)
    description = Column(TEXT, nullable=False)
    channel_prefix = Column(TEXT, nullable=False)
    roles_can_see = Column(ARRAY(BIGINT), nullable=True)
    roles_can_close = Column(ARRAY(BIGINT), nullable=True)
    delete_after_close = Column(BIGINT, nullable=True)
    enabled = Column(BOOLEAN, server_default='True')

    tickets = relationship('Ticket',
                           back_populates='ticket_type',
                           cascade='save-update, merge, delete',
                           passive_deletes=True)


class TicketStatus(Enum):
    OPEN = 'Открыт'
    CLOSED = 'Закрыт'
    DELETED = 'Удален'


class Ticket(Base):
    __tablename__ = "tickets"

    channel_id = Column(BIGINT, primary_key=True, autoincrement=False)
    first_message_id = Column(BIGINT, nullable=True)
    channel_name = Column(TEXT, nullable=False)
    ticket_type_id = Column(ForeignKey("ticket_types.type_id",
                                       ondelete='CASCADE', onupdate='CASCADE'), nullable=False)
    status = Column(ENUM(TicketStatus), nullable=False, server_default=f'{TicketStatus.OPEN.name}')
    author_id = Column(BIGINT, nullable=False)
    comment = Column(TEXT, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=now())
    closed_at = Column(TIMESTAMP, nullable=True)

    ticket_type = relationship(
        'TicketType',
        back_populates='tickets',
        innerjoin=True,
    )

    messages = relationship(
        'TicketMessage',
        back_populates='ticket',
        cascade='save-update, merge, delete',
        passive_deletes=True,
        order_by=TicketMessage.created_at
    )
