"""Helpers for launching a scorecard run on a Cursor Cloud Agent."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE lines into os.environ (does not override existing)."""
    env_path = path or (_REPO_ROOT / ".env")
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def default_repo_url() -> str:
    env = os.environ.get("SCORECARD_REPO_URL", "").strip()
    if env:
        return env
    try:
        url = (
            subprocess.check_output(
                ["git", "config", "--get", "remote.origin.url"],
                cwd=_REPO_ROOT,
                text=True,
            )
            .strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    if url.startswith("git@github.com:"):
        return "https://github.com/" + url.removeprefix("git@github.com:")
    if "github.com" in url and "@github.com/" in url:
        # https://x-access-token:TOKEN@github.com/org/repo
        return "https://github.com/" + url.split("@github.com/", 1)[1]
    return url


def cloud_env_vars_for_scorecard() -> dict[str, str]:
    """Env vars forwarded to the cloud VM (secrets + GCS sync)."""
    out: dict[str, str] = {}
    for key in (
        "CURSOR_API_KEY",
        "CURSOR_SCORECARD_MODEL",
        "CURSOR_SCORECARD_WORKERS",
        "GCS_BUCKET",
        "GCS_CREDENTIALS_JSON",
    ):
        val = os.environ.get(key, "").strip()
        if val:
            out[key] = val
    return out


def build_orchestrator_prompt(
    ticker: str,
    *,
    prompt_version: str,
    model: str,
    categories: str,
    fresh: bool,
    workers: int,
    stagger: float,
) -> str:
    cmd = (
        f"python3 run_scorecard_cursor.py {ticker.upper()} "
        f"--prompt-version {prompt_version} --model {model} "
        f"--workers {workers} --stagger {stagger}"
    )
    if fresh:
        cmd += " --fresh"
    if categories.lower() not in ("all", "todas", "*"):
        cmd += f' --categories "{categories}"'

    gcs_note = (
        "GCS_BUCKET and GCS_CREDENTIALS_JSON are set — the script will download "
        "scorecard.db before the run and upload after each answer."
        if os.environ.get("GCS_BUCKET")
        else "GCS is not configured — scorecard.db will only exist in this VM unless you copy it manually."
    )

    return f"""You are in a Cursor Cloud Agent VM with this repository checked out.

Goal: run the Value Investing scorecard for ticker **{ticker.upper()}** using the existing CLI (one Cursor research agent per question).

Follow these steps in order:
1. Change directory to the repository root (where `run_scorecard_cursor.py` lives).
2. Run: `pip install -r requirements.txt`
3. Confirm `CURSOR_API_KEY` is present in the environment (never print or log its value).
4. {gcs_note}
5. Run this exact command and wait until it finishes (may take a long time):
   `{cmd}`
6. Reply with a short report:
   - Final `run_id` printed by the script
   - Whether the run is **complete** or **partial**
   - **Total score** if complete
   - Any errors worth noting

Rules:
- Do not open a pull request.
- Do not edit application code unless the script fails due to a clear, fixable bug in this repo.
- Do not substitute a different workflow (no manual Q&A); use the CLI above.
"""
