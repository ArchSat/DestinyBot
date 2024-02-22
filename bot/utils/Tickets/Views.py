import datetime
import logging

import discord
from discord import ButtonStyle, SelectOption, PermissionOverwrite
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.Tikets import TicketType, Ticket, TicketStatus
from utils.Tickets.CreateTicketModal import CreateTicketModal
from utils.logger import create_logger

logger = create_logger(__name__)


class CreateTicketView(discord.ui.View):
    def __init__(self, bot, cog, category_for_new_tickets_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.cog = cog
        self.category_for_new_tickets_id = category_for_new_tickets_id

    @discord.ui.button(style=ButtonStyle.gray, label='Создать обращение', custom_id='tickets:create')
    async def create_ticket_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        select_ticket_type_view = TicketTypeView(self.bot, self.category_for_new_tickets_id, self.cog)
        await select_ticket_type_view.init()
        await interaction.followup.send(view=select_ticket_type_view)


class TicketTypeView(discord.ui.View):
    def __init__(self, bot, category_for_new_tickets_id, cog):
        super().__init__(timeout=None)
        self.select_ticket_type = None
        self.category_for_new_tickets_id = category_for_new_tickets_id
        self.bot = bot
        self.cog = cog

    async def init(self):
        async with AsyncSession(self.bot.db_engine) as session:
            query = select(TicketType).where(TicketType.enabled == True)
            all_types = list(await session.scalars(query))
        options = [SelectOption(label=ticket_type.display_name,
                                description=ticket_type.description,
                                value=str(ticket_type.type_id)) for ticket_type in all_types]
        self.select_ticket_type = discord.ui.Select(options=options,
                                                    min_values=1,
                                                    max_values=1,
                                                    placeholder='Выберите категорию обращения')
        self.add_item(self.select_ticket_type)
        self.select_ticket_type.callback = self.select_ticket_type_callback

    async def select_ticket_type_callback(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        self.stop()

        selected_ticket_type_id = int(self.select_ticket_type.values[0])

        modal = CreateTicketModal(bot=self.bot,
                                  cog=self.cog,
                                  ticket_type_id=selected_ticket_type_id,
                                  category_for_new_tickets_id=self.category_for_new_tickets_id)
        await interaction.response.send_modal(modal)
        await interaction.edit_original_response(view=self)
