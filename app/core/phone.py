"""Phone-number canonicalisation for patient identity.

Patients may type their number in many shapes — "+91 98765 43210",
"098765 43210", "9876543210" — but all of these must resolve to the *same*
patient account. We reduce a number to its national significant digits (the
bare 10-digit Indian mobile) so storage and lookups are stable regardless of
how the number was entered on the website, over voice, or via WhatsApp.
"""


def normalize_phone(raw: str) -> str:
    """Return the national significant digits of a phone number.

    Keeps digits only, then strips a leading Indian country code (``91``) or
    trunk prefix (``0``) when doing so leaves a 10-digit number. Anything that
    doesn't match those shapes is returned as its plain digits, so the function
    never raises and is safe to call on already-clean input.
    """
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        return digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        return digits[1:]
    return digits
