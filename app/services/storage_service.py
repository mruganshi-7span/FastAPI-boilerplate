import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from app.core.config import get_settings

settings = get_settings()

_s3_client = None


def _get_client():
    global _s3_client

    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
            endpoint_url=settings.s3_endpoint_url or None,
            config=BotoConfig(signature_version="s3v4"),
        )

    return _s3_client


def _bucket(private: bool) -> str:
    return settings.aws_bucket_private if private else settings.aws_bucket


def _full_key(key: str) -> str:
    """Prefix every key with AWS_ROOT, mirroring Laravel's disk `root` config."""
    return f"{settings.aws_root.strip('/')}/{key}" if settings.aws_root else key


def generate_presigned_upload_url(*, key: str, content_type: str, private: bool = False) -> str:
    """A time-limited URL the client can PUT the file to directly, bypassing our server."""
    return _get_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": _bucket(private), "Key": _full_key(key), "ContentType": content_type},
        ExpiresIn=settings.presigned_upload_url_expire_seconds,
    )


def generate_presigned_download_url(*, key: str, private: bool = False) -> str:
    """A time-limited URL to read a private object — regenerated on every read, never stored."""
    return _get_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket(private), "Key": _full_key(key)},
        ExpiresIn=settings.presigned_download_url_expire_seconds,
    )


def get_object_metadata(*, key: str, private: bool = False) -> dict[str, object] | None:
    """Size + content type straight from S3, or None if nothing was ever uploaded to this key."""
    try:
        response = _get_client().head_object(Bucket=_bucket(private), Key=_full_key(key))
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
            return None
        raise

    return {
        "size": response["ContentLength"],
        "content_type": response.get("ContentType") or "application/octet-stream",
    }


def delete_object(*, key: str, private: bool = False) -> None:
    _get_client().delete_object(Bucket=_bucket(private), Key=_full_key(key))
