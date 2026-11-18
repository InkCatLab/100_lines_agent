import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    result = subprocess.run(
        [sys.executable, "-u", str(Path(__file__).with_name("agent.py")), "在当前目录创建 hello.py，打印 hello，并运行它"],
    )
    
    print(result.returncode)  # 退出码