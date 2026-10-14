from custom_components.longmont_utility.sensor import (
    RATE_DESCRIPTION,
    SENSOR_DESCRIPTIONS,
)


def test_exposes_three_health_sensors() -> None:
    assert {item.key for item in SENSOR_DESCRIPTIONS} == {
        "data_age",
        "last_success",
        "latest_interval",
    }


def test_rate_sensor_is_diagnostic_price_per_kwh() -> None:
    assert RATE_DESCRIPTION.key == "electricity_rate"
    assert RATE_DESCRIPTION.native_unit_of_measurement == "USD/kWh"
    assert RATE_DESCRIPTION.entity_category == "diagnostic"
