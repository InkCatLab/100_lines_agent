import subprocess

def read_file(file_path: str) -> str:
    with open(file_path, encoding="utf-8") as f:
        return f.read()

def write_file(file_path: str, content: str) -> str:
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"已写入{file_path} ({len(content)})"


def run_shell(command: str) -> str:
    if input(f"\n [需要确认] 执行命令：{command}\n 允许？(y/n)").strip().lower() != "y":
        return "用户拒绝执行该命令"
    
    try:
        p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return "命令超时60s"
    except Exception as e:
        return f"命令执行失败: {e}"
    
    return (p.stdout + p.stderr)[-4000:] or "(无输出)"



TOOL_FUNCS = {
    "read_file": read_file,
    "write_file": write_file,
    "run_shell": run_shell
}


def _tool(name, desc, props):
    return {
        "type": "function",
        "function": {
            "name": name,
            "desc": desc,
            "parameters": {
                "type": "object",
                "properties": {k: {"type": "string", "description": v} for k, v in props.items()},
                "required": list(props)
            }
        }
    }


TOOLS = [
    _tool("read_file", "读取文件内容", {"file_path": "文件路径"}),
    _tool("write_file", "写入文件(覆盖)", {"file_path": "文件路径", "content": "要写入的文件内容"}),
    _tool("run_shell", "执行shell命令并返回输出", {"command": "要执行的命令"})
]


