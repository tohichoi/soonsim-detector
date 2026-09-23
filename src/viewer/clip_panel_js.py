"""Clip panel behaviour, part 1: state, list rendering and data access.

Spliced with ``clip_panel_wiring.py`` into a single IIFE by ``clip_panel.py``,
so both halves share one scope and no interface has to be exported. They are
kept apart only because the viewer serves plain strings and one file would blow
past the 300-line cap.
"""

CLIP_PANEL_JS_CORE = """
    const KIND_TEXT = { signal: '신호', event: '이벤트' };
    const LABELS = {
        real: { text: '진짜 배변', cls: 'clip-label-real' },
        false: { text: '오탐', cls: 'clip-label-false' },
        unsure: { text: '판단 보류', cls: 'clip-label-unsure' },
        // Different from unsure: unsure is "a human could not decide", deferred
        // is "recorded before the 2026-09-21 camera-roll fix, so out of scope".
        // Kept apart so the tuning data set is not contaminated.
        deferred: { text: '보류 · 구 좌표계', cls: 'clip-label-deferred' },
    };
    const NO_LABEL = { text: '미분류', cls: 'clip-label-none' };
    // What each tab's recordings actually are; shown under the panel title and
    // announced politely on tab change.
    const TAB_DESC = {
        event: '탐지기가 순심이가 배변판에 있다고 판단해 저장한 영상입니다. 텔레그램 알림이 발송됩니다. 진짜 배변이 아닌 것을 찾아 오탐으로 표시하면, 배변판 진입·체류 임계값을 조정하는 근거가 됩니다.',
        signal: '움직임은 감지됐는데 탐지기가 아무것도 찾지 못한 구간의 영상입니다. 텔레그램 알림은 발송되지 않습니다. 탐지기가 놓친 배변이 섞여 있을 수 있어, 진짜 배변을 찾으면 검출 임계값이나 조명 문제를 봐야 한다는 신호입니다.',
        all: '이벤트와 시그널을 함께 표시합니다. 이벤트는 탐지기가 배변으로 판단한 영상, 시그널은 움직임은 있었지만 탐지기가 찾지 못한 영상입니다.',
    };

    const listEl = document.getElementById('clipList');
    const countEl = document.getElementById('clipCountBadge');
    const descEl = document.getElementById('clipTabDesc');
    const unlabelledEl = document.getElementById('clipUnlabelledOnly');
    const modalEl = document.getElementById('clipModal');
    const videoEl = document.getElementById('clipVideo');
    const titleEl = document.getElementById('clipModalTitle');
    const timeEl = document.getElementById('clipModalTime');
    const stateEl = document.getElementById('clipLabelState');
    const toastEl = document.getElementById('clipToast');
    const prevBtn = document.getElementById('clipPrevBtn');
    const nextBtn = document.getElementById('clipNextBtn');

    // Events first: the false alarms cluster there, so that is what the
    // operator should be looking at on arrival.
    let kind = 'event';
    let unlabelledOnly = false;
    let clips = [];
    // The clip the player is showing, tracked by name: every load() swaps the
    // whole clips array for fresh objects, so an object reference goes stale.
    let openName = null;
    // Where that clip sits in clips. An integer, so that when the open clip
    // leaves a filtered list this naturally points at the clip that took its
    // place -- i.e. the next one to review.
    let lastIndex = -1;
    // Bumped on every load(); a response whose seq is stale (a newer load
    // started) is discarded, so a slow early response cannot overwrite the
    // newer list.
    let loadSeq = 0;
    let toastTimer = null;

    function labelInfo(label) {
        return (label && LABELS[label]) ? LABELS[label] : NO_LABEL;
    }

    function formatSize(bytes) {
        if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB';
        if (bytes >= 1024) return Math.round(bytes / 1024) + ' KB';
        return bytes + ' B';
    }

    function showToast(message, isError) {
        if (!toastEl) return;
        toastEl.textContent = message;
        toastEl.className = 'clip-toast show' + (isError ? ' error' : '');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () { toastEl.className = 'clip-toast'; }, 4000);
    }

    // A <li> so the message stays a valid child of the list.
    function showState(text, isError, actionLabel, action) {
        listEl.replaceChildren();
        const li = document.createElement('li');
        li.className = 'clip-state' + (isError ? ' error' : '');
        li.textContent = text;
        if (actionLabel) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'clip-retry';
            btn.textContent = actionLabel;
            btn.addEventListener('click', action);
            li.appendChild(document.createElement('br'));
            li.appendChild(btn);
        }
        listEl.appendChild(li);
    }

    function updateTabDescription() {
        if (!descEl) return;
        const text = TAB_DESC[kind] || '';
        // The initial markup already carries the event sentence; skip the
        // reassignment when it would not change anything.
        if (descEl.textContent !== text) descEl.textContent = text;
    }

    // Re-seat lastIndex after clips is replaced: follow the open clip by name
    // when it survived. When it is gone the slot may sit one past the end (the
    // open clip was last), so the range is [0, len], not [0, len-1].
    function syncIndex() {
        const i = clips.findIndex(function (c) { return c.name === openName; });
        if (i >= 0) {
            lastIndex = i;
        } else if (clips.length === 0) {
            lastIndex = -1;
        } else if (lastIndex > clips.length) {
            lastIndex = clips.length;
        } else if (lastIndex < 0) {
            lastIndex = 0;
        }
    }

    function render() {
        listEl.replaceChildren();
        countEl.textContent = clips.length + '건';
        if (clips.length === 0) {
            showState(unlabelledOnly
                ? '미분류 클립이 없습니다. 모두 분류되었습니다.'
                : '해당 종류의 녹화 클립이 없습니다.', false);
            return;
        }
        clips.forEach(function (clip) {
            const typeText = KIND_TEXT[clip.kind] || clip.kind;
            const li = document.createElement('li');
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'clip-item';
            btn.dataset.clipName = clip.name;
            btn.setAttribute('aria-label', clip.time_str + ' ' + typeText + ' 클립 재생 및 라벨링');
            btn.addEventListener('click', function () { openClipAt(clip); });

            const time = document.createElement('span');
            time.className = 'clip-time';
            time.textContent = clip.time_str;

            const kindBadge = document.createElement('span');
            kindBadge.className = 'clip-kind-badge clip-kind-' + (clip.kind === 'event' ? 'event' : 'signal');
            kindBadge.textContent = typeText;

            const size = document.createElement('span');
            size.className = 'clip-size';
            size.textContent = formatSize(clip.size_bytes);

            const spacer = document.createElement('span');
            spacer.className = 'clip-spacer';

            const info = labelInfo(clip.label);
            const labelBadge = document.createElement('span');
            labelBadge.className = 'clip-label-badge ' + info.cls;
            labelBadge.textContent = info.text;

            btn.append(time, kindBadge, size, spacer, labelBadge);
            li.appendChild(btn);
            listEl.appendChild(li);
        });
    }

    // Update the list badge in place after a successful POST; no reload.
    function updateBadge(name, label) {
        const info = labelInfo(label);
        const items = listEl.querySelectorAll('.clip-item');
        for (let i = 0; i < items.length; i++) {
            if (items[i].dataset.clipName !== name) continue;
            const badge = items[i].querySelector('.clip-label-badge');
            if (badge) {
                badge.className = 'clip-label-badge ' + info.cls;
                badge.textContent = info.text;
            }
            return;
        }
    }

    function sessionExpired() {
        clips = [];
        countEl.textContent = '—';
        showState(
            '세션이 만료되었습니다. 페이지를 새로고침한 뒤 다시 로그인해 주세요.',
            true,
            '새로고침',
            function () { window.location.reload(); }
        );
    }

    // Reloads the list. When the player is open the clip stays open and its
    // position is re-seated (syncIndex), so refresh / filter changes move by
    // position instead of dropping the player.
    async function load() {
        const seq = ++loadSeq;
        listEl.setAttribute('aria-busy', 'true');
        countEl.textContent = '—';
        showState('클립을 불러오는 중...', false);
        try {
            let url = '/api/clips?kind=' + encodeURIComponent(kind);
            if (unlabelledOnly) url += '&label=unlabelled';
            const res = await fetch(url);
            if (seq !== loadSeq) return;
            if (res.status === 401) {
                sessionExpired();
                return;
            }
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const data = await res.json();
            // A newer load started while this one was in flight: drop it so the
            // checkbox and the list cannot disagree.
            if (seq !== loadSeq) return;
            clips = Array.isArray(data.clips) ? data.clips : [];
            if (openName) syncIndex();
            render();
            updatePager();
        } catch (err) {
            if (seq !== loadSeq) return;
            console.error('clip list request failed:', err);
            clips = [];
            countEl.textContent = '—';
            showState('클립 목록을 불러오지 못했습니다.', true, '다시 시도', function () { load(); });
        } finally {
            if (seq === loadSeq) listEl.setAttribute('aria-busy', 'false');
        }
    }
"""
