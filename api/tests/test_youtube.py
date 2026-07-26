import pytest

from app.youtube import YouTubeError, _merge, _timestamp, video_id

VID = "lBVtvOpU80Q"


@pytest.mark.parametrize(
    "url",
    ["https://www.youtube.com/watch?v=lBVtvOpU80Q",
     "https://www.youtube.com/watch?v=lBVtvOpU80Q&pp=ygUNZ3JvdXAgbWVldGluZw%3D%3D",
     "https://youtu.be/lBVtvOpU80Q?t=42",
     "https://www.youtube.com/embed/lBVtvOpU80Q",
     "https://www.youtube.com/shorts/lBVtvOpU80Q",
     "youtube.com/watch?list=PL123&v=lBVtvOpU80Q"],
)
def test_video_id_survives_the_url_shapes_people_actually_paste(url):
    # Share links carry tracking params and the id is not always the first one.
    assert video_id(url) == VID


@pytest.mark.parametrize("url", ["https://example.com/watch?v=lBVtvOpU80Q", "", "not a url"])
def test_non_youtube_urls_are_rejected_as_input_errors(url):
    # YouTubeError subclasses ValueError so the route answers 400, not 500.
    with pytest.raises(YouTubeError):
        video_id(url)


def test_timestamp_formats_past_an_hour():
    assert _timestamp(0) == "00:00:00"
    assert _timestamp(2562) == "00:42:42"
    assert _timestamp(3725.9) == "01:02:05"


def test_merge_packs_fragments_and_keeps_the_block_start_time():
    # Auto-captions arrive as 3-8 word fragments; one line per fragment would give
    # the normaliser no context to infer where a speaker changes.
    segments = [{"start": 0.0 + i, "duration": 1.0, "text": f"word{i}"} for i in range(40)]
    lines = _merge(segments)

    assert len(lines) < len(segments)
    assert lines[0].startswith("[00:00:00] ")
    assert "word0" in lines[0]


def test_merge_drops_non_speech_cues():
    segments = [{"start": 0.0, "duration": 1.0, "text": "[Music]"},
                {"start": 1.0, "duration": 1.0, "text": "hello there"}]
    lines = _merge(segments)

    assert len(lines) == 1
    assert "Music" not in lines[0]
    assert lines[0] == "[00:00:01] hello there"  # timed from the first real speech
