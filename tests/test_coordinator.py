from datetime import date

from custom_components.longmont_utility.coordinator import refresh_window


def test_initial_refresh_requests_portal_maximum() -> None:
    assert refresh_window(date(2026, 9, 7), initial=True) == (
        date(2026, 6, 9),
        date(2026, 9, 6),
    )


def test_recurring_refresh_revisits_seven_complete_dates() -> None:
    assert refresh_window(date(2026, 9, 7), initial=False) == (
        date(2026, 8, 31),
        date(2026, 9, 6),
    )
