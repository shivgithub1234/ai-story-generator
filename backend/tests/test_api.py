import pytest
from fastapi.testclient import TestClient

from story_api.main import app

client = TestClient(app)
VALID_REQUEST = {
    "premise": "A Jaipur detective receives letters predicting crimes.",
    "genre": "mystery",
}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.2.0"}


def test_valid_request_normalizes_premise_and_supplies_defaults():
    response = client.post(
        "/api/story-requests/validate",
        json={**VALID_REQUEST, "premise": f"  {VALID_REQUEST['premise']}  "},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["valid"] is True
    assert result["request"] == {
        **VALID_REQUEST,
        "language": "English",
        "target_words": 1000,
        "tone": None,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("premise", ""),
        ("premise", " " * 20),
        ("premise", "x" * 2001),
        ("genre", "unknown"),
        ("language", "unsupported"),
        ("target_words", 199),
        ("target_words", 3001),
        ("target_words", True),
        ("target_words", "1000"),
        ("tone", "   "),
        ("tone", "x" * 101),
        ("unexpected", "value"),
    ],
)
def test_invalid_input_returns_field_error(field, value):
    response = client.post(
        "/api/story-requests/validate",
        json={**VALID_REQUEST, field: value},
    )
    assert response.status_code == 422
    assert any(error["loc"][-1] == field for error in response.json()["detail"])


def test_missing_premise_is_rejected():
    response = client.post("/api/story-requests/validate", json={"genre": "mystery"})
    assert response.status_code == 422


def test_hindi_and_explicit_preferences_are_accepted():
    response = client.post(
        "/api/story-requests/validate",
        json={
            **VALID_REQUEST,
            "language": "Hindi",
            "target_words": 200,
            "tone": " Suspenseful ",
        },
    )
    assert response.status_code == 200
    assert response.json()["request"]["tone"] == "Suspenseful"
