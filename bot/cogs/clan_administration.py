import datetime
import logging
import os
from typing import List, Union

import discord
from bungio.error import BungieException, BungieDead
from bungio.models import GroupV2, GroupApplicationResponse, AuthData, DestinyClan, \
    RuntimeGroupMemberType, GroupResponse, DestinyUser, GroupApplicationRequest, GroupMemberApplication
from discord import app_commands, Interaction, InteractionType, Permissions
from discord.app_commands import Choice
from discord.ext import commands
from discord.ext.commands import Context, CommandInvokeError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from utils.ClanAdmin.cls import clear_invites, create_cls_inv_result_pages, get_inactives, \
    create_inactives_result_pages, clear_inactives, create_cls_inac_result_pages, \
    check_discord_members, get_inactives_discord, create_discord_pages, \
    UnitedMember, clear_discord
from utils.ClanAdmin.edit import EditClanButton
from utils.ClanAdmin.exceptions import MissingPermissions, MissingCommandConfig
from utils.ClanAdmin.invite import invite_to_clan_by_destiny_id, render_invite_result, invite_to_clan_by_bungie_next_id, \
    ban_in_clan_by_destiny_id
from utils.ClanAdmin.membership import search_user_by_bungie_tag_in_clan, change_members_type, render_result, \
    search_user_by_bungie_id_in_clan
from utils.logger import create_logger
from utils.paginator import Paginator
from utils.ClanAdmin.share import search_destiny_players_by_full_tag, InviteButton
from ORM.schemes.Token import Token
from ORM.schemes.User import User
from utils.CustomCog import CustomCog
from utils.clan_stats_utils import get_clan_members
from ORM.schemes.Clan import Clan
from utils.db_utils import parse_time, get_full_clans
from utils.users_utils import get_clan_list_by_bungie_id, \
    get_all_tokens_bungie_id_by_discord_id, get_admins_and_founder_for_clan, get_main_bungie_id_by_discord_id

logger = create_logger(__name__)

main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))


async def clan_membership_type_autocomplete(interaction: Interaction, current: str):
    return [Choice(name=type.name, value=type.value) for type in RuntimeGroupMemberType]


class ClanAdministration(CustomCog):
    """Администрирование кланов"""

    def __init__(self, bot):
        super().__init__(bot)

    """
    cls - группа команд
        cls inv - отменяет все приглашения в клан
        cls inac <time> - удаляет инактив за указанный период
        cls discord <time> - удаляет участников без дискорда за указанный период
    invite <bungie_tag> - приглашает участника в клан
    membership <bungie_tag> <MembershipType> - Изменяет привелегии указанного участника
    edit   
        edit about    Изменяет описание клана
        edit callsign Изменяет аббревиатуру (краткое название) клана
        edit motto    Изменяет девиз клана
        edit name     Изменяет полное имя клана
        edit privacy  Изменяет настройки приватности клан
    edit - одной командой в виде модала
    """

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction, /):
        if interaction.type != InteractionType.component:
            return
        if interaction.data['custom_id'].startswith('invite_to_clan_'):
            disabled_button_view = discord.ui.View()
            disabled_button_view.add_item(InviteButton(membership_id=None, disabled=True))
            disabled_button_view.stop()
            await interaction.response.defer(ephemeral=True, thinking=True)
            bungie_id = int(interaction.data['custom_id'].replace('invite_to_clan_', ''))

            admin_check = False
            for role in self.config.get('roles_can_invite', []):
                role_obj = self.bot.get_guild(main_guild_id).get_role(role)
                if role_obj in interaction.user.roles:
                    admin_check = True
                    break

            if not admin_check:
                await interaction.followup.send(f'Данная кнопка создана для администраторов кланов, '
                                                f'чтобы скорее пригласить человека в клан.\n'
                                                f'У Вас недостаточно прав для выполнения этого действия!',
                                                ephemeral=True)
                return

            if not bungie_id:
                await interaction.followup.send(f'Не удалось автоматически получить BungieID пользователя (ошибка '
                                                f'с аккаунтом).\n '
                                                f'Приглашение отправлено не было!', ephemeral=True)
                new_content = interaction.message.content
                new_content += f"\nНе удалось автоматически получить BungieID пользователя " \
                               f"(ошибка с аккаунтом).\n" \
                               f"Приглашение отправлено не было!"
                await interaction.message.edit(content=new_content, view=disabled_button_view)
                return

            clan_id, auth = await self.check_permissions(None, interaction.user, 'invite')

            memberships = await DestinyUser(membership_id=bungie_id, membership_type=254). \
                get_membership_data_by_id()
            bugie_tag = memberships.bungie_net_user.unique_name
            clan = await DestinyClan(group_id=clan_id).get_group()
            invite_result_list = []
            for destiny_membership in memberships.destiny_memberships:
                try:
                    inv = await destiny_membership.individual_group_invite(auth=auth,
                                                                           group_id=clan_id,
                                                                           data=GroupApplicationRequest(
                                                                               message='Invite'))
                    invite_result_list.append(inv)
                except BungieException as e:
                    invite_result_list.append(e)
            invite_embed = render_invite_result(f'BungieID: {bugie_tag}', invite_result_list,
                                                clan_name=clan.detail.name)

            await interaction.followup.send(embed=invite_embed, ephemeral=True)

    async def cog_command_error(self, context: Context, exception: Exception):
        logger.exception(exception)
        if isinstance(exception, CommandInvokeError):
            exception = exception.original
        await context.reply(f'При выполнении команды возникла ошибка {exception.__class__.__name__}\n{exception}')

    async def init_config(self):
        self.config = {
            "sudo_permissions": {
                "roles": {
                    "1128208142271000618": ["cls_inv"]},
                "users": {"190371139183312896": ["cls_inv"]
                          }
            },

            'arguments_permissions': {
                'cls_inac': {
                    'minimal_seconds': {
                        'roles': {'1128208142271000618': 432000,
                                  '1128208142178717759': 864000},
                        'users': {'190371139183312896': 0}
                    }
                },
                'cls_discord': {
                    'minimal_seconds': {
                        'roles': {},
                        'users': {'190371139183312896': 0}
                    }
                }
            },

            "roles_can_invite": []
        }

    async def check_sudo(self, command, user: Union[discord.Member, discord.User]):
        sudo_permissions = self.config.get('sudo_permissions', None)
        if not sudo_permissions:
            return False
        commands_for_user = []
        if isinstance(user, discord.Member):
            guild = user.guild
            sudo_roles = sudo_permissions.get('roles', None)
            if sudo_roles:
                for role in guild.roles:
                    if user.get_role(role.id) and str(role.id) in sudo_roles:
                        commands_for_user += sudo_roles[str(role.id)]
        sudo_users = sudo_permissions.get('users', None)
        if str(user.id) in sudo_users:
            commands_for_user += sudo_users[str(user.id)]
        return command in commands_for_user

    def check_arguments(self, command, user: Union[discord.Member, discord.User], **kwargs) -> dict:
        """
        :raise
            IncorrectArguments: invalid arguments
        Создает словать вида {Аргумент: Значение аргумента}
        Приоритет конфигурации определяется старшей ролью
        Значения определенные для пользователей имеют приоритет над любыми ролями

        :param command:
        :param user:
        :param kwargs:
        :return:
        """
        permissions = self.config.get('arguments_permissions', None)
        if not permissions:
            raise MissingCommandConfig('Не удалось проверить валидность указанных параметров')
        command_permissions = permissions.get(command, None)
        if not command_permissions:
            raise MissingCommandConfig('Не удалось проверить валидность указанных параметров')
        result_permissions = {}  # arg: value
        if isinstance(user, discord.Member):
            guild = user.guild
            for arg in kwargs:
                for role in guild.roles:
                    if user.get_role(role.id) and arg in command_permissions:
                        arg_value = command_permissions[arg].get('roles', {}).get(str(role.id), None)
                        if arg_value is not None:
                            result_permissions.update({arg: arg_value})
        for arg in kwargs:
            arg_value = command_permissions[arg].get('users', {}).get(str(user.id), None)
            if arg_value is not None:
                result_permissions.update({arg: arg_value})
        return result_permissions

    async def get_clan_list_for_user_from_db(self, discord_id):
        async with AsyncSession(self.bot.db_engine) as session:
            clan_list = []
            user_tokes_query = select(Token.bungie_id).where(Token.discord_id == discord_id)
            bungie_ids = list(await session.scalars(user_tokes_query))
            for b_id in bungie_ids:
                clan_query = select(Clan). \
                    where((Clan.leader_bungie_id == b_id) |
                          (Clan.admins.contains(b_id)))
                clan_list += list(await session.scalars(clan_query))
        return clan_list

    async def get_auth_for_discord_id(self, discord_id):
        # Метод использует основную учетную запись
        auth = None
        async with AsyncSession(self.bot.db_engine) as session:
            bungie_id = await session.scalar(select(Token.bungie_id).where(
                Token.bungie_id == select(User.bungie_id).where(User.discord_id == discord_id).scalar_subquery()))
            try:
                auth = await self.bot.get_valid_auth(bungie_id)
            except Exception as e:
                logger.exception(e)
                pass
        return auth

    async def get_auth_for_bungie_id(self, bungie_id):
        auth = None
        try:
            auth = await self.bot.get_valid_auth(bungie_id)
        except:
            pass
        return auth

    async def clan_autocomplete(self, interaction: Interaction, current: str):
        clan_list = await self.get_clan_list_for_user_from_db(interaction.user.id)
        clan_result = [Choice(name=clan.clan_tag,
                              value=clan.clan_tag)
                       for clan in clan_list if current.lower() in clan.clan_tag.lower()][:25]
        return clan_result

    async def get_clan_id_by_tag(self, clan):
        if clan:
            async with AsyncSession(self.bot.db_engine) as session:
                clan_id_query = select(Clan.clan_id).where(Clan.clan_tag == clan)
                clan_id = await session.scalar(clan_id_query)
            if not clan_id:
                try:
                    clan_id = int(clan_id)
                except (TypeError, ValueError):
                    raise TypeError('Не удалось определить ID клана. '
                                    'Укажите корректный тег клана или ID клана.')
        else:
            clan_id = None
        return clan_id

    async def check_permissions(self, clan: Union[str, None],
                                discord_member: Union[discord.Member, discord.User],
                                command: str, founder_required: bool = False, /) \
            -> (Union[int, None], Union[AuthData, None]):
        """
        Args:
            clan - clan tag или clan id
            discord_member - пользователь Discord для проверки его прав на выполнение команды
            command - имя команды для проверки прав
        Returns:
            clan_id - идентификатор клана
            AuthData - токены
        Raises:
            TypeError - Не удалось определить клан
            ValueError - Ни одного или более одного клана найдено, нужно уточнить информацию
            MissingPermissions - Нет прав для выполнения действия в этом клане
        """
        clan_id = await self.get_clan_id_by_tag(clan)
        if not clan_id:
            auth = await self.get_auth_for_discord_id(discord_member.id)
            if not isinstance(auth, AuthData):
                raise MissingPermissions('Необходимо пройти регистрацию с расширенными правами!')
            clan_list: List[GroupV2] = await get_clan_list_by_bungie_id(membership_id=auth.membership_id,
                                                                        membership_type=auth.membership_type,
                                                                        auth=auth)
            if len(clan_list) > 1:
                if founder_required:
                    bungie_id_list = await get_all_tokens_bungie_id_by_discord_id(self.bot.db_engine, discord_member.id)
                    required_clan_id = None
                    for clan in clan_list:
                        clan_admins = await get_admins_and_founder_for_clan(clan.group_id)
                        for clan_admin in clan_admins:
                            if not clan_admin.member_type.FOUNDER:
                                continue
                            else:
                                if clan_admin.bungie_net_user_info.membership_id in bungie_id_list:
                                    if not required_clan_id:
                                        required_clan_id = clan.group_id
                                    else:
                                        raise ValueError('Найдено более одного клана на Вашем аккаунте!\n'
                                                         'Укажите клан вручную.')
                    if required_clan_id:
                        return required_clan_id, auth
                raise ValueError('Найдено более одного клана на Вашем аккаунте!\nУкажите клан вручную.')
            elif len(clan_list) == 0:
                raise ValueError('Вы не состоите ни в одном из кланов!')
            clan_id = clan_list[0].group_id
            return clan_id, auth
        else:
            clan_admins = await get_admins_and_founder_for_clan(clan_id)
            admins_bungie_ids = []
            for admin in clan_admins:
                if admin.bungie_net_user_info:
                    admins_bungie_ids.append(admin.bungie_net_user_info.membership_id)
                elif admin.destiny_user_info:
                    admins_bungie_ids.append(admin.destiny_user_info.membership_id)
            clan_founder = None
            for admin in clan_admins:
                if admin.member_type == RuntimeGroupMemberType.FOUNDER:
                    clan_founder = admin
                    break

            sudo = await self.check_sudo(command, discord_member)

            if not sudo:
                bungie_id_list = await get_all_tokens_bungie_id_by_discord_id(self.bot.db_engine, discord_member.id)
                if founder_required:
                    if clan_founder and (clan_founder.bungie_net_user_info.membership_id in bungie_id_list):
                        auth = await \
                            self.get_auth_for_bungie_id(clan_founder.bungie_net_user_info.membership_id)
                        if auth:
                            return clan_id, auth
                    raise MissingPermissions('Для выполнения этого действия '
                                             'требуется регистрация лидера клана с повышенными правами!')
                interseption = list(set(bungie_id_list) & set(admins_bungie_ids))
                if interseption:
                    if clan_founder.bungie_net_user_info.membership_id in interseption:
                        auth = await \
                            self.get_auth_for_bungie_id(clan_founder.bungie_net_user_info.membership_id)
                        if auth:
                            return clan_id, auth
                    try:
                        clan_admins.remove(clan_founder)
                    except ValueError:
                        pass

                    for admin in clan_admins:
                        if admin.bungie_net_user_info.membership_id not in interseption:
                            continue
                        else:
                            auth = await self.get_auth_for_bungie_id(admin.bungie_net_user_info.membership_id)
                            if auth:
                                return clan_id, auth
                    raise MissingPermissions('У Вас нет зарегистрированной учетной записи с необходимыми правами!')
                else:
                    raise MissingPermissions('Вы не можете выполнять действия в этом клане!')
            else:
                if founder_required:
                    if clan_founder:
                        auth = await self.get_auth_for_bungie_id(clan_founder.bungie_net_user_info.membership_id)
                        if auth:
                            return clan_id, auth
                    raise MissingPermissions('Для выполнения этого действия '
                                             'требуется регистрация лидера клана с повышенными правами!')
                if clan_founder:
                    auth = await self.get_auth_for_bungie_id(clan_founder.bungie_net_user_info.membership_id)
                    if auth:
                        return clan_id, auth
                try:
                    clan_admins.remove(clan_founder)
                except ValueError:
                    pass
                for admin in clan_admins:
                    auth = await self.get_auth_for_bungie_id(admin.bungie_net_user_info.membership_id)
                    if auth:
                        return clan_id, auth
                raise MissingPermissions('Не найдено учетных записей для выполнения этого действия!')

    @commands.hybrid_group(name='cls', guild_ids=[main_guild_id])
    @app_commands.guilds(main_guild_id)
    @app_commands.default_permissions(administrator=True)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def cls_group(self, ctx):
        await ctx.send('cls - группа команд для управления участниками клана и приглашениями')

    @cls_group.command(name='inv', guild_ids=[main_guild_id])
    @app_commands.describe(clan='Тег или ID клана')
    @app_commands.autocomplete(clan=clan_autocomplete)
    async def cls_inv_command(self, ctx: commands.Context, clan: Union[str, None]):
        await ctx.defer()
        clan_id, auth = await self.check_permissions(clan, ctx.author, 'cls_inv')

        result = await clear_invites(clan_id, auth)
        clan: GroupResponse = await DestinyClan(group_id=clan_id).get_group()
        pages = create_cls_inv_result_pages(result=result, clan=clan)
        if pages:
            await Paginator().start(ctx=ctx, pages=pages)
        else:
            await ctx.reply(embed=discord.Embed(title='Отмена приглашений\n'
                                                      f'{clan.detail.name}', colour=discord.Color.green(),
                                                description='В данный момент в клане нет приглашений!'))

    @cls_group.command(name='inac', guild_ids=[main_guild_id])
    @app_commands.describe(clan='Тег или ID клана',
                           time='За какой интервал исключать участников')
    @app_commands.autocomplete(clan=clan_autocomplete)
    async def cls_inac_command(self, ctx: commands.Context, time: Union[str, None], clan: Union[str, None]):
        await ctx.defer()
        if not time:
            time = datetime.timedelta(days=21)
        else:
            time: datetime.timedelta = parse_time(time)
        arguments_values = self.check_arguments(command='cls_inac',
                                                user=ctx.author,
                                                minimal_seconds=time)
        clan_id, auth = await self.check_permissions(clan, ctx.author, 'cls_inac')
        inactive_list = await get_inactives(clan_id=clan_id, inactive_time=time)
        clan: GroupResponse = await DestinyClan(group_id=clan_id).get_group()
        pages = create_inactives_result_pages(time=time, result=inactive_list, clan=clan)
        if pages:
            if arguments_values['minimal_seconds'] > time.total_seconds():
                # Некорректный аргумент времени (участник не удовлетворяет условиям)
                view = Paginator(accept_reject_buttons=False)
                interval = datetime.timedelta(seconds=arguments_values['minimal_seconds'])
                text = f'*Вы не можете исключать участников более чем за {interval}*!'
            else:
                view = Paginator(accept_reject_buttons=True, extra_data=inactive_list)
                text = None
            await view.start(ctx=ctx, pages=pages, text=text)
            await view.wait()
            if view.confirmed:
                cleared_members = await clear_inactives(inactive_list=view.extra_data, auth_data=auth)
                error = 0
                for res in cleared_members:
                    if isinstance(cleared_members[res][1], BungieException):
                        error += 1
                pages = create_cls_inac_result_pages(result=cleared_members, clan=clan, time=time)
                return await Paginator(accept_reject_buttons=False).start(
                    ctx=ctx,
                    pages=pages,
                    text=f"Всего: {len(cleared_members)}\n"
                         f"Успешно "
                         f"исключено: {len(cleared_members) - error}\n"
                         f"Ошибок при исключении: {error}")
        else:
            await ctx.reply(embed=discord.Embed(title=f'Инактив более {time}\n'
                                                      f'{clan.detail.name}', colour=discord.Color.green(),
                                                description='Неактивных игроков с указанным параметром времени нет!'))

    @cls_group.command(name='discord', guild_ids=[main_guild_id])
    @app_commands.describe(clan='Тег или ID клана',
                           time='За какой интервал исключать участников')
    @app_commands.autocomplete(clan=clan_autocomplete)
    async def cls_discord_command(self, ctx: commands.Context, time: Union[str, None], clan: Union[str, None]):
        await ctx.defer()
        if not time:
            time = datetime.timedelta(seconds=0)
        else:
            time: datetime.timedelta = parse_time(time)
        arguments_values = self.check_arguments(command='cls_discord',
                                                user=ctx.author,
                                                minimal_seconds=time)
        clan_id, auth = await self.check_permissions(clan, ctx.author, 'cls_discord')

        clan_members = await get_clan_members(clan_id=clan_id)
        clan: GroupResponse = await DestinyClan(group_id=clan_id).get_group()
        bungie_id_list = [member.bungie_net_user_info.membership_id
                          for member in clan_members if member.bungie_net_user_info]

        discord_members = await check_discord_members(bungie_id_list=bungie_id_list,
                                                      guild=ctx.guild,
                                                      db_engine=self.bot.db_engine)
        new_clan_members = []
        for member in clan_members:
            new_member = UnitedMember(destiny_member=member, discord_member=None)
            if member.bungie_net_user_info and member.bungie_net_user_info.membership_id in discord_members:
                new_member.discord_member = discord_members[member.bungie_net_user_info.membership_id]
            new_clan_members.append(new_member)

        members_for_cls = await get_inactives_discord(clan_members=new_clan_members, time=time)
        registered = [new_clan_member for new_clan_member in new_clan_members if new_clan_member.discord_member]
        leaved = [new_clan_member for new_clan_member in new_clan_members
                  if isinstance(new_clan_member.discord_member, int)]
        text = f"Всего участников: {len(clan_members)}\n" \
               f"Всего зарегистрировано: {len(registered)}\n" \
               f"Всего покинуло сервер: {len(leaved)}\n" \
               f"Всего не зарегистрировано: {len(clan_members) - len(registered)}"
        if 'minimal_seconds' not in arguments_values or arguments_values['minimal_seconds'] > time.total_seconds():
            view = Paginator(accept_reject_buttons=False)
            pages = create_discord_pages(time=time, input_result=new_clan_members, clan=clan)
            if 'minimal_seconds' in arguments_values:
                interval = datetime.timedelta(seconds=arguments_values['minimal_seconds'])
                text += f'\n*Вы не можете исключать участников более чем за {interval}*!'
            else:
                pass
        else:
            view = Paginator(accept_reject_buttons=True, extra_data=new_clan_members)
            pages = create_discord_pages(time=time, input_result=members_for_cls, clan=clan)

        await view.start(ctx=ctx, pages=pages, text=text)
        await view.wait()
        if view.confirmed:
            cleared_members = await clear_discord(inactive_list=view.extra_data, auth_data=auth)
            error = 0
            for res in cleared_members:
                if isinstance(cleared_members[res][1], BungieException):
                    error += 1
            pages = create_cls_inac_result_pages(result=cleared_members, clan=clan, time=time)
            return await Paginator(accept_reject_buttons=False).start(
                ctx=ctx,
                pages=pages,
                text=f"Всего: {len(cleared_members)}\n"
                     f"Успешно "
                     f"исключено: {len(cleared_members) - error}\n"
                     f"Ошибок при исключении: {error}")

    @commands.hybrid_command(name='invite', guild_ids=[main_guild_id])
    @app_commands.guilds(main_guild_id)
    @app_commands.describe(clan='Тег или ID клана',
                           bungie_tag='BungieTag игрока')
    @app_commands.autocomplete(clan=clan_autocomplete)
    @app_commands.default_permissions(administrator=True)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def invite_to_clan_command(self, ctx, bungie_tag: str, clan: Union[str, None]):
        await ctx.defer()
        clan_id, auth = await self.check_permissions(clan, ctx.author, 'invite')

        destiny_memberships = await search_destiny_players_by_full_tag(bungie_tag=bungie_tag,
                                                                       client=self.bot.bungio_client)
        invite_results = []
        for membership in destiny_memberships:
            invite_result: GroupApplicationResponse | BungieException = \
                await invite_to_clan_by_destiny_id(clan_id=clan_id,
                                                   auth=auth,
                                                   membership_id=membership.membership_id,
                                                   membership_type=membership.membership_type)
            invite_results.append(invite_result)
        clan = await DestinyClan(group_id=clan_id).get_group()
        embed = render_invite_result(bungie_tag=bungie_tag, invite_results=invite_results, clan_name=clan.detail.name)
        await ctx.send(embed=embed)

    @commands.hybrid_group(name='membership', guild_ids=[main_guild_id])
    @app_commands.guilds(main_guild_id)
    @app_commands.default_permissions(administrator=True)
    @commands.guild_only()
    async def membership_group(self, ctx):
        pass

    @membership_group.command(name='bungie', guild_ids=[main_guild_id])
    @app_commands.describe(clan='Тег или ID клана',
                           bungie_tag='BungieTag игрока')
    @app_commands.autocomplete(clan=clan_autocomplete, new_membership_type=clan_membership_type_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def change_membership_type_by_bungie_command(self, ctx,
                                                       bungie_tag: str,
                                                       new_membership_type: int,
                                                       clan: Union[str, None]):
        await ctx.defer()
        clan_id, auth = await self.check_permissions(clan, ctx.author, 'membership', True)

        members_in_clan = await search_user_by_bungie_tag_in_clan(bungie_tag=bungie_tag,
                                                                  clan_id=clan_id,
                                                                  client=self.bot.bungio_client)

        result = await change_members_type(members_list=members_in_clan,
                                           new_member_type=new_membership_type, clan_id=clan_id, auth=auth)
        await ctx.send(embed=render_result(result, bungie_tag))

    @membership_group.command(name='discord', guild_ids=[main_guild_id])
    @app_commands.describe(clan='Тег или ID клана',
                           user='Discord пользователь')
    @app_commands.autocomplete(clan=clan_autocomplete, new_membership_type=clan_membership_type_autocomplete)
    @app_commands.default_permissions(administrator=True)
    @commands.has_permissions(administrator=True)
    async def change_membership_type_by_discord_command(self, ctx,
                                                        user: discord.Member,
                                                        new_membership_type,
                                                        clan: Union[str, None]):
        await ctx.defer()
        clan_id, auth = await self.check_permissions(clan, ctx.author, 'membership', True)
        bungie_id = await get_main_bungie_id_by_discord_id(self.bot.db_engine, user.id)
        members_in_clan = await search_user_by_bungie_id_in_clan(bungie_id=bungie_id,
                                                                 clan_id=clan_id)

        result = await change_members_type(members_list=members_in_clan,
                                           new_member_type=new_membership_type, clan_id=clan_id, auth=auth)
        await ctx.send(embed=render_result(result, f'{user.display_name} ({bungie_id})'))

    @commands.hybrid_command(name='edit_clan', guild_ids=[main_guild_id])
    @app_commands.describe(clan='Тег или ID клана')
    @app_commands.default_permissions(administrator=True)
    @app_commands.guilds(main_guild_id)
    @commands.has_permissions(administrator=True)
    async def edit_clan_command(self, ctx, clan: Union[str, None]):
        await ctx.defer(ephemeral=True)
        clan_id, auth = await self.check_permissions(clan, ctx.author, 'edit', True)
        """
        edit about    Изменяет описание клана
        edit callsign Изменяет аббревиатуру (краткое название) клана
        edit motto    Изменяет девиз клана
        edit name     Изменяет полное имя клана
        edit privacy  Изменяет настройки приватности клан
        """
        group = await DestinyClan(group_id=clan_id).get_group()
        view = discord.ui.View(timeout=600)
        view.add_item(EditClanButton(group=group.detail, auth=auth))
        await ctx.send(view=view, ephemeral=True)

    @commands.hybrid_command(name='spamban', guild_ids=[main_guild_id])
    @app_commands.describe(bungie_tag='BungieID игрока')
    @app_commands.guilds(main_guild_id)
    @app_commands.default_permissions(administrator=True)
    @commands.guild_only()
    async def spamban_by_bungie_command(self, ctx, bungie_tag: str):
        await ctx.defer()
        destiny_memberships = await search_destiny_players_by_full_tag(bungie_tag=bungie_tag,
                                                                       client=self.bot.bungio_client)
        memberships_text = "\n".join([str(d) for d in destiny_memberships])
        result_message = await ctx.send(f'Игрок найден: {memberships_text}')

        clan_list = await get_full_clans(self.bot.db_engine)
        for clan in clan_list:
            try:
                clan_id, auth = await self.check_permissions(clan.clan_tag, ctx.author, 'spamban')
                for membership in destiny_memberships:
                    ban_result: int | BungieException = \
                        await ban_in_clan_by_destiny_id(clan_id=clan_id,
                                                        auth=auth,
                                                        membership_id=membership.membership_id,
                                                        membership_type=membership.membership_type)
                    if ban_result == 0:
                        ban_result = 'Игрок забанен'
            except Exception as e:
                ban_result = e
            try:
                result_message = await result_message.edit(
                content=result_message.content + f"\nКлан {clan.clan_tag} ({clan.clan_id}): "
                                                 f"{str(ban_result)}")
            except Exception as e:
                result_message = await result_message.reply(f"Клан {clan.clan_tag} ({clan.clan_id}): "
                                                            f"{str(ban_result)}")
        await ctx.send('Выполнение команды завершено!')


async def setup(bot):
    await bot.add_cog(ClanAdministration(bot))
    logger.info(f'Расширение {ClanAdministration} загружено!')
