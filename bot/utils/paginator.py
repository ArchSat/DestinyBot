from __future__ import annotations

import discord
from discord.ext import commands


class Paginator(discord.ui.View):
    """
    Embed Paginator.

    Parameters:
    ----------
    timeout: int
        How long the Paginator should timeout in, after the last interaction. (In seconds) (Overrides default of 60)
    PreviousButton: discord.ui.Button
        Overrides default previous button.
    NextButton: discord.ui.Button
        Overrides default next button.
    PageCounterStyle: discord.ButtonStyle
        Overrides default page counter style.
    InitialPage: int
        Page to start the pagination on.
    AllowExtInput: bool
        Overrides ability for 3rd party to interract with button.
    """

    def __init__(self, *,
                 timeout: int | None = 60,
                 previous_button: discord.ui.Button = discord.ui.Button(emoji=discord.PartialEmoji(name="\U000025c0")),
                 next_button: discord.ui.Button = discord.ui.Button(emoji=discord.PartialEmoji(name="\U000025b6")),
                 accept_reject_buttons: bool = False,
                 extra_data=None,
                 page_counter_style: discord.ButtonStyle = discord.ButtonStyle.grey,
                 initial_page: int = 0, allow_ext_input: bool = False,
                 ephemeral: bool = False) -> None:
        self.previous_button = previous_button
        self.next_button = next_button
        self.accept_reject_buttons = accept_reject_buttons
        self.page_counter_style = page_counter_style
        self.initial_page = initial_page
        self.allow_ext_input = allow_ext_input
        self.ephemeral = ephemeral
        if accept_reject_buttons:
            self.accept = discord.ui.Button(emoji="🟩")
            self.reject = discord.ui.Button(emoji="🟥")
        self.extra_data = extra_data
        self.confirmed = False

        self.pages = None
        self.ctx = None
        self.message = None
        self.current_page = None
        self.page_counter = None
        self.total_page_count = None

        super().__init__(timeout=timeout)

    async def start(self, ctx: discord.Interaction | commands.Context,
                    pages: list[discord.Embed],
                    text: str | None = None):

        if isinstance(ctx, discord.Interaction):
            ctx = await commands.Context.from_interaction(ctx)

        self.pages = pages
        self.total_page_count = len(pages)
        self.ctx = ctx
        self.current_page = self.initial_page

        self.previous_button.callback = self.previous_button_callback
        self.next_button.callback = self.next_button_callback

        self.page_counter = SimplePaginatorPageCounter(style=self.page_counter_style,
                                                       TotalPages=self.total_page_count,
                                                       InitialPage=self.initial_page)
        if self.total_page_count == 1:
            self.previous_button.disabled = True
            self.next_button.disabled = True
        else:
            self.previous_button.disabled = False
            self.next_button.disabled = False

        self.add_item(self.previous_button)
        if self.accept_reject_buttons:
            self.accept.callback = self.accept_button_callback
            self.reject.callback = self.reject_button_callback
            self.add_item(self.accept)
            self.add_item(self.page_counter)
            self.add_item(self.reject)
        else:
            self.add_item(self.page_counter)
        self.add_item(self.next_button)
        await self.send_message(ctx=ctx, text=text)

    async def send_message(self, ctx, text):
        self.message = await ctx.send(content=text,
                                      embed=self.pages[self.initial_page],
                                      view=self,
                                      ephemeral=self.ephemeral)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

    async def previous(self):
        if self.current_page == 0:
            self.current_page = self.total_page_count - 1
        else:
            self.current_page -= 1

        self.page_counter.label = f"{self.current_page + 1}/{self.total_page_count}"
        await self.message.edit(embed=self.pages[self.current_page], view=self)

    async def next(self):
        if self.current_page == self.total_page_count - 1:
            self.current_page = 0
        else:
            self.current_page += 1

        self.page_counter.label = f"{self.current_page + 1}/{self.total_page_count}"
        await self.message.edit(embed=self.pages[self.current_page], view=self)

    async def next_button_callback(self, interaction: discord.Interaction):
        if self.allow_ext_input and interaction.user != self.ctx.author:
            embed = discord.Embed(description="Вы не можете использовать это!",
                                  color=discord.Colour.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        await self.next()
        await interaction.response.defer()

    async def previous_button_callback(self, interaction: discord.Interaction):
        if self.allow_ext_input and interaction.user != self.ctx.author:
            embed = discord.Embed(description="Вы не можете использовать это!",
                                  color=discord.Colour.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        await self.previous()
        await interaction.response.defer()

    async def accept_button_callback(self, interaction: discord.Interaction):
        if self.allow_ext_input and interaction.user != self.ctx.author:
            embed = discord.Embed(description="Вы не можете использовать это!",
                                  color=discord.Colour.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        self.confirmed = True
        await interaction.response.defer()
        await self.on_timeout()
        self.stop()

    async def reject_button_callback(self, interaction: discord.Interaction):
        if self.allow_ext_input and interaction.user != self.ctx.author:
            embed = discord.Embed(description="Вы не можете использовать это!",
                                  color=discord.Colour.red())
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        self.confirmed = False
        await interaction.response.defer()
        await self.on_timeout()
        self.stop()


class SimplePaginatorPageCounter(discord.ui.Button):
    def __init__(self, style: discord.ButtonStyle, TotalPages, InitialPage, **kwargs):
        super().__init__(label=f"{InitialPage + 1}/{TotalPages}", style=style, disabled=True, **kwargs)
