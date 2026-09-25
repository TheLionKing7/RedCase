"""Task 2: screen gpt-5.6-luna for the RedCase ANSWER role.

Loads EXPLABS_API_KEY from apps/api/.env, then runs explabs_answer_probe.py
against gpt-5.6-luna ONLY. Diagnoses luna's fuzzy model slug from the catalog
and prints the T1-T4 screening verdict.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # repo root
ENV = ROOT / "apps" / "api" / ".env"


def _load_explabs_key() -> str:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("EXPLABS_API_KEY="):
            return line[len("EXPLABS_API_KEY="):].strip()
    raise SystemExit("EXPLABS_API_KEY not found in apps/api/.env")


def main() -> None:
    os.environ["EXPLABS_API_KEY"] = _load_explabs_key()
    # Run the probe against gpt-5.6-luna only. The probe reads sys.argv[1:].
    import sys
    sys.argv = ["explabs_answer_probe.py", "gpt-5.6-luna"]

    probe = ROOT / "docs" / "explabs_answer_probe.py"
    exec(compile(probe.read_text(encoding="utf-8"), str(probe), "exec"),
         {"__name__": "__main__", "__file__": str(probe), "__builtins__": __builtins__,
          "sys": sys, "os": os, "json": __import__("json"), "re": __import__("re"),
          "time": __import__("time"), "urllib": __import__("urllib")})


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
