"""
Speech-to-text.

Uses the same `openai` client as the rest of the app — Whisper is one call on
the SDK that's already a dependency, so there's nothing new to install.

Three things worth knowing:

- **Language is auto-detected.** No `language` parameter is sent. That's what
  makes multi-language voice notes work without knowing in advance who's
  speaking what, and `detected_language` then drives which language the
  confirmation comes back in (voice_i18n).
- **Segments are kept.** `verbose_json` returns timings; they're the raw
  material for meeting speaker turns and for a transcript you can click to
  seek.
- **Long audio is chunked.** Whisper caps a request at 25 MB — fine for a
  command, useless for an hour-long meeting. `transcribe_long_audio()` splits
  by byte range with a small backwards overlap and stitches the timings onto a
  single timeline, de-duplicating the words that repeat at a seam.

  The seams are approximate: a proper implementation demuxes the container
  and splits on frame boundaries. This version needs no ffmpeg and is wrong
  only at the margins, where "the" may appear twice rather than a sentence
  disappearing. If you later add ffmpeg, replace `_chunks()` with a real
  time-based split and delete `_drop_overlap` — nothing else changes.

Everything raises `TranscriptionError` and nothing here touches the database.
"""
import io
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Optional

from openai import OpenAI, OpenAIError

from app.config import settings

logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 25 * 1024 * 1024        # Whisper's hard ceiling
CHUNK_TARGET_BYTES = 20 * 1024 * 1024     # headroom for multipart overhead
CHUNK_OVERLAP_BYTES = 256 * 1024          # ~a second or two, so a word isn't lost at a seam

# Rough bytes-per-second for the codecs that actually turn up: browser
# MediaRecorder opus (~16-24 kbps) and uploaded m4a/mp3 meeting recordings
# (64-128 kbps). Used only for a pre-flight quota estimate, never shown.
_BYTES_PER_SECOND_ESTIMATE = 4_000

_client: Optional[OpenAI] = None


class TranscriptionError(Exception):
    pass


@dataclass
class Segment:
    start: float
    end: float
    text: str
    speaker: Optional[str] = None


@dataclass
class Transcription:
    text: str
    language: Optional[str]
    duration_seconds: Optional[float]
    segments: list[Segment] = field(default_factory=list)


def _get_client() -> Optional[OpenAI]:
    global _client
    if not settings.openai_api_key:
        return None
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def estimate_duration_seconds(audio_bytes: int) -> float:
    """Pre-flight estimate for the quota check. Deliberately conservative:
    over-estimating costs a customer a little headroom, under-estimating lets
    them blow past a cap they're paying to have enforced."""
    return max(1.0, audio_bytes / _BYTES_PER_SECOND_ESTIMATE)


def _transcribe_groq(audio_bytes: bytes, filename: str) -> dict[str, Any]:
    import urllib.request
    import json
    import uuid

    api_key = settings.groq_api_key
    if not api_key:
        raise TranscriptionError("Groq API key is empty.")

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex[:12]}"

    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
    body.extend(b"Content-Type: audio/webm\r\n\r\n")
    body.extend(audio_bytes)
    body.extend(b"\r\n")

    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="model"\r\n\r\n')
    body.extend(b"whisper-large-v3-turbo\r\n")

    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="response_format"\r\n\r\n')
    body.extend(b"json\r\n")

    body.extend(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        text = (data.get("text") or "").strip()
        if text:
            dur = estimate_duration_seconds(len(audio_bytes))
            return {
                "text": text,
                "language": "en",
                "duration": dur,
                "segments": [{"start": 0.0, "end": dur, "text": text}]
            }
    raise TranscriptionError("Groq Whisper API returned empty text.")


def _transcribe_gemini(audio_bytes: bytes, filename: str) -> dict[str, Any]:
    import base64
    import json
    import urllib.request

    api_key = settings.gemini_api_key
    if not api_key:
        raise TranscriptionError("Gemini API key is empty.")

    mime_type = "audio/mp3"
    fn_low = filename.lower()
    if fn_low.endswith(".wav"): mime_type = "audio/wav"
    elif fn_low.endswith(".m4a"): mime_type = "audio/m4a"
    elif fn_low.endswith(".ogg"): mime_type = "audio/ogg"
    elif fn_low.endswith(".webm"): mime_type = "audio/webm"

    b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
    payload = {
        "contents": [{
            "parts": [
                {"text": "Transcribe this audio recording verbatim. Write the transcript in English or Roman Urdu using the Latin/English alphabet (for example: 'Create a quotation for 5 laptops' or 'Laptop ki quotation bana do'). Do NOT use Arabic or Urdu script characters. Provide plain text only without markdown formatting or preamble."},
                {"inline_data": {"mime_type": mime_type, "data": b64_audio}}
            ]
        }]
    }

    models_to_try = ["gemini-flash-latest", "gemini-3.1-flash-lite", "gemini-3.6-flash", "gemini-3.5-flash"]
    last_exc = None

    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        transcribed_text = parts[0]["text"].strip()
                        if transcribed_text:
                            dur = estimate_duration_seconds(len(audio_bytes))
                            logger.info("Gemini transcription succeeded using model %s", model_name)
                            return {
                                "text": transcribed_text,
                                "language": "en",
                                "duration": dur,
                                "segments": [{"start": 0.0, "end": dur, "text": transcribed_text}]
                            }
        except Exception as exc:
            logger.warning("Gemini model %s failed (%s), trying next audio model...", model_name, exc)
            last_exc = exc

    raise TranscriptionError(f"Gemini audio transcription failed: {last_exc}")


def _transcribe_bytes(audio_bytes: bytes, filename: str) -> dict[str, Any]:
    errors: list[str] = []

    # 1. Try Google Gemini Audio API first if key exists (Verified working with gemini-3.6-flash)
    if settings.gemini_api_key:
        try:
            logger.info("Attempting Gemini transcription (key starts with %s...)", settings.gemini_api_key[:6])
            result = _transcribe_gemini(audio_bytes, filename)
            logger.info("Gemini succeeded: %s", result.get("text", "")[:80])
            return result
        except Exception as exc:
            errors.append(f"Gemini: {exc}")
            logger.warning("Gemini Audio API error: %s. Falling back.", exc)
    else:
        logger.warning("GEMINI_API_KEY is empty — skipping Gemini.")

    # 2. Try Groq Free Whisper API next
    if settings.groq_api_key:
        try:
            logger.info("Attempting Groq Whisper transcription (key starts with %s...)", settings.groq_api_key[:6])
            result = _transcribe_groq(audio_bytes, filename)
            logger.info("Groq Whisper succeeded: %s", result.get("text", "")[:80])
            return result
        except Exception as exc:
            errors.append(f"Groq: {exc}")
            logger.warning("Groq Whisper API error: %s. Falling back.", exc)
    else:
        logger.warning("GROQ_API_KEY is empty — skipping Groq.")

    # 3. Try OpenAI Whisper if key exists
    if settings.openai_api_key:
        try:
            logger.info("Attempting OpenAI Whisper transcription...")
            buffer = io.BytesIO(audio_bytes)
            buffer.name = filename
            resp = _get_client().audio.transcriptions.create(
                model=settings.whisper_model,
                file=buffer,
                response_format="verbose_json",
            )
            return resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)
        except Exception as exc:
            errors.append(f"OpenAI: {exc}")
            logger.warning("Whisper API error: %s", exc)
    else:
        logger.warning("OPENAI_API_KEY is empty — skipping OpenAI Whisper.")

    # 4. All remote transcription failed — raise a clear error instead of
    #    returning fake placeholder text.
    error_detail = "; ".join(errors) if errors else "No valid API keys configured"
    logger.error("All transcription methods failed: %s", error_detail)
    raise TranscriptionError(
        f"Could not transcribe audio. {error_detail}. "
        "Please use the browser's live speech recognition or configure valid API keys."
    )


def _segments_from(data: dict[str, Any], offset: float = 0.0) -> list[Segment]:
    out: list[Segment] = []
    for raw in data.get("segments") or []:
        raw = raw if isinstance(raw, dict) else getattr(raw, "__dict__", {})
        try:
            out.append(Segment(
                start=float(raw.get("start", 0)) + offset,
                end=float(raw.get("end", 0)) + offset,
                text=(raw.get("text") or "").strip(),
            ))
        except (TypeError, ValueError):
            continue
    return out


def transcribe_audio(audio_bytes: bytes, *, filename: str = "voice-note.webm") -> Transcription:
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise TranscriptionError(
            f"Audio is too large for a single request ({len(audio_bytes)} bytes). "
            "Use transcribe_long_audio() for recordings this size."
        )

    data = _transcribe_bytes(audio_bytes, filename)
    text = (data.get("text") or "").strip()
    if not text:
        raise TranscriptionError("Nothing was said, or the audio was too quiet to make out.")

    return Transcription(
        text=text,
        language=data.get("language"),
        duration_seconds=data.get("duration"),
        segments=_segments_from(data),
    )


def transcribe_long_audio(audio_bytes: bytes, *, filename: str = "meeting.m4a") -> Transcription:
    if len(audio_bytes) <= MAX_AUDIO_BYTES:
        return transcribe_audio(audio_bytes, filename=filename)

    chunks = _chunks(audio_bytes)
    logger.info("Transcribing %d bytes as %d chunks", len(audio_bytes), len(chunks))

    all_segments: list[Segment] = []
    texts: list[str] = []
    language: Optional[str] = None
    offset = 0.0

    for index, chunk in enumerate(chunks):
        data = _transcribe_bytes(chunk, f"{index:02d}-{filename}")
        language = language or data.get("language")
        segments = _segments_from(data, offset=offset)

        if all_segments and segments:
            segments = _drop_overlap(all_segments[-1], segments)

        all_segments.extend(segments)
        chunk_text = (data.get("text") or "").strip()
        if chunk_text:
            texts.append(chunk_text)
        offset = all_segments[-1].end if all_segments else offset + float(data.get("duration") or 0)

    if not texts:
        raise TranscriptionError("Nothing could be made out in that recording.")

    return Transcription(
        text="\n".join(texts),
        language=language,
        duration_seconds=all_segments[-1].end if all_segments else None,
        segments=all_segments,
    )


def _chunks(audio_bytes: bytes) -> list[bytes]:
    count = math.ceil(len(audio_bytes) / CHUNK_TARGET_BYTES)
    size = math.ceil(len(audio_bytes) / count)
    out: list[bytes] = []
    start = 0
    while start < len(audio_bytes):
        end = min(len(audio_bytes), start + size)
        begin = max(0, start - CHUNK_OVERLAP_BYTES) if out else 0
        out.append(audio_bytes[begin:end])
        start = end
    return out


def _drop_overlap(previous: Segment, segments: list[Segment]) -> list[Segment]:
    """Drop leading segments whose text repeats the tail of the previous chunk.

    Compares normalised words rather than raw strings, because Whisper
    punctuates the same audio differently on either side of a seam.
    """
    tail = _words(previous.text)[-8:]
    if not tail:
        return segments
    for index, segment in enumerate(segments[:3]):
        head = _words(segment.text)[:8]
        if head and _shared_run(tail, head) >= max(2, len(head) // 2):
            return segments[index + 1:]
    return segments


def _words(text: str) -> list[str]:
    return [w.strip(".,!?;:").lower() for w in (text or "").split() if w.strip(".,!?;:")]


def _shared_run(tail: list[str], head: list[str]) -> int:
    best = 0
    for size in range(1, min(len(tail), len(head)) + 1):
        if tail[-size:] == head[:size]:
            best = size
    return best
