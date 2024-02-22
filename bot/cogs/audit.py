import datetime
import os
from typing import List

import discord
from discord import AuditLogEntry, AuditLogAction
from discord.ext import commands
from dotenv import load_dotenv
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.User import User
from utils.CustomCog import CustomCog
from utils.logger import create_logger

load_dotenv(override=True)
logger = create_logger(__name__)
main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))


class AuditCog(CustomCog):
    """Модуль аудита"""

    def __init__(self, bot):
        super().__init__(bot)

    async def init_config(self):
        self.config = {
            'roles_logs_channel_id': 888378430742220850,
        }

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        if member.guild.id != guild.id:
            return
        try:
            await guild.system_channel.send(f'{member.mention} ({member}) покинул сервер. '
                                            f'(На сервере был с <t:{int(member.joined_at.timestamp())}:f>)')
        except:
            pass
        async with AsyncSession(self.bot.db_engine) as session:
            await session.execute(update(User).
                                  where(User.discord_id == member.id).
                                  values(leave_server_date=datetime.datetime.now()))
            await session.commit()

    def create_roles_diff_embed(self, target: discord.Member,
                                add_roles_diff: List[discord.Role],
                                remove_roles_diff: List[discord.Role],
                                moderator: discord.Member):
        text = f"Изменение ролей пользователя {target.mention} ({target.display_name})\n\n"
        if add_roles_diff:
            text += "**Добавлены роли**:\n"
            add_text = f'\n'.join([f'{role.mention} ({role.name})' for role in add_roles_diff])
            text += add_text
            text += '\n\n'
        if remove_roles_diff:
            text += "**Удалены роли**:\n"
            remove_text = f'\n'.join([f'{role.mention} ({role.name})' for role in remove_roles_diff])
            text += remove_text
            text += '\n\n'

        text += f'**Модератор**\n{moderator.mention} ({moderator.display_name})'
        embed = discord.Embed()

        embed.description = text
        embed.timestamp = datetime.datetime.now()
        return embed

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: AuditLogEntry):
        if entry.user.id == self.bot.user.id:
            return
        if entry.action == AuditLogAction.member_role_update:
            roles_logs_channel_id = self.config.get('roles_logs_channel_id', None)
            if roles_logs_channel_id:
                channel = self.bot.get_guild(main_guild_id).get_channel(roles_logs_channel_id)
                if channel:
                    add_roles_diff = list(set(entry.after.roles) - set(entry.before.roles))
                    remove_roles_diff = list(set(entry.before.roles) - set(entry.after.roles))
                    embed = self.create_roles_diff_embed(target=entry.target,
                                                         add_roles_diff=add_roles_diff,
                                                         remove_roles_diff=remove_roles_diff,
                                                         moderator=entry.user)
                    await channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(AuditCog(bot))
    logger.info(f'Расширение {AuditCog} загружено!')
