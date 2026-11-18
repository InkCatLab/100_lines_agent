"""bot.py 常驻的agent"""

import os
import sys
import time 

from agent import Session, run, create_client
from context import SESSION_DIR
from permissions import REMEMBERABLE, render_call
from telegram import Telegram
from wecom import WeCom


ALLOWED = {
    int(x) for x in os.environ.get("TG_ALLOWED_USERS", "").split(",") if x.strip()
}
CONFIRM_WAIT = 120


def make_chat_ask(channel, chat_id, wait=CONFIRM_WAIT):
    def ask(name, args):
        opts = "y 允许/ n 拒绝 "
        if name in REMEMBERABLE:
            opts += "/ a 本会话一直允许"
        
        channel.send(chat_id, f"⚠️ Agent 想执行：{name}\n"
                              f"🔧 命令: {render_call(name, args)}\n\n"
                              f"回复 {opts}\n（拒绝可附原因，如：n 先列出出来给我看看）\n{wait} 秒内不回复视为拒绝。")
        deadline = time.time() + wait
        while time.time() < deadline:
            left = max(1, int(deadline - time.time()))
            for c, u, text in channel.fetch(timeout=min(20, left)):
                ans, _, note = text.strip().partition(" ")
                if c == chat_id and ans.lower() in ("y", "n", "a"):
                    return ans.lower(), note.strip()
                channel.pending.append((c, u, text))
        return "n", "确认超时"
    return ask

def handle_message(channel, client, sessions, chat_id, user_id, text):
    if channel.name == "telegram":
        if user_id not in ALLOWED:
            print(f"[忽略] 非白名单用户 {user_id}")
            return
        
        if text.strip() == "/reset":
            sessions.pop(chat_id, None)
            (SESSION_DIR / f"{channel.name}-{chat_id}.json").unlink(missing_ok=True)
            channel.send(chat_id, "会话已重置。")
            return
    
    s = sessions.get(chat_id)
    if s is None:
        s = sessions[chat_id] = Session(f"{channel.name}-{chat_id}", ask=make_chat_ask(channel, chat_id))
    backup = list(s.messages)
    try:
        reply = run(s, client, text)
    except Exception as e:
        s.messages[:] = backup
        reply = f"[出错，本轮已撤销] {type(e).__name__}: {e}"
    s.save()
    channel.send(chat_id, reply)
    print(f"[AI BOT]: <- 回复了 {reply!r} \n")
    
        


def main():
    channel_name = "tg"
    if channel_name == "tg" and not ALLOWED:
        sys.exit("必须设置 TG_ALLOWED_USERS（逗号分隔的 Telegram 用户 ID），否则任何人都能操作你的电脑。")
    if channel_name == "tg":
        channel = Telegram(os.environ["TG_BOT_TOKEN"])
    elif channel_name == "wecom":
        channel = WeCom(
                bot_id=os.environ.get("BOT_ID"),
                secret=os.environ.get("secret"),
            )
    else:
        raise ValueError(f"不支持的channel：{channel_name}")
    client = create_client()
    sessions = {}
    print("moli-agent 已启动")
    while True:
        try:
            batch = channel.poll()
        except Exception as e:
            print(f"[轮询出错] {e}， 正在等待用户消息，5s后重试")
            time.sleep(5)
            continue
        for chat_id, user_id, text in batch:
            print(f"[用户{user_id}]: -> 发送了 {text!r} ")
            handle_message(channel, client, sessions, chat_id, user_id, text)


if __name__ == "__main__":
    main()