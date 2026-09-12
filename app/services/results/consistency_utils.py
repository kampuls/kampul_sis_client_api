from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

def safe_decimal(value, default=Decimal('0')):
    """Safely convert value to Decimal."""
    if value is None:
        return default
    try:
        if isinstance(value, str):
            value = value.replace(',', '').replace(' ', '').strip()
            if not value:
                return default
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default

def round_decimal_to_2_places(value: Decimal) -> Decimal:
    """Rounds a Decimal to 2 places."""
    return value.quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)

def q2(value: Decimal) -> Decimal:
    """Quantize to 2 decimals (display precision)."""
    return round_decimal_to_2_places(safe_decimal(value, Decimal("0")))


def is_match(a: Decimal, b: Decimal, tol: Decimal = Decimal("0.01")) -> bool:
    """Compare at display precision with tolerance."""
    try:
        return abs(q2(a) - q2(b)) <= tol
    except Exception:
        return False


def build_consistency_check(
    label: str,
    stored_avg: Decimal | None,
    calc_avg: Decimal | None,
    *,
    stored_total: Decimal | None = None,
    calc_total: Decimal | None = None,
) -> dict | None:
    """
    Build a consistency check result object.
    Returns None if inputs are missing.
    """
    if stored_avg is None or calc_avg is None:
        return None

    stored_avg_q = q2(stored_avg)
    calc_avg_q = q2(calc_avg)
    match = is_match(stored_avg_q, calc_avg_q)

    result = {
        "is_match": match,
        "label": label,
        "stored_avg": float(stored_avg_q),
        "calc_avg": float(calc_avg_q),
        "message": ""
    }

    if stored_total is not None and calc_total is not None:
        result["stored_total"] = float(q2(stored_total))
        result["calc_total"] = float(q2(calc_total))

    if match:
        result["message"] = f"✅ Match ({stored_avg_q:.2f} vs {calc_avg_q:.2f})"
    else:
        result["message"] = (
            f"⚠️ Mismatch ({stored_avg_q:.2f} vs {calc_avg_q:.2f}). "
            f"Result may be incorrect. Please contact administrator."
        )

    return result
