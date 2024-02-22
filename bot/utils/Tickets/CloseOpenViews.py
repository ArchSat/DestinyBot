import datetime
import logging
from copy import deepcopy, copy

import discord
from discord import ButtonStyle, PermissionOverwrite
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ORM.schemes.Tikets import Ticket, TicketStatus, TicketType
from utils.logger import create_logger

logger = create_logger(__name__)


class CloseTicketView(discord.ui.View):
    def __init__(self, bot, cog):
        super().__init__(timeout=None)
        self.bot = bot
        self.cog = cog

    @discord.ui.button(style=ButtonStyle.gray, label='Закрыть обращение', custom_id='tickets:close')
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True)
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            ticket = (await session.scalar(select(Ticket).options(joinedload(Ticket.ticket_type)).
                                           where(Ticket.channel_id == interaction.channel_id)))
            if not ticket:
                return await interaction.followup.send('Данное обращение не найдено в базе данных!!')
            if interaction.user.id != ticket.author_id and (not ticket.ticket_type.roles_can_close or
                                                            not any([interaction.user.get_role(role)
                                                                     for role in ticket.ticket_type.roles_can_close])):
                return await interaction.followup.send(f'{interaction.user.mention}, '
                                                       f'Вы не можете закрыть данное обращение!')
            ticket: Ticket
            ticket.status = TicketStatus.CLOSED
            ticket.closed_at = datetime.datetime.now()
            await session.merge(ticket)
            await session.commit()
            new_overwrites = copy(interaction.channel.overwrites)
            for role in interaction.channel.overwrites:
                new_overwrites[role].update(send_messages=False)
            await interaction.channel.edit(overwrites=new_overwrites)
            await interaction.followup.send(f'Обращение было закрыто пользователем {interaction.user.mention}!\n'
                                            f'Дата закрытия обращения: {datetime.datetime.now()}\n'
                                            f'Для повторного открытия данного обращения используйте кнопку под '
                                            f'данным сообщением!',
                                            view=ReopenTicketView(self.bot, self.cog))
            button.disabled = True
            await interaction.message.edit(view=self)
            self.cog.check_expire_tickets.restart()


class ReopenTicketView(discord.ui.View):
    def __init__(self, bot, cog):
        super().__init__(timeout=None)
        self.bot = bot
        self.cog = cog

    @discord.ui.button(style=ButtonStyle.gray, label='Открыть обращение', custom_id='tickets:reopen')
    async def reopen_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True)
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            ticket = (await session.scalar(select(Ticket).options(joinedload(Ticket.ticket_type)).
                                           where(Ticket.channel_id == interaction.channel_id)))
            if not ticket:
                return await interaction.followup.send('Данное обращение не найдено в базе данных!!',
                                                       ephemeral=True)
            if interaction.user.id != ticket.author_id and (not ticket.ticket_type.roles_can_close or
                                                            not any([interaction.user.get_role(role)
                                                                     for role in ticket.ticket_type.roles_can_close])):
                return await interaction.followup.send(f'{interaction.user.mention}, '
                                                       f'Вы не можете открыть данное обращение!')
            ticket: Ticket
            first_message = None
            try:
                first_message = await interaction.channel.fetch_message(ticket.first_message_id)
            except:
                pass
            if first_message:
                await first_message.edit(view=CloseTicketView(self.bot, self.cog))
            else:
                emb = discord.Embed(description='```Для закрытия обращения используйте кнопку под этим сообщением!```')
                view = CloseTicketView(self.bot, self.cog)
                first_message = await interaction.channel.send(embed=emb, view=view)
                ticket.first_message_id = first_message.id
            ticket.status = TicketStatus.OPEN
            ticket.closed_at = None
            await session.merge(ticket)
            await session.commit()

        button.disabled = True
        await interaction.message.edit(view=self)

        if interaction.channel.id in self.cog.expired_tickets:
            logger.info(f'Удаление тикета {interaction.channel.id} отменено!')
            self.cog.expired_tickets[interaction.channel.id].cancel()
            self.cog.expired_tickets.pop(interaction.channel.id, None)

        new_overwrites = copy(interaction.channel.overwrites)
        for role in interaction.channel.overwrites:
            new_overwrites[role].update(send_messages=True)
        await interaction.channel.edit(overwrites=new_overwrites)
        await interaction.followup.send(f'Обращение было открыто пользователем {interaction.user.mention}')
