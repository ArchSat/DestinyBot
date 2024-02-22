import datetime
import os

import discord
from discord import ButtonStyle, Interaction
from dotenv import load_dotenv
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ORM.schemes.Vote import VoteMember, Voting
from utils.logger import create_logger

logger = create_logger('suggestions')

load_dotenv(override=True)
main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))


class LikeButton(discord.ui.Button):
    def __init__(self, bot):
        super().__init__(
            style=ButtonStyle.gray,
            custom_id=f'suggestion_like',
            emoji='👍'
        )
        self.value = True
        self.bot = bot

    async def callback(self, interaction: Interaction):
        async with AsyncSession(self.bot.db_engine) as session:
            vote = VoteMember(voting_id=interaction.message.id,
                              member_id=interaction.user.id,
                              vote_value=self.value)
            await session.merge(vote)
            await session.commit()
        await self.view.render_suggestion(interaction.message)
        await interaction.response.defer()


class DislikeButton(discord.ui.Button):
    def __init__(self, bot):
        super().__init__(
            style=ButtonStyle.gray,
            custom_id=f'suggestion_dislike',
            emoji='👎'
        )
        self.value = False
        self.bot = bot

    async def callback(self, interaction: Interaction):
        async with AsyncSession(self.bot.db_engine) as session:
            vote = VoteMember(voting_id=interaction.message.id,
                              member_id=interaction.user.id,
                              vote_value=self.value)
            await session.merge(vote)
            await session.commit()
        await self.view.render_suggestion(interaction.message)
        await interaction.response.defer()


class SuggestionView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(LikeButton(bot=bot))
        self.add_item(DislikeButton(bot=bot))

    async def render_suggestion(self, message):
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            voting: Voting = await session.scalar(select(Voting).options(joinedload(Voting.votes)).
                                                  where(Voting.message_id == message.id))
            if not voting:
                return
        votes = {
            True: 0,
            False: 0
        }
        for vote in voting.votes:
            vote: VoteMember
            if vote.vote_value:
                votes[True] += 1
            else:
                votes[False] += 1
        author = await self.bot.get_guild(main_guild_id).fetch_member(voting.author_id)
        if not author:
            try:
                author = await self.bot.fetch_user(voting.author_id)
            except Exception as e:
                logger.exception(e)
                author = None
        await message.edit(embed=create_embed(author, voting.description, votes))


def render_row(value, total_count) -> str:
    one_symbol = '▬'
    final_symbol = '🔘'
    free_symbol = ' '
    max_symbol_count = 10
    if total_count != 0:
        complete_symbols_count = (value * max_symbol_count // total_count)
        if value == total_count:
            complete_symbols_count -= 1
        result = one_symbol * complete_symbols_count + final_symbol + \
                 free_symbol * (max_symbol_count - complete_symbols_count - 1)
    else:
        result = final_symbol + free_symbol * (max_symbol_count - 1)
    return result


def create_embed(author: discord.Member, description: str, votes=None) -> discord.Embed:
    if votes is None:
        votes = {True: 0, False: 0}
    text = description
    total_votes = votes[True] + votes[False]
    true_text = f'{round(votes[True] / total_votes, 4) * 10000 // 1 / 100}% ({votes[True]})' \
        if total_votes else '0% (0)'

    false_text = f'{round(votes[False] / total_votes, 4) * 10000 // 1 / 100}% ({votes[False]})' \
        if total_votes else '0% (0)'

    if votes[True] > votes[False]:
        text += '\n\n👍 - **Согласен**\n' \
                '👎 - Против\n\n'
    elif votes[False] > votes[True]:
        text += '\n\n👍 - Согласен\n' \
                '👎 - **Против**\n\n'
    else:
        text += '\n\n👍 - Согласен\n' \
                '👎 - Против\n\n'
    text += f'👍 [{render_row(votes[True], total_votes)}] {true_text}\n' \
            f'👎 [{render_row(votes[False], total_votes)}]{false_text}\n' \
            f'\n\n' \
            f'Всего голосов: {votes[True] + votes[False]}'
    embed = discord.Embed(
        colour=discord.Color.dark_theme(),
        description=text,
        timestamp=datetime.datetime.now()
    )
    if author:
        embed.set_author(name=f'{author.display_name}',
                         icon_url=author.avatar.url if author.avatar else None)
    return embed
