"""Cloudflare R2 object storage (S3-compatible) via boto3.

All reads go through presigned URLs (no public bucket needed). If R2
credentials are missing, every function degrades gracefully so local
dev keeps working without cloud access.
"""
import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from functools import lru_cache
from app.core.config import get_settings


def is_configured() -> bool:
    s = get_settings()
    return bool(s.R2_ACCOUNT_ID and s.R2_ACCESS_KEY_ID and s.R2_SECRET_ACCESS_KEY)


def _endpoint() -> str:
    s = get_settings()
    if s.R2_ENDPOINT_URL:
        return s.R2_ENDPOINT_URL.rstrip("/")
    return f"https://{s.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"


@lru_cache()
def _client():
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=_endpoint(),
        aws_access_key_id=s.R2_ACCESS_KEY_ID,
        aws_secret_access_key=s.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=BotoConfig(signature_version="s3v4"),
    )


def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Upload bytes to R2. Returns the key. Raises RuntimeError if not configured."""
    if not is_configured():
        raise RuntimeError("R2 not configured")
    _client().put_object(
        Bucket=get_settings().R2_BUCKET_NAME,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return key


def presigned_get_url(key: str, expires_in: int = 604800) -> str:
    """7-day presigned download URL for a key. Raises RuntimeError if not configured."""
    if not is_configured():
        raise RuntimeError("R2 not configured")
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": get_settings().R2_BUCKET_NAME, "Key": key},
        ExpiresIn=expires_in,
    )


def file_url(key: str, expires_in: int = 604800) -> str:
    """Public URL if R2_PUBLIC_URL set, else presigned URL."""
    s = get_settings()
    if s.R2_PUBLIC_URL:
        return f"{s.R2_PUBLIC_URL.rstrip('/')}/{key}"
    return presigned_get_url(key, expires_in)

def delete_key(key: str) -> None:
    if not is_configured():
        return
    try:
        _client().delete_object(Bucket=get_settings().R2_BUCKET_NAME, Key=key)
    except (BotoCoreError, ClientError):
        pass


def download_bytes(key: str) -> bytes:
    """Download an object. Raises RuntimeError if not configured or missing."""
    if not is_configured():
        raise RuntimeError("R2 not configured")
    try:
        obj = _client().get_object(Bucket=get_settings().R2_BUCKET_NAME, Key=key)
        return obj["Body"].read()
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"R2 download failed: {e}")
