"""Clip review panel fragment for the Soonsim Detector web viewer.

Spliced into ``HTML_TEMPLATE`` at the ``<!-- CLIP_PANEL -->`` placeholder. The
panel lists recorded clips (signal / event), plays the chosen one in a modal
that reuses the viewer's existing theater classes, and lets the operator label
it as a real defecation, a false alarm, or unsure. Those labels are the
training signal for tuning the detector, so the labelling flow is the point.

Markup and CSS live here; the behaviour is ``clip_panel_js.py``, kept apart so
each file stays under the 300-line cap.

Backend contract (served by the viewer app):
    GET  /api/clips?kind=all|signal|event -> {"clips": [...]} newest first
    GET  /api/clips/{name}                -> the mp4
    POST /api/clips/{name}/label          -> {"name": str, "label": str|null}
"""

from src.viewer.clip_panel_js import CLIP_PANEL_JS

_PANEL_TEMPLATE = """
<style>
    .clip-panel {
        width: 100%;
        max-width: 1320px;
        margin-top: 20px;
    }
    .clip-panel-title { font-weight: 600; font-size: 1.05rem; }
    .clip-panel-actions { display: flex; align-items: center; gap: 8px; }
    .clip-count {
        font-size: 0.8rem;
        background: #0ea5e9;
        color: white;
        padding: 2px 8px;
        border-radius: 9999px;
    }
    .clip-hint {
        font-size: 0.78rem;
        color: #64748b;
        margin-bottom: 10px;
        line-height: 1.5;
    }
    .clip-tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
    .clip-tab {
        background: #0f172a;
        border: 1px solid var(--border);
        color: #94a3b8;
        padding: 8px 16px;
        border-radius: 8px;
        font: inherit;
        font-size: 0.9rem;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s ease;
    }
    .clip-tab:hover { border-color: var(--accent); color: var(--accent); }
    .clip-tab[aria-pressed="true"] {
        background: #0ea5e9;
        border-color: #0ea5e9;
        color: white;
    }
    .clip-tab:focus-visible,
    .clip-item:focus-visible,
    .clip-retry:focus-visible {
        outline: 2px solid var(--accent);
        outline-offset: 2px;
    }
    .clip-list {
        list-style: none;
        display: flex;
        flex-direction: column;
        gap: 8px;
        max-height: 420px;
        overflow-y: auto;
        padding-right: 6px;
    }
    .clip-item {
        width: 100%;
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 12px;
        background: #0f172a;
        border: 1px solid var(--border);
        border-radius: 10px;
        color: var(--text-color);
        font: inherit;
        text-align: left;
        cursor: pointer;
        transition: all 0.2s ease;
    }
    .clip-item:hover {
        border-color: var(--accent);
        box-shadow: 0 4px 14px rgba(56, 189, 248, 0.15);
    }
    .clip-time {
        font-weight: 700;
        color: var(--accent);
        font-size: 0.95rem;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }
    .clip-size { color: #94a3b8; font-size: 0.82rem; }
    .clip-spacer { flex: 1; }
    .clip-kind-badge,
    .clip-label-badge {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 5px;
        font-weight: 700;
        font-size: 0.75rem;
        white-space: nowrap;
    }
    .clip-kind-signal { background: #334155; color: #e2e8f0; }
    .clip-kind-event { background: var(--accent); color: #0b1120; }
    .clip-label-real { background: var(--success); color: #000; }
    .clip-label-false { background: var(--alert); color: #fff; }
    .clip-label-unsure { background: var(--warning); color: #000; }
    .clip-label-none { background: #64748b; color: #fff; }
    .clip-state {
        padding: 24px 12px;
        text-align: center;
        color: #64748b;
        font-size: 0.9rem;
        line-height: 1.6;
    }
    .clip-state.error { color: var(--alert); }
    .clip-retry {
        margin-top: 8px;
        background: #0f172a;
        border: 1px solid var(--border);
        color: #94a3b8;
        padding: 8px 16px;
        border-radius: 8px;
        font: inherit;
        font-size: 0.85rem;
        font-weight: 600;
        cursor: pointer;
    }
    .clip-retry:hover { border-color: var(--accent); color: var(--accent); }
    .label-btn[aria-pressed="true"] {
        border-color: var(--accent);
        background: rgba(56, 189, 248, 0.25);
        color: #ffffff;
    }
    .label-btn:disabled { opacity: 0.5; cursor: default; }
    /* The shared .theater-footer-controls does not wrap, so on a phone the six
       clip buttons run past the right edge and the last one is unreachable.
       Scoped to #clipModal so the live theater modal keeps its own layout. */
    #clipModal .theater-footer-controls {
        flex-wrap: wrap;
        justify-content: flex-end;
    }
    #clipModal .theater-footer-controls .theater-btn { white-space: nowrap; }
    /* A clip name is one long token and would push the close button off the
       right edge on a phone. Let the title shrink and wrap instead. */
    #clipModal .theater-title-group { min-width: 0; }
    #clipModal .theater-actions { flex-shrink: 0; }
    #clipModal .theater-event-title { overflow-wrap: anywhere; }
    .clip-toast {
        position: fixed;
        left: 50%;
        bottom: 24px;
        transform: translateX(-50%);
        background: rgba(15, 23, 42, 0.96);
        border: 1px solid var(--border);
        color: var(--text-color);
        padding: 10px 16px;
        border-radius: 8px;
        font-size: 0.88rem;
        font-weight: 600;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
        z-index: 10001;
        opacity: 0;
        pointer-events: none;
        transition: opacity 0.2s ease;
    }
    .clip-toast.show { opacity: 1; }
    .clip-toast.error { border-color: var(--alert); color: #fca5a5; }
</style>

<section class="card clip-panel" aria-labelledby="clipPanelTitle">
    <div class="gallery-header">
        <span id="clipPanelTitle" class="clip-panel-title">녹화 클립 라벨링</span>
        <div class="clip-panel-actions">
            <span id="clipCountBadge" class="clip-count">0건</span>
            <button type="button" class="clip-tab" id="clipRefreshBtn">새로고침</button>
        </div>
    </div>
    <p class="clip-hint">
        저장된 영상을 확인하고 진짜 배변 / 오탐 / 판단 보류로 분류해 주세요.
        이 라벨이 탐지기 튜닝의 학습 신호가 됩니다.
    </p>
    <div class="clip-tabs" role="group" aria-label="클립 종류 필터">
        <button type="button" class="clip-tab" data-kind="signal" aria-pressed="true">신호</button>
        <button type="button" class="clip-tab" data-kind="event" aria-pressed="false">이벤트</button>
        <button type="button" class="clip-tab" data-kind="all" aria-pressed="false">전체</button>
    </div>
    <ul class="clip-list" id="clipList" aria-busy="true" aria-live="polite">
        <li class="clip-state">클립을 불러오는 중...</li>
    </ul>
</section>

<div id="clipModal" class="theater-modal" role="dialog" aria-modal="true" aria-labelledby="clipModalTitle">
    <div class="theater-header">
        <div class="theater-title-group">
            <span class="theater-live-badge history">RECORDED CLIP</span>
            <span id="clipModalTitle" class="theater-event-title">녹화 클립</span>
            <span id="clipModalTime" class="theater-timestamp">--:--:--</span>
        </div>
        <div class="theater-actions">
            <button type="button" class="theater-btn close-btn" id="clipCloseBtn" aria-label="닫기 (ESC)">✕</button>
        </div>
    </div>

    <div class="theater-viewport">
        <video id="clipVideo" class="theater-image" controls playsinline preload="metadata" tabindex="0"></video>
    </div>

    <div class="theater-footer">
        <div class="theater-status-box">
            <div>
                <div id="clipLabelState" class="theater-status-headline">현재 라벨: 미분류</div>
                <div class="theater-status-sub">분류 결과는 다음 튜닝의 학습 신호로 저장됩니다.</div>
            </div>
        </div>
        <div class="theater-footer-controls">
            <button type="button" class="theater-btn" id="clipPrevBtn">◀ 이전</button>
            <button type="button" class="theater-btn" id="clipNextBtn">다음 ▶</button>
            <button type="button" class="theater-btn label-btn" data-label="real" aria-pressed="false">진짜 배변</button>
            <button type="button" class="theater-btn label-btn" data-label="false" aria-pressed="false">오탐</button>
            <button type="button" class="theater-btn label-btn" data-label="unsure" aria-pressed="false">판단 보류</button>
            <button type="button" class="theater-btn" id="clipClearBtn">라벨 지우기</button>
        </div>
    </div>
</div>

<div class="clip-toast" id="clipToast" role="status" aria-live="polite"></div>

<script>
/*__CLIP_PANEL_JS__*/
</script>
"""

CLIP_PANEL_HTML = _PANEL_TEMPLATE.replace("/*__CLIP_PANEL_JS__*/", CLIP_PANEL_JS)
