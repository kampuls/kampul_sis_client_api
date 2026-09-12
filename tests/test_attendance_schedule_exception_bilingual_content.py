from app.api.v1.employee_attendance import _bilingual_text_pair


def test_english_only_is_used_as_safe_khmer_fallback():
    assert _bilingual_text_pair("Staff Meeting", None) == (
        "Staff Meeting",
        "Staff Meeting",
    )


def test_khmer_only_is_used_as_safe_english_fallback():
    assert _bilingual_text_pair(None, "កិច្ចប្រជុំបុគ្គលិក") == (
        "កិច្ចប្រជុំបុគ្គលិក",
        "កិច្ចប្រជុំបុគ្គលិក",
    )


def test_distinct_translations_are_preserved():
    assert _bilingual_text_pair("Staff Meeting", "កិច្ចប្រជុំបុគ្គលិក") == (
        "Staff Meeting",
        "កិច្ចប្រជុំបុគ្គលិក",
    )
