"""updater.py — Comprueba y aplica actualizaciones desde GitHub."""

import os
import sys
import subprocess
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CACHE_FILE = BASE_DIR / ".update_cache"
UPDATE_INTERVAL = 86400  # segundos entre comprobaciones (24 horas)

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

def _run(cmd, timeout=10):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, cwd=BASE_DIR, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None

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

    # Saltar si ya comprobamos hace menos de UPDATE_INTERVAL
    last_check = _load_cache()
    if time.time() - last_check < UPDATE_INTERVAL:
        return True

    if _run(["git", "--version"]) is None:
        return True

    r = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if r and r.returncode == 0 and r.stdout.strip():
        branch = r.stdout.strip()

    # Comprobación ligera con ls-remote (solo trae las cabezas, sin objetos)
    r = _run(["git", "ls-remote", "origin", branch], timeout=8)
    if r is None or r.returncode != 0:
        return True

    remote_commit = r.stdout.strip().split()[0] if r.stdout.strip() else ""

    r = _run(["git", "rev-parse", "HEAD"])
    local_commit = r.stdout.strip() if r and r.returncode == 0 else ""

    if not remote_commit or not local_commit or remote_commit == local_commit:
        _save_cache()
        return True

    # Hay cambios — hacer fetch + pull
    print(f"[updater] Actualización disponible en {repo}. Descargando...")

    r = _run(["git", "fetch", "origin"], timeout=30)
    if r is None or r.returncode != 0:
        print("[updater] Error al descargar. Se reintentará en el próximo arranque.")
        return False

    r = _run(["git", "status", "--porcelain"])
    has_changes = r and bool(r.stdout.strip())
    stashed = False
    if has_changes:
        r = _run(["git", "stash"])
        stashed = r is not None and r.returncode == 0

    r = _run(["git", "pull", "--ff-only"], timeout=30)
    if r is None or r.returncode != 0:
        print(f"[updater] Error al actualizar:\n{r.stderr.strip() if r else 'timeout'}")
        return False

    print("[updater] ¡Actualizado!")

    if stashed:
        _run(["git", "stash", "pop"])

    _save_cache()
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
