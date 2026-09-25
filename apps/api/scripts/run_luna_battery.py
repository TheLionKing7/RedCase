"""Run/resume the 50-question gpt-6-luna battery on the configured chain.

Loads required credentials from apps/api/.env and pins EXPLABS_MODEL to
gpt-6-luna for this battery run only. The configured provider/fallback chain
remains intact; the historical gpt-5.6-luna results are kept in a separate file.
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
    env["EXPLABS_MODEL"] = "gpt-6-luna"
    env.setdefault("ANSWER_MODEL_FALLBACK", "groq")
    out = ROOT / "apps" / "api" / "calibration_results" / "battery_explabs_gpt6_luna.json"

    cmd = [
        sys.executable, "-m", "scripts.run_battery",
        "--out", str(out),
        "--pace", "30",
    ]
    print(f"[luna-battery] model override: gpt-6-luna")
    print(f"[luna-battery] output: {out}")

    proc = subprocess.run(cmd, cwd=str(ROOT / "apps" / "api"), env=env, text=True)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
