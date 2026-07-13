"""Pluggable media storage.

Switch backends with the STORAGE_BACKEND env var:

  cloudinary        -> upload to Cloudinary (managed media CDN). Credentials come
                        from CLOUDINARY_* env vars.
  local  (default)  -> save files under MEDIA_ROOT, served by FastAPI at /media.
                        Great for local dev; range requests (audio seeking) work.
  s3                -> upload to any S3-compatible bucket (AWS S3, Cloudflare R2,
                        Supabase Storage, MinIO). Recommended for self-hosting.

The upload route calls save() and stores the returned public URL on the Song
row, so the mobile client is unchanged either way.
"""
import os
import shutil
from pathlib import Path
from typing import BinaryIO, Optional

import config  # noqa: F401  (ensures .env is loaded before we read os.environ)

STORAGE_BACKEND = os.environ.get('STORAGE_BACKEND', 'local').lower()

# --- Local backend ---
MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT', 'media')).resolve()
# Absolute base for building media URLs (e.g. https://api.example.com). When
# unset we fall back to the incoming request's base URL — fine for local dev.
PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL')

# --- Cloudinary backend ---
CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

# --- S3-compatible backend ---
S3_BUCKET = os.environ.get('S3_BUCKET')
S3_ENDPOINT_URL = os.environ.get('S3_ENDPOINT_URL')  # None for AWS S3
S3_REGION = os.environ.get('S3_REGION')
# Public base URL for objects/CDN, e.g. https://<bucket>.s3.amazonaws.com or a
# Cloudflare R2 / Supabase public URL. Credentials are read by boto3 from
# AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY.
S3_PUBLIC_URL = os.environ.get('S3_PUBLIC_URL')


def guess_ext(filename: Optional[str], default: str) -> str:
    """Return the file extension (with dot) from a name, or a default."""
    ext = Path(filename or '').suffix
    return ext if ext else default


def save(
    file: BinaryIO,
    key: str,
    *,
    request_base_url: Optional[str] = None,
    content_type: Optional[str] = None,
    resource_type: str = 'auto',
) -> str:
    """Persist a file under `key` and return a public URL to it."""
    if STORAGE_BACKEND == 'cloudinary':
        return _save_cloudinary(file, key, resource_type)
    if STORAGE_BACKEND == 's3':
        return _save_s3(file, key, content_type)
    return _save_local(file, key, request_base_url)


_cloudinary_configured = False


def _save_cloudinary(file: BinaryIO, key: str, resource_type: str) -> str:
    import cloudinary
    import cloudinary.uploader

    global _cloudinary_configured
    if not _cloudinary_configured:
        if not (CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET):
            raise RuntimeError(
                'Cloudinary is not configured — set CLOUDINARY_CLOUD_NAME, '
                'CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET'
            )
        cloudinary.config(
            cloud_name=CLOUDINARY_CLOUD_NAME,
            api_key=CLOUDINARY_API_KEY,
            api_secret=CLOUDINARY_API_SECRET,
            secure=True,
        )
        _cloudinary_configured = True

    try:
        file.seek(0)
    except Exception:
        pass
    # Keep the songs/<id> structure as the Cloudinary folder.
    folder = os.path.dirname(key) or None
    res = cloudinary.uploader.upload(file, resource_type=resource_type, folder=folder)
    # secure_url is https (nicer than the plain http 'url').
    return res.get('secure_url') or res['url']


def _save_local(file: BinaryIO, key: str, request_base_url: Optional[str]) -> str:
    dest = MEDIA_ROOT / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        file.seek(0)
    except Exception:
        pass
    with open(dest, 'wb') as out:
        shutil.copyfileobj(file, out)
    base = (PUBLIC_BASE_URL or request_base_url or '').rstrip('/')
    return f'{base}/media/{key}'


def _save_s3(file: BinaryIO, key: str, content_type: Optional[str]) -> str:
    import boto3  # imported lazily so local dev needs no AWS deps

    if not S3_BUCKET:
        raise RuntimeError('S3_BUCKET is not configured for STORAGE_BACKEND=s3')

    client = boto3.session.Session().client(
        's3',
        endpoint_url=S3_ENDPOINT_URL,
        region_name=S3_REGION,
    )
    try:
        file.seek(0)
    except Exception:
        pass
    extra = {'ACL': 'public-read'}
    if content_type:
        extra['ContentType'] = content_type
    client.upload_fileobj(file, S3_BUCKET, key, ExtraArgs=extra)

    base = (S3_PUBLIC_URL or '').rstrip('/')
    return f'{base}/{key}'
