"""Where the game client and the generated data live.

By default the tools folder sits inside the game client folder and the output goes to <client>\\tghm_data.
Override with the environment variables TGHM_GAME / TGHM_DATA, or with tools\\config.local.json:
    {"game": "D:\\\\Games\\\\TGHM Online", "data": "E:\\\\TGHM_Data"}
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CFG_FILE = _HERE / "config.local.json"
_cfg = json.loads(_CFG_FILE.read_text(encoding="utf-8")) if _CFG_FILE.exists() else {}

GAME = Path(os.environ.get("TGHM_GAME") or _cfg.get("game") or _HERE.parent)  # the game client folder
DATA = Path(os.environ.get("TGHM_DATA") or _cfg.get("data") or GAME / "tghm_data")  # extracted / generated data
ELEMENT = GAME / "element"
REF = DATA / "_tools_ref"  # reference captures and scratch output of the tools in _ref
