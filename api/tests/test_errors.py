from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors

import app.main as main
from app.config import get_settings

client = TestClient(main.app, raise_server_exceptions=False)


def _quota_error() -> genai_errors.ClientError:
    response = MagicMock()
    response.status_code = 429
    response.json.return_value = {"error": {"message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED"}}
    return genai_errors.ClientError(429, response.json.return_value, response)


def test_fallback_moves_to_the_next_model_and_logs_the_exhausted_one():
    # Free tier is 20 calls per day per model, so one model alone is a hard stop.
    # The fallback turns that into degraded service — but the exhausted attempt
    # must still be logged, or the dashboard looks healthy while the chain burns.
    import app.llm as llm

    ok = MagicMock()
    with patch.object(llm, "client") as client, \
         patch.object(llm, "log_query") as log_query:
        client.return_value.models.generate_content.side_effect = [_quota_error(), ok]
        response, model = llm.generate_with_fallback("q", "answered", 0.0, 4, contents="x")

    assert response is ok
    assert model == "gemini-2.0-flash"      # the second in the chain answered
    log_query.assert_called_once()          # exactly one failure row, for the first
    assert log_query.call_args[0][1] == "answered"
    assert log_query.call_args[0][9] == 4   # attributed to the meeting
    assert "429" in log_query.call_args[0][10]
    assert log_query.call_args[0][11] == "gemini-2.5-flash"  # which model failed


def test_fallback_raises_the_last_error_when_every_model_fails():
    import app.llm as llm

    chain = len(get_settings().answer_model_chain)
    with patch.object(llm, "client") as client, \
         patch.object(llm, "log_query") as log_query:
        client.return_value.models.generate_content.side_effect = [_quota_error()] * chain
        with pytest.raises(genai_errors.ClientError):
            llm.generate_with_fallback("q", "answered", 0.0, None, contents="x")

    # Every attempt is visible, not just the one that finally surfaced.
    assert log_query.call_count == chain


def test_describe_error_keeps_the_providers_message():
    from app.llm import describe_error

    described = describe_error(_quota_error())

    assert "429" in described
    assert "Quota exceeded" in described
    assert len(described) <= 400  # bounded: some bodies carry pages of retry metadata


def test_quota_error_surfaces_as_429_not_500():
    # A 500 sends the reader hunting for a bug in our code; the real cause is a
    # quota they can see and act on.
    with patch.object(main, "extract_actions", side_effect=_quota_error()):
        res = client.get("/transcripts/4/actions")

    assert res.status_code == 429
    assert "Quota exceeded" in res.json()["detail"]


@pytest.mark.parametrize(
    "exc, status",
    [(httpx.ConnectError("Temporary failure in name resolution"), 503),
     (httpx.ReadTimeout("timed out"), 504)],
)
def test_unreachable_upstream_is_distinguished_from_a_rejected_request(exc, status):
    with patch.object(main, "extract_actions", side_effect=exc):
        res = client.get("/transcripts/4/actions")

    assert res.status_code == status
    detail = res.json()["detail"]
    assert "network" in detail.lower()
    assert "quota" not in detail.lower()  # must not misdirect toward billing
