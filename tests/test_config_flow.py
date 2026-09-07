from custom_components.longmont_utility.config_flow import opaque_meter_unique_id


def test_meter_unique_id_is_stable_and_redacted() -> None:
    first = opaque_meter_unique_id("acct-test-1", "meter-test-1")
    second = opaque_meter_unique_id("acct-test-1", "meter-test-1")

    assert first == second
    assert "acct-test-1" not in first
    assert "meter-test-1" not in first
    assert len(first) == 32
