"""Tests for the pad contact metrics."""

import json

import numpy as np

from src.detector.zone_contact import PadGeometry, ZoneContactLog

# Same shape as the deployed pad zone, so the numbers below stay meaningful.
PAD = [(164, 201), (299, 271), (438, 211), (289, 164)]


def pad_geometry() -> PadGeometry:
    import cv2

    mask = np.zeros((360, 640), dtype=bool)
    cv2.fillPoly(mask.view(np.uint8), [np.array(PAD, np.int32)], 1)
    return PadGeometry(mask)


def test_margin_is_positive_when_the_dog_stands_in_front_of_the_pad():
    """A box whose bottom sits below the pad's near edge is nearer the camera."""
    geometry = pad_geometry()
    in_front = geometry.measure([12, 12, 633, 355])
    assert in_front is not None
    assert in_front.pad_bottom == 271
    assert in_front.margin > 0.2
    assert in_front.overlap == 0.0


def test_margin_is_not_positive_when_the_contact_line_reaches_the_pad():
    """With the box bottom level with the pad, the dog is standing on it."""
    geometry = pad_geometry()
    on_pad = geometry.measure([220, 60, 400, 260])
    assert on_pad is not None
    assert on_pad.margin < 0.0
    # The pad is only ~256px wide at its widest, so a 180px contact line covering
    # a third of the row it lands on is a real overlap, not a graze.
    assert on_pad.overlap > 0.3


def test_degenerate_boxes_are_skipped():
    geometry = pad_geometry()
    assert geometry.measure([10, 10, 10, 40]) is None
    assert geometry.measure([10, 40, 60, 40]) is None
    assert geometry.largest(None) is None


def test_largest_picks_the_dog_not_a_smaller_box():
    import supervision as sv

    geometry = pad_geometry()
    detections = sv.Detections(
        xyxy=np.array([[100.0, 100.0, 140.0, 140.0], [220.0, 60.0, 400.0, 260.0]]),
    )
    metrics = geometry.largest(detections)
    assert metrics is not None
    assert metrics.box == (220, 60, 400, 260)


def test_log_writes_one_json_line_per_frame(tmp_path):
    geometry = pad_geometry()
    log = ZoneContactLog(tmp_path / "zone_contact.jsonl")
    log.record(
        frame_idx=7,
        timestamp=1758450938.5,
        status="ACTIVE",
        track_ids=(2,),
        metrics=geometry.measure([220, 60, 400, 260]),
        in_zone=True,
    )
    log.record(frame_idx=8, timestamp=1758450938.6, status="IDLE", track_ids=(), metrics=None, in_zone=False)
    log.close()

    rows = [json.loads(line) for line in (tmp_path / "zone_contact.jsonl").read_text().splitlines()]
    assert len(rows) == 1, "frames without a detection should not be written"
    assert rows[0]["f"] == 7
    assert rows[0]["in"] is True
    assert rows[0]["ids"] == [2]
    assert "margin" in rows[0] and "overlap" in rows[0]
