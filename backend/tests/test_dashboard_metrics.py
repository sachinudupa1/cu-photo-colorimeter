from backend.app.model_service import _independent_test_metrics


def test_independent_test_metrics_are_grouped_by_model_and_exclude_promoted_or_rejected():
    rows = [
        {"test_id": "a", "model_version": "v2", "status": "OK", "predicted_concentration": 10.5, "reference_concentration": 10.0},
        {"test_id": "b", "model_version": "v2", "status": "CHECK", "predicted_concentration": 19.0, "reference_concentration": 20.0},
        {"test_id": "c", "model_version": "v2", "status": "OK", "predicted_concentration": 5.0, "reference_concentration": 5.0, "promoted_to_training": True},
        {"test_id": "d", "model_version": "v2", "status": "RETAKE", "predicted_concentration": None, "reference_concentration": 10.0},
        {"test_id": "e", "model_version": "v1", "status": "OK", "predicted_concentration": 8.0, "reference_concentration": 10.0},
    ]
    result = _independent_test_metrics(rows)
    assert [item["model_version"] for item in result] == ["v2", "v1"]
    assert result[0]["n"] == 2
    assert result[0]["mae"] == 0.75
    assert result[0]["rmse"] > 0
    assert result[0]["r2"] is not None
    assert result[1]["n"] == 1
    assert result[1]["r2"] is None
