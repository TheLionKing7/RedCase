"""Task 2 follow-up: run full 50-question battery against claude-opus-5.5 via explabs.
Loads EXPLABS_API_KEY + DATABASE_URL from apps/api/.env, overrides the explabs
model to claude-opus-5.5 via env var (serving .env untouched), and spawns the
battery runner with --provider explabs --pace 30. Resumes through 429s until
all 50 record.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ENV = ROOT / "apps" / "api" / ".env"


def _load_env(name: str) -> str:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(name + "="):
            return line[len(name) + 1:].strip()
    raise SystemExit(f"{name} not found in {ENV}")


def main() -> None:
    needed = ["EXPLABS_API_KEY", "DATABASE_URL", "JINA_API_KEY"]
    env = dict(os.environ)
    for k in needed:
        env[k] = _load_env(k)
    env["EXPLABS_MODEL"] = "claude-opus-5.5"
    env["ANSWER_TEMPERATURE"] = "1.0"
    out = ROOT / "apps" / "api" / "calibration_results" / "battery_explabs_opus.json"

    cmd = [
        sys.executable, "-m", "scripts.run_battery",
        "--provider", "explabs",
        "--out", str(out),
        "--pace", "30",
    ]
    print(f"[opus-battery] model override: claude-opus-5.5")
    print(f"[opus-battery] output: {out}")

    proc = subprocess.run(cmd, cwd=str(ROOT / "apps" / "api"), env=env, text=True)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
