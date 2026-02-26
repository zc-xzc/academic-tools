import pyautogui
import time
import random
import os
import cv2
import numpy as np
from pynput import keyboard
from PIL import ImageGrab

# ==================== 配置参数（根据实际情况调整）====================
# 图像路径
SERIAL_ICON_PATH = "cnki_serial.png"  # 放大后的序号截图（如"75"，仅序号文字）
DOWNLOAD_ICON_PATH = "cnki_download.png"  # 下载图标截图（蓝色箭头，必须准备）
# 识别参数
CONFIDENCE_SERIAL = 0.80  # 序号识别置信度（略降低，配合布局验证）
CONFIDENCE_DOWNLOAD = 0.75  # 下载图标验证置信度
SERIAL_LEFT_SPACE = 30  # 序号左侧空格宽度（像素，核心布局特征）
SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()  # 屏幕尺寸（过滤无效坐标）
# 偏移量（校准后自动赋值）
DX = None  # 序号→下载按钮 水平偏移
DY = None  # 序号→下载按钮 垂直偏移
# 人类模拟参数
MIN_CLICK_DELAY = 1.2
MAX_CLICK_DELAY = 2.3
MIN_MOVE_DURATION = 0.3
MAX_MOVE_DURATION = 0.6
SCROLL_TRIGGER_RANGE = [3, 6]
HESITATE_PROB = 0.18
MIN_HESITATE = 0.5
MAX_HESITATE = 1.2
# 页面相关
PAGE_ITEM_COUNT = 50  # 知网每页50个
SCROLL_STEP = 550
SCROLL_DELAY = 0.8
PAGE_TURN_DELAY = 3.5
PAGE_TURN_KEY = 'right'
# ====================================================================

# 全局状态
is_running = True
is_paused = False
scanned_serials = set()
start_serial = None
browser_window = None  # 浏览器窗口位置（用于限定识别范围）


def load_image(path, tip):
    """加载图像，带友好提示"""
    if not os.path.exists(path):
        print(f"❌ 未找到{tip}：{path}")
        exit(1)
    img = cv2.imread(path)
    if img is None:
        print(f"⚠️ {tip}截图无效，请重新截取清晰的图像")
        exit(1)
    return img


# 预加载图像
SERIAL_ICON = load_image(SERIAL_ICON_PATH, "序号截图")
DOWNLOAD_ICON = load_image(DOWNLOAD_ICON_PATH, "下载图标截图")
SERIAL_H, SERIAL_W = SERIAL_ICON.shape[:2]
DOWNLOAD_H, DOWNLOAD_W = DOWNLOAD_ICON.shape[:2]


def get_browser_window():
    """获取浏览器窗口位置（限定识别范围，提高准确率）"""
    print("\n📍 请在3秒内将鼠标移动到浏览器窗口内任意位置，按回车键确认！")
    time.sleep(3)
    x, y = pyautogui.position()
    # 简化：假设浏览器全屏，或限定屏幕中间区域（可后续通过F12优化）
    global browser_window
    browser_window = (0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)  # 全屏范围（后续可优化为精确窗口）
    print(f"✅ 已锁定识别范围：全屏（{SCREEN_WIDTH}x{SCREEN_HEIGHT}）")


def is_valid_coordinate(x, y):
    """验证坐标是否在屏幕可视范围内"""
    return 0 <= x <= SCREEN_WIDTH and 0 <= y <= SCREEN_HEIGHT


def check_serial_left_space(screen_bgr, serial_x, serial_y):
    """验证序号左侧是否有足够空格（布局特征双重验证）"""
    # 截取序号左侧SERIAL_LEFT_SPACE像素的区域，检查是否无其他序号
    left_x = max(0, serial_x - SERIAL_LEFT_SPACE - SERIAL_W // 2)
    top_y = max(0, serial_y - SERIAL_H // 2)
    right_x = serial_x - SERIAL_W // 2
    bottom_y = serial_y + SERIAL_H // 2

    # 截取左侧区域
    left_region = screen_bgr[top_y:bottom_y, left_x:right_x]
    if left_region.size == 0:
        return True  # 左侧已到屏幕边缘，视为有空格

    # 检查左侧区域是否有其他序号匹配
    result = cv2.matchTemplate(left_region, SERIAL_ICON, cv2.TM_CCOEFF_NORMED)
    return np.max(result) < 0.5  # 无匹配则视为有空格


def find_all_serials_multiscale():
    """多尺度识别序号 + 布局特征验证，返回有效序号列表（(x,y,relative_serial)）"""
    if not browser_window:
        get_browser_window()
    x1, y1, x2, y2 = browser_window

    # 截取浏览器窗口区域（避免识别屏幕其他内容）
    screen = ImageGrab.grab(bbox=(x1, y1, x2, y2))
    screen_np = np.array(screen)
    screen_bgr = cv2.cvtColor(screen_np, cv2.COLOR_RGB2BGR)

    serial_positions = []
    # 多尺度匹配（应对序号大小微小变化）
    scales = [0.9, 1.0, 1.1, 1.2]  # 缩放比例
    for scale in scales:
        # 缩放序号模板
        scaled_icon = cv2.resize(SERIAL_ICON, None, fx=scale, fy=scale)
        h, w = scaled_icon.shape[:2]
        if h > screen_bgr.shape[0] or w > screen_bgr.shape[1]:
            continue

        # 模板匹配
        result = cv2.matchTemplate(screen_bgr, scaled_icon, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= CONFIDENCE_SERIAL)

        # 提取并验证序号
        for pt in zip(*locations[::-1]):
            # 转换为屏幕绝对坐标
            center_x = x1 + pt[0] + w // 2
            center_y = y1 + pt[1] + h // 2

            # 过滤无效坐标
            if not is_valid_coordinate(center_x, center_y):
                continue

            # 布局特征验证：左侧有空格
            if not check_serial_left_space(screen_bgr, pt[0] + w // 2, pt[1] + h // 2):
                continue

            # 去重：距离已存位置小于30像素视为同一序号
            duplicate = False
            for (px, py, _) in serial_positions:
                if abs(center_x - px) < 30 and abs(center_y - py) < 30:
                    duplicate = True
                    break
            if not duplicate:
                serial_positions.append((center_x, center_y, None))

    # 按位置排序（从上到下、左到右），分配相对序号
    serial_positions.sort(key=lambda p: (p[1], p[0]))
    for idx, (x, y, _) in enumerate(serial_positions):
        serial_positions[idx] = (x, y, idx + 1)  # 相对序号1~50

    print(f"🔍 识别到{len(serial_positions)}个有效序号")
    return serial_positions


def verify_download_position(x, y):
    """验证坐标是否为下载图标位置（双重确认）"""
    # 截取目标位置周围区域
    x1 = max(0, x - DOWNLOAD_W)
    y1 = max(0, y - DOWNLOAD_H)
    x2 = min(SCREEN_WIDTH, x + DOWNLOAD_W)
    y2 = min(SCREEN_HEIGHT, y + DOWNLOAD_H)

    screen = ImageGrab.grab(bbox=(x1, y1, x2, y2))
    screen_np = np.array(screen)
    screen_bgr = cv2.cvtColor(screen_np, cv2.COLOR_RGB2BGR)

    # 匹配下载图标
    result = cv2.matchTemplate(screen_bgr, DOWNLOAD_ICON, cv2.TM_CCOEFF_NORMED)
    max_val = np.max(result)
    if max_val >= CONFIDENCE_DOWNLOAD:
        print(f"✅ 下载位置验证通过（置信度：{max_val:.2f}）")
        return True
    else:
        print(f"⚠️  下载位置未检测到下载图标（置信度：{max_val:.2f}）")
        return False


def calibrate_offset():
    """优化后的偏移量校准，增加位置验证"""
    global DX, DY
    print("\n📌 开始偏移量校准（确保定位精准）")

    # 步骤1：选择可视区域内的序号
    while True:
        print("步骤1：在3秒内将鼠标移动到【可视区域内】放大后的序号中心点，按回车键确认！")
        time.sleep(3)
        serial_x, serial_y = pyautogui.position()
        if is_valid_coordinate(serial_x, serial_y):
            print(f"✅ 序号位置已记录：({serial_x}, {serial_y})")
            break
        else:
            print(f"❌ 坐标({serial_x}, {serial_y})无效（超出屏幕范围），请重新选择可视区域内的序号！")

    # 步骤2：选择对应下载按钮
    while True:
        print("\n步骤2：在3秒内将鼠标移动到对应下载按钮的中心点，按回车键确认！")
        time.sleep(3)
        download_x, download_y = pyautogui.position()
        if is_valid_coordinate(download_x, download_y):
            print(f"✅ 下载按钮位置已记录：({download_x}, {download_y})")
            break
        else:
            print(f"❌ 坐标({download_x}, {download_y})无效（超出屏幕范围），请重新选择！")

    # 计算偏移量
    DX = download_x - serial_x
    DY = download_y - serial_y
    print(f"\n📊 校准完成！偏移量：dx={DX} 像素，dy={DY} 像素")
    print(f"👉 序号({serial_x}, {serial_y}) → 下载按钮({serial_x + DX}, {serial_y + DY})")

    # 验证下载位置
    if verify_download_position(serial_x + DX, serial_y + DY):
        confirm = input("是否确认该偏移量？（y/n）：")
        if confirm.lower() == "y":
            return
    else:
        print("⚠️  下载位置验证失败，请重新校准！")

    # 重新校准
    calibrate_offset()


def simulate_hesitation():
    """模拟人类犹豫"""
    if random.random() < HESITATE_PROB:
        hesitate_time = random.uniform(MIN_HESITATE, MAX_HESITATE)
        print(f"🤔 犹豫中...（{hesitate_time:.1f}秒）")
        time.sleep(hesitate_time)


def simulate_fine_adjust(x, y):
    """模拟鼠标微调"""
    if random.random() < 0.1:
        adjust_x = x + random.randint(-2, 2)
        adjust_y = y + random.randint(-2, 2)
        pyautogui.moveTo(adjust_x, adjust_y, duration=0.2)
        print(f"🔍 微调鼠标位置到：({adjust_x}, {adjust_y})")
        time.sleep(0.3)


def calculate_download_range(current_serials):
    """计算当前页下载范围"""
    if not current_serials:
        return []

    # 推导当前页绝对序号（适配知网50条/页）
    page_start = ((len(scanned_serials) // PAGE_ITEM_COUNT) * PAGE_ITEM_COUNT) + 1
    page_end = page_start + PAGE_ITEM_COUNT - 1

    download_list = []
    for x, y, relative_serial in current_serials:
        absolute_serial = page_start + relative_serial - 1
        if absolute_serial >= start_serial and absolute_serial not in scanned_serials:
            download_list.append((x, y, absolute_serial))

    return download_list


def on_key_press(key):
    """键盘控制"""
    global is_running, is_paused
    try:
        if key == keyboard.Key.esc:
            print("\n⚠️  检测到ESC键，停止下载...")
            is_running = False
            return False
        elif key == keyboard.Key.space:
            is_paused = not is_paused
            if is_paused:
                print("\n⏸️  已暂停（按空格键继续，ESC键停止）")
            else:
                print("\n▶️  继续下载")
    except Exception as e:
        print(f"\n❌ 键盘操作错误：{e}")


def auto_download():
    """核心下载逻辑"""
    global start_serial, scanned_serials
    print("=" * 70)
    print("📌 知网批量下载脚本（双重定位增强版）")
    print("特性：序号截图+布局特征双重定位、下载位置验证、防无效坐标")
    print("快捷键：空格键=暂停/继续 | ESC键=停止")
    print("=" * 70)

    # 步骤1：获取浏览器窗口范围
    get_browser_window()

    # 步骤2：校准偏移量
    calibrate_offset()

    # 步骤3：输入起始序号
    while True:
        start_input = input("\n请输入起始下载序号（如1、75）：")
        if start_input.isdigit():
            start_serial = int(start_input)
            print(f"✅ 已选定起始序号：{start_serial}")
            break
        else:
            print("❌ 输入无效，请输入数字序号")

    # 步骤4：启动键盘监听
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()

    print("\n🚀 开始下载（按空格键暂停，ESC键停止）")
    print("请确保：1. 知网页面在可视区域 2. 序号已放大 3. 下载图标清晰可见")
    input("按回车键开始...")

    current_page = 1
    download_count = 0
    scroll_trigger = random.randint(*SCROLL_TRIGGER_RANGE)

    try:
        while is_running:
            if is_paused:
                time.sleep(0.5)
                continue

            # 识别当前页序号（多尺度+布局验证）
            current_serials = find_all_serials_multiscale()
            if not current_serials:
                print(f"\n🔍 第{current_page}页未识别到有效序号，尝试排查：")
                print("  1. 序号是否已放大？")
                print("  2. 序号截图是否与页面序号完全一致？")
                print("  3. 页面是否在可视区域内？")
                choice = input("是否继续翻页？（y/n）：")
                if choice.lower() != "y":
                    break
                pyautogui.press(PAGE_TURN_KEY)
                time.sleep(PAGE_TURN_DELAY)
                current_page += 1
                scroll_trigger = random.randint(*SCROLL_TRIGGER_RANGE)
                continue

            # 计算下载范围
            download_list = calculate_download_range(current_serials)
            if not download_list:
                print(
                    f"\n✅ 第{current_page}页无需要下载的文件（已下载到{max(scanned_serials) if scanned_serials else 0}）")
                choice = input("是否切换到下一页？（y/n）：")
                if choice.lower() != "y":
                    break
                pyautogui.press(PAGE_TURN_KEY)
                time.sleep(PAGE_TURN_DELAY)
                current_page += 1
                scroll_trigger = random.randint(*SCROLL_TRIGGER_RANGE)
                continue

            print(
                f"\n📄 第{current_page}页下载范围：{download_list[0][2]}~{download_list[-1][2]}（共{len(download_list)}个）")

            # 批量下载
            for idx, (serial_x, serial_y, absolute_serial) in enumerate(download_list):
                if not is_running:
                    break
                while is_paused:
                    time.sleep(0.5)

                simulate_hesitation()

                # 计算下载位置（精准偏移）
                download_x = serial_x + DX + random.randint(-1, 1)
                download_y = serial_y + DY + random.randint(-1, 1)

                # 验证下载位置（双重确认）
                if not verify_download_position(download_x, download_y):
                    print("❌ 下载位置验证失败，跳过该文件")
                    continue

                # 平滑移动鼠标
                move_duration = random.uniform(MIN_MOVE_DURATION, MAX_MOVE_DURATION)
                pyautogui.moveTo(download_x, download_y, duration=move_duration)
                print(
                    f"\n📥 下载第{download_count + 1}个文件 | 序号：{absolute_serial} | 坐标：({download_x:.0f}, {download_y:.0f})")

                # 微调位置
                simulate_fine_adjust(download_x, download_y)

                # 点击下载
                pyautogui.click(clicks=1, interval=0.1)

                # 随机等待
                click_delay = random.uniform(MIN_CLICK_DELAY, MAX_CLICK_DELAY)
                time.sleep(click_delay)

                # 标记已处理
                scanned_serials.add(absolute_serial)
                download_count += 1

                # 随机滚动
                if (idx + 1) % scroll_trigger == 0:
                    print(f"🔄 滚动页面（触发阈值：{scroll_trigger}）...")
                    pyautogui.scroll(-SCROLL_STEP)
                    time.sleep(SCROLL_DELAY)
                    scroll_trigger = random.randint(*SCROLL_TRIGGER_RANGE)

            # 翻页
            choice = input(f"\n✅ 第{current_page}页下载完成，是否切换到下一页？（y/n）：")
            if choice.lower() != "y":
                break
            pyautogui.press(PAGE_TURN_KEY)
            time.sleep(PAGE_TURN_DELAY)
            current_page += 1
            scroll_trigger = random.randint(*SCROLL_TRIGGER_RANGE)

    finally:
        listener.stop()
        listener.join()
        print(f"\n📊 下载统计：共下载{download_count}个文件")
        print("👋 脚本已退出")


if __name__ == "__main__":
    try:
        auto_download()
    except KeyboardInterrupt:
        print("\n⚠️  用户手动停止脚本")
    except Exception as e:
        print(f"\n❌ 脚本运行错误：{e}")
        print("👉 若持续报错，可提供网页F12数据（如下载按钮的CSS选择器），将优化为HTML元素定位")