from datetime import date


def age_from_dob(dob: date | None, *, today: date | None = None) -> int | None:
    """Whole years between `dob` and today, or None if no date of birth."""
    if dob is None:
        return None
    ref = today or date.today()
    years = ref.year - dob.year - ((ref.month, ref.day) < (dob.month, dob.day))
    return max(years, 0)
