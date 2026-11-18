import os
import openai
from openai import OpenAI, APIStatusError
from tools import get_schemas, execute
import json
from permissions import PermissionManager
from context import compact, clear_old_tool_results, truncate_tool_result, load_session, save_session
from skills import project_notes, skill_section


BASE_SYSTEM = (
    "你是一个能操作本地文件和命令行的编程助手。"
    "需要时调用工具，完成任务后直接用文字总结，不要再调用工具。"
)
MAX_STEPS = 20
MODEL_NAME = "deepseek-flash"

HARD_LIMIT = 15000
SOFT_LIMIT = 10000


def build_system_prompt():
    return BASE_SYSTEM + project_notes() + skill_section()

def create_client():
    try:
        client = OpenAI(
            base_url=os.getenv("BASE_URL", "https://api.deepseek.com"),
            api_key=os.getenv("API_KEY")
        )
    except openai.OpenAIError as e:
        if str(e).startswith("Missing credentials. Please pass an `api_key`"):
            raise ValueError("缺少API_KEY, 请设置api_key的值。")
    return client


class Session:
    """一个会话 = 一份messages + 一个权限管理器 + 上一次的token数"""
    
    def __init__(self, name, ask=None, persist=True):
        self.name = name
        self.persist = persist
        saved = load_session(name) if persist else None
        self.messages = saved or [{"role": "system", "content": ""}]
        self.messages[0] = {"role": "system", "content": build_system_prompt()}
        self.perms = PermissionManager(ask=ask)
        self.prompt_tokens = 0
    
    def save(self):
        if self.persist:
            save_session(self.name, self.messages)
        
        

def run(session, client, user_input: str, model_name: str=MODEL_NAME, log=print) -> str:
    messages = session.messages
    messages.append({"role": "user", "content": user_input})
    for step in range(1, MAX_STEPS + 1):
        try:
            if session.prompt_tokens > HARD_LIMIT:
                log(f"[正在压缩上下文，当前prompt_tokens={session.prompt_tokens}]")
                messages[:] = compact(client, model_name, messages)
            elif session.prompt_tokens > SOFT_LIMIT:
                log(f"[正在清理旧的工具结果，当前prompt_tokens={session.prompt_tokens}]")
                messages = clear_old_tool_results(messages)
            
            resp = client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=get_schemas()
            )
        except APIStatusError as e:
            log("请求地址：", e.response.request.url)
            log("状态码：", e.status_code)
            log("响应内容：", e.response.text)
            raise
        prompt_tokens = resp.usage.prompt_tokens if resp.usage else 0
        session.prompt_tokens = prompt_tokens
        log(f"[消耗tokens数 prompt_tokens={prompt_tokens}]")
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        
        # 模型没有调用工具 = 它认为任务已经做完了，即本次task结束
        if not msg.tool_calls:
            return f"\n[完成，共{step}步]\n {msg.content}"
         
        # 模型调用tool，需要把tool_result喂回去
        for call in msg.tool_calls:
            result = handle_call(call, session.perms)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": truncate_tool_result(result)})
    
    return f"\n[达到{MAX_STEPS}步上限，已停止]"

def handle_call(call, perms: PermissionManager):
    name = call.function.name
    try:
        args = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError:
        return "Error: 参数不是合法的JSON"
    except Exception as e:  # 错误信息fallback给模型修正
       return f"工具执行出错：{type(e).__name__}:{e}"
    decision = perms.check(name, args)
    if not decision.allowed:
        return f"[权限拒绝] {decision.reason}"
    else:
        print(f"🔧 {name}({call.function.arguments[:80]})")
        result = execute(name, args)
    print(f"[工具调用结果]:\n{result}")
    return result

if __name__ == "__main__":
    client = create_client()
    session_name = "会话1"
    session = Session(name=session_name,)
    while True:
        q = input("你:>").strip()
        if q in ("exit", "quit"):
            break
        print("\n" + "AI Bot:>" + run(session, client, q, MODEL_NAME) + "\n")
        session.save()
         
