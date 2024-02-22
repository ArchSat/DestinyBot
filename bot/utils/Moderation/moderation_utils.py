import datetime
import os
from functools import partial
from typing import Union, List

import bungio
import discord
from discord import Interaction
from discord.ext import commands
from discord.ext.commands import Context
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession

import utils.paginator
from ORM.schemes.User import SanctionStatus, SanctionType, Sanction
from utils.db_utils import parse_time

load_dotenv(override=True)

main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))


def render_sanction(sanction: Sanction):
    embed = discord.Embed(title=f'{sanction.type.value}', colour=discord.Colour.green())
    description = f"**ID: {sanction.id}**\n" \
                  f"Выдано (кем): <@{sanction.author_id}>\n" \
                  f"Пользователю: <@{sanction.member_id}>\n" \
                  f"Тип наказания: {sanction.type.value}\n" \
                  f"Причина выдачи: {sanction.reason}\n" \
                  f"Истекает: {f'<t:{int(sanction.expire.timestamp())}:f>' if sanction.expire else 'Бессрочно'}\n" \
                  f"Статус: {sanction.status.value}\n" \
                  f"Link: https://discord.com/channels/" \
                  f"{main_guild_id}/" \
                  f"{sanction.channel_id}" \
                  f"{'/' + str(sanction.message_id) if sanction.message_id else ''}\n"
    embed.description = description
    return embed


class SanctionModal(discord.ui.Modal):
    def __init__(self, title, target: discord.Member, sanction_type: SanctionType, duration: str, bot,
                 sanction_function: Union[partial | None]):
        super().__init__(title=title)
        self.sanction_function = sanction_function
        self.bot = bot
        self.target = target
        self.sanction_type = sanction_type
        self.reason = discord.ui.TextInput(label='Причина выдачи',
                                           style=discord.TextStyle.long,
                                           required=True)
        self.add_item(self.reason)
        self.duration = discord.ui.TextInput(label='Длительность',
                                             style=discord.TextStyle.short,
                                             default=duration,
                                             required=True)
        self.add_item(self.duration)

    async def on_submit(self, interaction: Interaction, /) -> None:
        await interaction.response.defer(ephemeral=True)
        reason = self.reason.value
        if self.duration.value is None:
            duration = 0
        else:
            duration = parse_time(self.duration.value)

        new_sanction = Sanction(
            type=self.sanction_type,
            author_id=interaction.user.id,
            member_id=self.target.id,
            reason=reason,
            expire=datetime.datetime.now() + duration if duration else None,
            channel_id=interaction.channel_id if interaction.channel else None,
            message_id=interaction.message.id if interaction.message else None,
        )
        async with AsyncSession(self.bot.db_engine, expire_on_commit=False) as session:
            session.add(new_sanction)
            try:
                await session.commit()
                await session.refresh(new_sanction)
                sanction_embed = render_sanction(new_sanction)
                await self.sanction_function(sanction=new_sanction, sanction_embed=sanction_embed, reason=reason)
                await interaction.followup.send(embed=sanction_embed, ephemeral=True)
                await interaction.channel.send(embed=sanction_embed)
            except Exception as e:
                await session.rollback()
                await interaction.followup.send(e, ephemeral=True)


class WarnListView(utils.paginator.Paginator):
    def __init__(self,
                 update_warns_func,
                 message: discord.Message | None = None,
                 persistence: bool = False):
        super().__init__(timeout=None)
        self.allow_ext_input = False
        self.persistence = persistence
        self.reply = not persistence
        self.message = message
        self.update_warns = update_warns_func
        self.warn_list = []
        self.pages = []
        self.previous_button = discord.ui.Button(emoji=discord.PartialEmoji(name="\U000025c0"),
                                                 custom_id='warn_list:prev' if persistence else None)
        self.next_button = discord.ui.Button(emoji=discord.PartialEmoji(name="\U000025b6"),
                                             custom_id='warn_list:next' if persistence else None)

        self.pages = []
        self.current_page = self.initial_page

        self.previous_button.callback = self.previous_button_callback
        self.next_button.callback = self.next_button_callback

        if self.total_page_count == 1:
            self.previous_button.disabled = True
            self.next_button.disabled = True
        else:
            self.previous_button.disabled = False
            self.next_button.disabled = False

        self.add_item(self.previous_button)
        self.add_item(self.next_button)

    async def init(self):
        self.warn_list = await self.update_warns()
        self.pages = create_warnlist_pages(self.warn_list)
        self.start = partial(self.start, pages=self.pages)

    async def update(self):
        self.warn_list = await self.update_warns()
        self.pages = create_warnlist_pages(self.warn_list)
        if self.message:
            self.message = await self.message.edit(content=self.message.content,
                                                   embed=self.pages[self.initial_page],
                                                   view=self)

    async def send_message(self, ctx, text):
        if self.reply:
            if isinstance(ctx, discord.Interaction):
                ctx = await commands.Context.from_interaction(ctx)
            self.message = await ctx.send(content=text,
                                          embed=self.pages[self.initial_page],
                                          view=self,
                                          ephemeral=self.ephemeral)
        else:
            self.message = await ctx.channel.send(content=text,
                                                  embed=self.pages[self.initial_page],
                                                  view=self)

    async def previous(self):
        if self.current_page == 0:
            self.current_page = len(self.pages) - 1
        else:
            self.current_page -= 1
        await self.message.edit(embed=self.pages[self.current_page], view=self)

    async def next(self):
        if self.current_page == len(self.pages) - 1:
            self.current_page = 0
        else:
            self.current_page += 1
        await self.message.edit(embed=self.pages[self.current_page], view=self)


def create_warnlist_pages(warnlist: List[Sanction], on_page=10):
    timestamp = datetime.datetime.now()
    rendered_pages = []
    pages = list((bungio.utils.split_list(warnlist, on_page)))
    for page_number, page in enumerate(pages):
        embed = discord.Embed(title='Список предупреждений', colour=discord.Color.green())
        embed.set_footer(text=f'Итого: {len(warnlist)} • Страница {page_number + 1}/{len(pages)}')
        for warn in page:
            field_name = f"ID: {warn.id}"
            field_value = f"Выдано (кем): <@{warn.author_id}>\n" \
                          f"Пользователю: <@{warn.member_id}>\n" \
                          f"Тип наказания: {warn.type.value}\n" \
                          f"Причина выдачи: {warn.reason}\n" \
                          f"Истекает: {f'<t:{int(warn.expire.timestamp())}:f>' if warn.expire else 'Бессрочно'}\n" \
                          f"Статус: {warn.status.value}\n" \
                          f"Link: https://discord.com/channels/" \
                          f"{main_guild_id}/" \
                          f"{warn.channel_id}" \
                          f"{'/' + str(warn.message_id) if warn.message_id else ''}\n"
            embed.add_field(name=discord.utils.escape_markdown(field_name), value=field_value, inline=False)
            embed.timestamp = timestamp
        rendered_pages.append(embed)
    if not rendered_pages:
        embed = discord.Embed(title='Список предупреждений', colour=discord.Color.green())
        embed.description = 'В данный момент нет активных предупреждений!'
        embed.set_footer(text=f'Итого: {len(warnlist)} • Страница 1/1')
        embed.timestamp = timestamp
        rendered_pages.append(embed)
    return rendered_pages
