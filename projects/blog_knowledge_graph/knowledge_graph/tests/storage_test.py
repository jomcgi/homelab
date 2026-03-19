"""Tests for S3 storage layer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
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

    def test_store_with_none_published_at(self, storage, mock_boto3):
        """Store handles documents with no published_at (stores null in meta)."""
        doc = Document(
            source_type="rss",
            source_url="https://blog.example.com/post",
            title="Dateless Post",
            author=None,
            published_at=None,
            content="# Post\n\nContent.",
        )
        result = storage.store(doc)

        assert result == content_hash("# Post\n\nContent.")
        # Verify meta.json payload has null for published_at
        calls = mock_boto3.put_object.call_args_list
        meta_call = [c for c in calls if "meta.json" in str(c)]
        meta_body = meta_call[0].kwargs.get("Body") or meta_call[0][1].get("Body")
        meta_dict = json.loads(meta_body.decode("utf-8"))
        assert meta_dict["published_at"] is None

    def test_store_returns_sha256_hash_of_content(self, storage, mock_boto3):
        doc = Document(
            source_type="html",
            source_url="https://example.com",
            title="Test",
            author=None,
            published_at=None,
            content="unique content string",
        )
        result = storage.store(doc)
        assert result == content_hash("unique content string")
        assert len(result) == 64

    def test_store_content_stored_as_utf8(self, storage, mock_boto3):
        """Content bytes stored as UTF-8 encoded markdown."""
        content_str = "# Ünïcödé\n\nContent with special chars: 日本語"
        doc = Document(
            source_type="html",
            source_url="https://example.com",
            title="Unicode",
            author=None,
            published_at=None,
            content=content_str,
        )
        storage.store(doc)

        calls = mock_boto3.put_object.call_args_list
        content_call = [c for c in calls if "content.md" in str(c)]
        body = content_call[0].kwargs.get("Body") or content_call[0][1].get("Body")
        assert body == content_str.encode("utf-8")

    def test_store_with_timezone_aware_published_at(self, storage, mock_boto3):
        """store() serialises a timezone-aware datetime using isoformat(), preserving tz offset."""
        aware_dt = datetime(2025, 6, 15, 12, 30, 0, tzinfo=timezone.utc)
        doc = Document(
            source_type="html",
            source_url="https://example.com/tz-article",
            title="TZ Article",
            author=None,
            published_at=aware_dt,
            content="# TZ content",
        )
        storage.store(doc)

        calls = mock_boto3.put_object.call_args_list
        meta_call = [c for c in calls if "meta.json" in str(c)]
        meta_body = meta_call[0].kwargs.get("Body") or meta_call[0][1].get("Body")
        meta_dict = json.loads(meta_body.decode("utf-8"))

        # The stored value must be the ISO 8601 representation of the aware datetime
        assert meta_dict["published_at"] == aware_dt.isoformat()
        # Sanity-check: the UTC offset should appear in the stored string
        assert "+00:00" in meta_dict["published_at"]


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

    def test_uses_correct_key_path(self, storage, mock_boto3):
        """get_content fetches from sources/<hash>/content.md."""
        mock_body = MagicMock()
        mock_body.read.return_value = b"content"
        mock_boto3.get_object.return_value = {"Body": mock_body}

        storage.get_content("myhash")
        mock_boto3.get_object.assert_called_once_with(
            Bucket="test-bucket", Key="sources/myhash/content.md"
        )


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

    def test_uses_correct_key_path(self, storage, mock_boto3):
        """get_meta fetches from sources/<hash>/meta.json."""
        mock_body = MagicMock()
        mock_body.read.return_value = b"{}"
        mock_boto3.get_object.return_value = {"Body": mock_body}

        storage.get_meta("myhash")
        mock_boto3.get_object.assert_called_once_with(
            Bucket="test-bucket", Key="sources/myhash/meta.json"
        )


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

    def test_returns_empty_when_no_objects(self, storage, mock_boto3):
        paginator = MagicMock()
        mock_boto3.get_paginator.return_value = paginator
        paginator.paginate.return_value = [{}]  # No "Contents" key

        result = storage.list_all_hashes()
        assert result == []

    def test_deduplicates_hashes(self, storage, mock_boto3):
        """content.md and meta.json for same hash count as one."""
        paginator = MagicMock()
        mock_boto3.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "sources/abc/content.md"},
                    {"Key": "sources/abc/meta.json"},
                ]
            }
        ]

        result = storage.list_all_hashes()
        assert result == ["abc"]

    def test_result_is_sorted(self, storage, mock_boto3):
        paginator = MagicMock()
        mock_boto3.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "sources/zzz/content.md"},
                    {"Key": "sources/aaa/content.md"},
                    {"Key": "sources/mmm/content.md"},
                ]
            }
        ]

        result = storage.list_all_hashes()
        assert result == ["aaa", "mmm", "zzz"]

    def test_multi_page_paginator_aggregates_all_hashes(self, storage, mock_boto3):
        """list_all_hashes collects hashes from every page returned by the paginator."""
        paginator = MagicMock()
        mock_boto3.get_paginator.return_value = paginator
        # Simulate two separate pages of results
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "sources/hash_page1_a/content.md"},
                    {"Key": "sources/hash_page1_a/meta.json"},
                    {"Key": "sources/hash_page1_b/content.md"},
                ]
            },
            {
                "Contents": [
                    {"Key": "sources/hash_page2_a/content.md"},
                    {"Key": "sources/hash_page2_a/meta.json"},
                ]
            },
        ]

        result = storage.list_all_hashes()

        # All unique hashes across both pages must appear
        assert sorted(result) == [
            "hash_page1_a",
            "hash_page1_b",
            "hash_page2_a",
        ]


class TestS3StorageInit:
    def test_creates_client_with_credentials_when_provided(self):
        """When access_key is provided, boto3.client receives credentials."""
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.storage.boto3"
        ) as mock_boto3:
            client = MagicMock()
            mock_boto3.client.return_value = client
            client.head_bucket.return_value = {}

            S3Storage(
                endpoint="http://localhost:8333",
                bucket="my-bucket",
                access_key="mykey",
                secret_key="mysecret",
            )

        call_kwargs = mock_boto3.client.call_args.kwargs
        assert call_kwargs.get("aws_access_key_id") == "mykey"
        assert call_kwargs.get("aws_secret_access_key") == "mysecret"

    def test_creates_unsigned_client_when_no_credentials(self):
        """When access_key is empty, UNSIGNED config is used."""
        from botocore import UNSIGNED

        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.storage.boto3"
        ) as mock_boto3:
            client = MagicMock()
            mock_boto3.client.return_value = client
            client.head_bucket.return_value = {}

            S3Storage(
                endpoint="http://localhost:8333",
                bucket="public-bucket",
                access_key="",
                secret_key="",
            )

        call_kwargs = mock_boto3.client.call_args.kwargs
        # UNSIGNED config should be present, no explicit credentials
        assert "aws_access_key_id" not in call_kwargs
        assert "config" in call_kwargs

    def test_creates_bucket_when_not_exists(self):
        """If head_bucket raises ClientError, create_bucket is called."""
        with patch(
            "projects.blog_knowledge_graph.knowledge_graph.app.storage.boto3"
        ) as mock_boto3:
            client = MagicMock()
            mock_boto3.client.return_value = client
            client.head_bucket.side_effect = ClientError(
                {"Error": {"Code": "404"}}, "HeadBucket"
            )

            S3Storage(
                endpoint="http://localhost:8333",
                bucket="new-bucket",
                access_key="key",
                secret_key="secret",
            )

        client.create_bucket.assert_called_once_with(Bucket="new-bucket")
