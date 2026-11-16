from datetime import datetime
from pathlib import Path
import subprocess

import urllib


DECORATOR_README = """
# 1. 计算装饰器表达式，得到 decorator 函数
_decorator = tool(
    name="hello",
    description="打招呼",
    parameters={},
)

# 2. 创建 hello 的函数对象，此时不会执行函数体
_function = ...  # Python 根据编译好的函数体创建函数对象

# 3. 将函数对象作为参数，调用装饰器
_result = _decorator(_function)

# 4. 把返回值绑定到 hello 这个名称
hello = _result
"""

TOOLS = {}
MAX_OUTPUT = 4000

def tool(name, description, paramters):
    
    def decorator(func):
        TOOLS[name] = {
            "schema": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": paramters
                }
            },
            "func": func
        }
        return func
    
    return decorator

def get_schemas():
    return [t["schema"] for t in TOOLS.values()]

def _params(**props):
    return {
        "type": "object",
        "properties": {k: {"type": "string", "description": v} for k, v in props.items()},
        "required": list(props)
    }

@tool(name="list_dir", description="列出某个目录下的文件和子目录。", paramters=_params(directory="目录路径，当前目录写 ."))
def list_dir(directory: str = ".") -> str:
    file_dir = Path(directory)
    dirs_list = []
    for x in file_dir.iterdir():
        if x.is_dir():
            dirs_list.append(x.name + "/")
        else:
            dirs_list.append(x.name)
    if dirs_list:
        return "\n".join(sorted(dirs_list))
    return "（空目录）"
   
@tool(name="read_file", description="读取一个文件的内容", paramters=_params(file_path="文件路径"))
def read_file(file_path: str) -> str:
    p = Path(file_path)
    return p.read_text(encoding="utf-8")

@tool(name="write_file", description="把内容写入文件，已存在则覆盖，目录不存在会自动创建。", paramters=_params(file_path="文件路径", content="要写入的内容"))
def write_file(file_path: str, content: str) -> str:
    p = Path(file_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"已写入{file_path} ({len(content)})"

@tool(name="edit_file", description="编辑文件，将旧的字符编辑为新的字符", paramters=_params(file_path="文件路径", old="旧的字符", new="新的字符"))
def edit_file(file_path: str, old: str, new: str | None) -> str:
    file_content = read_file(file_path)
    count = file_content.count(old)
    if count == 0:
        return f"Error: {file_path}中没有{old}字符。"
    if count > 1:
        return f"Error: {file_path}中{old}字符出现多次，仅支持单次替换。"
    after_replace_content = file_content.replace(old, new, 1)
    write_file(file_path, after_replace_content)
    return f"已替换{file_path}中的{old}为{new}。"

@tool(name="run_shell", description="执行shell命令并返回输出", paramters=_params(command="需要执行的命令"))
def run_shell(command: str) -> str:
    if input(f"\n [需要确认] 执行命令：{command}\n 允许？(y/n)").strip().lower() != "y":
        return "用户拒绝执行该命令"
    
    try:
        p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return "命令超时60s"
    except Exception as e:
        return f"命令执行失败: {e}"
    
    return "[exit {p.returncode}]\n" + (p.stdout + p.stderr)[-MAX_OUTPUT:] or "(无输出)"

@tool(name="fetch_url", description="抓取一个网页或者接口的文本内容。url必须以http或者https开头", paramters=_params(url="完整的url"))
def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "moli-agent"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")

@tool(name="get_time", description="获取当前时间", paramters={})
def get_time():
    return datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    
def execute(name, args):
    """执行工具，永远返回字符串，永远不抛异常"""
    if name not in TOOLS:
        return f"Error: 不存在工具名称：'{name}', 可用工具：{','.join(TOOLS)}"
    try:
        result = str(TOOLS[name].get("func")(**args))
    except Exception as e:
        return f"Error: {type(e).__name__}： {e}"
    
    if len(result) > MAX_OUTPUT:
        result = result[:MAX_OUTPUT] + f"\n...（已截断，共{len(result)} 字符）"
    return result

        