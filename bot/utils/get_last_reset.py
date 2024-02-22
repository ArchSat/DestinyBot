import datetime


# Возвращает последний недельный ресет (вторник)
def get_last_reset(date: datetime.datetime | None = None) -> datetime.datetime:
    if not date:
        date = datetime.datetime.now()
    last_reset = date - datetime.timedelta(days=7)
    last_reset = last_reset.replace(day=date.day + (1 - date.weekday()))
    last_reset = last_reset.replace(hour=20, minute=0, second=0, microsecond=0)
    if date - last_reset >= datetime.timedelta(days=7):
        last_reset += datetime.timedelta(days=7)
    elif date - last_reset < datetime.timedelta(milliseconds=0):
        last_reset -= datetime.timedelta(days=7)
    return last_reset


# Возвращает последний недельный ресет (пятница)
def get_last_friday_reset(date: datetime.datetime | None = None) -> datetime.datetime:
    if not date:
        date = datetime.datetime.now()
    last_reset = date - datetime.timedelta(days=7)
    last_reset = last_reset.replace(day=date.day + (4 - date.weekday()))
    last_reset = last_reset.replace(hour=20, minute=0, second=0, microsecond=0)
    if date - last_reset >= datetime.timedelta(days=7):
        last_reset += datetime.timedelta(days=7)
    elif date - last_reset < datetime.timedelta(milliseconds=0):
        last_reset -= datetime.timedelta(days=7)
    return last_reset


# Возвращает последний дневной ресет
def get_last_reset_day(date: datetime.datetime | None = None) -> datetime.datetime:
    if not date:
        date = datetime.datetime.now()
    last_reset = date - datetime.timedelta(days=1)
    last_reset = last_reset.replace(hour=20, minute=0, second=0, microsecond=0)
    if date - last_reset >= datetime.timedelta(days=1):
        last_reset += datetime.timedelta(days=1)
    elif date - last_reset < datetime.timedelta(milliseconds=0):
        last_reset -= datetime.timedelta(days=1)
    return last_reset
