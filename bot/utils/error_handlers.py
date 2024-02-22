from discord import Interaction
from discord.ext.commands import Context
from discord.ext.commands._types import BotT

from utils.logger import create_logger

logger = create_logger('Errors')


async def on_command_error(context: Context[BotT], exception: Exception, /):
    command = context.command
    if command and command.has_error_handler():
        return

    cog = context.cog
    if cog and cog.has_error_handler():
        return

    logger.error('Ignoring exception in command %s', command, exc_info=exception)

    await context.reply(f'При выполнении команды произошла ошибка: {exception}')


async def on_application_command_error(interaction: Interaction, error: Exception):
    if interaction.response.is_done():
        await interaction.followup.send(f'При взаимодействии произошла ошибка: {error}', ephemeral=True)
    else:
        await interaction.response.send_message(f'При взаимодействии произошла ошибка: {error}', ephemeral=True)
    logger.exception(type(error))
