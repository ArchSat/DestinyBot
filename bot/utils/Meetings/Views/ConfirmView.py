import discord


class ConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.confirmed = False

    @discord.ui.button(label='Опубликовать сбор')
    async def confirm_publish(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        self.confirmed = True
        await interaction.response.defer()
        await interaction.edit_original_response(view=self)
        self.stop()
