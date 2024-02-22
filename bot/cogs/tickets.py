import asyncio
import datetime
import logging
import os
from asyncio import sleep
from typing import List, Union

import discord
from discord import app_commands, Interaction, Permissions
from discord.app_commands import Choice
from discord.ext import commands, tasks

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ORM.schemes.Tikets import Ticket, TicketType, TicketStatus, TicketMessage
from utils.CustomCog import CustomCog
from utils.Tickets.CloseOpenViews import CloseTicketView, ReopenTicketView
from utils.Tickets.Views import CreateTicketView
from utils.Tickets.tickets_utilities import delete_ticket
from utils.db_utils import parse_time
from utils.logger import create_logger

logger = create_logger('tickets')

main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))

check_expire_tickets_interval = 60


class ExpireTicket:
    def __init__(self, channel_id, closed_at, delete_delay):
        self.channel_id = channel_id
        self.closed_at = closed_at
        self.delete_delay = delete_delay
        self.status = TicketStatus.CLOSED


class TicketsCog(CustomCog):
    """Модуль работы с обращениями пользователей"""

    def __init__(self, bot):
        super().__init__(bot)
        self.expired_tickets = {}
        self.check_expire_tickets.start()

    async def cog_load(self) -> None:
        await self.load_config()
        await self.init()

    async def on_config_update(self):
        await self.load_config()
        await self.init()

    async def init(self):
        create_ticket_view = CreateTicketView(self.bot,
                                              cog=self,
                                              category_for_new_tickets_id=
                                              self.config['category_id_for_new_tickets'])
        self.bot.add_view(create_ticket_view)
        reopen_ticket_view = ReopenTicketView(bot=self.bot, cog=self)
        self.bot.add_view(reopen_ticket_view)
        close_ticket_view = CloseTicketView(bot=self.bot, cog=self)
        self.bot.add_view(close_ticket_view)

    async def init_config(self):
        self.config = {
            'category_id_for_new_tickets': 1128208145324453947,
            'category_id_for_closed_tickets': 1128208145542565987,
        }

    @tasks.loop(minutes=check_expire_tickets_interval)
    async def check_expire_tickets(self):
        await self.bot.wait_until_ready()
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            query = select(Ticket.channel_id, Ticket.closed_at, TicketType.delete_after_close).join(
                TicketType.tickets).where(
                and_(
                    (func.date_part('EPOCH', Ticket.closed_at) + TicketType.delete_after_close) <=
                    (datetime.datetime.now() +
                     datetime.timedelta(minutes=180 + check_expire_tickets_interval)).timestamp(),
                    Ticket.status == TicketStatus.CLOSED)
            )

            tickets_to_delete = list((await session.execute(query)))
        tickets_to_delete = [ExpireTicket(row[0], row[1], row[2]) for row in tickets_to_delete]
        for ticket in tickets_to_delete:
            self.expired_tickets[ticket.channel_id] = (
                asyncio.create_task((self.process_expired_ticket(expire_ticket=ticket))))

    async def process_expired_ticket(self, expire_ticket: ExpireTicket):
        while True:
            if (expire_ticket.closed_at + datetime.timedelta(seconds=expire_ticket.delete_delay)
                    <= datetime.datetime.now()):
                try:
                    logger.info(f'Ticket {expire_ticket.channel_id} удаляется')
                    deleted = await delete_ticket(bot=self.bot, channel_id=expire_ticket.channel_id)
                    if deleted:
                        logger.info(f'Ticket {expire_ticket.channel_id} удален!')
                        expire_ticket.status = TicketStatus.DELETED
                except discord.errors.NotFound:
                    logger.info(f'Ticket {expire_ticket.channel_id} удален!')
                    expire_ticket.status = TicketStatus.DELETED
                    async with AsyncSession(self.bot.db_engine) as session:
                        await session.merge(Ticket(channel_id=expire_ticket.channel_id,
                                                   status=TicketStatus.DELETED))
                        await session.commit()
                except Exception as e:
                    logger.exception(e)
            else:
                await sleep(1)
            if expire_ticket.status == TicketStatus.DELETED:
                break

    tickets_commands_group = app_commands.Group(
        name='ticket',
        description='Команды управлениями обращениями',
        guild_ids=[main_guild_id],
        default_permissions=Permissions(8)
    )

    async def ticket_autocomplete(self, interaction: Interaction, current: str) -> List[app_commands.Choice[str]]:
        options = interaction.data.get('options', [])
        if len(options) == 0:
            return []
        options = options[0].get('options', [])
        author_id = None
        for option in options:
            if option['name'] == 'ticket' and not option['focused']:
                return []
            elif option['name'] == 'user' and option['value']:
                author_id = option['value']
        if not author_id:
            return []
        else:
            author_id = int(author_id)

        query = select(Ticket).where(and_(Ticket.author_id == author_id,
                                          Ticket.status == TicketStatus.DELETED)).order_by(Ticket.closed_at)
        async with AsyncSession(self.bot.db_engine) as session:
            tickets_list = list(await session.scalars(query))

        result_list = []
        for ticket in tickets_list:
            ticket: Ticket
            author = interaction.guild.get_member(ticket.author_id)
            if author:
                author = author.display_name
            else:
                author = ticket.author_id
            choice = Choice(name=f'{author} от {ticket.created_at.strftime("%d.%m.%y (%H:%M)")}',
                            value=str(ticket.channel_id))
            result_list.append(choice)
        return result_list[:25]

    @tickets_commands_group.command(name='restore', description='Восстановить обращение из истории')
    @app_commands.describe(ticket='Идентификатор обращения для восстановления')
    @app_commands.autocomplete(ticket=ticket_autocomplete)
    async def restore_ticket_command(self, interaction: Interaction,
                                     user: Union[discord.Member],
                                     ticket: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            query = select(Ticket).where(Ticket.channel_id == int(ticket)).options(joinedload(Ticket.messages),
                                                                                   joinedload(Ticket.ticket_type))
            ticket: Ticket = await session.scalar(query)
        category: discord.CategoryChannel = \
            await self.bot.get_guild(main_guild_id).fetch_channel(self.config['category_id_for_closed_tickets'])
        new_channel = await category.create_text_channel(name=f"restored-{ticket.channel_name}"[:99])
        for message in ticket.messages:
            message: TicketMessage
            text = f"Автор: <@{message.author_id}>\n" \
                   f"Создано: {message.created_at}\n" \
                   f"{message.message_content}"
            for att in message.attachments:
                text += f"\n{att}"
            text = text[:2000]
            await new_channel.send(content=text,
                                   embeds=[discord.Embed.from_dict(emb) for emb in message.embed_json],
                                   )
        await interaction.followup.send(f'{new_channel.jump_url}')

    @tickets_commands_group.command(name='init_channel', description='Создает в канале кнопку для создания обращений')
    async def init_tickets_channel(self, interaction: Interaction, text_with_button: Union[str, None]):
        tickets_view = CreateTicketView(bot=self.bot,
                                        cog=self,
                                        category_for_new_tickets_id=self.config['category_id_for_new_tickets'])
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.send(content=text_with_button, view=tickets_view)
        await interaction.followup.send('Канал создан')

    tickets_type_group = app_commands.Group(
        name='type',
        description='Управление типами обращений',
        guild_ids=[main_guild_id],
        parent=tickets_commands_group
    )

    @tickets_type_group.command(name='add', description='Создает или редактирует категорию обращений')
    @app_commands.describe(display_name='Отображаемое название категории обращений',
                           description='Отображаемое описание категории обращений',
                           delete_after_close='Время, через которое канал обращения будет удаляться после закрытия',
                           roles_can_see='Список идентификаторов (ID) ролей, которые будут видеть канал обращения',
                           roles_can_close='Список идентификаторов (ID) ролей, которые смогут закрыть обращение',
                           ticket_type_id='Если указать этот атрибут - команда обновит существующую группу')
    async def add_tickets_type_group_command(self, interaction: Interaction,
                                             display_name: str,
                                             description: str,
                                             channel_prefix: app_commands.Range[str, 0, 5],
                                             delete_after_close: Union[str, None],
                                             roles_can_see: Union[str, None],
                                             roles_can_close: Union[str, None],
                                             ticket_type_id: Union[int, None]):
        await interaction.response.defer()
        if delete_after_close:
            delete_after_close = int(parse_time(delete_after_close).seconds)
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            if ticket_type_id:
                query = select(TicketType).where(TicketType.type_id == ticket_type_id)
                new_type = await session.scalar(query)
                if not new_type:
                    return await interaction.followup.send('Тип обращений с указанным ID не найден!')
            else:
                new_type = TicketType(display_name=display_name,
                                      description=description,
                                      channel_prefix=channel_prefix,
                                      delete_after_close=delete_after_close,
                                      roles_can_see=[int(role_id) for role_id in roles_can_see.split(',')]
                                      if roles_can_see else None,
                                      roles_can_close=[int(role_id) for role_id in roles_can_close.split(',')]
                                      if roles_can_close else None)
            new_type.display_name = display_name
            new_type.description = description
            new_type.channel_prefix = channel_prefix
            new_type.delete_after_close = delete_after_close
            new_type.roles_can_see = [int(role_id) for role_id in roles_can_see.split(',')] \
                if roles_can_see else None
            new_type.roles_can_close = [int(role_id) for role_id in roles_can_close.split(',')] \
                if roles_can_close else None

            query = select(func.count(TicketType.type_id)).where(TicketType.enabled == True)
            enabled_count = await session.scalar(query)
            if not ticket_type_id:
                limit = 25
            else:
                limit = 26
            if enabled_count < limit:
                await session.merge(new_type)
                await session.commit()
            else:
                await session.rollback()
                return await interaction.followup.send(f'Нельзя иметь более 25 активных категорий!')
            return await interaction.followup.send(f'Новая категория обращений создана: '
                                                   f'{new_type.display_name} ({new_type.type_id})')

    @tickets_type_group.command(name='list', description='Выдает список категорий обращений')
    async def enable_tickets_type_group(self, interaction: Interaction,
                                        ):
        await interaction.response.defer()
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            types = list(await session.scalars(select(TicketType)))
        if not types:
            return await interaction.followup.send('Нет ни одной категории обращений!')
        for ticket_type in types:
            ticket_type: TicketType
            text = f'ID: {ticket_type.type_id} | {ticket_type.display_name}'
            if ticket_type.description:
                text += f' - ({ticket_type.description})'
            if ticket_type.channel_prefix:
                text += f' | Префикс каналов: {ticket_type.channel_prefix}'
            text += f' | Удаление после закрытия (сек): ' \
                    f'{ticket_type.delete_after_close if ticket_type.delete_after_close is None else "Не удаляется"} ' \
                    f'| Включено: {ticket_type.enabled}'
            await interaction.channel.send(text)

        await interaction.followup.send('Все доступные категории:')

    @tickets_type_group.command(name='enable', description='Включает/Отключает возможность использовать '
                                                           'категорию обращений для пользователей')
    @app_commands.describe(ticket_type_id='ID группы обращений',
                           enabled='True - сделать доступной, False - наоборот')
    async def enable_tickets_type_group(self, interaction: Interaction,
                                        ticket_type_id: int,
                                        enabled: bool):
        await interaction.response.defer()
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            query = select(TicketType).where(TicketType.type_id == ticket_type_id)
            new_type = await session.scalar(query)
            if not new_type:
                return await interaction.followup.send('Тип обращений с указанным ID не найден!')
            new_type.enabled = enabled
            await session.merge(new_type)
            await session.commit()
            await interaction.followup.send(f'Категория обращений изменена: '
                                            f'{new_type.display_name} ({new_type.type_id}) '
                                            f'включена: {new_type.enabled}')


async def setup(bot):
    await bot.add_cog(TicketsCog(bot))
    logger.info(f'Расширение {TicketsCog} загружено!')
