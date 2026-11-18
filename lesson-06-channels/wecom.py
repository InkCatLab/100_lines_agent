"""wecom.py —— 第 6 课：WeCom 渠道（长轮询，不需要公网 IP）"""

import json
import ssl
import time
import uuid
import certifi
import websocket

class WeCom:


    def __init__(self, bot_id, secret, timeout=30) -> None:
        self.bot_id = bot_id
        self.secret = secret
        self.timeout = timeout
        self.ws = None
        self.pending = []
        self.req_id = None
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.load_verify_locations(cafile=certifi.where())
    
    def connect(self):
        # 第一步：建立websocket连接
        self.ws = websocket.create_connection(
            "wss://openws.work.weixin.qq.com",
            timeout=self.timeout,
            sslopt={"context": self.ssl_context},
        )
        # 第二步：在同一连接上发送订阅消息
        req_id = uuid.uuid4().hex
        payload = {
            "cmd": "aibot_subscribe",
            "headers": {
                "req_id": req_id
            },
            "body": {
                "bot_id": self.bot_id,
                "secret": self.secret
            }
        }
        self.ws.send(json.dumps(payload))
        
        # 查看服务端回执
        response = json.loads(self.ws.recv())
        if response.get("errcode") != 0:
            raise RuntimeError(f"订阅失败：{response}")
        return response

    def fetch(self, timeout=None):
        try:
            message = json.loads(self.ws.recv())
        except websocket.WebSocketTimeoutException:
            raise
        out = []
        if message.get("cmd") == "aibot_msg_callback":
            body = message["body"]
            headers = message["headers"]
            self.req_id = headers["req_id"]
            if body.get("chattype") == "single" and body.get("msgtype") == "text":
                chat_id = body["aibotid"]
                user_id = body["from"]["userid"]
                content = body["text"]["content"]
                out.append((chat_id, user_id, content))
        return out

    def poll(self, timeout=None):
        """如果有积压的消息，先消费；消费完再拉取新的"""
        if not self.ws:
            self.connect()
            
        if self.pending:
            out, self.pending = self.pending, []
            return out
        return self.fetch(timeout)
    
    def close(self):
        if self.ws is not None:
            self.ws.close()
            self.ws = None

    def send(self, chat_id = None, text = "（空回复）"):
        payload = {
            "cmd": "aibot_respond_msg",
            "headers": {
                "req_id": self.req_id
            },
            "body": {
                "msgtype": "markdown",
                "markdown": {
                    "content": text,
                    "feedback": {
                        "id": "FEEDBACKID"
                    }
                }
            }
        }
        self.ws.send(json.dumps(payload))
    
    @property
    def name(self):
        return "wecom"

if __name__ == "__main__":
    bot = WeCom(
        bot_id="aibvW9IDXH-2U_y6dzcd7MKx0_e_nEE8GZL",
        secret="B9BCcXkXaYAo9HBbkLYgjN78PBYKflIsvTtwgyXdzMT",
    )

    try:
        response = bot.connect()
        print("订阅回执：", response)
        while True:
            try:
                batch = bot.poll()
            except Exception as e:
                print(f"[轮询出错] {e}， 5s后重试")
                time.sleep(5)
                continue
            for chat_id, user_id, text in batch:
                bot.send(chat_id, text)
    finally:
        bot.close()
