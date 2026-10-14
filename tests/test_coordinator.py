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


class _Entry:
    entry_id = "entry-test"


class _Tracker:
    def __init__(self, result, failures: int) -> None:
        self.result = result
        self.consecutive_failures = failures

    async def async_check(self, today, now):
        return self.result


def _coordinator(monkeypatch, result, failures: int = 0):
    import custom_components.longmont_utility.coordinator as module

    created: list[tuple[str, dict]] = []
    deleted: list[str] = []
    monkeypatch.setattr(
        module.ir,
        "async_create_issue",
        lambda hass, domain, issue_id, **kwargs: created.append((issue_id, kwargs)),
    )
    monkeypatch.setattr(
        module.ir,
        "async_delete_issue",
        lambda hass, domain, issue_id: deleted.append(issue_id),
    )
    coordinator = module.LongmontDataUpdateCoordinator.__new__(
        module.LongmontDataUpdateCoordinator
    )
    coordinator.hass = None
    coordinator._entry = _Entry()
    coordinator.rates = _Tracker(result, failures)
    return coordinator, created, deleted


def test_rate_change_raises_repair_and_requests_repricing(monkeypatch) -> None:
    import asyncio
    from datetime import date

    from custom_components.longmont_utility.rates import RateCheck
    from custom_components.longmont_utility.tariff import RE_SCHEDULES

    changed = RE_SCHEDULES[0].__class__(
        date(2027, 1, 1), RE_SCHEDULES[0].customer_charge, RE_SCHEDULES[0].tiers
    )
    coordinator, created, deleted = _coordinator(
        monkeypatch, RateCheck(attempted=True, changed=changed)
    )

    assert asyncio.run(coordinator._async_check_rates()) is True
    assert deleted == ["rates_unreadable_entry-test"]
    assert created[0][0] == "rates_changed_entry-test_2027-01-01"
    assert created[0][1]["translation_key"] == "rates_changed"


def test_seven_failed_days_raise_unreadable_repair(monkeypatch) -> None:
    import asyncio

    from custom_components.longmont_utility.rates import RateCheck

    coordinator, created, _ = _coordinator(
        monkeypatch, RateCheck(attempted=True, error="TimeoutError"), failures=7
    )

    assert asyncio.run(coordinator._async_check_rates()) is False
    assert [issue for issue, _ in created] == ["rates_unreadable_entry-test"]


def test_six_failed_days_stay_quiet(monkeypatch) -> None:
    import asyncio

    from custom_components.longmont_utility.rates import RateCheck

    coordinator, created, deleted = _coordinator(
        monkeypatch, RateCheck(attempted=True, error="TimeoutError"), failures=6
    )

    assert asyncio.run(coordinator._async_check_rates()) is False
    assert created == [] and deleted == []


def test_rate_check_errors_never_fail_refresh(monkeypatch) -> None:
    import asyncio

    coordinator, created, _ = _coordinator(monkeypatch, None)

    async def boom(today, now):
        raise RuntimeError("unexpected")

    coordinator.rates.async_check = boom

    assert asyncio.run(coordinator._async_check_rates()) is False
    assert created == []
