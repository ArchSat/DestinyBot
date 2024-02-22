import asyncio
from decimal import Decimal
from typing import Union, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from utils.Balance.exceptions import NegativeBalanceException
from ORM.schemes.User import BalanceTransaction, User, TransactionStatus


def transform_float_to_decimal(number: float) -> Decimal:
    return Decimal(number).quantize(Decimal('1.00'))


async def change_balance(db_engine, discord_id, amount, description, force=False,
                         notify_func: Union[Callable, None] = None):
    amount = transform_float_to_decimal(amount)
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        user = await session.get(User, discord_id)
        if not user:
            user = User(discord_id=discord_id)
            session.add(user)
            await session.flush()
            await session.refresh(user)
        if (user.balance + amount < 0 and amount < 0) and not force:
            transaction = BalanceTransaction(discord_id=discord_id,
                                             amount=amount,
                                             description=description,
                                             status=TransactionStatus.REJECTED)
            await session.flush([transaction])
            await session.commit()
            await session.refresh(user)
            raise NegativeBalanceException(abs_balance=user.balance,
                                           transaction_id=transaction.id)
        else:
            user.balance += amount
        new_user_object = await session.merge(user)
        transaction = BalanceTransaction(discord_id=discord_id,
                                         amount=amount,
                                         description=description,
                                         status=TransactionStatus.SUCCESS)
        session.add(transaction)
        await session.flush([transaction])
        await session.commit()
        session.expunge_all()
    if notify_func:
        asyncio.create_task(notify_func(discord_id, transaction))
    return new_user_object


async def transfer_balance(db_engine, from_discord_id, to_discord_id, amount, description,
                           notify_func: Union[Callable, None] = None):
    amount = Decimal(abs(amount))
    async with AsyncSession(db_engine, expire_on_commit=False) as session:

        user_from = await session.get(User, from_discord_id)
        user_to = await session.get(User, to_discord_id)

        if not user_from:
            user_from = User(discord_id=from_discord_id)
            session.add(user_from)
        if not user_to:
            user_to = User(discord_id=to_discord_id)
            session.add(user_to)
        await session.flush([user_from, user_to])
        await session.refresh(user_from)
        await session.refresh(user_to)

        if user_from.balance - amount < 0:
            transaction_from = BalanceTransaction(discord_id=from_discord_id,
                                                  amount=-amount,
                                                  description=description,
                                                  status=TransactionStatus.REJECTED)
            transaction_to = BalanceTransaction(discord_id=to_discord_id,
                                                amount=amount,
                                                description=description,
                                                status=TransactionStatus.REJECTED)
            session.add(transaction_from)
            session.add(transaction_to)
            await session.flush([transaction_from, transaction_to])
            transaction_from.pair_transaction = transaction_to.id
            transaction_to.pair_transaction = transaction_from.id
            await session.flush([transaction_from, transaction_to])
            await session.commit()
            raise NegativeBalanceException(abs_balance=user_from.balance,
                                           transaction_id=transaction_from.id)
        else:
            user_from.balance -= amount
            user_to.balance += amount

        transaction_from = BalanceTransaction(discord_id=from_discord_id,
                                              amount=-amount,
                                              description=description,
                                              status=TransactionStatus.SUCCESS)
        transaction_to = BalanceTransaction(discord_id=to_discord_id,
                                            amount=amount,
                                            description=description,
                                            status=TransactionStatus.SUCCESS)
        session.add(transaction_from)
        session.add(transaction_to)
        await session.flush([transaction_from, transaction_to])
        transaction_to.pair_transaction = transaction_from.id
        transaction_from.pair_transaction = transaction_to.id
        await session.commit()
        await session.refresh(user_to)
        await session.refresh(user_from)
        session.expunge_all()
    if notify_func:
        asyncio.create_task(notify_func(transaction_from.discord_id, transaction_from))
        asyncio.create_task(notify_func(transaction_to.discord_id, transaction_to))
    return user_from, user_to
