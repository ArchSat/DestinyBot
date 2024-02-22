from sqlalchemy import Column, BIGINT, ForeignKey, TEXT, BOOLEAN
from sqlalchemy.orm import relationship

from ORM import Base


class Voting(Base):
    __tablename__ = "voting"
    message_id = Column(BIGINT, primary_key=True, autoincrement=False)
    author_id = Column(BIGINT, nullable=False)
    description = Column(TEXT, nullable=False)
    votes = relationship(
        'VoteMember',
        back_populates='voting',
        cascade='delete',
        innerjoin=True,
    )


class VoteMember(Base):
    __tablename__ = "votes_members"
    voting_id = Column(BIGINT, ForeignKey("voting.message_id", ondelete='CASCADE', onupdate='CASCADE'),
                       primary_key=True, autoincrement=False)
    member_id = Column(BIGINT, primary_key=True, autoincrement=False)
    vote_value = Column(BOOLEAN, nullable=False)
    voting = relationship(
        'Voting',
        back_populates='votes',
        cascade='delete',
        innerjoin=True,
    )
