import os
from openai import OpenAI, APIStatusError
from tools import get_schemas, execute
import json
import sys


os.environ["BASE_URL"] = "https://api.deepseek.com"
os.environ["API_KEY"] = "sk-4759653faffa48629183433df1def26d"

client = OpenAI(
    base_url=os.getenv("BASE_URL"),
    api_key=os.getenv("API_KEY")
)


SYSTEM = (
    "你是一个能操作本地文件和命令行的编程助手。"
    "需要时调用工具，完成任务后直接用文字总结，不要再调用工具。"
)
MAX_STEPS = 20
MODEL_NAME = "deepseek-flash"


def run(user_input: str, messages: list) -> None:
    messages.append({"role": "user", "content": user_input})
    for step in range(1, MAX_STEPS + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=get_schemas()
            )
        except APIStatusError as e:
            print("请求地址：", e.response.request.url)
            print("状态码：", e.status_code)
            print("响应内容：", e.response.text)
            raise
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        
        # 模型没有调用工具 = 它认为任务已经做完了，即本次task结束
        if not msg.tool_calls:
            return f"\n[完成，共{step}步]\n {msg.content}"
         
        # 模型调用tool，需要把tool_result喂回去
        for call in msg.tool_calls:
            name = call.function.name
            print(f"\n[第{step}步]\n {name}({call.function.arguments[:80]})") 
            try:
                args = json.loads(call.function.arguments)
            except json.JSONDecodeError:
                result = "Error: 参数不是合法的JSON"
            except Exception as e:  # 错误信息fallback给模型修正
                result = f"工具执行出错：{type(e).__name__}:{e}"
            else:
                print(f"🔧 {name}({call.function.arguments[:80]})")
                result = execute(name, args)
            print(f"\n[工具调用结果: {result}]")
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    
    return "\n[达到{MAX_STEPS}步上限，已停止]"


if __name__ == "__main__":
    messages = [{
        "role": "system",
        "content": SYSTEM
    }]
    while True:
        q = input("你:>").strip()
        if q in ("exit", "quit"):
            break
        print("\n" + "AI Bot:>" + run(q, messages) + "\n")
         