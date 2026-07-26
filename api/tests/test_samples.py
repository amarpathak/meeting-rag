from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import app.samples as samples

TRANSCRIPT = """Meeting: Sprint 24 Retro
Date: 2026-07-20

[00:00:09] Ravi Menon: Did the migration ship?
[00:00:21] Dana Cole: Shipped, but it locked the orders table.
[00:00:44] Ravi Menon: Let's write that up.
"""


def _cursor_returning(rows):
    cur = MagicMock()
    cur.fetchall.return_value = rows
    ctx = MagicMock()
    ctx.__enter__.return_value = cur
    ctx.__exit__.return_value = False
    return ctx


@pytest.mark.parametrize("name", ["../../etc/passwd", "/etc/passwd", "nested/other.txt"])
def test_a_sample_name_cannot_escape_the_samples_directory(name):
    # `name` reaches this straight from the query string, so the guard is the only
    # thing between a URL and an arbitrary file read.
    with pytest.raises(ValueError):
        samples.ingest_sample(name)


def test_unknown_sample_is_rejected_rather_than_read():
    with pytest.raises(ValueError):
        samples.ingest_sample("not-a-bundled-file.txt")


def test_listing_reports_a_sample_as_loaded_by_content_hash(tmp_path: Path):
    # Ingest deduplicates on the content hash, not the filename, so the "already
    # loaded" badge has to agree with that or it will offer a load that no-ops.
    (tmp_path / "retro.txt").write_text(TRANSCRIPT)
    digest = samples.content_hash(TRANSCRIPT)

    with patch.object(samples, "SAMPLES_DIR", tmp_path), \
         patch.object(samples, "cursor", return_value=_cursor_returning([(digest, 12)])):
        listed = samples.list_samples()

    assert len(listed) == 1
    assert listed[0]["transcript_id"] == 12
    assert listed[0]["title"] == "Sprint 24 Retro"
    assert listed[0]["turns"] == 3
    assert listed[0]["speakers"] == 2  # distinct, not one per turn


def test_a_sample_not_yet_ingested_has_no_transcript_id(tmp_path: Path):
    (tmp_path / "retro.txt").write_text(TRANSCRIPT)

    with patch.object(samples, "SAMPLES_DIR", tmp_path), \
         patch.object(samples, "cursor", return_value=_cursor_returning([])):
        listed = samples.list_samples()

    assert listed[0]["transcript_id"] is None
