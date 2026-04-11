"""Tests for the URL ingest queue."""

import pytest
from unittest.mock import patch, MagicMock

from knowledge.ingest_queue import (
    IngestQueueItem,
    fetch_youtube_transcript,
    fetch_webpage,
)


def test_ingest_queue_item_defaults():
    item = IngestQueueItem(url="https://youtube.com/watch?v=abc", source_type="youtube")
    assert item.status == "pending"
    assert item.error is None
    assert item.started_at is None
    assert item.processed_at is None


def test_ingest_queue_item_source_type_validation():
    """source_type must be youtube or webpage."""
    IngestQueueItem(url="https://example.com", source_type="youtube")
    IngestQueueItem(url="https://example.com", source_type="webpage")


@pytest.mark.asyncio
async def test_fetch_youtube_transcript_extracts_text():
    mock_api = MagicMock()
    mock_api.fetch.return_value.to_raw_data.return_value = [
        {"text": "Hello world", "start": 0.0, "duration": 1.0},
        {"text": "This is a test", "start": 1.0, "duration": 1.0},
    ]
    with patch("knowledge.ingest_queue.YouTubeTranscriptApi", return_value=mock_api):
        title, body = await fetch_youtube_transcript(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )
    assert "Hello world" in body
    assert "This is a test" in body


@pytest.mark.asyncio
async def test_fetch_youtube_transcript_extracts_video_id():
    """Should extract video ID from various YouTube URL formats."""
    mock_api = MagicMock()
    mock_api.fetch.return_value.to_raw_data.return_value = [
        {"text": "test", "start": 0.0, "duration": 1.0},
    ]
    with patch("knowledge.ingest_queue.YouTubeTranscriptApi", return_value=mock_api):
        await fetch_youtube_transcript("https://youtu.be/dQw4w9WgXcQ")
        mock_api.fetch.assert_called_with("dQw4w9WgXcQ")


@pytest.mark.asyncio
async def test_fetch_webpage_returns_markdown():
    with patch("knowledge.ingest_queue.trafilatura") as mock_traf:
        mock_traf.fetch_url.return_value = (
            "<html><body><h1>Title</h1><p>Content</p></body></html>"
        )
        mock_traf.extract.return_value = "# Title\n\nContent"
        mock_traf.extract_metadata.return_value = MagicMock(title="Title")
        title, body = await fetch_webpage("https://example.com/article")
    assert title == "Title"
    assert "Content" in body
    mock_traf.extract.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_webpage_handles_no_content():
    with patch("knowledge.ingest_queue.trafilatura") as mock_traf:
        mock_traf.fetch_url.return_value = "<html></html>"
        mock_traf.extract.return_value = None
        with pytest.raises(RuntimeError, match="no content extracted"):
            await fetch_webpage("https://example.com/empty")
