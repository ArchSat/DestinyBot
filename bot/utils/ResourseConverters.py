from enum import Enum
from functools import partial


def raid_dungeon_report_transformer_membership_type(membership_type: int):
    converter = {
        1: 'xb',  # TigerXbox
        2: 'ps',  # TigerPsn
        3: 'pc',  # TigerSteam
        4: 'pc',  # TigerBlizzard
        5: 'pc',  # TigerStadia
        6: 'pc',  # TigerEgs
        10: 'pc'  # TigerDemon
    }
    return converter.get(membership_type)


def get_raid_report_link(**kwargs):
    membership_id, membership_type = kwargs.get('membership_id'), kwargs.get('membership_type')
    if membership_id and membership_type:
        return f"https://raid.report/{raid_dungeon_report_transformer_membership_type(membership_type)}/{membership_id}"


def get_dungeon_report_link(**kwargs):
    membership_id, membership_type = kwargs.get('membership_id'), kwargs.get('membership_type')
    if membership_id and membership_type:
        return f"https://dungeon.report/{raid_dungeon_report_transformer_membership_type(membership_type)}/{membership_id}"


def get_crusible_report_link(**kwargs):
    membership_id, membership_type = kwargs.get('membership_id'), kwargs.get('membership_type')
    if membership_id and membership_type:
        return f"https://crucible.report/{membership_type}/{membership_id}"


def get_trials_report_link(**kwargs):
    membership_id, membership_type = kwargs.get('membership_id'), kwargs.get('membership_type')
    if membership_id and membership_type:
        return f"https://trials.report/report/{membership_type}/{membership_id}"


def get_nightfall_report_link(**kwargs):
    membership_id, membership_type = kwargs.get('membership_id'), kwargs.get('membership_type')
    if membership_id and membership_type:
        return f"https://nightfall.report/guardian/{membership_type}/{membership_id}"


def get_triump_report_link(**kwargs):
    membership_id, membership_type = kwargs.get('membership_id'), kwargs.get('membership_type')
    if membership_id and membership_type:
        return f"https://triumph.report/{membership_type}/{membership_id}"


def get_destiny_tracker_link(**kwargs):
    membership_id, membership_type = kwargs.get('membership_id'), kwargs.get('membership_type')
    if membership_id and membership_type:
        return f"https://destinytracker.com/destiny-2/profile/{membership_type}/{membership_id}"


class ResourseType(Enum):
    RAID_REPORT = partial(get_raid_report_link)
    DUNGEON_REPORT = partial(get_dungeon_report_link)
    CRUSIBLE_REPORT = partial(get_crusible_report_link)
    TRIALS_REPORT = partial(get_trials_report_link)
    NIGHTFALL_REPORT = partial(get_nightfall_report_link)
    TRIUMPH_REPORT = partial(get_triump_report_link)
    DESTINY_TRACKER = partial(get_destiny_tracker_link)
