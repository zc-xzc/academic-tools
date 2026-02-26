import pyautogui
import time
import random
import os
from pynput import keyboard
from pathlib import Path

# ==================== 核心配置（基于手动校准参数） ====================
FIXED_X = 1922  # 固定x轴坐标（用户提供）
FIRST_BUTTON_Y = 400  # 第一个按钮基准y坐标（用户提供）
TARGET_BUTTONS = 10  # 每页目标下载数
PRIMARY_SPACING = 80  # 主要间距（优先使用）
SECONDARY_SPACING = 60  # 备用间距（失败时切换）
MAX_SPACING_RETRY = 2  # 连续失败次数达此时切换间距
SINGLE_CLICK_TIMEOUT = 1  # 点击后判断失败时间（秒）
PAGE_TOTAL_TIMEOUT = 15  # 单页总超时（秒）
SINGLE_CLICK_DELAY = (0.1, 0.25)  # 点击间隔（≤0.25s）
BUTTON_INTERVAL = (0.5, 1.0)  # 按钮间操作间隔（≤1s）

# y轴偏移策略（优先小范围，再扩大）
OFFSET_STRATEGY = [
    3,  # 向下3px
    -3,  # 向上3px
    5,  # 向下5px
    -5,  # 向上5px
    8,  # 向下8px
    -8,  # 向上8px
    10,  # 向下10px（间距误差补偿）
    -10  # 向上10px（间距误差补偿）
]

# 全局状态
is_running = True
is_paused = False
downloaded_total = 0
current_page = 1
screen_size = pyautogui.size()
current_spacing = PRIMARY_SPACING  # 当前使用的间距
consecutive_failures = 0  # 连续失败计数（用于切换间距）


# ==================== 下载路径初始化 ====================
def init_download_path(download_path=r"D:\Downloads"):
    Path(download_path).mkdir(exist_ok=True)
    print(f"✅ 下载路径：{download_path}")
    return download_path


# ==================== 计算按钮坐标（核心逻辑） ====================
def calculate_button_coords(page=1):
    """根据基准坐标和间距计算所有按钮坐标"""
    coords = []
    for i in range(TARGET_BUTTONS):
        # 第i个按钮的y坐标 = 基准y + 间距*i
        y = FIRST_BUTTON_Y + current_spacing * i
        coords.append((FIXED_X, y))
    print(f"📌 第{page}页按钮坐标计算完成（间距：{current_spacing}px）")
    return coords


# ==================== 单个按钮下载（带偏移重试） ====================
def download_single_button(button_idx, base_x, base_y, download_path):
    """下载单个按钮，带偏移重试"""
    global consecutive_failures
    print(f"\n📌 第{current_page}页 第{button_idx + 1}个（基准：{base_x},{base_y}）")

    # 记录初始文件列表
    initial_files = set(os.listdir(download_path))
    success = False

    # 尝试基准位置 + 偏移策略
    for offset in [0] + OFFSET_STRATEGY:  # 先试基准位置，再试偏移
        current_x = base_x
        current_y = base_y + offset  # 偏移仅作用于y轴
        print(f"🔍 尝试坐标：({current_x},{current_y})（偏移{offset}px）")

        # 移动并点击
        pyautogui.moveTo(current_x, current_y, duration=0.1)
        pyautogui.click()
        time.sleep(random.uniform(*SINGLE_CLICK_DELAY))  # 点击后短暂等待

        # 检查是否有新文件生成（1秒超时）
        time.sleep(SINGLE_CLICK_TIMEOUT)
        current_files = set(os.listdir(download_path))
        new_files = [f for f in (current_files - initial_files)
                     if not f.endswith(('.crdownload', '.part', '.tmp'))]

        if new_files and os.path.getsize(os.path.join(download_path, new_files[0])) > 1024:
            print(f"✅ 下载成功：{new_files[0]}")
            consecutive_failures = 0  # 重置连续失败计数
            success = True
            break

    if not success:
        print(f"❌ 第{button_idx + 1}个下载失败")
        consecutive_failures += 1  # 累加连续失败计数
    return success


# ==================== 整页下载逻辑 ====================
def download_page(download_path):
    global downloaded_total, current_spacing, consecutive_failures
    page_start_time = time.time()
    page_success = 0

    # 计算当前页所有按钮坐标
    buttons = calculate_button_coords(current_page)

    for idx, (x, y) in enumerate(buttons):
        # 检查单页超时
        if time.time() - page_start_time > PAGE_TOTAL_TIMEOUT:
            print(f"⏰ 单页超时（{PAGE_TOTAL_TIMEOUT}s），剩余{len(buttons) - idx}个未下载")
            break
        if not is_running:
            break
        while is_paused:
            time.sleep(0.1)

        # 检查是否需要切换间距（连续失败达阈值）
        if consecutive_failures >= MAX_SPACING_RETRY:
            current_spacing = SECONDARY_SPACING if current_spacing == PRIMARY_SPACING else PRIMARY_SPACING
            print(f"🔄 连续失败{MAX_SPACING_RETRY}次，切换间距为{current_spacing}px，重新计算坐标")
            # 重新计算剩余按钮坐标
            buttons = calculate_button_coords(current_page)
            x, y = buttons[idx]  # 更新当前按钮坐标
            consecutive_failures = 0  # 重置计数

        # 下载单个按钮
        if download_single_button(idx, x, y, download_path):
            downloaded_total += 1
            page_success += 1

        # 按钮间等待间隔
        time.sleep(random.uniform(*BUTTON_INTERVAL))

    print(f"📊 第{current_page}页：成功{page_success}/{len(buttons)}个")
    return page_success


# ==================== 翻页逻辑（仅向右键） ====================
def turn_page():
    global current_page, current_spacing
    print(f"\n📑 翻页到第{current_page + 1}页")
    # 激活页面并按向右键
    pyautogui.moveTo(screen_size[0] // 2, screen_size[1] // 2, duration=0.1)
    pyautogui.click()  # 激活浏览器
    time.sleep(0.2)
    pyautogui.press('right')  # 仅向右键翻页
    time.sleep(1.5)  # 等待页面加载
    current_page += 1
    # 重置间距为默认（新页面可能恢复正常间距）
    current_spacing = PRIMARY_SPACING
    print(f"✅ 已翻到第{current_page}页，重置间距为{PRIMARY_SPACING}px")
    return True


# ==================== 键盘控制 ====================
def on_key_press(key):
    global is_running, is_paused
    try:
        if key == keyboard.Key.esc:
            print("\n⚠️ 按ESC停止下载")
            is_running = False
            return False
        elif key == keyboard.Key.space:
            is_paused = not is_paused
            print(f"\n{'⏸️ 暂停' if is_paused else '▶️ 继续'}")
    except:
        pass


# ==================== 主程序 ====================
def main():
    global is_running
    print("=" * 80)
    print("📌 知网下载器（坐标校准版）")
    print(f"✅ 核心参数：x={FIXED_X}，首个y={FIRST_BUTTON_Y}，间距{PRIMARY_SPACING}/{SECONDARY_SPACING}px")
    print("✅ 快捷键：ESC停止 | 空格暂停")
    print("=" * 80)

    # 初始化下载路径
    download_path = init_download_path()

    # 确认基准坐标
    print(f"\n⚠️ 即将使用以下基准坐标：第1个按钮({FIXED_X},{FIRST_BUTTON_Y})，间距{PRIMARY_SPACING}px")
    input("👉 确认坐标正确（回车开始）...")

    # 启动键盘监听
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()
    print(f"\n🚀 开始下载（第{current_page}页）")

    try:
        while is_running:
            # 下载当前页
            page_success = download_page(download_path)

            # 若当前页下载成功数≥5，继续翻页；否则判定为最后一页
            if page_success >= 5:
                turn_page()
            else:
                print("\n📋 当前页有效按钮不足，判定为最后一页")
                break

    finally:
        listener.stop()
        print("\n" + "=" * 70)
        print(f"🎉 任务结束：共{current_page}页，下载{downloaded_total}个文件")
        print(f"📁 下载路径：{download_path}")
        print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ 用户手动停止")
        print(f"📊 总下载：{downloaded_total}个文件")