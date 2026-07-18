import pyautogui
import time
import tkinter as tk
from tkinter import messagebox

# 全局变量存储点击坐标
click_x = 0
click_y = 0
is_running = False


def select_click_area():
    """弹出提示框，引导用户选择点击区域"""
    global click_x, click_y
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口

    # 提示用户准备选择
    messagebox.showinfo(
        "选择点击区域",
        "点击确定后，请在3秒内将鼠标移动到目标窗口的指定位置（无需点击），程序会记录该坐标"
    )
    root.destroy()

    # 倒计时3秒，给用户移动鼠标的时间
    print("3秒后记录鼠标位置...")
    time.sleep(3)

    # 获取当前鼠标坐标（即用户选定的点击位置）
    click_x, click_y = pyautogui.position()
    print(f"已记录点击位置：({click_x}, {click_y})")
    print("程序将每5秒点击一次该位置，按 Ctrl+C 停止运行")


def auto_click():
    """每5秒自动点击指定位置"""
    global is_running
    is_running = True
    try:
        while is_running:
            # 模拟鼠标左键点击（按下+松开）
            pyautogui.click(click_x, click_y)
            print(f"已点击 ({click_x}, {click_y})，下次点击将在5秒后...")
            time.sleep(2)  # 间隔5秒
    except KeyboardInterrupt:
        # 捕获 Ctrl+C 中断信号
        is_running = False
        print("\n程序已停止运行")


if __name__ == "__main__":
    # 步骤1：安装依赖（首次运行需执行）
    try:
        import pyautogui
    except ImportError:
        print("正在安装依赖库 pyautogui...")
        import subprocess
        import sys

        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyautogui"])
        import pyautogui

        print("依赖安装完成")

    # 步骤2：选择点击区域
    select_click_area()

    # 步骤3：开始自动点击
    auto_click()