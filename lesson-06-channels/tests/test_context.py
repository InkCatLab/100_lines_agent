
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).parent.parent))
from context import truncate_tool_result, load_session
import pytest

text = "x" * 10000
out = truncate_tool_result(text)
assert len(out) < 4200
assert "省略" in out
assert truncate_tool_result("short") == "short"

import json

messages = load_session("default")

def check_pairing(messages):
    """每条 tool 消息，前面必须有声明了该 tool_call_id 的 assistant 消息"""
    declared = set()
    for m in messages:
        if m["role"] == "assistant":
            for c in m.get("tool_calls") or []:
                declared.add(c["id"])
        if m["role"] == "tool":
            assert m["tool_call_id"] in declared, f"孤立的 tool 消息: {m['tool_call_id']}"