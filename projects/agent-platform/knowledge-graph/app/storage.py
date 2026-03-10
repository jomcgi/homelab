"""S3 storage layer (content-addressable via SHA256)."""

from __future__ import annotations

import json
import logging
from datetime import datetime

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError

from projects.agent_platform.knowledge_graph.app.models import Document, content_hash

logger = logging.getLogger(__name__)


class S3Storage:
    def __init__(
        self, endpoint: str, bucket: str, access_key: str = "", secret_key: str = ""
    ):
        kwargs: dict = {"endpoint_url": endpoint}
        if access_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key
        else:
            kwargs["config"] = Config(signature_version=UNSIGNED)
        self._client = boto3.client("s3", **kwargs)
        self._bucket = bucket
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            logger.info("Creating bucket %s", self._bucket)
            self._client.create_bucket(Bucket=self._bucket)

    def _key(self, hash_key: str, filename: str) -> str:
        return f"sources/{hash_key}/{filename}"

    def exists(self, hash_key: str) -> bool:
        """HEAD request to check existence (cheap)."""
        try:
            self._client.head_object(
                Bucket=self._bucket, Key=self._key(hash_key, "content.md")
            )
            return True
        except ClientError:
            return False

    def store(self, doc: Document) -> str:
        """Store content.md + meta.json, return content_hash."""
        hash_key = content_hash(doc["content"])

        self._client.put_object(
            Bucket=self._bucket,
            Key=self._key(hash_key, "content.md"),
            Body=doc["content"].encode("utf-8"),
            ContentType="text/markdown",
        )

        meta = {
            "source_type": doc["source_type"],
            "source_url": doc["source_url"],
            "title": doc["title"],
            "author": doc["author"],
            "published_at": (
                doc["published_at"].isoformat() if doc["published_at"] else None
            ),
            "retrieved_at": datetime.now().isoformat(),
            "content_hash": hash_key,
        }
        self._client.put_object(
            Bucket=self._bucket,
            Key=self._key(hash_key, "meta.json"),
            Body=json.dumps(meta).encode("utf-8"),
            ContentType="application/json",
        )

        return hash_key

    def get_content(self, hash_key: str) -> str | None:
        try:
            obj = self._client.get_object(
                Bucket=self._bucket, Key=self._key(hash_key, "content.md")
            )
            return obj["Body"].read().decode("utf-8")
        except ClientError:
            return None

    def get_meta(self, hash_key: str) -> dict | None:
        try:
            obj = self._client.get_object(
                Bucket=self._bucket, Key=self._key(hash_key, "meta.json")
            )
            return json.loads(obj["Body"].read().decode("utf-8"))
        except ClientError:
            return None

    def list_all_hashes(self) -> list[str]:
        """List all content hashes in the bucket."""
        hashes: set[str] = set()
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix="sources/"):
            for obj in page.get("Contents", []):
                parts = obj["Key"].split("/")
                if len(parts) >= 2:
                    hashes.add(parts[1])
        return sorted(hashes)
