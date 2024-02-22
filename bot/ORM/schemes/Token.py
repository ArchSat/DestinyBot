from enum import Enum

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import BIGINT, TEXT, TIMESTAMP, ENUM

from ORM.Base import Base


class TokenType(Enum):
    EXTENDED = 'Токен с расширенными правами'
    BASE = 'Токен с базовыми правами'


class Token(Base):
    __tablename__ = "tokens"

    bungie_id = Column(BIGINT, primary_key=True, autoincrement=False)
    discord_id = Column(BIGINT, nullable=False)
    token = Column(TEXT, nullable=False)
    token_expire = Column(TIMESTAMP, nullable=False)
    token_type = Column(ENUM(TokenType), nullable=False, server_default=str(TokenType.BASE.name))

    def __repr__(self):
        return "<Token(bungie_id='%s', discord_id='%s', token='%s', token_expire='%s')>" % (
            self.bungie_id,
            self.discord_id,
            self.token,
            self.token_expire
        )
