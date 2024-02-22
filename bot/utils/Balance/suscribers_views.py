import os

import discord
from discord import SelectOption, Interaction
from dotenv import load_dotenv

load_dotenv(override=True)

main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))


class SelectColourRoleView(discord.ui.View):
    def __init__(self, bot, get_config):
        super().__init__(timeout=None)
        self.bot = bot
        self.get_config = get_config
        self.options = []
        self.update()
        self.select_role = discord.ui.Select(min_values=1, max_values=1, options=self.options,
                                             custom_id='sub:select_role')
        self.select_role.callback = self.select_callback
        self.add_item(self.select_role)

    def update(self):
        config = self.get_config()
        roles_ids = config['subscribe_colour_roles']
        self.options = []
        for i, role_id in enumerate(roles_ids):
            role: discord.Role = self.bot.get_guild(main_guild_id).get_role(role_id)
            if role:
                option = SelectOption(label=f'{i+1}. {role.name} ({role.colour})', value=f'{role_id}')
                self.options.append(option)

    def create_embed(self):
        self.update()
        embed = discord.Embed(title='Выбор цвета')
        embed.description = 'Выбор ролей доступен только для подписчиков!\n'
        config = self.get_config()
        roles_ids = config['subscribe_colour_roles']
        for i, role_id in enumerate(roles_ids):
            embed.description += f'{i+1}. <@&{role_id}>\n'
        return embed

    async def select_callback(self, interaction: Interaction):
        await interaction.response.defer()
        config = self.get_config()
        subscriber_role_id = config['subscribers_role']
        if not interaction.user.get_role(subscriber_role_id):
            return await interaction.response.send_message('Вы не являетесь подписчиком!\n'
                                                           'Для покупки подписки используйте '
                                                           '/subscribe', ephemeral=True)
        selected_role_id = int(self.select_role.values[0])
        role = interaction.guild.get_role(selected_role_id)
        if role:
            for role_id in config['subscribe_colour_roles']:
                current_role = interaction.user.get_role(role_id)
                if current_role:
                    await interaction.user.remove_roles(current_role, reason='Пользователь изменил цвет')
            await interaction.user.add_roles(role, reason='Цвет выбран пользователем')
        await interaction.message.edit(embed=self.create_embed(), view=self)
