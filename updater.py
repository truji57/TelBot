"""updater.py — Comprueba y aplica actualizaciones desde GitHub."""

import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def main():
    repo = os.getenv("GITHUB_REPO", "")
    branch = os.getenv("GITHUB_BRANCH", "main")

    try:
        import config
        if hasattr(config, "GITHUB_REPO") and config.GITHUB_REPO:
            repo = config.GITHUB_REPO
        if hasattr(config, "GITHUB_BRANCH") and config.GITHUB_BRANCH:
            branch = config.GITHUB_BRANCH
    except ImportError:
        pass

    if not repo:
        print("[updater] GITHUB_REPO no configurado en .env. Saltando.")
        return True

    print(f"[updater] Buscando actualizaciones en {repo} (rama: {branch})...")

    try:
        r = subprocess.run(["git", "--version"], capture_output=True, text=True)
        if r.returncode != 0:
            print("[updater] Git no instalado. Saltando.")
            return True
    except FileNotFoundError:
        print("[updater] Git no encontrado. Saltando.")
        return True

    r = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, cwd=BASE_DIR
    )
    if r.returncode != 0:
        print("[updater] No es un repositorio git. Haz 'git clone' primero.")
        return True

    r = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True, text=True, cwd=BASE_DIR
    )
    if r.returncode != 0:
        print("[updater] No hay remote 'origin'. Si clonaste el repo, comprueba.")
        return True

    r = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, cwd=BASE_DIR
    )
    if r.returncode == 0 and r.stdout.strip():
        branch = r.stdout.strip()
        print(f"[updater] Rama detectada: {branch}")

    print("[updater] Conectando con GitHub...")
    r = subprocess.run(
        ["git", "fetch", "origin"],
        capture_output=True, text=True, cwd=BASE_DIR
    )
    if r.returncode != 0:
        print(f"[updater] Error al conectar con GitHub:\n{r.stderr.strip()}")
        return False

    r = subprocess.run(
        ["git", "rev-list", "--count", f"HEAD..origin/{branch}"],
        capture_output=True, text=True, cwd=BASE_DIR
    )
    if r.returncode != 0:
        print(f"[updater] No se pudo verificar la rama '{branch}'.")
        return True

    behind = int(r.stdout.strip())
    if behind == 0:
        print("[updater] Ya tienes la última versión.")
        return True

    print(f"[updater] {behind} actualización(es) disponible(s). Descargando...")

    r = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=BASE_DIR
    )
    has_changes = bool(r.stdout.strip())
    stashed = False
    if has_changes:
        print("[updater] Guardando cambios locales temporalmente...")
        r = subprocess.run(
            ["git", "stash"],
            capture_output=True, text=True, cwd=BASE_DIR
        )
        stashed = r.returncode == 0

    r = subprocess.run(
        ["git", "pull", "--ff-only"],
        capture_output=True, text=True, cwd=BASE_DIR
    )
    if r.returncode != 0:
        print(f"[updater] Error al actualizar:\n{r.stderr.strip()}")
        print("[updater] Puede que tengas cambios locales en conflicto.")
        return False

    print(f"[updater] ¡Actualizado! Se descargaron {behind} cambio(s).")

    if stashed:
        print("[updater] Restaurando cambios locales...")
        subprocess.run(["git", "stash", "pop"], capture_output=True, cwd=BASE_DIR)

    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
