"""Clip panel behaviour, part 2: the player, labelling and event wiring.

Spliced after ``clip_panel_js.py`` into one IIFE by ``clip_panel.py``, so these
functions see the list state and helpers declared there. Split out only to stay
under the 300-line file cap.
"""

CLIP_PANEL_JS_PLAYER = """
    function paintLabelState(label) {
        stateEl.textContent = '현재 라벨: ' + labelInfo(label).text;
        const btns = document.querySelectorAll('.label-btn');
        for (let i = 0; i < btns.length; i++) {
            btns[i].setAttribute('aria-pressed', btns[i].dataset.label === label ? 'true' : 'false');
        }
    }

    // Where 이전/다음 would land, or -1 when it would fall off the list.
    // Normally that is the open clip's own position +/- one. When the open clip
    // has left a filtered list, lastIndex is the slot it vacated: the clip now
    // sitting in that slot is the one to review next, and the clip just before
    // the slot is 이전.
    function navTarget(delta) {
        const cur = clips.findIndex(function (c) { return c.name === openName; });
        const from = cur >= 0 ? cur : (delta > 0 ? lastIndex - 1 : lastIndex);
        const target = from + delta;
        return (target >= 0 && target < clips.length) ? target : -1;
    }

    function updatePager() {
        prevBtn.style.display = navTarget(-1) >= 0 ? 'inline-flex' : 'none';
        nextBtn.style.display = navTarget(1) >= 0 ? 'inline-flex' : 'none';
    }

    function openClipAt(clip) {
        if (!clip) return;
        lastIndex = clips.indexOf(clip);
        showClip(clip);
    }

    // Put a clip on screen. lastIndex is the caller's responsibility.
    function showClip(clip) {
        openName = clip.name;
        titleEl.textContent = clip.name;
        timeEl.textContent = clip.time_str;
        videoEl.src = '/api/clips/' + encodeURIComponent(clip.name);
        paintLabelState(clip.label);
        modalEl.classList.add('active');
        updatePager();
        videoEl.focus();
        const played = videoEl.play();
        if (played && played.catch) played.catch(function () {});
    }

    // restoreFocus is an explicit boolean at every call site: true for the
    // close button / Escape, false for a tab switch that replaces the list.
    function closeClipModal(restoreFocus) {
        const name = openName;
        const at = lastIndex;
        modalEl.classList.remove('active');
        videoEl.pause();
        videoEl.removeAttribute('src');
        videoEl.load();
        openName = null;
        lastIndex = -1;
        if (document.fullscreenElement === modalEl) {
            document.exitFullscreen().catch(function () {});
        }
        if (!restoreFocus) return;
        // render() rebuilds every item, so a saved element is already detached;
        // look the item up again by name.
        const items = listEl.querySelectorAll('.clip-item');
        let target = null;
        for (let i = 0; i < items.length; i++) {
            if (items[i].dataset.clipName === name) { target = items[i]; break; }
        }
        // The clip left the filtered list, so fall back to the item that took
        // its slot rather than leaving focus on the hidden video.
        if (!target && at >= 0 && items.length) target = items[Math.min(at, items.length - 1)];
        (target || document.getElementById('clipRefreshBtn')).focus();
    }

    function navigateClip(delta) {
        const next = navTarget(delta);
        if (next < 0) return;
        lastIndex = next;
        showClip(clips[next]);
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
        if (!openName) return;
        const name = openName;
        setLabelBusy(true);
        try {
            const res = await fetch(
                '/api/clips/' + encodeURIComponent(name) + '/label',
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
            const saved = data.label !== undefined ? data.label : label;
            // The player may have moved on while the POST was in flight; only
            // paint the label if the same clip is still on screen.
            if (openName === name) paintLabelState(saved);
            showToast('라벨을 저장했습니다.');
            if (!unlabelledOnly) {
                updateBadge(name, saved);
            } else if (saved) {
                // No longer unlabelled, so drop it by name. lastIndex stays on
                // the vacated slot, which the clip that moved up now occupies,
                // so 다음 opens exactly that next unlabelled clip.
                clips = clips.filter(function (c) { return c.name !== name; });
                render();
                updatePager();
            } else {
                // Clearing a label puts it back; refetch so it lands in order.
                await load();
            }
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
            // A different tab is a different list, so the open clip cannot
            // carry over: close the player and keep focus on the tab, never on
            // the now-hidden video.
            closeClipModal(false);
            tabs[i].focus();
            kind = tabs[i].dataset.kind;
            for (let j = 0; j < tabs.length; j++) {
                tabs[j].setAttribute('aria-pressed', tabs[j] === tabs[i] ? 'true' : 'false');
            }
            updateTabDescription();
            load();
        });
    }
    if (unlabelledEl) {
        unlabelledEl.addEventListener('change', function () {
            unlabelledOnly = unlabelledEl.checked;
            load();
        });
    }
    document.getElementById('clipRefreshBtn').addEventListener('click', function () { load(); });
    document.getElementById('clipCloseBtn').addEventListener('click', function () { closeClipModal(true); });
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
            closeClipModal(true);
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

    updateTabDescription();
    load();
"""
