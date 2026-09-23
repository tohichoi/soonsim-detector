"""One-time backfill: convert existing mp4v clips to H.264.

Clips written before the export path learned to convert are still mp4v, which
no browser can play in the viewer. Run once, from the project root:

    uv run python -m src.cli.transcode_clips

It is slow on purpose (nice 19, one thread) because the NAS keeps running
inference while it works.
"""

from src.config import load_config
from src.recorder.exporter import CLIP_PREFIXES
from src.recorder.transcode import backfill


def main() -> None:
    output_dir = load_config().recorder.output_dir
    candidates = [p for p in output_dir.glob("*.mp4") if p.name.startswith(CLIP_PREFIXES)]
    converted, failed = backfill(output_dir)
    skipped = len(candidates) - converted - failed
    print(
        f"클립 변환 완료: 변환 {converted}건 / 실패 {failed}건 / 건너뜀 {skipped}건 "
        f"({output_dir})"
    )


if __name__ == "__main__":
    main()
