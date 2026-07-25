from unittest.mock import MagicMock, patch

import app.ingest as ingest


def test_ingest_is_idempotent_on_duplicate_hash():
    # Simulate a transcript with this content hash already existing: the SELECT
    # returns a row, so ingest must skip — and never pay to embed.
    existing_cursor = MagicMock()
    existing_cursor.fetchone.return_value = (7,)  # id of the existing transcript
    ctx = MagicMock()
    ctx.__enter__.return_value = existing_cursor
    ctx.__exit__.return_value = False

    with patch.object(ingest, "cursor", return_value=ctx), \
         patch.object(ingest, "embed_documents") as embed_documents:
        result = ingest.ingest_transcript("meeting.txt", "any content")

    assert result["status"] == "already_ingested"
    assert result["transcript_id"] == 7
    embed_documents.assert_not_called()  # duplicate ⇒ the embed step is skipped
