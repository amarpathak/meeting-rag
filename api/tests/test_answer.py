from datetime import datetime, timezone
from unittest.mock import patch

import pytest

import app.answer as answer
from app.retrieval import Retrieved

CACHED = {"answered": True, "answer": "Dana owns the rollback.", "top_score": 0.81,
          "citations": [{"chunk_id": 3, "speakers": ["Dana Cole"],
                         "ts_start": "00:00:21", "ts_end": "00:00:44"}]}


def test_floor_triggers_refusal_without_a_model_call():
    # Retrieval returns a below-floor match, so answering must refuse before
    # ever calling the model. We fake retrieval, the logger, and the client.
    weak = [
        Retrieved(chunk_id=1, content="unrelated", speakers=["A"],
                  ts_start="00:00:00", ts_end="00:00:01", similarity=0.05)
    ]
    with patch.object(answer, "retrieve", return_value=weak), \
         patch.object(answer, "log_query") as log_query, \
         patch.object(answer, "generate_with_fallback") as generate:
        result = answer.answer_question("something off-topic")

    assert result["answered"] is False
    assert result["citations"] == []
    generate.assert_not_called()    # the guard's whole point: no LLM call
    log_query.assert_called_once()  # but it is still recorded — no silent skip


def test_a_repeated_question_is_served_without_retrieving_or_generating():
    # The point of the cache: clicking a recent chip must cost nothing at all —
    # not the model call, and not the embedding call retrieval would make either.
    at = datetime(2026, 7, 26, 17, 0, tzinfo=timezone.utc)
    with patch.object(answer, "_cached", return_value=(CACHED, at)), \
         patch.object(answer, "retrieve") as retrieve, \
         patch.object(answer, "generate_with_fallback") as generate:
        result = answer.answer_question("Who owns the rollback?", transcript_id=5)

    assert result["cached"] is True
    assert result["answer"] == CACHED["answer"]
    assert result["citations"] == CACHED["citations"]  # citations survive the round trip
    retrieve.assert_not_called()
    generate.assert_not_called()


def test_refresh_bypasses_the_cache_even_on_a_hit():
    at = datetime(2026, 7, 26, 17, 0, tzinfo=timezone.utc)
    strong = [Retrieved(chunk_id=3, content="[00:00:21] Dana Cole: shipped", speakers=["Dana Cole"],
                        ts_start="00:00:21", ts_end="00:00:21", similarity=0.81)]
    with patch.object(answer, "_cached", return_value=(CACHED, at)) as cached, \
         patch.object(answer, "retrieve", return_value=strong), \
         patch.object(answer, "log_query"), \
         patch.object(answer, "_store", return_value=at), \
         patch.object(answer, "generate_with_fallback") as generate:
        generate.return_value = (_fake_response("A fresh answer."), "gemini-2.5-flash")
        result = answer.answer_question("Who owns the rollback?", transcript_id=5, refresh=True)

    cached.assert_not_called()
    generate.assert_called_once()
    assert result["answer"] == "A fresh answer."
    assert result["cached"] is False


@pytest.mark.parametrize("variant", [
    "  Who owns   the rollback?  ",  # collapsed whitespace
    "WHO OWNS THE ROLLBACK?",        # casefolded
])
def test_the_same_question_asked_differently_hits_the_same_key(variant):
    # Otherwise retyping a question you already asked quietly costs a second call.
    assert answer._cache_key(variant) == answer._cache_key("Who owns the rollback?")


def test_an_unscoped_question_is_never_cached():
    # Without a transcript_id the search spans every meeting, so the answer changes
    # as meetings are ingested and there is nothing stable to key on.
    strong = [Retrieved(chunk_id=3, content="x", speakers=["Dana Cole"],
                        ts_start="00:00:21", ts_end="00:00:21", similarity=0.81)]
    with patch.object(answer, "_cached") as cached, \
         patch.object(answer, "_store") as store, \
         patch.object(answer, "retrieve", return_value=strong), \
         patch.object(answer, "log_query"), \
         patch.object(answer, "generate_with_fallback") as generate:
        generate.return_value = (_fake_response("Answer."), "gemini-2.5-flash")
        result = answer.answer_question("Who owns the rollback?", transcript_id=None)

    cached.assert_not_called()
    store.assert_not_called()
    assert result["cached"] is False


def _fake_response(text: str):
    class Usage:
        prompt_token_count = 120
        candidates_token_count = 40

    class Response:
        usage_metadata = Usage()

    response = Response()
    response.text = text
    return response
