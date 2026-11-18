"""telegram.py —— 第 6 课：Telegram 渠道（长轮询，不需要公网 IP）"""

import json
import urllib.request
import ssl
import certifi

MAX_LEN = 4000  # Telegram单条上限4096，留点余量

class Telegram:
    def __init__(self, token, timeout=30):
        # https://help.aliyun.com/zh/chatapp/use-cases/how-to-create-telegram-bots
        # https://core.telegram.org/bots/api#making-requests-when-getting-updates
        self.base_url = f"https://api.telegram.org/bot{token}/"
        self.timeout = timeout
        self.offset = 0
        self.pending = []
        # 保留系统/环境配置的 CA，并补充 Python 安装中可能缺失的公共 CA。
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.load_verify_locations(cafile=certifi.where())

    def _call(self, method, **params):
        req = urllib.request.Request(
            url=self.base_url + method, 
            data=json.dumps(params).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=self.timeout + 10, context=self.ssl_context) as r:
            body = json.loads(r.read())
        if not body.get("ok"):
            raise RuntimeError(f"Telegram API错误：{body}")
        return body["result"]
    
    def fetch(self, timeout=None):
        updates = self._call(
            "getUpdates",
            offset=self.offset,
            timeout=self.timeout if timeout is None else timeout
        )
        out = []
        for u in updates:
            self.offset = u["update_id"] + 1
            m = u.get("message")
            if m and "text" in m and m["chat"]["type"] == "private":
                out.append((m["chat"]["id"], m["from"]["id"], m["text"]))
        return out
    
    def poll(self, timeout=None):
        """如果有积压的消息，先消费；消费完再拉取新的"""
        if self.pending:
            out, self.pending = self.pending, []
            return out
        return self.fetch(timeout)
    
    def send(self, chat_id, text):
        text = text or "（空回复）"
        for i in range(0, len(text), MAX_LEN):
            self._call(
                "sendMessage",
                chat_id=chat_id,
                text=text[i:i+MAX_LEN]
            )
    
    @property
    def name(self):
        return "telegram"

