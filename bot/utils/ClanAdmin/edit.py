from typing import Union

import discord.ui
from bungio.error import BungieException
from bungio.models import GroupV2, AuthData, GroupEditAction
from discord import ui, Interaction, ButtonStyle


class EditClanButton(discord.ui.Button):
    def __init__(self, group: GroupV2, auth: AuthData):
        self.group = group
        self.auth = auth
        super().__init__(label='Редактировать', style=ButtonStyle.green)

    async def callback(self, interaction: Interaction):
        await interaction.response.send_modal(EditClanModal(self.group, self.auth))
        for item in self.view.children:
            item.disabled = True
        await interaction.edit_original_response(view=self.view)


class EditClanModal(discord.ui.Modal):
    def __init__(self, group: GroupV2, auth: AuthData):
        super().__init__(title='Редактирование клана')
        """
            about    Изменяет описание клана
            callsign Изменяет аббревиатуру (краткое название) клана
            motto    Изменяет девиз клана
            name     Изменяет полное имя клана
            privacy  Изменяет настройки приватности клан
        """
        self.group = group
        self.auth = auth
        self.clan_name = ui.TextInput(label='Имя клана',
                                      style=discord.TextStyle.short,
                                      default=group.name,
                                      placeholder=group.name[:100],
                                      required=True)
        self.add_item(self.clan_name)

        self.clan_callsign = ui.TextInput(label='Тэг клана',
                                          style=discord.TextStyle.short,
                                          default=group.clan_info.clan_callsign,
                                          placeholder=group.clan_info.clan_callsign[:100],
                                          required=True)
        self.add_item(self.clan_callsign)

        self.motto = ui.TextInput(label='Девиз клана',
                                  style=discord.TextStyle.short,
                                  default=group.motto,
                                  placeholder=group.motto[:100],
                                  required=True)
        self.add_item(self.motto)

        self.about = ui.TextInput(label='Описание клана',
                                  style=discord.TextStyle.long,
                                  default=group.about,
                                  placeholder=group.about[:100],
                                  required=True)
        self.add_item(self.about)

        self.membership_option = ui.TextInput(label='Параметры вступления',
                                              style=discord.TextStyle.short,
                                              default=str(group.membership_option.value),
                                              placeholder=f"Reviewed: 0, Open: 1, Closed: 2",
                                              required=True)
        self.add_item(self.membership_option)

    async def on_submit(self, interaction: Interaction, /) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        """
        about: str = custom_field()
        allow_chat: bool = custom_field()
        avatar_image_index: int = custom_field()
        callsign: str = custom_field()
        chat_security: int = custom_field()
        default_publicity: int = custom_field()
        enable_invitation_messaging_for_admins: bool = custom_field()
        homepage: int = custom_field()
        is_public: bool = custom_field()
        is_public_topic_admin_only: bool = custom_field()
        locale: str = custom_field()
        membership_option: int = custom_field()
        motto: str = custom_field()
        name: str = custom_field()
        tags: str = custom_field()
        theme: str = custom_field()
        """
        data = GroupEditAction(about=self.about.value,
                               callsign=self.clan_callsign.value,
                               membership_option=int(self.membership_option.value),
                               motto=self.motto.value,
                               name=self.clan_name.value)
        try:
            result = await edit_clan(self.group, self.auth, data)
        except BungieException as e:
            result = e
        await interaction.followup.send(embed=render_result_clan_edit(result), clan=self.group)


def render_result_clan_edit(result: Union[BungieException | int], clan: GroupV2):
    embed = discord.Embed(title=f'Результат редактирования клана {clan.name}', colour=discord.Colour.green())
    if isinstance(result, int):
        name_field = "Клан успешно отредактирован!"
        value_field = f"{result}"
    else:
        name_field = "Ошибка редактирования клана!"
        value_field = f'Ошибка {result.code}: {result.error}\n' \
                      f'Описание: {result.message}\n'
    embed.description = f"**{name_field}**\n{value_field}\n"
    return embed


async def edit_clan(group: GroupV2, auth: AuthData, data: GroupEditAction):
    result = await group.edit_group(data=data, auth=auth)
    return result
