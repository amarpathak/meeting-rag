from unittest.mock import patch

import app.answer as answer
from app.retrieval import Retrieved


def test_floor_triggers_refusal_without_a_model_call():
    # Retrieval returns a below-floor match, so answering must refuse before
    # ever calling the model. We fake retrieval, the logger, and the client.
    weak = [
        Retrieved(chunk_id=1, content="unrelated", speakers=["A"],
                  ts_start="00:00:00", ts_end="00:00:01", similarity=0.05)
    ]
    with patch.object(answer, "retrieve", return_value=weak), \
         patch.object(answer, "log_query") as log_query, \
         patch.object(answer, "client") as client:
        result = answer.answer_question("something off-topic")

    assert result["answered"] is False
    assert result["citations"] == []
    client.assert_not_called()      # the guard's whole point: no LLM call
    log_query.assert_called_once()  # but it is still recorded — no silent skip
