import os

import discord
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.Tikets import TicketMessage, Ticket, TicketStatus

load_dotenv(override=True)

main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))


async def delete_ticket(bot, channel_id) -> bool:
    channel: discord.TextChannel = await bot.get_guild(main_guild_id).fetch_channel(channel_id)
    messages = [message async for message in channel.history(limit=1000)]

    async with AsyncSession(bot.db_engine) as session:
        for message in messages:
            message: discord.Message
            db_message = TicketMessage(ticket_id=channel_id,
                                       message_id=message.id,
                                       author_id=message.author.id,
                                       message_content=message.content,
                                       embed_json=[emb.to_dict() for emb in message.embeds],
                                       attachments=[att.url for att in message.attachments],
                                       created_at=message.created_at.replace(tzinfo=None))
            await session.merge(db_message)

        ticket = Ticket(channel_id=channel_id, status=TicketStatus.DELETED)
        await session.merge(ticket)
        await session.commit()
        await channel.delete()
    return True
