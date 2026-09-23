"""Behaviour for the clip review panel (see clip_panel.py for the markup).

Kept in its own module because the viewer serves plain strings and the panel's
markup and script together blow past the 300-line file cap. Wrapped in an IIFE
so nothing leaks into the viewer's global scope.
"""

CLIP_PANEL_JS = """
(function () {
    const KIND_TEXT = { signal: '신호', event: '이벤트' };
    const LABELS = {
        real: { text: '진짜 배변', cls: 'clip-label-real' },
        false: { text: '오탐', cls: 'clip-label-false' },
        unsure: { text: '판단 보류', cls: 'clip-label-unsure' },
    };
    const NO_LABEL = { text: '미분류', cls: 'clip-label-none' };

    const listEl = document.getElementById('clipList');
    const countEl = document.getElementById('clipCountBadge');
    const modalEl = document.getElementById('clipModal');
    const videoEl = document.getElementById('clipVideo');
    const titleEl = document.getElementById('clipModalTitle');
    const timeEl = document.getElementById('clipModalTime');
    const stateEl = document.getElementById('clipLabelState');
    const toastEl = document.getElementById('clipToast');
    const prevBtn = document.getElementById('clipPrevBtn');
    const nextBtn = document.getElementById('clipNextBtn');

    let kind = 'signal';
    let clips = [];
    let openIndex = -1;
    let lastTrigger = null;
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

    function render() {
        listEl.replaceChildren();
        countEl.textContent = clips.length + '건';
        if (clips.length === 0) {
            showState('해당 종류의 녹화 클립이 없습니다.', false);
            return;
        }
        clips.forEach(function (clip, idx) {
            const typeText = KIND_TEXT[clip.kind] || clip.kind;
            const li = document.createElement('li');
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'clip-item';
            btn.dataset.clipName = clip.name;
            btn.setAttribute('aria-label', clip.time_str + ' ' + typeText + ' 클립 재생 및 라벨링');
            btn.addEventListener('click', function () { openClip(idx, btn); });

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

    async function load() {
        listEl.setAttribute('aria-busy', 'true');
        countEl.textContent = '—';
        showState('클립을 불러오는 중...', false);
        try {
            const res = await fetch('/api/clips?kind=' + encodeURIComponent(kind));
            if (res.status === 401) {
                sessionExpired();
                return;
            }
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const data = await res.json();
            clips = Array.isArray(data.clips) ? data.clips : [];
            render();
        } catch (err) {
            console.error('clip list request failed:', err);
            clips = [];
            countEl.textContent = '—';
            showState('클립 목록을 불러오지 못했습니다.', true, '다시 시도', load);
        } finally {
            listEl.setAttribute('aria-busy', 'false');
        }
    }

    function paintLabelState(label) {
        stateEl.textContent = '현재 라벨: ' + labelInfo(label).text;
        const btns = document.querySelectorAll('.label-btn');
        for (let i = 0; i < btns.length; i++) {
            btns[i].setAttribute('aria-pressed', btns[i].dataset.label === label ? 'true' : 'false');
        }
    }

    function openClip(idx, trigger) {
        if (idx < 0 || idx >= clips.length) return;
        const clip = clips[idx];
        openIndex = idx;
        if (trigger) lastTrigger = trigger;

        titleEl.textContent = clip.name;
        timeEl.textContent = clip.time_str;
        videoEl.src = '/api/clips/' + encodeURIComponent(clip.name);
        paintLabelState(clip.label);

        prevBtn.style.display = idx > 0 ? 'inline-flex' : 'none';
        nextBtn.style.display = idx < clips.length - 1 ? 'inline-flex' : 'none';

        modalEl.classList.add('active');
        videoEl.focus();
        const played = videoEl.play();
        if (played && played.catch) played.catch(function () {});
    }

    function closeClipModal() {
        modalEl.classList.remove('active');
        videoEl.pause();
        videoEl.removeAttribute('src');
        videoEl.load();
        openIndex = -1;
        if (document.fullscreenElement === modalEl) {
            document.exitFullscreen().catch(function () {});
        }
        // Return focus to the list item that opened the player.
        if (lastTrigger && document.contains(lastTrigger)) lastTrigger.focus();
        lastTrigger = null;
    }

    function navigateClip(delta) {
        if (openIndex < 0) return;
        openClip(openIndex + delta, lastTrigger);
    }

    function toggleClipFullscreen() {
        if (!document.fullscreenElement) {
            modalEl.requestFullscreen().catch(function () {});
        } else {
            document.exitFullscreen().catch(function () {});
        }
    }

    function setLabelBusy(busy) {
        const btns = document.querySelectorAll('.label-btn');
        for (let i = 0; i < btns.length; i++) btns[i].disabled = busy;
    }

    async function setClipLabel(label) {
        if (openIndex < 0) return;
        const clip = clips[openIndex];
        setLabelBusy(true);
        try {
            const res = await fetch(
                '/api/clips/' + encodeURIComponent(clip.name) + '/label',
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ label: label }),
                }
            );
            if (res.status === 401) {
                showToast('세션이 만료되었습니다. 페이지를 새로고침한 뒤 다시 로그인해 주세요.', true);
                return;
            }
            if (!res.ok) {
                showToast('라벨을 저장하지 못했습니다.', true);
                return;
            }
            const data = await res.json();
            clip.label = data.label !== undefined ? data.label : label;
            paintLabelState(clip.label);
            updateBadge(clip.name, clip.label);
            showToast('라벨을 저장했습니다.');
        } catch (err) {
            console.error('label request failed:', err);
            showToast('서버와 통신할 수 없습니다.', true);
        } finally {
            setLabelBusy(false);
        }
    }

    const tabs = document.querySelectorAll('.clip-tab[data-kind]');
    for (let i = 0; i < tabs.length; i++) {
        tabs[i].addEventListener('click', function () {
            kind = tabs[i].dataset.kind;
            for (let j = 0; j < tabs.length; j++) {
                tabs[j].setAttribute('aria-pressed', tabs[j] === tabs[i] ? 'true' : 'false');
            }
            load();
        });
    }
    document.getElementById('clipRefreshBtn').addEventListener('click', load);
    document.getElementById('clipCloseBtn').addEventListener('click', closeClipModal);
    prevBtn.addEventListener('click', function () { navigateClip(-1); });
    nextBtn.addEventListener('click', function () { navigateClip(1); });
    document.getElementById('clipClearBtn').addEventListener('click', function () { setClipLabel(null); });
    const labelBtns = document.querySelectorAll('.label-btn[data-label]');
    for (let i = 0; i < labelBtns.length; i++) {
        labelBtns[i].addEventListener('click', function () { setClipLabel(labelBtns[i].dataset.label); });
    }

    // Capture phase so the viewer's global shortcuts (F opens the live theater,
    // arrows walk snapshots) never fire while a clip is open.
    window.addEventListener('keydown', function (e) {
        if (!modalEl.classList.contains('active')) return;
        if (e.key === 'Escape') {
            closeClipModal();
        } else if (e.key === 'f' || e.key === 'F') {
            toggleClipFullscreen();
        } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
            navigateClip(-1);
        } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
            navigateClip(1);
        } else {
            return;
        }
        e.preventDefault();
        e.stopPropagation();
    }, true);

    load();
})();
"""
