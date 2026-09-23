"""Human labels for recorded clips, appended to a JSONL file beside them.

Append-only, like the pad-contact log: a write can never destroy an earlier
judgement, so two people labelling the same recording cannot lose each other's
work and a power-off cannot lose the file. The last label for a name wins.
"""

import json
import threading
from pathlib import Path
from typing import Optional

# A label is a verdict about one clip, so the vocabulary stays tiny. Anything
# else is a typo, not a fifth category.
#
# "deferred" is deliberately not folded into "unsure". unsure means a person
# looked and could not decide; deferred means the clip cannot answer the
# question at all (it predates the 2026-09-21 roll calibration, so its screen is
# tilted and its pad polygon is not the current one). Only unsure is a
# judgement, so only it belongs in threshold-tuning data.
ALLOWED_LABELS = ("real", "false", "unsure", "deferred")
LABEL_FILE = "clip_labels.jsonl"

# ponytail: one lock for the whole file. Labels are written by hand, so a
# per-clip lock would never pay for itself.
_write_lock = threading.Lock()


def set_label(output_dir: Path, name: str, label: Optional[str]) -> None:
    """Append one label for a clip. A None label clears the clip's verdict."""
    if label is not None and label not in ALLOWED_LABELS:
        raise ValueError(f"Unsupported label: {label!r}")
    path = Path(output_dir) / LABEL_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"name": name, "label": label}
    with _write_lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()


def load_labels(output_dir: Path) -> dict[str, str]:
    """Fold the label log to the last label per clip.

    A clip whose last line is a null label is simply absent, which is what the
    viewer means by unlabelled. Corrupt lines are skipped: a half-written last
    line must not hide every label before it.
    """
    labels: dict[str, str] = {}
    try:
        text = (Path(output_dir) / LABEL_FILE).read_text(encoding="utf-8")
    except OSError:
        return labels

    for line in text.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        name, label = row.get("name"), row.get("label")
        if not isinstance(name, str):
            continue
        if label is None:
            labels.pop(name, None)
        elif label in ALLOWED_LABELS:
            labels[name] = label
    return labels
