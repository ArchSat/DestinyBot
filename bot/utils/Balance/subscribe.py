import asyncio
import datetime
from decimal import Decimal
from typing import Callable, Union

import discord.ui
from discord import Interaction
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ORM.schemes.User import BalanceTransaction, TransactionStatus, User, Subscribe
from utils.Balance.balance import transform_float_to_decimal
from utils.Balance.exceptions import NegativeBalanceException


async def prolong_subscribe(db_engine, discord_id: int,
                            subscribe_length: datetime.timedelta,
                            subscribe_cost: float | Decimal,
                            renew: bool = True,
                            description: str | None = None,
                            notify_func: Union[Callable, None] = None):
    subscribe_cost = transform_float_to_decimal(abs(subscribe_cost))
    start_date = datetime.datetime.now()
    end_date = start_date + subscribe_length
    if not description:
        description = f'Оплата подписки до {end_date.strftime("%d.%m.%y (%H:%M)")}'

    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        subscribe_obj = await session.scalar(
            select(Subscribe).where(Subscribe.discord_id == discord_id).options(joinedload(Subscribe.user))
        )
        if subscribe_obj:
            user = subscribe_obj.user
        else:
            user = await session.get(User, discord_id)
        if not user or user.balance < subscribe_cost:
            transaction = BalanceTransaction(discord_id=discord_id,
                                             amount=-subscribe_cost,
                                             description=description,
                                             status=TransactionStatus.REJECTED)
            session.add(transaction)
            await session.flush([transaction])
            if subscribe_obj:
                subscribe_obj.transactions += [transaction.id]
                subscribe_obj.auto_renewal = False
                await session.merge(subscribe_obj)
            await session.commit()
            raise NegativeBalanceException(abs_balance=user.balance,
                                           transaction_id=transaction.id)
        user.balance -= subscribe_cost
        await session.flush([user])
        transaction = BalanceTransaction(discord_id=discord_id,
                                         amount=-subscribe_cost,
                                         description=description,
                                         status=TransactionStatus.SUCCESS)
        session.add(transaction)
        await session.flush([transaction])
        now = datetime.datetime.now()
        if subscribe_obj:
            subscribe_obj.auto_renewal = renew
            subscribe_obj.role_removed = False
            if subscribe_obj.end_date <= datetime.datetime.now():
                subscribe_obj.end_date = datetime.datetime.now() + subscribe_length
            else:
                subscribe_obj.end_date += subscribe_length
            subscribe_obj.transactions += [transaction.id]
        else:
            subscribe_obj = Subscribe(
                discord_id=discord_id,
                auto_renewal=renew,
                end_date=now + subscribe_length,
                transactions=[transaction.id],
                role_removed=False
            )
        await session.merge(subscribe_obj)
        await session.commit()
        session.expunge_all()
    if notify_func:
        asyncio.create_task(notify_func(discord_id, transaction))
    return subscribe_obj


class SubscribeView(discord.ui.View):
    def __init__(self, get_config_function, db_engine):
        super().__init__(timeout=None)
        self.get_config_function = get_config_function
        self.db_engine = db_engine

    def create_current_subscribe_embed(self, subscribe: Subscribe) -> discord.Embed:
        config = self.get_config_function()
        embed = discord.Embed(title='Информация о подписке')
        if subscribe is None:
            embed.description = f'В данный момент у Вас нет активной подписки!'
        elif subscribe.role_removed:
            embed.description = (f'В данный момент у Вас нет активной подписки!\n'
                                 f'Подписка истекла: <t:{int(subscribe.end_date.timestamp())}:f>')
        else:
            subscribe: Subscribe
            description = f'Подписка истекает: <t:{int(subscribe.end_date.timestamp())}:f>'
            embed.description = description
        embed.description += (f'\nСтоимость: {config["subscribe_cost"]}'
                              f'\nДлительность: {datetime.timedelta(seconds=config["subscribe_length"])}')
        return embed

    async def get_current_subscribe(self, discord_id) -> Subscribe | None:
        async with AsyncSession(self.db_engine, expire_on_commit=False) as session:
            subscribe_obj = await session.scalar(
                select(Subscribe).where(Subscribe.discord_id == discord_id).options(joinedload(Subscribe.user))
            )
        return subscribe_obj

    @discord.ui.button(label='Текущая подписка', custom_id='info:subscribe')
    async def info_subscribe_button_callback(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        config = self.get_config_function()
        subscribe = await self.get_current_subscribe(interaction.user.id)
        if subscribe:
            role = interaction.guild.get_role(config['subscribers_role'])
            if role not in interaction.user.roles:
                await interaction.user.add_roles(role, reason=f'Покупка подписки до {subscribe.end_date}')
        embed = self.create_current_subscribe_embed(subscribe)
        return await interaction.followup.send(embed=embed)

    @discord.ui.button(label='Оформить подписку', custom_id='buy:subscribe')
    async def buy_subscribe_button_callback(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        config = self.get_config_function()
        subscribe_length = datetime.timedelta(seconds=config['subscribe_length'])
        try:
            new_subscribe = await prolong_subscribe(db_engine=self.db_engine,
                                                    discord_id=interaction.user.id,
                                                    subscribe_cost=config['subscribe_cost'],
                                                    subscribe_length=subscribe_length)
            if new_subscribe:
                role = interaction.guild.get_role(config['subscribers_role'])
                if role not in interaction.user.roles:
                    await interaction.user.add_roles(role, reason=f'Покупка подписки до {new_subscribe.end_date}')
        except NegativeBalanceException as e:
            return await interaction.followup.send(f'{e}\n'
                                                   f'ID транзакции: {e.transaction_id}')
        embed = self.create_current_subscribe_embed(new_subscribe)
        return await interaction.followup.send(embed=embed)
