"""终端或 PyCharm 中的人工密码/验证码输入，不识别或绕过验证码。"""

import getpass
import os
import sys

from .config import PreparationError


def read_secret(prompt, *, image_path=None):
    if image_path is not None:
        print(f"请查看本次验证码：{image_path}", flush=True)
        if os.name == "nt":
            os.startfile(str(image_path))
    print(prompt, flush=True)
    if sys.stdin.isatty() and not os.environ.get("PYCHARM_HOSTED"):
        answer = getpass.getpass("").strip()
    else:
        # Windows getpass 在 IDE 运行窗口里可能无提示地等待，改用掩码弹窗。
        try:
            import tkinter as tk
            from tkinter import simpledialog
        except ImportError:
            raise PreparationError("当前 IDE 不能隐藏输入，请在 PowerShell 中用 -s 运行") from None
        root = None
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            answer = simpledialog.askstring("若依人工输入", prompt, show="*", parent=root)
        except tk.TclError:
            raise PreparationError("无法显示输入框，请在 PowerShell 中用 -s 运行") from None
        finally:
            if root is not None:
                root.destroy()
        answer = answer.strip() if answer else ""
    if not answer:
        raise PreparationError("输入为空或已取消，不提交后续登录")
    return answer
