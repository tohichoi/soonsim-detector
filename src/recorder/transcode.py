"""Convert recorded clips to H.264 so a browser can play them.

sv.VideoSink defaults to the mp4v codec (MPEG-4 Part 2), which is what wrote
every clip so far. No browser decodes it in a <video> element. The container's
OpenCV cannot encode H.264 (h264_v4l2m2m has no device) but its ffmpeg has
libx264, so a clip is converted after export instead.

The NAS also runs real-time inference while this happens, so the transcode is
deliberately polite: nice 19 and a single thread. Being slow in wall-clock
terms is fine; stealing CPU from the detector is not.
"""

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Sequence

from loguru import logger

from src.recorder.exporter import CLIP_PREFIXES

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
FINE_CPU = 19
# Only signal clips are capped (signal_recorder.MAX_SIGNAL_SEC); an event clip
# is pre_buffer + stay + post_buffer and has no upper bound, so the limit cannot
# be derived from a maximum clip length. It is derived from throughput instead:
# a 45s clip converts in about three seconds single-threaded on the NAS, so five
# minutes covers well over ten minutes of clip even under inference contention.
# A conversion still running past that is stuck, not slow. Bounding it keeps a
# wedged ffmpeg from holding a worker thread (and a nice'd process) for half an
# hour.
TIMEOUT_SEC = 300.0
# The exporter writes straight into the final filename, so a clip this fresh
# may still be growing on disk. backfill must not read it: a half-written file
# would convert to a truncated H.264 and then overwrite the original.
RECENT_SEC = 60.0

# Paths being converted right now *within this process*, so two threads never
# fight over one file. A separate process is guarded by the pid in the temp
# name instead, since a module-level set cannot see across processes.
_in_flight: set[str] = set()
_in_flight_lock = threading.Lock()


def is_h264(path: Path) -> bool:
    """True when ffprobe reports the file's first video stream as H.264."""
    try:
        result = subprocess.run(
            [
                FFPROBE, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path),
            ],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning(f"ffprobe could not read {path}: {e}")
        return False
    return result.returncode == 0 and result.stdout.strip() == "h264"


def is_transcoding(path: Path) -> bool:
    """True while another thread is converting this exact file."""
    with _in_flight_lock:
        return os.path.realpath(path) in _in_flight


def _claim(path: Path) -> bool:
    """Mark a path as ours, or return False when someone already has it."""
    key = os.path.realpath(path)
    with _in_flight_lock:
        if key in _in_flight:
            return False
        _in_flight.add(key)
        return True


def _release(path: Path) -> None:
    with _in_flight_lock:
        _in_flight.discard(os.path.realpath(path))


def _is_usable(path: Path) -> bool:
    """True when a freshly written file is a non-empty H.264 clip.

    A truncated or empty file that ffmpeg still exited 0 on would otherwise
    replace a good clip with an unplayable one, and the original cannot be
    recovered afterwards.
    """
    try:
        empty = path.stat().st_size == 0
    except OSError:
        return False
    return not empty and is_h264(path)


def _run_ffmpeg(path: Path, tmp: Path, timeout_sec: float) -> bool:
    """Convert path into the temp file; True when ffmpeg left something behind.

    The process is niced and single-threaded because the NAS is running
    inference at the same time: a slow transcode is fine, a starved detector is
    not.
    """
    result = subprocess.run(
        [
            "nice", "-n", str(FINE_CPU),
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(path),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
            "-threads", "1", "-movflags", "+faststart", str(tmp),
        ],
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    if result.returncode != 0 or not tmp.is_file():
        logger.warning(f"ffmpeg failed on {path.name}: {result.stderr.strip()[:300]}")
        return False
    return True


def to_h264(path: Path, timeout_sec: float = TIMEOUT_SEC) -> bool:
    """Transcode one clip to H.264 in place.

    The result is written beside the original and swapped in with os.replace,
    which is atomic, and only after the output has been checked to be a
    non-empty H.264 file. Even an ffmpeg that exits 0 having written nothing
    usable therefore leaves the original clip intact. Never raises: a clip that
    fails to convert still has to be uploaded and pruned like any other.
    """
    path = Path(path)
    if not path.is_file():
        logger.warning(f"Nothing to transcode: {path} is not a file.")
        return False
    if not _claim(path):
        logger.warning(f"A transcode of {path.name} is already running; skipping it.")
        return False

    # The pid keeps another process (the backfill CLI beside the running
    # service) off this temp file: without it both would write the same path and
    # one os.replace could install the other's half-written output.
    tmp = path.with_name(f".{path.stem}.{os.getpid()}.transcode.tmp.mp4")
    try:
        if not _run_ffmpeg(path, tmp, timeout_sec):
            return False
        if not _is_usable(tmp):
            logger.warning(
                f"ffmpeg returned success but left {path.name} unusable; "
                "keeping the original clip."
            )
            return False
        os.replace(tmp, path)
        logger.info(f"Converted {path.name} to H.264.")
        return True
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning(f"Could not transcode {path.name}: {e}")
        return False
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        _release(path)


def backfill(
    directory: Path,
    prefixes: Sequence[str] = CLIP_PREFIXES,
    recent_sec: float = RECENT_SEC,
) -> tuple[int, int]:
    """Convert every settled clip in a directory that is not H.264 yet.

    Returns (converted, failed). A clip is left alone when it is already H.264,
    when another thread here is converting it, or when it was written within the
    last ``recent_sec`` — the last case is a clip the running service is still
    writing, and converting it would truncate the original.
    """
    directory = Path(directory)
    now = time.time()
    converted = failed = 0
    for path in sorted(directory.glob("*.mp4")):
        if not path.name.startswith(tuple(prefixes)):
            continue
        try:
            if now - path.stat().st_mtime < recent_sec:
                continue
        except OSError:
            continue
        if is_h264(path) or is_transcoding(path):
            continue
        if to_h264(path):
            converted += 1
        else:
            failed += 1
    return converted, failed
