"""S3 (or S3-compatible) object storage with presigned URLs.

Files never stream through the API. A client asks for a presigned PUT URL,
uploads straight to the bucket, then tells the API which key it used. Reads get
a fresh presigned GET URL every time, so no URL is ever stored.

boto3 is synchronous, so every call runs in a worker thread to keep the event
loop free. Presigning is local signing, but the first call may resolve
credentials (IAM role, instance metadata), which can block.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from ..config.settings import get_settings
from .exceptions import StorageError, StorageNotConfiguredError

settings = get_settings()

_NOT_FOUND_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


@dataclass(frozen=True)
class ObjectMetadata:
    """What S3 reports about a stored object."""

    size: int
    content_type: str


class S3Storage:
    """Thin async wrapper around a lazily created boto3 S3 client."""

    def __init__(self) -> None:
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = boto3.client(
                "s3",
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
                endpoint_url=settings.S3_ENDPOINT_URL or None,
                config=BotoConfig(signature_version="s3v4"),
            )
        return self._client

    @staticmethod
    def _bucket(private: bool) -> str:
        bucket = settings.AWS_BUCKET_PRIVATE if private else settings.AWS_BUCKET
        if not bucket:
            name = "AWS_BUCKET_PRIVATE" if private else "AWS_BUCKET"
            raise StorageNotConfiguredError(f"{name} is not configured")
        return bucket

    @staticmethod
    def full_key(key: str) -> str:
        """Prefix a key with AWS_ROOT, so environments can share one bucket."""
        root = settings.AWS_ROOT.strip("/")
        return f"{root}/{key}" if root else key

    async def generate_presigned_upload_url(self, *, key: str, content_type: str, private: bool = False) -> str:
        """A time-limited URL the client can PUT the file to directly.

        The content type is part of the signature, so the client must send the
        same ``Content-Type`` header with the upload.
        """
        params = {"Bucket": self._bucket(private), "Key": self.full_key(key), "ContentType": content_type}
        url = await self._call(
            "generate_presigned_url",
            "put_object",
            Params=params,
            ExpiresIn=settings.PRESIGNED_UPLOAD_URL_EXPIRE_SECONDS,
        )
        return str(url)

    async def generate_presigned_download_url(self, *, key: str, private: bool = False) -> str:
        """A time-limited URL to read an object. Regenerate on every read; never store it."""
        params = {"Bucket": self._bucket(private), "Key": self.full_key(key)}
        url = await self._call(
            "generate_presigned_url",
            "get_object",
            Params=params,
            ExpiresIn=settings.PRESIGNED_DOWNLOAD_URL_EXPIRE_SECONDS,
        )
        return str(url)

    async def get_object_metadata(self, *, key: str, private: bool = False) -> ObjectMetadata | None:
        """Size and content type straight from S3, or None if nothing was uploaded to this key."""
        try:
            response = await self._call("head_object", Bucket=self._bucket(private), Key=self.full_key(key), raw=True)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _NOT_FOUND_CODES:
                return None
            raise StorageError(f"head_object failed for {key}") from exc

        return ObjectMetadata(
            size=int(response["ContentLength"]),
            content_type=response.get("ContentType") or "application/octet-stream",
        )

    async def delete_object(self, *, key: str, private: bool = False) -> None:
        """Delete an object. S3 treats deleting a missing key as success."""
        await self._call("delete_object", Bucket=self._bucket(private), Key=self.full_key(key))

    async def _call(self, method: str, *args: Any, raw: bool = False, **kwargs: Any) -> Any:
        """Run a boto3 client method in a worker thread.

        Args:
            method: Client method name.
            raw: When true, ClientError propagates so the caller can inspect it.
        """
        try:
            return await asyncio.to_thread(getattr(self._get_client(), method), *args, **kwargs)
        except ClientError as exc:
            if raw:
                raise
            raise StorageError(f"S3 {method} failed") from exc
        except BotoCoreError as exc:
            raise StorageError(f"S3 {method} failed") from exc


storage = S3Storage()
