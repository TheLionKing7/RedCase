"""Resolve the exact explabs catalog slug for gpt-5.6-luna from apps/api/.env key."""
import os
import urllib.request
from pathlib import Path

KEY = None
for line in Path("apps/api/.env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line.startswith("EXPLABS_API_KEY="):
        KEY = line[len("EXPLABS_API_KEY="):].strip()

req = urllib.request.Request(
    "https://api.experientiallabs.ai/v1/models",
    headers={"Authorization": f"Bearer {KEY}", "Accept": "application/json"},
)
import json
d = json.loads(urllib.request.urlopen(req, timeout=60).read())
hits = [m["id"] for m in d["data"] if "luna" in m["id"].lower()]
print("LUNA_SLUGS=", hits)
