"""updater.py — Comprueba y aplica actualizaciones desde GitHub."""

import os
import sys
import json
import time
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CACHE_FILE = BASE_DIR / ".update_cache"
UPDATE_INTERVAL = 86400  # 24h entre comprobaciones

def _load_cache():
    try:
        if CACHE_FILE.is_file():
            return int(CACHE_FILE.read_text().strip())
    except:
        pass
    return 0

def _save_cache():
    try:
        CACHE_FILE.write_text(str(int(time.time())))
    except:
        pass

def _latest_remote_commit(repo, branch):
    """Obtiene el SHA del último commit via API HTTP de GitHub (rápido)."""
    url = f"https://api.github.com/repos/{repo}/commits/{branch}"
    req = urllib.request.Request(url, headers={"User-Agent": "TelBot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
            return data.get("sha", "")
    except:
        return ""

def _git(*args, timeout=10):
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=BASE_DIR, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except:
        return ""

def main():
    repo = os.getenv("GITHUB_REPO", "")
    branch = os.getenv("GITHUB_BRANCH", "master")

    try:
        import config
        if hasattr(config, "GITHUB_REPO") and config.GITHUB_REPO:
            repo = config.GITHUB_REPO
        if hasattr(config, "GITHUB_BRANCH") and config.GITHUB_BRANCH:
            branch = config.GITHUB_BRANCH
    except ImportError:
        pass

    if not repo:
        return True

    # Saltar si ya comprobamos hace menos de 24h
    if time.time() - _load_cache() < UPDATE_INTERVAL:
        return True

    local = _git("rev-parse", "HEAD")
    if not local:
        return True

    # Detectar rama activa
    detected = _git("rev-parse", "--abbrev-ref", "HEAD")
    if detected:
        branch = detected

    # Comprobación vía API HTTP (mucho más rápida que git ls-remote)
    remote = _latest_remote_commit(repo, branch)
    if not remote:
        return True  # sin conexión o error, lo intentamos en 24h

    if remote == local:
        _save_cache()
        return True

    # Hay cambios — hacer fetch + pull
    import urllib.parse
    owner, repo_name = repo.split("/")

    print(f"[updater] Nueva versión disponible. Descargando...")

    r = subprocess.run(["git", "fetch", "origin"], capture_output=True, text=True, cwd=BASE_DIR, timeout=60)
    if r.returncode != 0:
        print(f"[updater] Error al descargar: {r.stderr.strip()}")
        return False

    has_changes = bool(_git("status", "--porcelain"))
    stashed = False
    if has_changes:
        r = subprocess.run(["git", "stash"], capture_output=True, text=True, cwd=BASE_DIR)
        stashed = r.returncode == 0

    r = subprocess.run(["git", "pull", "--ff-only"], capture_output=True, text=True, cwd=BASE_DIR, timeout=60)
    if r.returncode != 0:
        print(f"[updater] Error al actualizar: {r.stderr.strip()}")
        return False

    print("[updater] ¡Actualizado!")

    if stashed:
        subprocess.run(["git", "stash", "pop"], capture_output=True, text=True, cwd=BASE_DIR)

    _save_cache()
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
