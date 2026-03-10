"""Tests for S3 storage layer."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from projects.blog_knowledge_graph.knowledge_graph.app.models import (
    Document,
    content_hash,
)
from projects.blog_knowledge_graph.knowledge_graph.app.storage import S3Storage


@pytest.fixture
def mock_boto3():
    with patch(
        "projects.blog_knowledge_graph.knowledge_graph.app.storage.boto3"
    ) as mock:
        client = MagicMock()
        mock.client.return_value = client
        # head_bucket succeeds (bucket exists)
        client.head_bucket.return_value = {}
        yield client


@pytest.fixture
def storage(mock_boto3):
    return S3Storage(
        endpoint="http://localhost:8333",
        bucket="test-bucket",
        access_key="key",
        secret_key="secret",
    )


class TestExists:
    def test_exists_returns_true(self, storage, mock_boto3):
        mock_boto3.head_object.return_value = {}
        assert storage.exists("abc123") is True
        mock_boto3.head_object.assert_called_once_with(
            Bucket="test-bucket", Key="sources/abc123/content.md"
        )

    def test_exists_returns_false(self, storage, mock_boto3):
        mock_boto3.head_object.side_effect = ClientError(
            {"Error": {"Code": "404"}}, "HeadObject"
        )
        assert storage.exists("abc123") is False


class TestStore:
    def test_stores_content_and_meta(self, storage, mock_boto3):
        doc = Document(
            source_type="html",
            source_url="https://example.com",
            title="Test",
            author="Author",
            published_at=datetime(2025, 1, 15),
            content="# Hello\n\nWorld.",
        )
        result = storage.store(doc)

        assert result == content_hash("# Hello\n\nWorld.")
        assert mock_boto3.put_object.call_count == 2

        # Check content.md was stored
        calls = mock_boto3.put_object.call_args_list
        content_call = [c for c in calls if "content.md" in str(c)]
        assert len(content_call) == 1

        # Check meta.json was stored
        meta_call = [c for c in calls if "meta.json" in str(c)]
        assert len(meta_call) == 1


class TestGetContent:
    def test_returns_content(self, storage, mock_boto3):
        mock_body = MagicMock()
        mock_body.read.return_value = b"# Hello"
        mock_boto3.get_object.return_value = {"Body": mock_body}

        result = storage.get_content("abc123")
        assert result == "# Hello"

    def test_returns_none_on_missing(self, storage, mock_boto3):
        mock_boto3.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey"}}, "GetObject"
        )
        assert storage.get_content("missing") is None


class TestGetMeta:
    def test_returns_meta_dict(self, storage, mock_boto3):
        mock_body = MagicMock()
        mock_body.read.return_value = b'{"title": "Test"}'
        mock_boto3.get_object.return_value = {"Body": mock_body}

        result = storage.get_meta("abc123")
        assert result == {"title": "Test"}

    def test_returns_none_on_missing(self, storage, mock_boto3):
        mock_boto3.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey"}}, "GetObject"
        )
        assert storage.get_meta("missing") is None


class TestListAllHashes:
    def test_lists_hashes(self, storage, mock_boto3):
        paginator = MagicMock()
        mock_boto3.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "sources/hash1/content.md"},
                    {"Key": "sources/hash1/meta.json"},
                    {"Key": "sources/hash2/content.md"},
                ]
            }
        ]

        result = storage.list_all_hashes()
        assert sorted(result) == ["hash1", "hash2"]
