"""UK phone number utilities (phonenumbers lib, region GB)."""

import phonenumbers


def normalize_uk_phone(raw: str) -> str:
    """Parse `raw` as a UK number and return E.164 format (e.g. +447...).

    Raises:
        ValueError("Invalid UK phone number"): if parsing fails or the
            number is not possible/valid or not a UK (+44) number.
    """
    if not raw or not str(raw).strip():
        raise ValueError("Invalid UK phone number")
    try:
        number = phonenumbers.parse(str(raw), "GB")
    except Exception:
        raise ValueError("Invalid UK phone number")
    try:
        possible = phonenumbers.is_possible_number(number)
        valid = phonenumbers.is_valid_number(number)
    except Exception:
        raise ValueError("Invalid UK phone number")
    if not possible or not valid:
        raise ValueError("Invalid UK phone number")
    if number.country_code != 44:
        raise ValueError("Invalid UK phone number")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def is_valid_uk_mobile(raw: str) -> bool:
    """Return True if `raw` is a valid UK mobile number, else False. Never raises."""
    try:
        normalized = normalize_uk_phone(raw)
    except Exception:
        return False
    try:
        number = phonenumbers.parse(normalized, "GB")
        if not phonenumbers.is_valid_number(number):
            return False
        number_type = phonenumbers.number_type(number)
        return number_type in (
            phonenumbers.PhoneNumberType.MOBILE,
            phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE,
        )
    except Exception:
        return False
