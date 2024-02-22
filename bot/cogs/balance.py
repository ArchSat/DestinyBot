import asyncio
import datetime
import logging
import os
from functools import partial
from typing import Union

import discord
from discord import app_commands, Interaction
from discord.ext import commands, tasks
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from utils.Balance.balance import change_balance, transfer_balance, transform_float_to_decimal
from utils.Balance.exceptions import NegativeBalanceException
from ORM.schemes.User import User, Subscribe, BalanceTransaction
from utils.Balance.salary import create_salary_list, pay_salary_in_database
from utils.Balance.subscribe import prolong_subscribe, SubscribeView
from utils.Balance.suscribers_views import SelectColourRoleView
from utils.CustomCog import CustomCog
from utils.get_last_reset import get_last_reset
from utils.logger import create_logger

logger = create_logger(__name__)

main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))

check_subscribes = 3600


class Balance(CustomCog):
    """Управление балансом"""

    def __init__(self, bot):
        super().__init__(bot)
        self.subscribe_renew_tasks = {}

    async def init_config(self):
        self.config = {'can_check_balance': {'roles': [], 'users': [190371139183312896]},
                       'subscribers_role': 1128208142103236679,
                       'subscribe_cost': 400,
                       'subscribe_length': 2678400,
                       'subscribe_colour_roles': [1128208142178717761, 1128208142178717762],
                       'salary': {
                           'base_admin': 40,
                           'base_leader': 60,
                           'each_10_over_50_discord': 40,
                           'less_than_85_members_each': -5,
                           'each_inactive_more_than_21_day': -4,
                           'each_inactive_more_than_31_day': -10,
                           'twin_clan_premium': 0.1
                       },
                       'last_reset_salary_pay': 0
                       }

    @commands.Cog.listener()
    async def on_ready(self):
        await self.bot.wait_until_ready()
        self.check_expired_subscribes.start()
        # self.pay_salary.start()
        self.bot.add_view(SubscribeView(db_engine=self.bot.db_engine,
                                        get_config_function=self.get_config))
        self.bot.add_view(SelectColourRoleView(bot=self.bot,
                                               get_config=self.get_config))

    async def balance_change_notify(self, discord_id: int, transaction: BalanceTransaction):
        logger.info(f'Отправка уведомления о выплате -> {discord_id} ({transaction.id})')
        try:
            member: discord.Member = await self.bot.get_guild(main_guild_id).fetch_member(discord_id)
            if transaction.amount > 0:
                embed = discord.Embed(title='Пополнение', colour=discord.Colour.green())
            else:
                embed = discord.Embed(title='Списание', colour=discord.Colour.red())
            embed.description = (f'ID транзакции: {transaction.id}\n'
                                 f'Сумма: {transaction.amount}\n'
                                 f'Описание: {transaction.description}'
                                 )
            await member.send('Уведомление о изменении баланса', embed=embed)
            logger.info(f'Уведомление доставлено {discord_id}')
        except Exception as e:
            logger.error(f'Ошибка при отправке уведомления о выплате {discord_id}')
            logger.exception(e)

    @tasks.loop(count=1)
    async def pay_salary(self):
        await self.bot.wait_until_ready()
        guild = self.bot.get_guild(main_guild_id)
        while True:
            if datetime.datetime.now().timestamp() - \
                    self.config['last_reset_salary_pay'] >= \
                    datetime.timedelta(days=7).total_seconds():
                logger.info('Начинается недельная выплата зарплаты')
                try:
                    salary = await create_salary_list(db_engine=self.bot.db_engine,
                                                      guild=guild,
                                                      salary_dict=self.config['salary']
                                                      )
                except Exception as e:
                    logger.error('Ошибка при выплате зарплаты!')
                    logger.exception(e)
                    await asyncio.sleep(10)
                    continue
                try:
                    result_salary = await pay_salary_in_database(db_engine=self.bot.db_engine,
                                                                 salary_dict=salary)
                    last_reset_salary_pay = get_last_reset()
                    self.config['last_reset_salary_pay'] = int(last_reset_salary_pay.timestamp())
                    await self.save_config()
                except Exception as e:
                    logger.error('Критическая ошибка при выплате зарплаты!')
                    logger.exception(e)
                    break
                for discord_id in result_salary:
                    try:
                        await self.balance_change_notify(discord_id, result_salary[discord_id])
                    except:
                        continue
            else:
                await asyncio.sleep(10)
                continue

    def get_config(self):
        return self.config

    @tasks.loop(hours=check_subscribes)
    async def check_expired_subscribes(self):
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            query = select(Subscribe).where(
                and_(Subscribe.role_removed == False,
                     Subscribe.end_date <= datetime.datetime.now() + datetime.timedelta(seconds=check_subscribes)))
            expired_subscribes = list(await session.scalars(query))
        for sub in expired_subscribes:
            sub: Subscribe
            logger.info(f'Подписка пользователя {sub.discord_id} истекает {sub.end_date}')
            if sub.discord_id not in self.subscribe_renew_tasks:
                self.subscribe_renew_tasks[sub.discord_id] = asyncio.create_task(self.process_expired_subscribe(sub))

    async def remove_subscriber_role(self, subscribe):
        member: discord.Member = await self.bot.get_guild(main_guild_id).fetch_member(subscribe.discord_id)
        await member.remove_roles(member.get_role(self.config['subscribers_role']), reason='Подписка истекла!')

    async def process_expired_subscribe(self, subscribe: Subscribe):
        while True:
            if subscribe.end_date <= datetime.datetime.now():
                if not subscribe.auto_renewal:
                    logger.info(f'Подписка пользователя {subscribe.discord_id} не имеет пролонгации и устарела! '
                                f'Снимаются роли...')
                    try:
                        await self.remove_subscriber_role(subscribe)
                    except:
                        pass
                    async with AsyncSession(self.bot.db_engine) as session:
                        subscribe.role_removed = True
                        await session.merge(subscribe)
                        await session.commit()
                    logger.info(f'Снятие роли с пользователя {subscribe.discord_id} выполнено!')
                    return self.subscribe_renew_tasks.pop(subscribe.discord_id, None)
                try:
                    logger.info(f'Попытка продлить подписку пользователя {subscribe.discord_id}...')
                    timedelta = datetime.timedelta(seconds=self.config['subscribe_length'])
                    new_subscribe: Subscribe = await prolong_subscribe(
                        db_engine=self.bot.db_engine,
                        discord_id=subscribe.discord_id,
                        subscribe_cost=self.config['subscribe_cost'],
                        subscribe_length=timedelta,
                        description=f'Продление подписки до '
                                    f'{(subscribe.end_date + timedelta).strftime("%d.%m.%y (%H:%M)")}',
                        notify_func=self.balance_change_notify)
                    logger.info(f'Подписка {subscribe.discord_id} продлена до {new_subscribe.end_date}!')
                    if new_subscribe.end_date <= datetime.datetime.now() + datetime.timedelta(seconds=check_subscribes):
                        self.subscribe_renew_tasks[subscribe.discord_id] = (
                            asyncio.create_task(self.process_expired_subscribe(new_subscribe)))
                        return
                    else:
                        return self.subscribe_renew_tasks.pop(subscribe.discord_id, None)
                except NegativeBalanceException:
                    logger.info(f'У пользователя {subscribe.discord_id} недостаточно денег для продления подписки!')
                    try:
                        await self.remove_subscriber_role(subscribe)
                    except:
                        pass
                    async with AsyncSession(self.bot.db_engine) as session:
                        subscribe.auto_renewal = False
                        subscribe.role_removed = True
                        await session.merge(subscribe)
                        await session.commit()
                    logger.info(f'Снятие роли с пользователя {subscribe.discord_id} выполнено!')
                    return self.subscribe_renew_tasks.pop(subscribe.discord_id, None)
            else:
                await asyncio.sleep(1)
                continue

    @app_commands.command(name='subscribe')
    @app_commands.default_permissions(administrator=True)
    @app_commands.guilds(main_guild_id)
    async def subscribe_command(self, interaction: Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        view = SubscribeView(db_engine=self.bot.db_engine,
                             get_config_function=self.get_config)
        await interaction.followup.send(view=view)

    @commands.hybrid_command(name='balance', guild_ids=[main_guild_id])
    @app_commands.describe(user='Пользователь для проверки баланса')
    @app_commands.default_permissions(administrator=True)
    @app_commands.guilds(main_guild_id)
    async def balance_check(self, ctx: commands.Context, user: Union[discord.Member, None]):
        can_check = True
        if user is not None:
            can_check = False
            users_can_check = self.config.get('can_check_balance', {}).get('users', [])
            if ctx.author.id not in users_can_check:
                roles_can_check = self.config.get('can_check_balance', {}).get('roles', [])
                for role_id in roles_can_check:
                    if ctx.author.get_role(role_id):
                        can_check = True
                        break
            else:
                can_check = True
        else:
            user = ctx.author
        if user and can_check:
            user_id = user.id
        else:
            user_id = ctx.author.id
        async with AsyncSession(self.bot.db_engine) as session:
            balance = await session.scalar(select(User.balance).where(User.discord_id == user_id))
        await ctx.reply(f"Баланс пользователя {user.display_name}: {balance}",
                        ephemeral=True, mention_author=False)

    @app_commands.command(name='pay', description='Перевод другому пользователю')
    @app_commands.describe(recipient='Пользователь для перевода',
                           amount='Сумма перевода',
                           description='Комментарий перевода')
    @app_commands.default_permissions(administrator=True)
    @app_commands.guilds(main_guild_id)
    async def pay_command(self, interaction: Interaction, recipient: discord.Member,
                          amount: app_commands.Range[float, 0.01, None],
                          description: Union[str, None]):
        await interaction.response.defer(thinking=True)
        if interaction.user.id == recipient.id:
            return await interaction.followup.send('Невозможно сделать перевод самому себе!')
        amount = transform_float_to_decimal(abs(amount))
        try:
            user_from, user_to = await transfer_balance(db_engine=self.bot.db_engine,
                                                        from_discord_id=interaction.user.id,
                                                        to_discord_id=recipient.id,
                                                        amount=amount,
                                                        description=f'Перевод пользователя '
                                                                    f'{interaction.user.display_name} с комментарием: '
                                                                    f'{description}',
                                                        notify_func=self.balance_change_notify)
            user_from: User
            user_to: User
        except NegativeBalanceException as e:
            return await interaction.followup.send(f'{e}\n'
                                                   f'ID транзакции: {e.transaction_id}')
        except Exception as e:
            return await interaction.followup.send(f'Произошла ошибка: {e}')
        return await interaction.followup.send(f'<@{user_from.discord_id}> -> {amount} -> <@{user_to.discord_id}>\n'
                                               f'{description if description else ""}')

    @commands.hybrid_group(name='bal', guild_ids=[main_guild_id])
    @app_commands.default_permissions(administrator=True)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def bal_group(self, ctx):
        pass

    @bal_group.command(name='change', guild_ids=[main_guild_id])
    @app_commands.default_permissions(administrator=True)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def change_balance(self, ctx,
                             user: discord.Member,
                             amount: float, description: Union[str, None],
                             force: bool = False):
        await ctx.defer()
        description = f"Изменение баланса пользователем {ctx.author.id} ({ctx.author.display_name})" \
                      + f": {description}" if description else ""
        try:
            user: User = await change_balance(db_engine=self.bot.db_engine,
                                              amount=amount,
                                              discord_id=user.id,
                                              description=description,
                                              force=force,
                                              notify_func=self.balance_change_notify)
            await ctx.send(f'Баланс успешно изменен: {user}')
        except NegativeBalanceException as e:
            await ctx.send(f'Ошибка изменения баланса: {e}\n'
                           f'ID транзакции: {e.transaction_id}')

    @app_commands.command(name='roleselector',
                          description='Создает в канале возможность выбора роли цвета для подписчиков')
    @app_commands.default_permissions(administrator=True)
    @app_commands.guilds(main_guild_id)
    async def init_role_selector_command(self, interaction: Interaction):

        await interaction.response.defer(ephemeral=True)
        view = SelectColourRoleView(bot=self.bot,
                                    get_config=self.get_config)
        await interaction.channel.send(embed=view.create_embed(), view=view)
        await interaction.followup.send('Канал инициализирован')


async def setup(bot):
    await bot.add_cog(Balance(bot))
