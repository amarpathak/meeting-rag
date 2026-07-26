from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import app.actions as actions

CACHED = [{"owner": "Marcus Bell", "task": "send the SOC 2 report", "due": "Thursday",
           "timestamp": "00:02:16"}]
EXTRACTED_AT = datetime(2026, 7, 26, 7, 34, 34, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "raw, expected",
    [("[00:02:30]", "00:02:30"),   # the model echoing the transcript's line format
     ("00:02:30", "00:02:30"),
     (" [00:02:30] ", "00:02:30"),
     ("0:02:30", "00:02:30"),      # unpadded hour would not match a turn either
     ("at 00:02:30 in the call", "00:02:30")],
)
def test_timestamp_is_normalised_to_match_a_turn(raw, expected):
    # A citation that does not match a turn timestamp exactly fails silently:
    # the click does nothing at all rather than raising.
    assert actions._clean_timestamp(raw) == expected


def test_extracted_timestamps_are_cleaned_before_caching():
    response = MagicMock()
    response.parsed = [actions.ActionItem(owner="Iris Park", task="ship the settings page",
                                          due=None, timestamp="[00:02:30]")]
    response.usage_metadata.prompt_token_count = 10
    response.usage_metadata.candidates_token_count = 5

    with patch.object(actions, "_cached", return_value=None), \
         patch.object(actions, "_store", return_value=EXTRACTED_AT) as store, \
         patch.object(actions, "transcript_text", return_value=("x", [1])), \
         patch.object(actions, "generate_with_fallback") as generate, \
         patch.object(actions, "log_query"):
        generate.return_value = (response, "gemini-2.5-flash")
        result = actions.extract_actions(5)

    assert result["action_items"][0]["timestamp"] == "00:02:30"
    assert store.call_args[0][2][0]["timestamp"] == "00:02:30"  # cached clean, not raw


def test_cache_hit_skips_the_model_call():
    # The reason the cache exists: switching meetings in the UI must not spend a
    # request from the daily quota to re-derive an answer we already have.
    with patch.object(actions, "_cached", return_value=(CACHED, EXTRACTED_AT)), \
         patch.object(actions, "generate_with_fallback") as generate, \
         patch.object(actions, "log_query") as log_query:
        result = actions.extract_actions(4)

    assert result["cached"] is True
    assert result["action_items"] == CACHED
    # The UI dates the result from this, so a cache hit must report when the
    # extraction actually ran — not when it was served.
    assert result["extracted_at"] == EXTRACTED_AT.isoformat()
    generate.assert_not_called()
    log_query.assert_not_called()  # no model call ⇒ nothing to log


def test_refresh_bypasses_the_cache_and_re_extracts():
    response = MagicMock()
    response.parsed = [actions.ActionItem(owner="Grace Liu", task="review the DPA",
                                          due=None, timestamp="00:01:14")]
    response.usage_metadata.prompt_token_count = 800
    response.usage_metadata.candidates_token_count = 100

    with patch.object(actions, "_cached") as cached, \
         patch.object(actions, "_store", return_value=EXTRACTED_AT) as store, \
         patch.object(actions, "transcript_text", return_value=("00:01:14 Grace Liu: hi", [1])), \
         patch.object(actions, "generate_with_fallback") as generate, \
         patch.object(actions, "log_query"):
        generate.return_value = (response, "gemini-2.5-flash")
        result = actions.extract_actions(4, refresh=True)

    cached.assert_not_called()  # refresh must not even read the cache
    assert result["cached"] is False
    assert result["action_items"][0]["owner"] == "Grace Liu"
    store.assert_called_once()  # a fresh extraction replaces the cached row
