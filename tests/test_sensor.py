from custom_components.longmont_utility.sensor import SENSOR_DESCRIPTIONS


def test_exposes_three_health_sensors() -> None:
    assert {item.key for item in SENSOR_DESCRIPTIONS} == {
        "data_age",
        "last_success",
        "latest_interval",
    }
