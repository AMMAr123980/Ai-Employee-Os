"""
Keeping the audio.

v1 transcribed the bytes and threw them away, while pitching the
VoiceCommand table as an audit log. Those two things can't both be true: if
someone disputes "you told the AI to move Acme to lost", a transcript the
same AI produced is not evidence. So the bytes are retained, for a bounded
window, behind signed URLs.

Three backends behind one interface, chosen by `settings.voice_audio_backend`:

- `"s3"` — AWS S3 or any S3-compatible endpoint. Cloudflare R2 is S3-
  compatible, so R2 is this backend plus an `endpoint_url`; there is no
  separate R2 code path and there doesn't need to be.
- `"local"` — a directory on disk. For development, and for self-hosted
  installs that don't want object storage.
- `"none"` — v1 behaviour. Nothing is written, `save_audio` returns None,
  and everything downstream already handles a null `audio_key`. Kept as a
  first-class option because some customers' data policies require exactly
  this.

boto3 is imported lazily inside the S3 backend so it stays an optional
dependency — the same lazy-import trick voice_actions.py uses for
whatsapp_sender. An install that never sets `voice_audio_backend="s3"`
never needs boto3 at all, which keeps the module's "no new dependencies"
promise intact for everyone else.

Retention is enforced in two independent places, deliberately:
`audio_expires_at` on the row (so the API refuses to sign a URL for expired
audio the moment it expires) and `sweep_expired_audio()` (which actually
deletes the object). Belt and braces, because the row check is instant and
free while the sweep runs on a timer that could be down.
"""
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 90


class StorageError(Exception):
    pass


@dataclass
class StoredAudio:
    key: str
    size_bytes: int
    expires_at: datetime


def _backend() -> str:
    return (getattr(settings, "voice_audio_backend", "none") or "none").lower()


def _retention_days() -> int:
    return int(getattr(settings, "voice_audio_retention_days", DEFAULT_RETENTION_DAYS) or DEFAULT_RETENTION_DAYS)


def _build_key(company_id: str, kind: str, filename: str) -> str:
    stamp = datetime.utcnow().strftime("%Y/%m/%d")
    ext = os.path.splitext(filename)[1] or ".ogg"
    return f"voice/{company_id}/{kind}/{stamp}/{uuid.uuid4().hex}{ext}"


# --------------------------------------------------------------------------
# S3 / R2
# --------------------------------------------------------------------------

def _s3_client():
    try:
        import boto3  # lazy: optional dependency
    except ImportError as exc:  # pragma: no cover
        raise StorageError(
            "voice_audio_backend is 's3' but boto3 isn't installed. "
            "Either `pip install boto3` or set voice_audio_backend='local'."
        ) from exc

    kwargs = {}
    endpoint = getattr(settings, "s3_endpoint_url", None)  # set this for Cloudflare R2
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    if getattr(settings, "aws_access_key_id", None):
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    if getattr(settings, "aws_region", None):
        kwargs["region_name"] = settings.aws_region
    return boto3.client("s3", **kwargs)


# --------------------------------------------------------------------------
# Public interface
# --------------------------------------------------------------------------

def save_audio(audio_bytes: bytes, *, company_id: str, filename: str = "voice-note.ogg",
               kind: str = "commands") -> Optional[StoredAudio]:
    """Persist the recording. Returns None when retention is switched off.

    Never raises on a storage failure: a voice command that worked must not
    fail because the bucket was briefly unreachable. The transcript is the
    product; the audio is the receipt. Failures are logged and the row keeps
    a null key.
    """
    backend = _backend()
    if backend == "none":
        return None

    key = _build_key(company_id, kind, filename)
    expires_at = datetime.utcnow() + timedelta(days=_retention_days())

    try:
        if backend == "s3":
            _s3_client().put_object(
                Bucket=settings.s3_bucket,
                Key=key,
                Body=audio_bytes,
                ContentType="audio/ogg",
            )
        elif backend == "local":
            root = getattr(settings, "voice_audio_local_dir", "./var/voice-audio")
            path = os.path.join(root, key)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(audio_bytes)
        else:
            raise StorageError(f"Unknown voice_audio_backend: {backend!r}")
    except Exception:
        logger.exception("Failed to store voice audio for company %s", company_id)
        return None

    return StoredAudio(key=key, size_bytes=len(audio_bytes), expires_at=expires_at)


def load_audio(key: str) -> Optional[bytes]:
    """Read the stored bytes back.

    Playback goes through the app's own authenticated endpoint rather than a
    presigned URL, for one reason: an `<audio src>` tag can't carry an
    Authorization header, so a presigned URL would be the only thing standing
    between a pasted link and someone else's recording. Streaming through the
    API keeps the same ownership check every other route uses — the same
    trade-off the frontend already makes for PDFs.
    """
    if not key:
        return None
    backend = _backend()
    try:
        if backend == "s3":
            obj = _s3_client().get_object(Bucket=settings.s3_bucket, Key=key)
            return obj["Body"].read()
        if backend == "local":
            root = getattr(settings, "voice_audio_local_dir", "./var/voice-audio")
            path = os.path.join(root, key)
            if not os.path.exists(path):
                return None
            with open(path, "rb") as handle:
                return handle.read()
    except Exception:
        logger.exception("Could not read audio %s", key)
    return None


def delete_audio(key: str) -> bool:
    if not key:
        return False
    backend = _backend()
    try:
        if backend == "s3":
            _s3_client().delete_object(Bucket=settings.s3_bucket, Key=key)
            return True
        if backend == "local":
            root = getattr(settings, "voice_audio_local_dir", "./var/voice-audio")
            path = os.path.join(root, key)
            if os.path.exists(path):
                os.remove(path)
            return True
    except Exception:
        logger.exception("Could not delete audio %s", key)
    return False


def sweep_expired_audio(db, *, limit: int = 500) -> dict:
    """Hang this off the same scheduler tick as the followups sweep.

    Deletes the object and nulls the key, but keeps the row: the transcript
    and the audit trail outlive the recording. Storage usage is decremented
    so a company that hits its cap gets the space back as recordings age out.
    """
    from app.voice_models import VoiceCommand, MeetingSession
    from app import usage_metering

    now = datetime.utcnow()
    deleted = 0

    rows = (
        db.query(VoiceCommand)
        .filter(VoiceCommand.audio_key.isnot(None), VoiceCommand.audio_expires_at <= now)
        .limit(limit)
        .all()
    )
    for row in rows:
        if delete_audio(row.audio_key):
            usage_metering.release(db, row.company_id, usage_metering.STORAGE_BYTES, row.audio_bytes or 0)
            row.audio_key = None
            row.audio_bytes = None
            deleted += 1

    cutoff = now - timedelta(days=_retention_days())
    meetings = (
        db.query(MeetingSession)
        .filter(MeetingSession.audio_key.isnot(None), MeetingSession.created_at <= cutoff)
        .limit(limit)
        .all()
    )
    for meeting in meetings:
        if delete_audio(meeting.audio_key):
            usage_metering.release(db, meeting.company_id, usage_metering.STORAGE_BYTES, meeting.audio_bytes or 0)
            meeting.audio_key = None
            meeting.audio_bytes = None
            deleted += 1

    db.commit()
    return {"deleted": deleted}
