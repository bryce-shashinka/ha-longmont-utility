"""Privacy-preserving diagnostics for Longmont Utility."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from homeassistant.core import HomeAssistant

from .coordinator import CoordinatorData, LongmontConfigEntry


class _Coordinator(Protocol):
    data: CoordinatorData


def build_diagnostics(coordinator: _Coordinator) -> dict[str, Any]:
    """Build a payload containing health data and no portal identifiers."""

    data = coordinator.data
    age_hours = (
        (datetime.now(UTC) - data.latest_interval).total_seconds() / 3600
        if data.latest_interval is not None
        else None
    )
    return {
        "status": "ok" if data.last_error_category is None else "error",
        "last_success": data.last_success.isoformat(),
        "latest_interval": (
            data.latest_interval.isoformat()
            if data.latest_interval is not None
            else None
        ),
        "data_age_hours": age_hours,
        "error_category": data.last_error_category,
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: LongmontConfigEntry,
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""

    return build_diagnostics(entry.runtime_data)
