import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import ffmpeg
from django.conf import settings
from django.core.files.base import ContentFile


@dataclass(frozen=True)
class CompressedReel:
    file: ContentFile
    duration_seconds: float
    width: int
    height: int
    size_bytes: int


class ReelValidationError(ValueError):
    pass


def _rotation(stream):
    tags = stream.get("tags") or {}
    try:
        return int(tags.get("rotate", 0)) % 360
    except (TypeError, ValueError):
        pass
    for side_data in stream.get("side_data_list") or []:
        try:
            return int(side_data.get("rotation", 0)) % 360
        except (TypeError, ValueError):
            continue
    return 0


def _probe_reel(path):
    try:
        probe = ffmpeg.probe(path, cmd=settings.SOCIAL_FFPROBE_BINARY)
    except (ffmpeg.Error, OSError) as exc:
        raise ReelValidationError(
            "The uploaded file is not a readable video. Upload an MP4 or MOV file."
        ) from exc

    stream = next(
        (item for item in probe.get("streams", []) if item.get("codec_type") == "video"),
        None,
    )
    if not stream:
        raise ReelValidationError("The uploaded file does not contain a video track.")

    duration_value = stream.get("duration") or (probe.get("format") or {}).get("duration")
    try:
        duration = float(duration_value)
        width = int(stream["width"])
        height = int(stream["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ReelValidationError("Could not read the video's duration or dimensions.") from exc

    if not math.isfinite(duration):
        raise ReelValidationError("Could not read a valid video duration.")
    if _rotation(stream) in {90, 270}:
        width, height = height, width
    return duration, width, height


def _validate_source(upload, duration, width, height):
    if upload.size > settings.SOCIAL_REEL_MAX_SOURCE_SIZE_BYTES:
        raise ReelValidationError(
            f"The source video exceeds the {settings.SOCIAL_REEL_MAX_SOURCE_SIZE_MB} MB upload limit."
        )
    if duration < settings.SOCIAL_REEL_MIN_DURATION_SECONDS:
        raise ReelValidationError(
            f"A Reel must be at least {settings.SOCIAL_REEL_MIN_DURATION_SECONDS} seconds long."
        )
    if duration > settings.SOCIAL_REEL_MAX_DURATION_SECONDS:
        raise ReelValidationError(
            f"A Reel cannot be longer than {settings.SOCIAL_REEL_MAX_DURATION_SECONDS} seconds."
        )
    if width < 540 or height < 960:
        raise ReelValidationError(
            "A Reel must be at least 540x960 pixels."
        )
    aspect_ratio = width / height
    if abs(aspect_ratio - (9 / 16)) > settings.SOCIAL_REEL_ASPECT_RATIO_TOLERANCE:
        raise ReelValidationError(
            "A Reel must use a vertical 9:16 aspect ratio. "
            f"The uploaded video is {width}x{height}."
        )


def _encode(input_path, output_path, duration, bitrate_kbps):
    source = ffmpeg.input(input_path)
    video = (
        source.video
        .filter(
            "scale",
            720,
            1280,
            force_original_aspect_ratio="decrease",
        )
        .filter("pad", 720, 1280, "(ow-iw)/2", "(oh-ih)/2", color="black")
        .filter("fps", fps=30)
    )
    output_kwargs = {
        "vcodec": "libx264",
        "preset": settings.SOCIAL_REEL_FFMPEG_PRESET,
        "pix_fmt": "yuv420p",
        "profile:v": "high",
        "level": "4.1",
        "b:v": f"{bitrate_kbps}k",
        "maxrate": f"{bitrate_kbps}k",
        "bufsize": f"{bitrate_kbps * 2}k",
        "movflags": "+faststart",
        "map_metadata": "-1",
        "t": min(duration, settings.SOCIAL_REEL_MAX_DURATION_SECONDS),
    }
    if any(stream.get("codec_type") == "audio" for stream in ffmpeg.probe(
        input_path,
        cmd=settings.SOCIAL_FFPROBE_BINARY,
    ).get("streams", [])):
        output = ffmpeg.output(
            video,
            source.audio,
            output_path,
            acodec="aac",
            **{"b:a": "96k", "ar": 48000, **output_kwargs},
        )
    else:
        output = ffmpeg.output(video, output_path, an=None, **output_kwargs)
    try:
        output.run(
            cmd=settings.SOCIAL_FFMPEG_BINARY,
            overwrite_output=True,
            capture_stdout=True,
            capture_stderr=True,
        )
    except (ffmpeg.Error, OSError) as exc:
        detail = ""
        if isinstance(exc, ffmpeg.Error) and exc.stderr:
            detail = exc.stderr.decode("utf-8", errors="ignore").strip().splitlines()[-1]
        raise ReelValidationError(
            "The video could not be compressed."
            + (f" Encoder message: {detail}" if detail else "")
        ) from exc


def compress_reel_upload(upload):
    """Validate and transcode a short vertical Reel before storage sees it."""
    suffix = Path(upload.name or "reel.mp4").suffix.lower()
    if suffix not in {".mp4", ".mov", ".m4v"}:
        raise ReelValidationError("Upload an MP4, MOV, or M4V video.")
    if upload.size > settings.SOCIAL_REEL_MAX_SOURCE_SIZE_BYTES:
        raise ReelValidationError(
            f"The source video exceeds the {settings.SOCIAL_REEL_MAX_SOURCE_SIZE_MB} MB upload limit."
        )

    input_path = output_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as source_file:
            input_path = source_file.name
            for chunk in upload.chunks():
                source_file.write(chunk)
        upload.seek(0)

        duration, width, height = _probe_reel(input_path)
        _validate_source(upload, duration, width, height)

        output_handle = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        output_path = output_handle.name
        output_handle.close()

        target_bytes = int(settings.SOCIAL_REEL_MAX_SIZE_BYTES * 0.96)
        total_kbps = int((target_bytes * 8) / max(duration, 1) / 1000)
        bitrate_kbps = max(500, min(4000, total_kbps - 128))

        for attempt in range(3):
            _encode(input_path, output_path, duration, bitrate_kbps)
            size_bytes = os.path.getsize(output_path)
            if size_bytes <= settings.SOCIAL_REEL_MAX_SIZE_BYTES:
                break
            reduction = settings.SOCIAL_REEL_MAX_SIZE_BYTES / size_bytes
            bitrate_kbps = max(400, int(bitrate_kbps * reduction * 0.92))
        else:
            raise ReelValidationError(
                f"The compressed Reel is still larger than {settings.SOCIAL_REEL_MAX_SIZE_MB} MB."
            )

        with open(output_path, "rb") as compressed_file:
            content = compressed_file.read()
        stem = Path(upload.name or "reel").stem[:80] or "reel"
        django_file = ContentFile(content, name=f"{stem}-reel.mp4")
        return CompressedReel(
            file=django_file,
            duration_seconds=round(duration, 3),
            width=720,
            height=1280,
            size_bytes=len(content),
        )
    finally:
        for path in (input_path, output_path):
            if path:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
