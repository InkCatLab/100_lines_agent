"""scheduler.py --- 第7课：定时任务与心跳"""
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import uuid

from context import STATE_DIR
from tools import tool

TASK_FILE = STATE_DIR / "task.json"
MIN_INTERVAL = timedelta(minutes=5)
MAX_TASKS = 20
PRE_AUTHORIZABLE = {"fetch_url", "write_file"}  # run_shell 不预授权
HEARTBEAT_OK = "HEARTBEAT_OK"

CURRENT = {"chat_id": None}  # 当前正在对话的聊天


HEARTBEAT_PROMPT = (
    f"这是一次例行检查。按下面的要求检查；如果没有任何需要告诉用户的内容，"
    f"只回复 {HEARTBEAT_OK}，不要回复其他任何文字。\n要求："
)

def get_unique_id():
    return uuid.uuid4().hex

def next_run(spec, after):
    """两种写法：every 30m / every 2h / daily 09:00"""
    spec = spec.strip().lower()
    m = re.fullmatch(r"every\s+(\d+)\s*([mh])", spec)
    if m:
        n = int(m[1])
        delta = timedelta(minutes=n) if m[2] == "m" else timedelta(hours=n)
        if delta < MIN_INTERVAL:
            raise ValueError(f"时间间隔不能小于 {MIN_INTERVAL}")
        return after + delta
    m = re.fullmatch(r"daily\s+(\d{1,2}):(\d{2})", spec)
    if m:
        h, mi = int(m[1]), int(m[2])
        if h > 23 or mi > 59:
            raise ValueError(f"时间格式不合法 {h}:{mi}")
        t = after.replace(hour=h, minute=mi, second=0, microsecond=0)
        return t if t > after else t + timedelta(days=1)
    raise ValueError(f"不支持的时间规则： {spec!r}, 支持every 30m / every 2h / daily 09:00")


class Scheduler:
    
    def __init__(self, path=TASK_FILE, now=datetime.now):
        self.path = Path(path)
        self.now = now
        self.tasks = json.loads(self.path.read_text("utf-8")) if self.path.exists() else[]
    
    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.tasks, ensure_ascii=False, indent=2))
        tmp.replace(self.path)  # 原子替换，写一半崩溃也不会留下坏文件
    
    def add(self, spec, prompt, chat_id, allow=(), kind="task"):
        if len(self.tasks) >= MAX_TASKS:
            raise ValueError(f"最多 {MAX_TASKS} 个任务。")
        bad = set(allow) - PRE_AUTHORIZABLE
        if bad:
            raise ValueError(f"这些工具无法预授权： {', '.join(sorted(bad))}")
        task = {
            "id" : get_unique_id(),
            "spec": spec,
            "prompt": prompt,
            "chat_id": chat_id,
            "allow": sorted(allow),
            "kind": kind,
            "next_run": next_run(spec, self.now()).isoformat(timespec="seconds")
        }
        self.tasks.append(task)
        self._save()
        return task
    
    def remove(self, task_id, chat_id=None):
        before = len(self.tasks)
        self.tasks = [
            t
            for t in self.tasks
            if not (t["id"] == task_id and t["chat_id"] is None or t["chat_id"] == chat_id)
        ]
        return len(self.tasks) < before

    def due(self):
        """筛选到期的任务，预定任务"""
        now = self.now()
        return [t for t in self.tasks if datetime.fromisoformat(t["next_run"]) < now]
    
    def mark_started(self, task):
        # 过期任务从现在开始，计算下一次时间，停机期间不补跑
        task["next_run"] = next_run(task["spec"], self.now()).isoformat(timespec="seconds")
        self._save()

SCHED = None

def get_scheduler():
    global SCHED
    if SCHED is None:
        SCHED = Scheduler()
    return SCHED

def make_task_ask(task):
    """无人值守，只放行预授权允许的工具"""
    allowed = set(task.get("allow", []))
    
    def ask(name, args):
        if name not in allowed:
            return "y", ""
        return "n", "这是无人值守的定时任务，该操作没有被预授权"
    return ask

            
def task_input(task):
    head = f"[定时任务 {task['id']}, 无人值守，需要确认的操作会被拒绝]\n"
    if task["kind"] == "heartbeat":
        return head + HEARTBEAT_PROMPT + task["prompt"]
    return head + task["prompt"]

def format_tasks(tasks):
    if not tasks:
        return "当前没有定时任务"
    return "\n".join([
        f"{t['id']}  {t['spec']}  下次 {t['next_run']}  "
        f"{'[心跳] ' if t['kind'] == 'heartbeat' else ''}{t['prompt'][:40]}"
        + (f"  预授权：{','.join(t['allow'])}" if t["allow"] else "")
        for t in tasks
        
   ])
@tool(
    name="schedule_task", 
    description=(
        "创建一个定时任务，到时间后 Agent 会在无人值守的情况下执行 prompt，并把结果发给用户。"
        "spec 写法：every 30m / every 2h / daily 09:00。"
        "kind=heartbeat 表示例行检查，没有需要汇报的内容时不打扰用户。"
        "allow 是逗号分隔的预授权工具，只能从 fetch_url、write_file 中选，可以为空。"
     ), 
    paramters={
        "type": "object", 
        "properties": {
            "spec": {"type": "string"}, 
            "prompt": {"type": "string"},
            "kind": {"type": "string", "enum": ["task", "heartbeat"]},
            "allow": {"type": "string"}
        }, 
        "required": ["spec", "prompt"]
})
def schedule_task(spec, prompt, kind="task", allow=""):
    if CURRENT["chat_id"] is None:
        return "Error: 只能在消息渠道里创建定时任务"
    allow_set = {a.strip() for a in allow.split(",") if a.strip()}
    try:
        t = get_scheduler().add(spec, prompt, CURRENT["chat_id"], allow_set, kind)
    except ValueError as e:
        return f"Error: {e}"
    return f"已创建任务 {t['id']}, 下次执行：{t['next_run']}"


@tool(
    name="list_tasks",
    description="列出当亲啊聊天的所有定时任务",
    paramters={
        "type": "object",
        "properties": {}
    }
)
def list_tasks():
    return format_tasks([t for t in get_scheduler().tasks if t["chat_id"] == CURRENT["chat_id"]])


@tool(
    name="cancel_task",
    description="取消一个定时任务",
    paramters={
        "type": "object",
        "properties": {
            "task_id": {"type": "string"}
        },
        "required": ["task_id"]
    }
)
def cancel_task(task_id):
    ok = get_scheduler().remove(task_id, CURRENT["chat_id"])
    return f"已取消 {task_id}" if ok else f"Error：没有找到任务 {task_id}"