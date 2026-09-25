from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_luna_battery


def test_luna_battery_launcher_uses_gpt6_without_changing_provider_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "EXPLABS_API_KEY=test-key\nDATABASE_URL=postgresql://test\nJINA_API_KEY=test-jina\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(run_luna_battery, "ENV", env_file)
    monkeypatch.setenv("ANSWER_MODEL_PRIMARY", "explabs")
    monkeypatch.setenv("ANSWER_MODEL_FALLBACK", "groq")
    captured: dict[str, object] = {}

    def fake_run(cmd, *, cwd, env, text):
        captured.update(cmd=cmd, cwd=cwd, env=env, text=text)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(run_luna_battery.subprocess, "run", fake_run)
    monkeypatch.setattr(run_luna_battery, "ROOT", tmp_path)

    with pytest.raises(SystemExit) as exit_info:
        run_luna_battery.main()

    assert exit_info.value.code == 0
    command = captured["cmd"]
    assert isinstance(command, list)
    assert "--provider" not in command
    assert Path(command[command.index("--out") + 1]) == (
        tmp_path / "apps/api/calibration_results/battery_explabs_gpt6_luna.json"
    )
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["EXPLABS_MODEL"] == "gpt-6-luna"
    assert env["ANSWER_MODEL_PRIMARY"] == "explabs"
    assert env["ANSWER_MODEL_FALLBACK"] == "groq"
