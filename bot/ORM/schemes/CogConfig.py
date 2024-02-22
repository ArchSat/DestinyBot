from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import TEXT, JSONB

from ORM import Base


class CogConfig(Base):
    __tablename__ = "cogs_configs"

    cog_name = Column(TEXT, primary_key=True, autoincrement=False)
    cog_config = Column(JSONB, nullable=False)
