import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """Tests never call a real model; they run on the rule-based reader."""
    from app import understand
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    understand._remembered.clear()  # each test starts with nothing remembered


def load_scripts():
    scripts = []
    for folder in ("conversations", "adversarial"):
        for path in sorted((ROOT / folder).glob("*.json")):
            scripts.append(json.loads(path.read_text(encoding="utf-8")))
    return scripts
