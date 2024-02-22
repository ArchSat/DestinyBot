import datetime
import os
import uuid

import discord.ui
from discord import Interaction
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.Tikets import Ticket, TicketType
from utils.Tickets.CloseOpenViews import CloseTicketView

load_dotenv(override=True)

main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))


class CreateTicketModal(discord.ui.Modal):
    def __init__(self, bot, ticket_type_id, category_for_new_tickets_id, cog, **kwargs):
        super().__init__(title='Создание нового обращения')
        self.bot = bot
        self.cog = cog
        self.ticket_type_id = int(ticket_type_id)
        self.category_id = category_for_new_tickets_id
        self.description = discord.ui.TextInput(label=f'Текст обращения',
                                                style=discord.TextStyle.long,
                                                min_length=20,
                                                max_length=1000,
                                                required=True)
        self.add_item(self.description)

    async def on_submit(self, interaction: Interaction, /):
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with AsyncSession(self.bot.db_engine) as session:
            query = select(TicketType).where(TicketType.type_id == self.ticket_type_id)
            ticket_type = await session.scalar(query)
            if not ticket_type:
                return await interaction.followup.send('Тип обращений с указанным ID не найден!')
            ticket_type: TicketType
            ticket_channel_name = f'{ticket_type.channel_prefix}-{interaction.user.display_name}'[:99]

            category: discord.CategoryChannel = await self.bot.get_guild(main_guild_id).fetch_channel(self.category_id)

            new_overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True,
                                                              add_reactions=True,
                                                              read_messages=True,
                                                              send_messages=True,
                                                              embed_links=True,
                                                              attach_files=True,
                                                              read_message_history=True)
            }
            if ticket_type.roles_can_see:
                for role_id in ticket_type.roles_can_see:
                    new_overwrites.update({interaction.guild.get_role(role_id):
                                               discord.PermissionOverwrite(view_channel=True,
                                                                           add_reactions=True,
                                                                           read_messages=True,
                                                                           send_messages=True,
                                                                           embed_links=True,
                                                                           attach_files=True,
                                                                           read_message_history=True)})
                    new_overwrites.pop(None, None)

            new_channel = await category.create_text_channel(name=ticket_channel_name,
                                                             overwrites=new_overwrites)

            text = f"{interaction.user.mention}, здравствуйте! Заявка открыта!"
            emb = discord.Embed(description='```Для закрытия обращения используйте кнопку под этим сообщением!```')
            view = CloseTicketView(self.bot, self.cog)
            first_message = await new_channel.send(text, embed=emb, view=view)
            await new_channel.send(f'Описание обращения: {self.description.value}')

            new_ticket = Ticket(channel_id=new_channel.id,
                                first_message_id=first_message.id,
                                channel_name=new_channel.name,
                                ticket_type_id=ticket_type.type_id,
                                author_id=interaction.user.id,
                                comment=self.description.value
                                )
            await session.merge(new_ticket)
            await session.commit()
            await interaction.followup.send(f'Обращение создано: {new_channel.jump_url}\n'
                                            f'В данном канале Вы можете описать подробнее суть Вашего обращения,'
                                            f'дополнив его, по необходимости, скриншотами или видео-роликами.')
