"""HTML UI templates for Soonsim Detector Web Viewer."""

LOGIN_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="순심이">
    <meta name="theme-color" content="#0b1120">
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='48' fill='%230b1120' stroke='%2322c55e' stroke-width='4'/%3E%3Cpath d='M30 40 Q20 25 35 25 Q45 25 40 40 Z' fill='%23f8fafc'/%3E%3Cpath d='M70 40 Q80 25 65 25 Q55 25 60 40 Z' fill='%23f8fafc'/%3E%3Cellipse cx='50' cy='55' rx='28' ry='22' fill='%23f8fafc'/%3E%3Ccircle cx='40' cy='52' r='4' fill='%230f172a'/%3E%3Ccircle cx='60' cy='52' r='4' fill='%230f172a'/%3E%3Cellipse cx='50' cy='62' rx='6' ry='4' fill='%23f43f5e'/%3E%3Ccircle cx='78' cy='22' r='10' fill='%2322c55e'/%3E%3C/svg%3E">
    <link rel="apple-touch-icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='48' fill='%230b1120' stroke='%2322c55e' stroke-width='4'/%3E%3Cpath d='M30 40 Q20 25 35 25 Q45 25 40 40 Z' fill='%23f8fafc'/%3E%3Cpath d='M70 40 Q80 25 65 25 Q55 25 60 40 Z' fill='%23f8fafc'/%3E%3Cellipse cx='50' cy='55' rx='28' ry='22' fill='%23f8fafc'/%3E%3Ccircle cx='40' cy='52' r='4' fill='%230f172a'/%3E%3Ccircle cx='60' cy='52' r='4' fill='%230f172a'/%3E%3Cellipse cx='50' cy='62' rx='6' ry='4' fill='%23f43f5e'/%3E%3Ccircle cx='78' cy='22' r='10' fill='%2322c55e'/%3E%3C/svg%3E">
    <title>순심이 실시간 감시 - 보안 잠금</title>
    <style>
        :root {
            --bg-color: #0b1120;
            --card-bg: #1e293b;
            --text-color: #f8fafc;
            --accent: #38bdf8;
            --alert: #ef4444;
            --success: #22c55e;
            --border: #334155;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .lock-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 32px 24px;
            width: 100%;
            max-width: 360px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
            text-align: center;
            animation: fadeIn 0.3s ease;
        }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .logo-icon {
            width: 68px;
            height: 68px;
            margin: 0 auto 16px;
            background: #0f172a;
            border: 2px solid #22c55e;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2rem;
            box-shadow: 0 0 16px rgba(34, 197, 94, 0.3);
        }
        .title { font-size: 1.35rem; font-weight: 700; color: #f8fafc; margin-bottom: 6px; }
        .subtitle { font-size: 0.85rem; color: #94a3b8; margin-bottom: 24px; line-height: 1.4; }
        .pin-display {
            background: #0f172a;
            border: 2px solid var(--border);
            border-radius: 12px;
            height: 52px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.6rem;
            letter-spacing: 12px;
            color: var(--accent);
            margin-bottom: 20px;
            font-family: monospace;
            padding: 0 16px;
            transition: all 0.2s ease;
        }
        .pin-display.error {
            border-color: var(--alert);
            color: var(--alert);
            animation: shake 0.4s ease;
        }
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            20%, 60% { transform: translateX(-8px); }
            40%, 80% { transform: translateX(8px); }
        }
        .keypad {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            margin-bottom: 16px;
        }
        .key-btn {
            background: #0f172a;
            border: 1px solid var(--border);
            border-radius: 12px;
            height: 54px;
            font-size: 1.4rem;
            font-weight: 600;
            color: #f8fafc;
            cursor: pointer;
            transition: all 0.1s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            user-select: none;
        }
        .key-btn:active {
            background: #334155;
            transform: scale(0.95);
        }
        .key-btn.action {
            font-size: 0.95rem;
            color: #94a3b8;
        }
        .key-btn.submit {
            background: #059669;
            color: white;
            border-color: #10b981;
        }
        .key-btn.submit:active {
            background: #047857;
        }
        .msg {
            font-size: 0.82rem;
            color: var(--alert);
            min-height: 20px;
        }
    </style>
</head>
<body>
    <div class="lock-card" id="lockCard">
        <div class="logo-icon">🐕</div>
        <h1 class="title">순심이 감시 뷰어</h1>
        <p class="subtitle">보안 잠금 상태입니다.<br>PIN 비밀번호를 입력해주세요.</p>
        
        <div class="pin-display" id="pinDisplay">····</div>
        
        <div class="keypad">
            <button class="key-btn" onclick="pressKey('1')">1</button>
            <button class="key-btn" onclick="pressKey('2')">2</button>
            <button class="key-btn" onclick="pressKey('3')">3</button>
            <button class="key-btn" onclick="pressKey('4')">4</button>
            <button class="key-btn" onclick="pressKey('5')">5</button>
            <button class="key-btn" onclick="pressKey('6')">6</button>
            <button class="key-btn" onclick="pressKey('7')">7</button>
            <button class="key-btn" onclick="pressKey('8')">8</button>
            <button class="key-btn" onclick="pressKey('9')">9</button>
            <button class="key-btn action" onclick="clearPin()">지우기</button>
            <button class="key-btn" onclick="pressKey('0')">0</button>
            <button class="key-btn submit" onclick="submitPin()">확인</button>
        </div>
        <div class="msg" id="msgText"></div>
    </div>

    <script>
        let currentPin = "";

        function updateDisplay() {
            const display = document.getElementById('pinDisplay');
            if (currentPin.length === 0) {
                display.innerText = "····";
                display.style.color = "#475569";
            } else {
                display.innerText = "●".repeat(currentPin.length);
                display.style.color = "#38bdf8";
            }
        }

        function pressKey(num) {
            if (currentPin.length < 10) {
                currentPin += num;
                updateDisplay();
                document.getElementById('msgText').innerText = "";
                document.getElementById('pinDisplay').classList.remove('error');
            }
        }

        function clearPin() {
            currentPin = "";
            updateDisplay();
            document.getElementById('msgText').innerText = "";
            document.getElementById('pinDisplay').classList.remove('error');
        }

        async function submitPin() {
            if (currentPin.length === 0) return;
            try {
                const res = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pin: currentPin })
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    window.location.reload();
                } else {
                    const display = document.getElementById('pinDisplay');
                    display.classList.add('error');
                    document.getElementById('msgText').innerText = data.detail || "비밀번호가 일치하지 않습니다.";
                    currentPin = "";
                    setTimeout(() => {
                        updateDisplay();
                    }, 400);
                }
            } catch (e) {
                document.getElementById('msgText').innerText = "인증 서버 통신 실패";
            }
        }

        // Keyboard support
        window.addEventListener('keydown', (e) => {
            if (e.key >= '0' && e.key <= '9') {
                pressKey(e.key);
            } else if (e.key === 'Backspace') {
                currentPin = currentPin.slice(0, -1);
                updateDisplay();
            } else if (e.key === 'Enter') {
                submitPin();
            } else if (e.key === 'Escape') {
                clearPin();
            }
        });

        updateDisplay();
    </script>
</body>
</html>
"""


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="순심이">
    <meta name="theme-color" content="#0b1120">
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='48' fill='%230b1120' stroke='%2322c55e' stroke-width='4'/%3E%3Cpath d='M30 40 Q20 25 35 25 Q45 25 40 40 Z' fill='%23f8fafc'/%3E%3Cpath d='M70 40 Q80 25 65 25 Q55 25 60 40 Z' fill='%23f8fafc'/%3E%3Cellipse cx='50' cy='55' rx='28' ry='22' fill='%23f8fafc'/%3E%3Ccircle cx='40' cy='52' r='4' fill='%230f172a'/%3E%3Ccircle cx='60' cy='52' r='4' fill='%230f172a'/%3E%3Cellipse cx='50' cy='62' rx='6' ry='4' fill='%23f43f5e'/%3E%3Ccircle cx='78' cy='22' r='10' fill='%2322c55e'/%3E%3C/svg%3E">
    <link rel="apple-touch-icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='48' fill='%230b1120' stroke='%2322c55e' stroke-width='4'/%3E%3Cpath d='M30 40 Q20 25 35 25 Q45 25 40 40 Z' fill='%23f8fafc'/%3E%3Cpath d='M70 40 Q80 25 65 25 Q55 25 60 40 Z' fill='%23f8fafc'/%3E%3Cellipse cx='50' cy='55' rx='28' ry='22' fill='%23f8fafc'/%3E%3Ccircle cx='40' cy='52' r='4' fill='%230f172a'/%3E%3Ccircle cx='60' cy='52' r='4' fill='%230f172a'/%3E%3Cellipse cx='50' cy='62' rx='6' ry='4' fill='%23f43f5e'/%3E%3Ccircle cx='78' cy='22' r='10' fill='%2322c55e'/%3E%3C/svg%3E">
    <title>순심이 실시간 감시 뷰어 (30분 스마트 큐)</title>
    <style>
        :root {
            --bg-color: #0b1120;
            --card-bg: #1e293b;
            --text-color: #f8fafc;
            --accent: #38bdf8;
            --alert: #ef4444;
            --success: #22c55e;
            --warning: #f59e0b;
            --border: #334155;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            padding: 16px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .header {
            width: 100%;
            max-width: 1240px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 14px;
            flex-wrap: wrap;
            gap: 12px;
        }
        .title-group {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        .title { font-size: 1.45rem; font-weight: 700; color: var(--accent); }
        
        /* Header-sized Pulsating Circle and DateTime Text */
        .polling-indicator {
            display: flex;
            align-items: center;
            gap: 12px;
            background: #0f172a;
            border: 2px solid #334155;
            padding: 6px 18px;
            border-radius: 9999px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
        }
        .pulse-dot {
            width: 22px;
            height: 22px;
            border-radius: 50%;
            background: #22c55e;
            box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7);
            animation: pulse-green 1.6s infinite;
            transition: background-color 0.3s ease;
        }
        .pulse-dot.green {
            background: #22c55e;
            animation: pulse-green 1.6s infinite;
        }
        .pulse-dot.yellow {
            background: #eab308;
            animation: pulse-yellow 1.6s infinite;
        }
        .pulse-dot.red {
            background: #ef4444;
            animation: pulse-red 1.6s infinite;
        }
        @keyframes pulse-green {
            0% { transform: scale(0.92); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.8); }
            70% { transform: scale(1.12); box-shadow: 0 0 0 12px rgba(34, 197, 94, 0); }
            100% { transform: scale(0.92); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }
        }
        @keyframes pulse-yellow {
            0% { transform: scale(0.92); box-shadow: 0 0 0 0 rgba(234, 179, 8, 0.8); }
            70% { transform: scale(1.12); box-shadow: 0 0 0 12px rgba(234, 179, 8, 0); }
            100% { transform: scale(0.92); box-shadow: 0 0 0 0 rgba(234, 179, 8, 0); }
        }
        @keyframes pulse-red {
            0% { transform: scale(0.92); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.8); }
            70% { transform: scale(1.12); box-shadow: 0 0 0 12px rgba(239, 68, 68, 0); }
            100% { transform: scale(0.92); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
        }
        .poll-text {
            font-size: 1.15rem;
            font-weight: 700;
            color: #f1f5f9;
            letter-spacing: -0.3px;
        }
        .poll-text span {
            color: #38bdf8;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        }

        .header-controls {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .audio-btn {
            background: #334155;
            color: #94a3b8;
            border: 1px solid var(--border);
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 0.9rem;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.2s ease;
        }
        .audio-btn.active {
            background: #059669;
            color: white;
            border-color: #10b981;
        }
        .main-container {
            width: 100%;
            max-width: 1320px;
            display: grid;
            grid-template-columns: 1.25fr 1fr;
            gap: 20px;
        }
        @media (max-width: 1080px) {
            .main-container { grid-template-columns: 1fr; }
        }
        .card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
        }
        .card-title {
            font-size: 1.05rem;
            margin-bottom: 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .live-wrapper {
            position: relative;
            width: 100%;
            border-radius: 8px;
            overflow: hidden;
            background: #000;
            border: 2px solid var(--border);
            cursor: pointer;
        }
        .live-preview {
            width: 100%;
            aspect-ratio: 16 / 9;
            object-fit: cover;
            display: block;
            transition: transform 0.2s ease;
        }
        .live-wrapper:hover .live-preview {
            transform: scale(1.01);
        }
        .live-theater-overlay-btn {
            position: absolute;
            bottom: 12px;
            right: 12px;
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid rgba(255, 255, 255, 0.25);
            color: #f8fafc;
            padding: 8px 14px;
            border-radius: 8px;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            backdrop-filter: blur(6px);
            transition: all 0.2s ease;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
        }
        .live-wrapper:hover .live-theater-overlay-btn {
            background: rgba(30, 41, 59, 0.95);
            border-color: var(--accent);
            color: var(--accent);
            transform: scale(1.05);
        }
        .status-banner {
            margin-top: 14px;
            padding: 14px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            gap: 14px;
            border: 1px solid var(--border);
            transition: all 0.3s ease;
        }
        .status-banner.no_change {
            background: rgba(30, 41, 59, 0.8);
            border-color: #475569;
        }
        .status-banner.motion {
            background: rgba(245, 158, 11, 0.15);
            border-color: var(--warning);
        }
        .status-banner.dog_on_pad {
            background: rgba(34, 197, 94, 0.2);
            border-color: var(--success);
            animation: padGlow 1.5s infinite alternate;
        }
        @keyframes padGlow {
            0% { box-shadow: 0 0 5px rgba(34, 197, 94, 0.3); }
            100% { box-shadow: 0 0 15px rgba(34, 197, 94, 0.8); }
        }
        .status-icon {
            font-size: 1.8rem;
        }
        .status-text-group { flex: 1; }
        .status-headline { font-size: 1.1rem; font-weight: 700; }
        .status-sub { font-size: 0.85rem; color: #94a3b8; margin-top: 3px; }

        .gallery-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .gallery {
            display: flex;
            flex-direction: column;
            gap: 14px;
            max-height: 640px;
            overflow-y: auto;
            padding-right: 6px;
        }
        .gallery-item {
            display: flex;
            gap: 14px;
            padding: 10px;
            border-radius: 10px;
            background: #0f172a;
            border: 1px solid var(--border);
            cursor: pointer;
            transition: all 0.2s ease;
            position: relative;
        }
        .gallery-item:hover {
            border-color: var(--accent);
            transform: translateX(-3px);
            box-shadow: 0 4px 14px rgba(56, 189, 248, 0.15);
        }
        .gallery-item.DOG_ON_PAD {
            border-color: var(--success);
            background: #064e3b;
        }
        .gallery-item.MOTION_CHANGE {
            border-color: #d97706;
            background: #451a03;
        }
        .gallery-thumb {
            width: 200px;
            height: 112px;
            aspect-ratio: 16 / 9;
            border-radius: 8px;
            object-fit: cover;
            background: #000;
            flex-shrink: 0;
            border: 1px solid rgba(255, 255, 255, 0.08);
            transition: transform 0.2s ease;
        }
        .gallery-item:hover .gallery-thumb {
            transform: scale(1.03);
        }
        .gallery-info {
            flex: 1;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            font-size: 0.9rem;
            padding: 4px 0;
        }
        .time-tag { font-weight: 700; color: var(--accent); font-size: 0.95rem; }
        .obj-tag { color: #94a3b8; margin-top: 4px; font-size: 0.82rem; }
        .badge-tag {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 5px;
            font-weight: 700;
            font-size: 0.75rem;
            width: fit-content;
            margin-top: 6px;
        }
        .badge-dog { background: var(--success); color: #000; }
        .badge-motion { background: var(--warning); color: #000; }
        .badge-baseline { background: #64748b; color: white; }

        /* Netflix-style Cinema / Fullscreen Modal */
        .theater-modal {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(3, 7, 18, 0.98);
            backdrop-filter: blur(16px);
            z-index: 9999;
            display: none;
            flex-direction: column;
            justify-content: space-between;
            align-items: center;
            padding: 16px 20px;
            box-sizing: border-box;
            opacity: 0;
            transition: opacity 0.25s ease;
        }
        .theater-modal.active {
            display: flex;
            opacity: 1;
        }
        .theater-header {
            width: 100%;
            max-width: 100%;
            display: flex;
            justify-content: space-between;
            align-items: center;
            z-index: 10;
            padding: 0 8px;
        }
        .theater-title-group {
            display: flex;
            align-items: center;
            gap: 14px;
            flex-wrap: wrap;
        }
        .theater-live-badge {
            background: #ef4444;
            color: white;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 800;
            letter-spacing: 1px;
            animation: pulse-red 1.6s infinite;
        }
        .theater-live-badge.history {
            background: #0ea5e9;
            animation: none;
        }
        .theater-event-title {
            font-size: 1.25rem;
            font-weight: 700;
            color: #f8fafc;
        }
        .theater-timestamp {
            font-size: 0.95rem;
            color: #94a3b8;
            font-family: monospace;
        }
        .theater-actions {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .theater-btn {
            background: rgba(30, 41, 59, 0.85);
            border: 1px solid rgba(255, 255, 255, 0.2);
            color: #f8fafc;
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 0.92rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            user-select: none;
        }
        .theater-btn:hover {
            background: rgba(51, 65, 85, 0.95);
            border-color: #38bdf8;
            transform: scale(1.03);
        }
        .theater-btn.close-btn {
            background: rgba(239, 68, 68, 0.25);
            border-color: rgba(239, 68, 68, 0.5);
            color: #fca5a5;
            font-size: 1.2rem;
            padding: 6px 14px;
        }
        .theater-btn.close-btn:hover {
            background: #ef4444;
            color: white;
        }
        .theater-viewport {
            flex: 1;
            width: 100%;
            height: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            position: relative;
            margin: 8px 0;
            min-height: 0;
            overflow: hidden;
        }
        .theater-image {
            width: 100%;
            height: 100%;
            max-width: 100%;
            max-height: 100%;
            aspect-ratio: 16 / 9;
            object-fit: contain;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.12);
            box-shadow: 0 25px 60px -10px rgba(0, 0, 0, 0.95);
            background: #000;
        }
        .theater-footer {
            width: 100%;
            max-width: 100%;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(15, 23, 42, 0.9);
            border: 1px solid rgba(255, 255, 255, 0.15);
            padding: 10px 18px;
            border-radius: 10px;
            flex-wrap: wrap;
            gap: 12px;
            z-index: 10;
        }
        .theater-status-box {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .theater-status-icon { font-size: 1.5rem; }
        .theater-status-headline { font-size: 1.05rem; font-weight: 700; color: #f8fafc; }
        .theater-status-sub { font-size: 0.82rem; color: #94a3b8; }
        .theater-footer-controls {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .theater-btn.live-return-btn {
            background: #059669;
            border-color: #10b981;
            color: white;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="title-group">
            <div class="title">순심이 상시 감시 뷰어</div>
            <!-- Traffic-light Pulsating Circle and DateTime Text -->
            <div class="polling-indicator">
                <div class="pulse-dot green" id="pulseDot"></div>
                <div class="poll-text"><span id="pollStatusLabel">감시중</span>: <span id="pollDatetimestamp">대기 중</span></div>
            </div>
        </div>
        <div class="header-controls">
            <button class="audio-btn" id="audioToggle" onclick="toggleAudio()">소리 알림: OFF (클릭하여 켜기)</button>
            <button class="audio-btn" style="background:#1e293b; color:#94a3b8;" onclick="logout()">🔒 잠금</button>
        </div>
    </div>

    <div class="main-container">
        <!-- Live Large View & Status -->
        <div class="card">
            <div class="card-title">
                <span>실시간 프레임 (NOW)</span>
                <span id="liveTimestamp" style="font-size: 0.88rem; color: #94a3b8;">대기 중...</span>
            </div>
            <div class="live-wrapper" onclick="openLiveTheater()" title="클릭하여 전체화면 극장 모드로 보기">
                <img id="liveImage" class="live-preview" src="/api/snapshot/latest" alt="Live Stream Frame">
                <button class="live-theater-overlay-btn" type="button">⛶ 전체 화면</button>
            </div>

            <!-- Real-time Scene Status Banner -->
            <div class="status-banner no_change" id="statusBanner">
                <div class="status-icon" id="statusIcon">🟢</div>
                <div class="status-text-group">
                    <div class="status-headline" id="statusHeadline">현재 변화 없음 (정적 상태)</div>
                    <div class="status-sub" id="statusSub">5초마다 카메라를 능동 감시 중이며, 화면 및 배변판에 유의미한 변화가 없습니다.</div>
                </div>
            </div>
        </div>

        <!-- 30-Minute Significant Event Timeline -->
        <div class="card">
            <div class="gallery-header">
                <span style="font-weight: 600; font-size: 1.05rem;">최근 30분 이벤트 타임라인</span>
                <span id="eventCountBadge" style="font-size: 0.8rem; background: #0ea5e9; color: white; padding: 2px 8px; border-radius: 9999px;">0건</span>
            </div>
            <p style="font-size: 0.78rem; color: #64748b; margin-bottom: 10px;">
                * 썸네일 클릭 시 상세 전체화면 극장 뷰어로 확대됩니다.
            </p>
            <div class="gallery" id="historyGallery">
                <div style="color: #64748b; text-align: center; padding: 30px;">최근 30분 내 감지된 이벤트가 없습니다.</div>
            </div>
        </div>
    </div>

    <!-- Netflix-style Cinema / Fullscreen Modal Component -->
    <div id="theaterModal" class="theater-modal" role="dialog" aria-modal="true">
        <div class="theater-header">
            <div class="theater-title-group">
                <span id="theaterBadge" class="theater-live-badge">LIVE ON-AIR</span>
                <span id="theaterTitle" class="theater-event-title">실시간 라이브 모니터</span>
                <span id="theaterTimestamp" class="theater-timestamp">--:--:--</span>
            </div>
            <div class="theater-actions">
                <button class="theater-btn" onclick="toggleTheaterFullscreen()" title="브라우저 전체화면 전환 (F)">
                    <span id="fsIcon">⛶</span> 전체화면
                </button>
                <button class="theater-btn close-btn" onclick="closeTheater()" title="닫기 (ESC)">✕</button>
            </div>
        </div>

        <div class="theater-viewport">
            <img id="theaterImage" class="theater-image" src="/api/snapshot/latest" alt="Theater Mode View">
        </div>

        <div class="theater-footer">
            <div class="theater-status-box">
                <span id="theaterStatusIcon" class="theater-status-icon">🟢</span>
                <div>
                    <div id="theaterStatusHeadline" class="theater-status-headline">정상 감시 중</div>
                    <div id="theaterStatusSub" class="theater-status-sub">실시간 감시 프레임이 스트리밍되고 있습니다.</div>
                </div>
            </div>
            <div class="theater-footer-controls">
                <button id="theaterPrevBtn" class="theater-btn" onclick="navigateHistory(-1)" style="display:none;">◀ 이전 이벤트</button>
                <button id="theaterNextBtn" class="theater-btn" onclick="navigateHistory(1)" style="display:none;">다음 이벤트 ▶</button>
                <button id="theaterLiveReturnBtn" class="theater-btn live-return-btn" onclick="openLiveTheater()" style="display:none;">🔴 실시간 라이브로 복귀</button>
            </div>
        </div>
    </div>

    <script>
        let audioEnabled = false;
        let audioCtx = null;
        let lastAlertId = 0;
        let currentHistoryList = [];
        let theaterMode = 'live'; // 'live' | 'history'
        let currentHistoryIndex = -1;

        function initAudio() {
            if (!audioCtx) {
                audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            }
            if (audioCtx.state === 'suspended') {
                audioCtx.resume();
            }
        }

        function toggleAudio() {
            initAudio();
            audioEnabled = !audioEnabled;
            const btn = document.getElementById('audioToggle');
            if (audioEnabled) {
                btn.className = 'audio-btn active';
                btn.innerText = '소리 알림: ON (멍멍!)';
                playDogBark();
            } else {
                btn.className = 'audio-btn';
                btn.innerText = '소리 알림: OFF (클릭하여 켜기)';
            }
        }

        function playSingleBark(startTime) {
            if (!audioCtx) return;
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            const filter = audioCtx.createBiquadFilter();

            osc.type = 'sawtooth';
            filter.type = 'bandpass';
            filter.frequency.setValueAtTime(450, startTime);
            filter.Q.setValueAtTime(3.0, startTime);

            osc.frequency.setValueAtTime(350, startTime);
            osc.frequency.exponentialRampToValueAtTime(120, startTime + 0.18);

            gain.gain.setValueAtTime(0.01, startTime);
            gain.gain.linearRampToValueAtTime(0.8, startTime + 0.03);
            gain.gain.exponentialRampToValueAtTime(0.01, startTime + 0.20);

            osc.connect(filter);
            filter.connect(gain);
            gain.connect(audioCtx.destination);

            osc.start(startTime);
            osc.stop(startTime + 0.22);
        }

        function playDogBark() {
            if (!audioEnabled || !audioCtx) return;
            initAudio();
            const now = audioCtx.currentTime;
            playSingleBark(now);
            playSingleBark(now + 0.25);
        }

        function updateTrafficLight(stateMode, labelText, timeStr) {
            const dot = document.getElementById('pulseDot');
            const label = document.getElementById('pollStatusLabel');
            const timeSpan = document.getElementById('pollDatetimestamp');
            if (dot) dot.className = `pulse-dot ${stateMode}`;
            if (label) label.innerText = labelText;
            if (timeSpan && timeStr) timeSpan.innerText = timeStr;
        }

        // Theater Modal Functions
        function openLiveTheater() {
            theaterMode = 'live';
            currentHistoryIndex = -1;
            const modal = document.getElementById('theaterModal');
            const badge = document.getElementById('theaterBadge');
            const title = document.getElementById('theaterTitle');
            const timeTag = document.getElementById('theaterTimestamp');
            const prevBtn = document.getElementById('theaterPrevBtn');
            const nextBtn = document.getElementById('theaterNextBtn');
            const liveReturnBtn = document.getElementById('theaterLiveReturnBtn');

            badge.className = 'theater-live-badge';
            badge.innerText = 'LIVE ON-AIR';
            title.innerText = '순심이 실시간 라이브 극장 모드';
            timeTag.innerText = document.getElementById('pollDatetimestamp')?.innerText || '';

            prevBtn.style.display = 'none';
            nextBtn.style.display = 'none';
            liveReturnBtn.style.display = 'none';

            document.getElementById('theaterImage').src = `/api/snapshot/latest?t=${Date.now()}`;
            modal.classList.add('active');
        }

        function openHistoryTheaterByIndex(idx) {
            if (idx < 0 || idx >= currentHistoryList.length) return;
            theaterMode = 'history';
            currentHistoryIndex = idx;
            const item = currentHistoryList[idx];

            const modal = document.getElementById('theaterModal');
            const badge = document.getElementById('theaterBadge');
            const title = document.getElementById('theaterTitle');
            const timeTag = document.getElementById('theaterTimestamp');
            const icon = document.getElementById('theaterStatusIcon');
            const headline = document.getElementById('theaterStatusHeadline');
            const sub = document.getElementById('theaterStatusSub');
            const prevBtn = document.getElementById('theaterPrevBtn');
            const nextBtn = document.getElementById('theaterNextBtn');
            const liveReturnBtn = document.getElementById('theaterLiveReturnBtn');

            badge.className = 'theater-live-badge history';
            badge.innerText = 'RECORDED EVENT';
            
            let eventName = '감지 이벤트 스냅샷';
            if (item.event_type === 'DOG_ON_PAD') {
                eventName = '🐕 순심이 배변판 감지 스냅샷';
                icon.innerText = '🐕';
            } else if (item.event_type === 'ANIMAL_DETECTED') {
                eventName = '🐾 동물 감지 스냅샷';
                icon.innerText = '🐾';
            } else if (item.event_type === 'MOTION_CHANGE') {
                eventName = `⚠️ 움직임 감지 스냅샷 (${item.change_score.toFixed(1)})`;
                icon.innerText = '⚠️';
            } else {
                icon.innerText = '📷';
            }

            title.innerText = eventName;
            timeTag.innerText = item.timestamp_str;
            headline.innerText = `${item.timestamp_str} 기록`;
            const objs = item.detected_objects.length > 0 ? item.detected_objects.join(', ') : '화면 움직임';
            sub.innerText = `감지 객체: ${objs} | 점수: ${item.change_score.toFixed(1)} | (${idx + 1} / ${currentHistoryList.length})`;

            prevBtn.style.display = idx > 0 ? 'inline-flex' : 'none';
            nextBtn.style.display = idx < currentHistoryList.length - 1 ? 'inline-flex' : 'none';
            liveReturnBtn.style.display = 'inline-flex';

            document.getElementById('theaterImage').src = `/api/snapshot/${item.id}`;
            modal.classList.add('active');
        }

        function navigateHistory(delta) {
            if (theaterMode !== 'history') return;
            openHistoryTheaterByIndex(currentHistoryIndex + delta);
        }

        function closeTheater() {
            const modal = document.getElementById('theaterModal');
            modal.classList.remove('active');
            if (document.fullscreenElement) {
                document.exitFullscreen().catch(() => {});
            }
        }

        function toggleTheaterFullscreen() {
            const modal = document.getElementById('theaterModal');
            if (!document.fullscreenElement) {
                modal.requestFullscreen().catch(() => {});
            } else {
                document.exitFullscreen().catch(() => {});
            }
        }

        async function fetchLiveStatus() {
            try {
                const res = await fetch('/api/live');
                if (!res.ok) {
                    updateTrafficLight('red', '오류', '응답 실패');
                    const banner = document.getElementById('statusBanner');
                    if (banner) banner.className = 'status-banner error';
                    return;
                }
                const live = await res.json();

                const nowSec = Date.now() / 1000;
                const lagSec = live.last_poll_epoch > 0 ? (nowSec - live.last_poll_epoch) : 999;

                if (live.status_type === 'idle' || live.last_poll_epoch === 0) {
                    updateTrafficLight('yellow', '대기중', live.last_poll_str);
                } else if (lagSec > 25.0) {
                    updateTrafficLight('red', '정지됨', `${live.last_poll_str} (지연)`);
                } else if (lagSec > 10.0) {
                    updateTrafficLight('yellow', '지연중', live.last_poll_str);
                } else {
                    updateTrafficLight('green', '감시중', live.last_poll_str);
                }

                document.getElementById('liveTimestamp').innerText = `최근 확인: ${live.last_poll_str}`;
                const liveImgUrl = `/api/snapshot/latest?t=${Date.now()}`;
                document.getElementById('liveImage').src = liveImgUrl;

                if (theaterMode === 'live' && document.getElementById('theaterModal').classList.contains('active')) {
                    document.getElementById('theaterImage').src = liveImgUrl;
                    document.getElementById('theaterTimestamp').innerText = live.last_poll_str;
                    document.getElementById('theaterStatusHeadline').innerText = live.status_title;
                    document.getElementById('theaterStatusSub').innerText = live.status_desc;
                    const theaterIcon = document.getElementById('theaterStatusIcon');
                    if (live.status_type === 'dog_on_pad') theaterIcon.innerText = '🐕';
                    else if (live.status_type === 'motion') theaterIcon.innerText = '⚠️';
                    else theaterIcon.innerText = '🟢';
                }

                const banner = document.getElementById('statusBanner');
                const icon = document.getElementById('statusIcon');
                const headline = document.getElementById('statusHeadline');
                const sub = document.getElementById('statusSub');

                banner.className = `status-banner ${live.status_type}`;
                headline.innerText = live.status_title;
                sub.innerText = live.status_desc;

                if (live.status_type === 'dog_on_pad') {
                    icon.innerText = '🐕';
                    if (live.last_poll_epoch !== lastAlertId) {
                        lastAlertId = live.last_poll_epoch;
                        playDogBark();
                    }
                } else if (live.status_type === 'motion') {
                    icon.innerText = '⚠️';
                } else if (lagSec > 25.0) {
                    icon.innerText = '🔴';
                } else if (live.status_type === 'idle' || lagSec > 10.0) {
                    icon.innerText = '🟡';
                } else {
                    icon.innerText = '🟢';
                }

                document.getElementById('eventCountBadge').innerText = `${live.total_events_30m}건`;

                const histRes = await fetch('/api/history');
                const history = await histRes.json();
                currentHistoryList = [...history].reverse(); // newest first

                const gallery = document.getElementById('historyGallery');
                if (currentHistoryList.length === 0) {
                    gallery.innerHTML = '<div style="color: #64748b; text-align: center; padding: 30px;">최근 30분 내 감지된 이벤트가 없습니다. (정적 상태 유지 중)</div>';
                } else {
                    gallery.innerHTML = '';
                    currentHistoryList.forEach((item, idx) => {
                        const div = document.createElement('div');
                        div.className = `gallery-item ${item.event_type}`;
                        div.title = '클릭하여 전체화면 극장 모드로 보기';
                        div.onclick = () => {
                            openHistoryTheaterByIndex(idx);
                        };

                        let badgeClass = 'badge-baseline';
                        let badgeText = '기준점';
                        if (item.event_type === 'DOG_ON_PAD') {
                            badgeClass = 'badge-dog';
                            badgeText = '순심이 배변판';
                        } else if (item.event_type === 'ANIMAL_DETECTED') {
                            badgeClass = 'badge-dog';
                            badgeText = '동물 감지';
                        } else if (item.event_type === 'MOTION_CHANGE') {
                            badgeClass = 'badge-motion';
                            badgeText = `움직임 (${item.change_score.toFixed(1)})`;
                        }

                        const objs = item.detected_objects.length > 0 ? item.detected_objects.join(', ') : '화면 변화';

                        div.innerHTML = `
                            <img class="gallery-thumb" src="/api/snapshot/${item.id}" alt="thumb">
                            <div class="gallery-info">
                                <div class="time-tag">${item.timestamp_str.split(' ')[1]}</div>
                                <div class="obj-tag">${objs}</div>
                                <div class="badge-tag ${badgeClass}">${badgeText}</div>
                            </div>
                        `;
                        gallery.appendChild(div);
                    });
                }
            } catch (err) {
                console.error("Error fetching live status:", err);
                updateTrafficLight('red', '연결 끊김', '통신 오류');
                const banner = document.getElementById('statusBanner');
                if (banner) banner.className = 'status-banner error';
                const headline = document.getElementById('statusHeadline');
                if (headline) headline.innerText = '서버 연결 끊김';
                const sub = document.getElementById('statusSub');
                if (sub) sub.innerText = '모니터 서버와 통신할 수 없습니다. 재연결을 시도합니다.';
                const icon = document.getElementById('statusIcon');
                if (icon) icon.innerText = '🔴';
            }
        }

        async function logout() {
            try {
                await fetch('/api/auth/logout', { method: 'POST' });
                window.location.reload();
            } catch (e) {
                window.location.reload();
            }
        }

        // Global Keyboard Shortcuts
        window.addEventListener('keydown', (e) => {
            const modal = document.getElementById('theaterModal');
            const isTheaterOpen = modal.classList.contains('active');
            if (e.key === 'Escape') {
                if (isTheaterOpen) closeTheater();
            } else if (e.key === 'f' || e.key === 'F') {
                if (isTheaterOpen) {
                    toggleTheaterFullscreen();
                } else {
                    openLiveTheater();
                }
            } else if (isTheaterOpen && (e.key === 'ArrowLeft' || e.key === 'ArrowUp')) {
                navigateHistory(-1);
            } else if (isTheaterOpen && (e.key === 'ArrowRight' || e.key === 'ArrowDown')) {
                navigateHistory(1);
            }
        });

        setInterval(fetchLiveStatus, 2500);
        fetchLiveStatus();
    </script>
</body>
</html>
"""

