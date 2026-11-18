from datetime import datetime, timedelta
import pytest
import scheduler
from permissions import PermissionManager


def test_next_run():
    t = datetime(2026, 10, 28, 10, 0)
    assert scheduler.next_run("every 30m", t) == t + timedelta(minutes=30)
    assert scheduler.next_run("daily 09:00", t) == datetime(2026, 10, 29, 9, 0)   # 今天已过，排到明天
    assert scheduler.next_run("daily 11:30", t) == datetime(2026, 10, 28, 11, 30)
    for bad in ("every 1m", "daily 25:00", "每天九点"):
        with pytest.raises(ValueError):
            scheduler.next_run(bad, t)


def test_no_catch_up_and_preauth(tmp_path):
    now = [datetime(2026, 11, 18, 17, 0)]
    s = scheduler.Scheduler(tmp_path / "t.json", now=lambda: now[0])
    task = s.add("every 1h", "看看", chat_id=1, allow={"fetch_url"})
    with pytest.raises(ValueError):
        s.add("every 1h", "x", 1, allow={"run_shell"})     # run_shell 不能预授权
    now[0] = datetime(2026, 11, 18, 22, 5)                  # 停机 5 小时
    assert len(s.due()) == 1                                # 只到期一次，不是五次
    s.mark_started(task)
    assert s.due() == [] and task["next_run"] == "2026-11-18T23:05:00"


def test_task_cannot_schedule_tasks_or_shell():
    pm = PermissionManager(ask=scheduler.make_task_ask({"allow": ["fetch_url"]}))
    assert pm.check("fetch_url", {"url": "https://x"}).allowed          # 预授权过
    assert not pm.check("run_shell", {"command": "ls"}).allowed         # 没有人能确认
    assert not pm.check("schedule_task", {"spec": "every 5m", "prompt": "x"}).allowed
    assert pm.check("read_file", {"path": "a.txt"}).allowed             # SAFE 照常放行