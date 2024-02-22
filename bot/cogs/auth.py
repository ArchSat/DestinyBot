import asyncio
import datetime
import json
import logging
import os

import bungio.error
from discord import app_commands, Permissions, Interaction, SelectOption
from discord.ext.commands import Context

from utils.ClanAdmin.share import InviteButton
from utils.CustomCog import CustomCog
from utils.db_utils import get_full_clans_ids
from utils.logger import create_logger

from utils.tokens import encode_key, get_encode_key, sym_encrypt

from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.Token import Token, TokenType
from ORM.schemes.User import User

from random import randint

import aio_pika
import discord
from discord.ext import tasks, commands

from sqlalchemy import select, update

from dotenv import load_dotenv

from utils.users_utils import get_clan_list_by_bungie_id, get_bungie_name_by_bungie_id, get_info_for_bungie_id, \
    search_all_bungie_ids_by_discord

load_dotenv(override=True)

main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))

logger = create_logger(__name__)


async def insert_user_in_main_table(db_engine, discord_id: int, bungie_id: int):
    bungie_id = int(bungie_id)
    new_user = User(discord_id=discord_id, bungie_id=bungie_id)
    async with AsyncSession(db_engine) as session:
        query = select(User).where(User.bungie_id == bungie_id)
        existing_user = (await session.execute(query)).scalar()
        if existing_user is not None:
            existing_user.bungie_id = None
            await session.merge(existing_user)
        await session.merge(new_user)
        await session.commit()


async def insert_extended_data(db_engine, discord_id: int, bungie_data, extended=True):
    encode_key_value = await get_encode_key(bungie_data['membership_id'])
    key = encode_key(key_value=encode_key_value)
    refresh_token = sym_encrypt(bungie_data['refresh_token'], key)
    token = Token(bungie_id=int(bungie_data['membership_id']),
                  discord_id=discord_id,
                  token=refresh_token,
                  token_expire=(datetime.datetime.now() +
                                datetime.timedelta(seconds=bungie_data['refresh_expires_in'])),
                  token_type=TokenType.EXTENDED if extended else TokenType.BASE)
    async with AsyncSession(db_engine) as session:
        await session.merge(token)
        await session.commit()


class AccountDropdown(discord.ui.Select):
    def __init__(self, options):
        super().__init__(
            placeholder="Выбрать основной аккаунт",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        for item in self.view.children:
            item.disabled = True
        self.view.selected_account = self.values[0]
        self.view.stop()
        await interaction.response.defer()


class RegButton(discord.ui.Button):
    def __init__(self, extended):
        if extended:
            super().__init__(label='Авторизоваться', url=f"{os.environ['REDIRECT_URI']}auth/bungie/admin")
        else:
            super().__init__(label='Авторизоваться', url=f"{os.environ['REDIRECT_URI']}auth/bungie")


class SelectMainAccount(discord.ui.View):
    def __init__(self, guild, author_id, options, trusted_roles):
        super().__init__(timeout=60)
        self.trusted_roles = trusted_roles
        self.add_item(AccountDropdown(options))
        self.author_id = author_id
        self.selected_account = None
        self.guild = guild

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

    async def interaction_check(self, interaction: Interaction):
        if interaction.user.id == self.author_id:
            return True
        trusted_list = []
        for member in self.guild.members:
            for role in self.trusted_roles:
                if member.get_role(role):
                    trusted_list.append(member.id)
        if interaction.user.id in trusted_list:
            return True
        return False


class AuthCog(CustomCog):
    """Работает с регистрацией авторизацией в боте."""

    def __init__(self, bot):
        super().__init__(bot)
        self.update_refresh_tokens.start()
        self.info_command = app_commands.ContextMenu(guild_ids=[main_guild_id], name='Информация',
                                                     callback=self.info_command_callback)
        self.bot.tree.add_command(self.info_command)

    def create_registration_embed(self):
        color = discord.Color.from_rgb(randint(0, 255), randint(0, 255), randint(0, 255))
        guild: discord.Guild = self.bot.get_guild(main_guild_id)
        guardian_role = guild.get_role(self.config['guardian_role_id'])
        rules_channel = guild.get_channel(self.config['rules_channel_id'])
        bot_requests_channel = guild.get_channel(self.config['bot_requests_channel_id'])
        emb = discord.Embed(title='Регистрация', colour=color)
        name = f"Добро пожаловать в клан ELderLy!"
        value = f"Пожалуйста, ознакомьтесь с каналом \n{rules_channel.mention} " \
                f"и [авторизуйтесь]({os.getenv('REDIRECT_URI')}auth/bungie)\n" \
                f"Спасибо!\n" \
                f"**Внимание!**\n" \
                f"```Для авторизации, сайт использует файлы cookie!\n" \
                f"Пожалуйста, убедитесь, что разрешили сайту их использовать!\n" \
                f"Все данные для входа Вы вводите ТОЛЬКО на официальных сайтах bungie.net и discord.com\n" \
                f"После авторизации бот связывает Ваши BungieID и DiscordID.\n" \
                f"После авторизации Вы получите роль {guardian_role.name} " \
                f"и возможность получить все роли,\n" \
                f"связанные со статистикой в канале {bot_requests_channel.name}.```"
        emb.add_field(name=name, value=value)
        return emb

    async def init_config(self):
        self.config = {
            'on_join_roles': [],
            'icon_url': 'https://cdn.discordapp.com/attachments/762697165117587466/934473051318390804/Logo_eld_1.png',
            'icon_footer_url': 'https://cdn.discordapp.com/attachments/759438318806237244/770439133566599169/ELDERLY_E-04.png',
            'channel_for_new_members': 1128208145324453943,
            'bot_requests_channel_id': 1128208145324453945,
            'rules_channel_id': 1128208145324453942,
            'reg_channel_id': 1128208145324453941,
            'guardian_role_id': 1128208142124191773
        }

    async def cog_load(self):
        await self.load_config()
        connection = None
        while connection is None:
            connection = await aio_pika.connect_robust(os.getenv('RABBIT_BOT_URL'))
            await asyncio.sleep(5)

        channel = await connection.channel()
        queue = await channel.declare_queue(os.getenv('RABBIT_REGISTRATION_QUERY_NAME'), durable=True)
        await queue.consume(self.process_message)

    async def process_message(self,
                              message: aio_pika.abc.AbstractIncomingMessage,
                              ) -> None:
        async with message.process():
            message_json = json.loads(message.body)
            await insert_user_in_main_table(self.bot.db_engine, int(message_json['discord']),
                                            message_json['bungie']['membership_id'])
            if message_json['admin']:
                await insert_extended_data(self.bot.db_engine,
                                           int(message_json['discord']),
                                           message_json['bungie'],
                                           message_json['admin'])
            await self.process_registration(int(message_json['discord']),
                                            message_json['bungie'])

    async def check_and_send_register(self, discord_id, bungie_id,
                                      member: discord.Member | None = None,
                                      guild: discord.Guild | None = None,
                                      extra_text: str | None = None):
        if not guild:
            guild: discord.Guild = await self.bot.fetch_guild(main_guild_id)
        if not member:
            member = await guild.fetch_member(discord_id)
        reg_channel = await guild.fetch_channel(self.config['reg_channel_id'])
        guardian_role = guild.get_role(self.config['guardian_role_id'])

        member_clans_list = await get_clan_list_by_bungie_id(bungie_id)
        local_clan_ids_list = await get_full_clans_ids(self.bot.db_engine)

        member_clans_text = "\n".join([clan.name for clan in member_clans_list])
        guardian = bool(set([clan.group_id for clan in member_clans_list]) & set(local_clan_ids_list))

        if guardian:
            await member.add_roles(guardian_role, reason=member_clans_text)
            view = None
        else:
            member_clans_text = f'Игрок не состоит в кланах ElderLy!\n{member_clans_text}'
            view = discord.ui.View()
            view.add_item(InviteButton(bungie_id))
            view.stop()
        if extra_text:
            member_clans_text += f'\n{extra_text}'
        await reg_channel.send(f'Регистрация <@{discord_id}>\n' + member_clans_text, view=view)

    async def process_registration(self, discord_id, bungie_data):
        guild: discord.Guild = await self.bot.fetch_guild(main_guild_id)
        try:
            member = await guild.fetch_member(discord_id)
        except discord.errors.NotFound:
            return
        try:
            await self.check_and_send_register(bungie_id=bungie_data['membership_id'],
                                               discord_id=discord_id,
                                               guild=guild,
                                               member=member)
        except bungio.error.BungieDead:
            try:
                await member.send('Серверы Bungie.net сейчас недоступны!\n'
                                  'Повторите попытку регистрации позже!')
            except:
                pass
        except bungio.error.BungIOException as e:
            logger.exception(e)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        for role_id in self.config['on_join_roles']:
            try:
                await member.add_roles(member.guild.get_role(role_id), reason='Выдана автоматически')
            except:
                pass

        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            registered_user = await session.scalar(select(User).where(User.discord_id == member.id))
            registered_user: User

        if registered_user:
            extra_text = None
            if registered_user.leave_server_date:
                extra_text = f'Выходил с сервера: <t:{int(registered_user.leave_server_date.timestamp())}:f>'
            await self.check_and_send_register(bungie_id=registered_user.bungie_id,
                                               discord_id=registered_user.discord_id,
                                               member=member,
                                               extra_text=extra_text)
        else:
            guild = self.bot.get_guild(main_guild_id)
            novichok_channel = guild.get_channel(self.config['channel_for_new_members'])  # ❗для-новичков❗
            role = guild.get_role(self.config['guardian_role_id'])

            color = discord.Color.from_rgb(randint(0, 255), randint(0, 255), randint(0, 255))
            emb = discord.Embed(title='Регистрация', colour=color)
            emb.set_thumbnail(url=self.config['icon_url'])
            name = f"Добро пожаловать в клан ELderLy"
            value = f"Пожалуйста, ознакомьтесь с каналом \n{novichok_channel.mention} " \
                    f"и [авторизуйтесь]({os.environ['REDIRECT_URI']}auth/bungie)\n" \
                    f"Спасибо!\n" \
                    f"**Внимание!**\n" \
                    f"```Для авторизации, сайт использует файлы cookie!\n" \
                    f"Пожалуйста, убедитесь, что разрешили сайту их использовать!\n" \
                    f"Все данные для входа Вы вводите ТОЛЬКО на официальных сайтах bungie.net и discord.com\n" \
                    f"После авторизации бот связывает Ваши BungieID и DiscordID.\n" \
                    f"После авторизации Вы получите роль {role.name} и возможность получить все роли,\n" \
                    f"связанные со статистикой.```"
            emb.add_field(name=name, value=value)
            emb.set_image(url=self.config['icon_footer_url'])
            reg_view = discord.ui.View(timeout=None)
            reg_view.add_item(RegButton(extended=False))
            try:
                await member.send(embed=emb, view=reg_view)
            except:
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id == self.config['reg_channel_id']:
            if message.author.get_role(self.config['guardian_role_id']):
                return
            reg_view = discord.ui.View(timeout=None)
            reg_view.add_item(RegButton(extended=False))
            await message.reply(embed=self.create_registration_embed(), view=reg_view)

    register_commands = app_commands.Group(name='reg',
                                           description='Команды регистрации для пользователей',
                                           default_permissions=Permissions(8),
                                           guild_ids=[main_guild_id])

    @app_commands.command(name='register', description='Команда регистрации с базовым набором прав')
    async def basic_register_command(self, interaction):
        emb = self.create_registration_embed()
        reg_view = discord.ui.View(timeout=None)
        reg_view.add_item(RegButton(extended=False))
        reg_view.stop()
        await interaction.response.send_message(embed=emb, view=reg_view, ephemeral=True)

    @register_commands.command(name='extended', description='Команда регистрации с расширенным набором прав')
    async def extended_register_command(self, interaction):
        color = discord.Color.from_rgb(randint(0, 255), randint(0, 255), randint(0, 255))
        emb = discord.Embed(title='Регистрация с расширенным набором прав', colour=color)
        emb.description = f"Пожалуйста, [авторизуйтесь]({os.environ['REDIRECT_URI']}auth/bungie/admin)\n" \
                          f"Спасибо!"
        reg_view = discord.ui.View(timeout=None)
        reg_view.add_item(RegButton(extended=True))
        reg_view.stop()
        await interaction.response.send_message(embed=emb, view=reg_view, ephemeral=True)

    @tasks.loop(hours=1.0)
    async def update_refresh_tokens(self):
        await self.bot.wait_until_ready()
        async with AsyncSession(self.bot.db_engine) as session:
            expire_date = datetime.datetime.now() + datetime.timedelta(weeks=1)
            query = select(Token.bungie_id).where(Token.token_expire <= expire_date)
            expire_tokens = list(await session.scalars(query))
        for bungie_id in expire_tokens:
            await self.bot.get_valid_auth(self.bot.db_engine, bungie_id)

    @commands.hybrid_command(name='main', description='Выбрать основной аккаунт, если их привязано более одного')
    @app_commands.default_permissions(administrator=True)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def select_main_account_command(self, ctx: Context):
        async with AsyncSession(self.bot.db_engine) as session:
            query = select(Token.bungie_id).where(Token.discord_id == ctx.author.id)
            bungie_id_list = list(await session.scalars(query))
        if len(bungie_id_list) == 0:
            await ctx.reply("Вы не зарегистрированы!", mention_author=False)
            return
        elif len(bungie_id_list) == 1:
            await ctx.reply("У Вас найдено менее двух аккаунтов!", mention_author=False)
            return
        await ctx.defer()
        # await interaction.response.defer(thinking=True)
        options = []
        for bungie_id in bungie_id_list:
            clan_list = await get_clan_list_by_bungie_id(bungie_id, 254)
            bungie_name = await get_bungie_name_by_bungie_id(bungie_id, 254)

            clan_list = [clan.name for clan in clan_list]
            clan_list_text = ' '.join(clan_list) if clan_list else None
            options.append(SelectOption(label=str(bungie_id), description=f"{bungie_name}\n{clan_list_text}",
                                        value=str(bungie_id)))

        view = SelectMainAccount(ctx.guild,
                                 author_id=ctx.author.id,
                                 options=options,
                                 trusted_roles=self.bot.config['trusted_roles']
                                 )

        answer = await ctx.reply("Выберите основной аккаунт", view=view, mention_author=False)

        await view.wait()
        if view.selected_account is None:
            for item in view.children:
                item.disabled = True
            return await answer.edit(content=f"Время ожидания истекло!", view=view)

        elif view.selected_account:
            await insert_user_in_main_table(db_engine=self.bot.db_engine,
                                            discord_id=ctx.author.id,
                                            bungie_id=view.selected_account)
            await answer.edit(content=f"Основной аккаунт выбран: {view.selected_account}", view=view)

    select_main_account_command.default_permissions = Permissions(8)

    async def info_command_callback(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(thinking=True, ephemeral=True)
        bungie_ids = await search_all_bungie_ids_by_discord(self.bot.db_engine, user.id)
        if not bungie_ids:
            return await interaction.followup.send('Пользователь не зарегистрирован!', ephemeral=True)
        embed = discord.Embed(title=f'Информация о пользователе {user.display_name}')
        for bungie_id in bungie_ids:
            info = await get_info_for_bungie_id(bungie_id=bungie_id)
            bungie_name = await get_bungie_name_by_bungie_id(membership_id=bungie_id,
                                                             membership_type=254)
            embed.add_field(name=f'{bungie_name if bungie_name else bungie_id}', value='\n'.join(info))
        return await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AuthCog(bot))
    logger.info(f'Расширение {AuthCog} загружено!')
