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


def test_panel_keeps_the_accessibility_contract():
    assert 'controls' in CLIP_PANEL_HTML  # the player must be controllable
    assert 'aria-modal="true"' in CLIP_PANEL_HTML
    assert 'aria-labelledby="clipModalTitle"' in CLIP_PANEL_HTML
    assert CLIP_PANEL_HTML.count('class="theater-btn label-btn"') == 3
    assert 'aria-pressed="false"' in CLIP_PANEL_HTML
