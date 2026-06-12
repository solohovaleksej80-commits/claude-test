"""One-command launcher for local testing (DEMO).

Starts everything needed to open the Mini App inside Telegram from localhost:
  1. backend (FastAPI on :8000, also serves the Mini App at /app/)
  2. a cloudflared quick tunnel -> grabs the public https URL automatically
  3. the Telegram bot, with WEBAPP_URL set to that tunnel URL (no copy-paste)

Usage:
    python run_all.py

Ctrl+C stops everything. Requires BOT_TOKEN in .env.
"""

import os
import platform
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
IS_WIN = platform.system() == "Windows"
CF_BIN = ROOT / ("cloudflared.exe" if IS_WIN else "cloudflared")

CF_URLS = {
    ("Windows", "AMD64"): "cloudflared-windows-amd64.exe",
    ("Windows", "x86"): "cloudflared-windows-386.exe",
    ("Linux", "x86_64"): "cloudflared-linux-amd64",
    ("Linux", "aarch64"): "cloudflared-linux-arm64",
    ("Darwin", "x86_64"): "cloudflared-darwin-amd64.tgz",
    ("Darwin", "arm64"): "cloudflared-darwin-amd64.tgz",
}

procs = []


def log(msg):
    print(f"\n[run_all] {msg}\n", flush=True)


def ensure_cloudflared():
    if CF_BIN.exists():
        return
    key = (platform.system(), platform.machine())
    asset = CF_URLS.get(key)
    if not asset:
        # sensible fallbacks
        asset = "cloudflared-windows-amd64.exe" if IS_WIN else "cloudflared-linux-amd64"
    url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/{asset}"
    log(f"Скачиваю cloudflared: {url}")
    urllib.request.urlretrieve(url, CF_BIN)
    if not IS_WIN:
        os.chmod(CF_BIN, 0o755)
    log("cloudflared загружен.")


def backend_up():
    try:
        with urllib.request.urlopen("http://localhost:8000/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def start_backend():
    if backend_up():
        log("Бэкенд уже запущен на :8000 — переиспользую.")
        return
    log("Запускаю бэкенд (uvicorn :8000)…")
    p = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--port", "8000"],
        cwd=str(ROOT),
    )
    procs.append(p)
    for _ in range(30):
        if backend_up():
            log("Бэкенд готов.")
            return
        time.sleep(1)
    log("Бэкенд не поднялся за 30с — проверьте вывод выше.")


def start_tunnel():
    log("Запускаю туннель cloudflared…")
    p = subprocess.Popen(
        [str(CF_BIN), "tunnel", "--url", "http://localhost:8000"],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    procs.append(p)

    url_pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
    found = {"url": None}

    def reader():
        for line in p.stdout:
            if found["url"] is None:
                m = url_pattern.search(line)
                if m:
                    found["url"] = m.group(0)
            # keep draining so the pipe never blocks cloudflared
        # stream ended

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    for _ in range(40):
        if found["url"]:
            log(f"Туннель готов: {found['url']}")
            return found["url"]
        time.sleep(0.5)
    log("Не удалось получить адрес туннеля за 20с.")
    return None


def set_webapp_url(url):
    webapp = url.rstrip("/") + "/app/"
    lines = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    out, replaced = [], False
    for ln in lines:
        if ln.startswith("WEBAPP_URL="):
            out.append(f"WEBAPP_URL={webapp}")
            replaced = True
        else:
            out.append(ln)
    if not replaced:
        out.append(f"WEBAPP_URL={webapp}")
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    log(f"WEBAPP_URL = {webapp}  (записан в .env)")
    return webapp


def start_bot(webapp_url):
    log("Запускаю Telegram-бот…")
    env = os.environ.copy()
    if webapp_url:
        env["WEBAPP_URL"] = webapp_url  # env wins over .env in pydantic-settings
    p = subprocess.Popen(
        [sys.executable, "-m", "bot.bot"],
        cwd=str(ROOT),
        env=env,
    )
    procs.append(p)
    return p


def shutdown(*_):
    log("Останавливаю всё…")
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    time.sleep(1)
    for p in procs:
        try:
            if p.poll() is None:
                p.kill()
        except Exception:
            pass
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, shutdown)
    if not ENV_FILE.exists():
        log("Нет .env — создайте его и впишите BOT_TOKEN. См. .env.example.")
        sys.exit(1)

    ensure_cloudflared()
    start_backend()
    url = start_tunnel()
    webapp = set_webapp_url(url) if url else None
    bot = start_bot(webapp)

    log("Всё запущено. Откройте бота в Telegram и отправьте /start.")
    log("Остановить — Ctrl+C в этом окне.")

    # Wait on the bot; if it exits, tear everything down.
    try:
        bot.wait()
    except KeyboardInterrupt:
        pass
    shutdown()


if __name__ == "__main__":
    main()
