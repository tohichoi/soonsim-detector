"""Listing and resolving recorded clips for the web viewer.

The records directory holds the clips beside the detector's logs, so naming is
the only thing separating the two. Everything here treats the filename as the
record: the timestamp is in it, and only an exact clip name may ever be served.
"""

import re
from pathlib import Path
from typing import Optional

from src.viewer.labels import load_labels

# A clip name is the whole trust boundary: records/ also holds detection*.log
# and zone_contact.jsonl, and neither may be downloaded through the viewer.
CLIP_NAME_RE = re.compile(r"^(soonsim|signal)_(\d{8})_(\d{6})\.mp4$")
KINDS = ("all", "signal", "event")
KIND_BY_PREFIX = {"soonsim": "event", "signal": "signal"}


def _time_str(date_part: str, time_part: str) -> str:
    """Reformat a clip's filename stamp as "YYYY-MM-DD HH:MM:SS".

    The stamp was already written in KST by the exporter, so it is only
    re-punctuated here, never converted.
    """
    return (
        f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:]} "
        f"{time_part[:2]}:{time_part[2:4]}:{time_part[4:]}"
    )


def list_clips(output_dir: Path, kind: str = "all") -> list[dict]:
    """Describe every recorded clip, newest first.

    ``kind`` is "all", "signal" (kept on a miss) or "event" (a confirmed visit).
    A bad kind raises ValueError; the route turns that into a 400.
    """
    if kind not in KINDS:
        raise ValueError(f"Unsupported kind: {kind!r}")

    directory = Path(output_dir)
    if not directory.is_dir():
        return []
    labels = load_labels(directory)

    found: list[tuple[str, dict]] = []
    for path in directory.glob("*.mp4"):
        match = CLIP_NAME_RE.match(path.name)
        if match is None:
            continue
        clip_kind = KIND_BY_PREFIX[match.group(1)]
        if kind != "all" and kind != clip_kind:
            continue
        try:
            size_bytes = path.stat().st_size
        except OSError:
            # Retention pruned it between the glob and here; it is not a clip
            # the viewer can offer, so it is simply not listed.
            continue
        found.append((
            match.group(2) + match.group(3),
            {
                "name": path.name,
                "kind": clip_kind,
                "time_str": _time_str(match.group(2), match.group(3)),
                "size_bytes": size_bytes,
                "label": labels.get(path.name),
            },
        ))

    found.sort(key=lambda item: item[0], reverse=True)
    return [entry for _, entry in found]


def resolve_clip(output_dir: Path, name: str) -> Optional[Path]:
    """Map a requested clip name to the file, or None when it is not one.

    Trust boundary. The name must be exactly a clip filename, must not contain a
    directory part, and must resolve to a real file inside ``output_dir`` even
    after symlinks — otherwise detection.log, zone_contact.jsonl, config.toml
    and the rest of the volume would be downloadable.
    """
    if CLIP_NAME_RE.match(name) is None or Path(name).name != name:
        return None

    root = Path(output_dir).resolve()
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate
