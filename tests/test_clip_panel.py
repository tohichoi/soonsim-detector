"""The clip review panel must reach the served page intact."""

from fastapi.testclient import TestClient

from src.config import AppConfig
from src.viewer.app import create_viewer_app
from src.viewer.clip_panel import CLIP_PANEL_HTML
from src.viewer.templates import HTML_TEMPLATE


def test_panel_is_spliced_into_the_template():
    assert "<!-- CLIP_PANEL -->" not in HTML_TEMPLATE
    assert CLIP_PANEL_HTML in HTML_TEMPLATE
    assert 'id="clipList"' in HTML_TEMPLATE
    assert 'id="clipModal"' in HTML_TEMPLATE


def test_panel_renders_on_the_authenticated_page():
    config = AppConfig()
    client = TestClient(create_viewer_app(config=config))
    assert client.post("/api/auth/login", json={"pin": config.viewer.pin}).status_code == 200
    page = client.get("/")
    assert page.status_code == 200
    assert 'id="clipList"' in page.text
    assert 'id="clipVideo"' in page.text


def test_events_are_the_default_tab():
    # False alarms cluster in the event clips, so that is where the operator
    # should land.
    assert 'data-kind="event" aria-pressed="true"' in CLIP_PANEL_HTML
    assert 'data-kind="signal" aria-pressed="true"' not in CLIP_PANEL_HTML
    assert "let kind = 'event';" in CLIP_PANEL_HTML


def test_tab_descriptions_are_present_and_announced():
    assert 'id="clipTabDesc"' in CLIP_PANEL_HTML
    assert 'role="status"' in CLIP_PANEL_HTML
    for sentence in (
        "탐지기가 순심이가 배변판에 있다고 판단해 저장한 영상입니다.",
        "움직임은 감지됐는데 탐지기가 아무것도 찾지 못한 구간의 영상입니다.",
        "이벤트와 시그널을 함께 표시합니다.",
    ):
        assert sentence in CLIP_PANEL_HTML


def test_unlabelled_filter_is_only_sent_when_switched_on():
    # An empty label= is a 400 from the backend, so the parameter must be
    # absent unless the checkbox is ticked.
    assert "if (unlabelledOnly) url += '&label=unlabelled';" in CLIP_PANEL_HTML
    assert 'id="clipUnlabelledOnly"' in CLIP_PANEL_HTML


def test_panel_keeps_the_accessibility_contract():
    assert 'controls' in CLIP_PANEL_HTML  # the player must be controllable
    assert 'aria-modal="true"' in CLIP_PANEL_HTML
    assert 'aria-labelledby="clipModalTitle"' in CLIP_PANEL_HTML
    assert CLIP_PANEL_HTML.count('class="theater-btn label-btn"') == 4
    assert 'aria-pressed="false"' in CLIP_PANEL_HTML


def test_player_tracks_the_open_clip_by_name_and_position():
    # Every load() replaces the clips array, so a saved object reference goes
    # stale. The player must track the open clip by name and its position as an
    # integer re-seated on each load.
    assert "let openName = null;" in CLIP_PANEL_HTML
    assert "let lastIndex = -1;" in CLIP_PANEL_HTML
    assert "clips.indexOf(openClip)" not in CLIP_PANEL_HTML
    assert "if (openName) syncIndex();" in CLIP_PANEL_HTML
    # Focus returns by name, so it survives the list being rebuilt.
    assert "items[i].dataset.clipName === name" in CLIP_PANEL_HTML


def test_late_responses_cannot_corrupt_the_visible_state():
    # A label POST that lands after the player moved on must not repaint the
    # newly-opened clip.
    assert "if (openName === name) paintLabelState(saved);" in CLIP_PANEL_HTML
    # A superseded clip-list response must be discarded, so the checkbox and the
    # list cannot disagree after a fast toggle.
    assert "if (seq !== loadSeq) return;" in CLIP_PANEL_HTML


def test_deferred_is_a_label_separate_from_unsure():
    # deferred is "pre camera-roll fix, out of scope"; unsure is "human could
    # not decide". They must not collapse into one value.
    assert 'data-label="deferred"' in CLIP_PANEL_HTML
    assert "보류 · 구 좌표계" in CLIP_PANEL_HTML
    assert "deferred: { text: '보류 · 구 좌표계', cls: 'clip-label-deferred' }" in CLIP_PANEL_HTML
    assert ".clip-label-deferred" in CLIP_PANEL_HTML
    assert "clip-label-deferred" not in CLIP_PANEL_HTML.split(".clip-label-unsure")[0]
