import pytest
import voluptuous as vol

from custom_components.longmont_utility.config_flow import (
    OPTIONS_SCHEMA,
    opaque_meter_unique_id,
)


def test_meter_unique_id_is_stable_and_redacted() -> None:
    first = opaque_meter_unique_id("acct-test-1", "meter-test-1")
    second = opaque_meter_unique_id("acct-test-1", "meter-test-1")

    assert first == second
    assert "acct-test-1" not in first
    assert "meter-test-1" not in first
    assert len(first) == 32


def test_options_schema_accepts_cycle_day_range() -> None:
    assert OPTIONS_SCHEMA({}) == {"billing_cycle_start_day": 1}
    assert OPTIONS_SCHEMA({"billing_cycle_start_day": "28"}) == {
        "billing_cycle_start_day": 28
    }
    for bad in (0, 29):
        with pytest.raises(vol.Invalid):
            OPTIONS_SCHEMA({"billing_cycle_start_day": bad})


def test_flow_schema_library_matches_core() -> None:
    """Suggested values only apply when markers come from the core's library."""
    from homeassistant.data_entry_flow import FlowHandler

    from custom_components.longmont_utility import config_flow

    schema = config_flow.vol.Schema({config_flow.vol.Required("username"): str})
    filled = FlowHandler().add_suggested_values_to_schema(
        schema, {"username": "someone"}
    )
    (key,) = filled.schema
    assert key.description == {"suggested_value": "someone"}
