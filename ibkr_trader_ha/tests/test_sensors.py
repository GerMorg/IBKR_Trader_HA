from app.sensors import SensorPublisher


def test_sensor_map_contains_full_runtime_observability() -> None:
    mapped = SensorPublisher(False)._sensor_map({
        "status": "READY", "data_ready": 4, "decision_ready": 2,
        "submitted": 1, "filled": 1,
    })
    assert mapped["status"] == "READY"
    assert mapped["data_ready"] == 4
    assert mapped["decision_ready"] == 2
    assert mapped["submitted"] == 1
    assert mapped["filled"] == 1


def test_sensor_publish_is_safe_without_supervisor() -> None:
    result = SensorPublisher(True, supervisor_token="").publish({"status": "READY"})
    assert result["published"] is False
