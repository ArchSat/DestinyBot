from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import BIGINT, INTEGER, TEXT, TIMESTAMP, BOOLEAN

from ORM.Base import Base


class Clan(Base):
    __tablename__ = "clans"

    clan_id = Column(BIGINT, primary_key=True, autoincrement=False)
    clan_tag = Column(TEXT, nullable=True, unique=True)
    total_members = Column(INTEGER, nullable=True, server_default='0')
    discord_members = Column(INTEGER, nullable=True, server_default='0')
    inactive_10d = Column(INTEGER, nullable=True, server_default='0')
    inactive_14d = Column(INTEGER, nullable=True, server_default='0')
    inactive_21d = Column(INTEGER, nullable=True, server_default='0')
    inactive_31d = Column(INTEGER, nullable=True, server_default='0')
    leader_bungie_id = Column(INTEGER, nullable=True)
    last_update = Column(TIMESTAMP, nullable=True, server_default='now()')
    admins = Column(TEXT, nullable=True)
    visible = Column(BOOLEAN, nullable=False, server_default='True')

