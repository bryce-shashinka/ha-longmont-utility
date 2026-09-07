from datetime import UTC, datetime

from custom_components.longmont_utility.coordinator import CoordinatorData
from custom_components.longmont_utility.diagnostics import build_diagnostics


class FakeCoordinator:
    data = CoordinatorData(
        last_success=datetime(2026, 9, 7, 12, tzinfo=UTC),
        latest_interval=datetime(2026, 9, 6, 23, 45, tzinfo=UTC),
    )


def test_diagnostics_contain_only_public_safe_health_data() -> None:
    payload = build_diagnostics(FakeCoordinator())
    serialized = repr(payload)

    assert payload["status"] == "ok"
    assert payload["last_success"] == "2026-09-07T12:00:00+00:00"
    assert "username" not in serialized
    assert "password" not in serialized
    assert "account" not in serialized
    assert "meter" not in serialized
