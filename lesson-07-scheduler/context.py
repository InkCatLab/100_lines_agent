# context.py 

import json
import os
from pathlib import Path



MAX_TOOL_CHARS = 4000  # 单个工具结果最多保留的字符数
KEEP_RECENT_TOOL_RESULTS = 3   # 保留最近的几条工具结果
KEEP_LAST_TURNS = 2  # 压缩时保留用户最近的几轮对话（哲学：贪心）

PLACEHOLDER = "[旧工具结果已清理，如需要请重新调用工具]"

KEEP_PREFIXES = ("[skill]",)

SUMMARY_PROMPT = """你是对话摘要器。把下面这段 Agent 的历史对话压缩成摘要，要求：
1. 保留：用户的目标、已完成的步骤、关键结论、重要的文件路径和参数、尚未解决的问题
2. 丢弃：寒暄、重复内容、工具返回的大段原文
3. 用简洁的条目写，不要超过 500 字
只输出摘要本身。"""


# agent运行时状态
STATE_DIR = Path(os.environ.get("MOLI_STATE_DIR", Path.home() / ".moli-agent"))
SESSION_DIR = STATE_DIR / "sessions"


# 工具结果截断
def truncate_tool_result(text, limit=MAX_TOOL_CHARS):
    if len(text) <= limit:
        return text
    mid = limit // 2
    return f"{text[:mid]}\n...[中间省略{len(text) - limit}字]...\n{text[-mid:]}"


# 注意：不能直接删除工具结果，llm会要求每个tool_call_id必须都有对应的tool消息，删掉会直接报错。
def clear_old_tool_results(messages, keep=KEEP_RECENT_TOOL_RESULTS):
    tool_idxs = [i for i, m in enumerate(messages) if m["role"] == "tool" and not m["content"].startswith(KEEP_PREFIXES)]
    old = tool_idxs[:-keep] if keep > 0 else tool_idxs
    for i in old:
        messages[i]["content"] = PLACEHOLDER
    return messages


# 摘要压缩，不能随便从中间切消息，tool_calls要和tool消息对应，稳妥做法是在user消息前开始切，user是一轮消息的开头
def split_for_compact(messages, keep_turns=KEEP_LAST_TURNS):
    user_idxs = [i for i, m in enumerate(messages) if m["role"] == "user"]
    if len(user_idxs) < keep_turns:
        return None
    cut = user_idxs[-keep_turns]
    if cut <= 1:
        return None
    return messages[1:cut], messages[cut:]


# 摘要总结
def render_for_summary(msgs):
    lines = []
    for m in msgs:
        if m["role"] == "assistant" and m.get("tool_calls"):
            calls = ", ".join(
                f'{c["function"]["name"]}{c["function"]["arguments"]}'
                for c in m["tool_calls"]
            )
            if m.get("content"):
                lines.append(f'[assistant] {m["content"]}')
            lines.append(f"[assistant 调用工具] {calls}")
        else:
            lines.append(f'{m["role"]} {m.get("content") or ""}')
    
    return "\n".join(lines)

# 压缩
def compact(client, model, messages):
    parts = split_for_compact(messages)
    if parts is None:
        return messages
    old, recent = parts
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": render_for_summary(old)},
        ]
    )
    summary = resp.choices[0].message.content
    return [
        messages[0],
        {"role": "user", "content": f"[以下是此前对话的摘要]\n{summary}"},
        {"role": "assistant", "content": "好的，我已了解之前的进展，继续。"},
        *recent
    ]


# 会话持久化
def save_session(name, messages):
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    save_path = SESSION_DIR / f"{name}.json"
    save_path.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")


def load_session(name):
    load_path = SESSION_DIR / f"{name}.json"
    if not load_path.exists():
        return None
    return json.loads(load_path.read_text(encoding="utf-8"))
