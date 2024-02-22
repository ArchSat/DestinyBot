import logging
import os

import discord
from dotenv import load_dotenv

from ORM.schemes.Meeting import Meeting, MeetingChannel, MeetingMember, MemberStatus
from utils.logger import create_logger

load_dotenv(override=True)

main_guild_id = int(os.getenv('DISCORD_GUILD_ID'))

logger = create_logger(__name__)


def init_channel_embed(title, description) -> discord.Embed:
    return discord.Embed(title=title, description=description)


def create_meeting_embed() -> discord.Embed:
    embed = discord.Embed(title='Создание сбора...')
    return embed


def create_embed(meeting: Meeting):
    active_members = [member for member in meeting.meeting_members
                      if member.status in [MemberStatus.LEADER, MemberStatus.MEMBER]]
    main_memberships_list = [mid for mid in map(lambda l: l.other_data.get("membership_id", None),
                                                active_members) if mid]
    guardian_report_link = f'https://guardian.report/?guardians={",".join(map(str, main_memberships_list))}'

    title = f'{meeting.meeting_channel.name}\n'
    count = meeting.fireteam_max - len(active_members) + 1
    if count:
        title += f'Осталось: +{count}'
    else:
        title += 'Сбор завершен'

    embed = discord.Embed(title=title,
                          description=meeting.comment)
    if main_memberships_list:
        embed.url = guardian_report_link

    members_rows = []
    for i, member in enumerate(active_members):
        member: MeetingMember
        member_text = f"#{i + 1} <@{member.discord_id}>"
        if member.bungie_name:
            member_text += f"({member.bungie_name})"

            member_metric_value = member.other_data.get('metric_value', None)
            if member_metric_value is not None:
                member_text += f" | {member.other_data['metric_value']}"

            if meeting.meeting_channel.activity_type:
                resource_link = meeting.meeting_channel.activity_type.value(**member.other_data)
                if resource_link:
                    if member_metric_value is not None:
                        member_text = \
                            member_text.replace(f' | {member_metric_value}',
                                                f" | [{member_metric_value}]({resource_link})")
                    else:
                        # Название ресурса генерируется напрямую из названий атрибутов Enum ActivityType
                        resource_name = meeting.meeting_channel.activity_type.name
                        resource_name = resource_name.replace('_', ' ').title().replace(' ', '')
                        member_text += f' | [{resource_name}]({resource_link})'

        if member.status == MemberStatus.LEADER:
            member_text = f'{member_text} <:leader:975902609040867409>'

        members_rows.append(member_text)
    embed.add_field(name='Боевая группа:', value='\n'.join(members_rows))
    embed.set_footer(text=f'ID: {meeting.meeting_id}')
    if meeting.meeting_channel.icon_url:
        embed.set_thumbnail(url=meeting.meeting_channel.icon_url)
    embed.timestamp = meeting.start_at
    return embed
