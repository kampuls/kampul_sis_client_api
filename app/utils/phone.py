"""Phone number matching helpers.

Phone columns in this database are not normalised: the same Cambodian number may
be stored as ``096...``, ``96...``, ``85596...`` or ``+85596...`` depending on
which import or form created the row. Lookups therefore compare against every
plausible spelling rather than a single string.
"""

from typing import List, Optional


def canonical_phone(phone: Optional[str]) -> Optional[str]:
    """Reduce a stored phone to one comparable key, or None if there isn't one.

    ``096555444``, ``96555444``, ``85596555444`` and ``+855 96 555 444`` all
    collapse to ``96555444``. Use this to decide whether two rows hold the same
    number; use :func:`get_phone_variations` to search for one in the database.
    """
    if not phone:
        return None
    digits = "".join(filter(str.isdigit, phone))
    if not digits:
        return None
    if digits.startswith("855"):
        digits = digits[3:]
    digits = digits.lstrip("0")
    return digits or None


def get_phone_variations(phone: str) -> List[str]:
    """
    Generate variations of a phone number to handle inconsistent database formats.

    Variations generated:
    1. Clean number (digits only)
    2. Local format with leading zero (e.g., 096...)
    3. Local format without leading zero (e.g., 96...)
    4. International format (e.g., +85596...) if originally provided
    """
    if not phone:
        return []

    variations = set()

    # 0. Original input stripped
    cleaned = phone.strip()
    variations.add(cleaned)

    # Remove all non-digit characters for processing
    digits = "".join(filter(str.isdigit, cleaned))

    if not digits:
        return [v for v in variations if v]

    # 1. Format: Digits only (e.g., 85596...)
    variations.add(digits)

    # Handle Cambodia (+855) specific logic as it's the primary context
    # If starts with 855, remove it to get local parts
    if digits.startswith("855"):
        local_part = digits[3:]
    else:
        local_part = digits

    # 2. Local format without leading zero (e.g., 96...)
    # Remove leading zero if present
    no_zero = local_part.lstrip("0")
    if no_zero:
        variations.add(no_zero)
        # 3. Local format with leading zero (e.g., 096...)
        variations.add("0" + no_zero)

    # Never return an empty variation: ``phone IN ('', ...)`` would match every
    # row whose phone column is blank and hand the caller a stranger's account.
    return [v for v in variations if v]
