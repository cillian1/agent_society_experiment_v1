"""Time: one simulation turn is one hour. 24 hours a day, 30 days a month, 12 months a year."""
HOURS_PER_DAY = 24
DAY = HOURS_PER_DAY
DAYS_PER_MONTH = 30
MONTHS = ["Thawing", "Blossom", "Sowing", "Greening", "Highsun", "Longday",
          "Ripening", "Harvest", "Leaffall", "Mistmoon", "Frost", "Deepwinter"]
START_HOUR = 6                      # the world begins at dawn
NIGHT_FROM, NIGHT_TO = 22, 6        # everyone sleeps from 22:00 to 06:00


def when(tick: int) -> dict:
    h = tick + START_HOUR
    days = h // HOURS_PER_DAY
    return {"hour": h % HOURS_PER_DAY, "day": days % DAYS_PER_MONTH + 1, "month": (days // DAYS_PER_MONTH) % 12 + 1,
            "month_name": MONTHS[(days // DAYS_PER_MONTH) % 12], "year": days // (DAYS_PER_MONTH * 12) + 1,
            "day_number": days + 1}


def stamp(tick: int) -> str:
    w = when(tick)
    return f"{w['month_name']} {w['day']}, year {w['year']}, {w['hour']:02d}:00"


def short(tick: int) -> str:
    w = when(tick)
    return f"{w['month_name'][:3]} {w['day']} {w['hour']:02d}:00"


def is_night(tick: int) -> bool:
    hour = when(tick)["hour"]
    return hour >= NIGHT_FROM or hour < NIGHT_TO


def part_of_day(tick: int) -> str:
    hour = when(tick)["hour"]
    return ("night" if is_night(tick) else "morning" if hour < 12 else "afternoon" if hour < 17 else "evening")


def age_text(hours: int) -> str:
    days = max(0, hours) // HOURS_PER_DAY
    if days < DAYS_PER_MONTH:
        return f"{days} day{'s' if days != 1 else ''}" if days else f"{max(0, hours)} hours"
    months, d = divmod(days, DAYS_PER_MONTH)
    if months < 12:
        return f"{months} month{'s' if months > 1 else ''}" + (f" {d} days" if d else "")
    years, months = divmod(months, 12)
    return f"{years} year{'s' if years > 1 else ''}" + (f" {months} months" if months else "")


def calendar() -> dict:
    """What the hub needs to show the same clock."""
    return {"start_hour": START_HOUR, "hours_per_day": HOURS_PER_DAY, "days_per_month": DAYS_PER_MONTH,
            "months": MONTHS, "night_from": NIGHT_FROM, "night_to": NIGHT_TO}
