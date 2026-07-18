import pyautogui
import time
import random
import os
import cv2
import numpy as np
from pynput import keyboard
from PIL import ImageGrab
from pathlib import Path

# ==================== 核心配置（纯颜色定位，放弃模板匹配） ====================
TARGET_BUTTONS_PER_PAGE = 10
MIN_LAST_PAGE_BUTTONS = 1
DOWNLOAD_PATH = r"D:\Downloads"
# 关键：调整蓝色按钮的HSV范围（更适合网页按钮）
# 先转为HSV空间（对颜色识别更稳定），H=100-130是蓝色范围
HSV_LOW = np.array([100, 43, 46])  # 蓝色下限
HSV_HIGH = np.array([130, 255, 255])  # 蓝色上限
BUTTON_AREA_MIN = 10  # 按钮最小像素面积（过滤噪点）
BUTTON_AREA_MAX = 200  # 按钮最大像素面积
BUTTON_DUPLICATE_DISTANCE = 40  # 按钮间距（根据网页布局调整）
FLOAT_RANGE = 10
TEMP_SCREENSHOT = "temp_screenshot.png"
WINDOW_TITLE = "框选右侧操作列（红色框区域）"
FILE_MIN_SIZE = 2048
DOWNLOAD_TIMEOUT = 30
PAGE_LOAD_DELAY = 5
PAGE_TURN_RETRY = 3

# 时间设置
MOVE_DURATION = (0.2, 0.5)
CLICK_DELAY = (0.4, 0.7)
DOWNLOAD_INTERVAL = (0.8, 1.2)
PAGE_TURN_DELAY = (1.5, 2.0)

# 全局状态
is_running = True
is_paused = False
saved_region = None
downloaded_total = 0
current_page = 1
screen_size = pyautogui.size()


# ==================== 工具函数 ====================
def init_download_path():
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
    print(f"✅ 下载路径：{DOWNLOAD_PATH}")


def take_screenshot():
    try:
        # 高DPI屏幕适配：直接截图并保存为原始尺寸
        screen = ImageGrab.grab()
        screen.save(TEMP_SCREENSHOT)
        if os.path.getsize(TEMP_SCREENSHOT) < 102400:
            print("❌ 截图过小，可能未捕获完整页面")
            return False
        return True
    except Exception as e:
        print(f"❌ 截图失败：{str(e)}")
        return False


# ==================== 区域选择 ====================
def select_region():
    global saved_region
    ref_point = []
    cropping = False

    while not take_screenshot():
        print("🔄 重新尝试截图...")
        time.sleep(2)

    img = cv2.imread(TEMP_SCREENSHOT)
    img_copy = img.copy()
    img_h, img_w = img.shape[:2]

    cv2.putText(img_copy, "框选右侧红色框标记的'操作'列区域 → 按ESC确认", (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    cv2.putText(img_copy, "确保包含所有蓝色下载图标（不要太宽，避免其他蓝色元素）", (30, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    def click_event(event, x, y, flags, param):
        nonlocal ref_point, cropping
        if event == cv2.EVENT_LBUTTONDOWN:
            ref_point = [(x, y)]
            cropping = True
        elif event == cv2.EVENT_LBUTTONUP:
            ref_point.append((x, y))
            cropping = False
            cv2.rectangle(img_copy, ref_point[0], ref_point[1], (0, 255, 0), 4)
            cv2.imshow(WINDOW_TITLE, img_copy)
        elif event == cv2.EVENT_MOUSEMOVE and cropping:
            temp_img = img_copy.copy()
            cv2.rectangle(temp_img, ref_point[0], (x, y), (0, 255, 0), 3)
            cv2.imshow(WINDOW_TITLE, temp_img)

    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_TITLE, img_w // 2, img_h // 2)  # 缩放窗口方便操作
    cv2.imshow(WINDOW_TITLE, img_copy)
    cv2.setMouseCallback(WINDOW_TITLE, click_event)

    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
    cv2.destroyAllWindows()

    if len(ref_point) == 2:
        # 精确框选，不扩大范围（避免引入其他蓝色元素）
        x1 = min(ref_point[0][0], ref_point[1][0])
        y1 = min(ref_point[0][1], ref_point[1][1])
        x2 = max(ref_point[0][0], ref_point[1][0])
        y2 = max(ref_point[0][1], ref_point[1][1])
        # 确保不超出屏幕
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(screen_size[0], x2)
        y2 = min(screen_size[1], y2)
        saved_region = (x1, y1, x2, y2)
        print(f"✅ 已保存区域：({x1},{y1})→({x2},{y2})")
        return True
    else:
        print("❌ 框选失败，请重新尝试")
        return False


# ==================== 核心改进：基于颜色聚类定位按钮 ====================
def find_buttons_by_color():
    """直接通过蓝色识别按钮，不依赖模板"""
    if not saved_region:
        return None

    x1, y1, x2, y2 = saved_region

    # 确保截图成功
    for _ in range(3):
        if take_screenshot():
            break
        time.sleep(1)
    else:
        return None

    # 读取截图并提取ROI（你框选的操作列区域）
    img = cv2.imread(TEMP_SCREENSHOT)
    roi = img[y1:y2, x1:x2]  # 仅处理框选的区域

    # 转换为HSV空间（更适合颜色识别）
    hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    # 提取蓝色区域
    blue_mask = cv2.inRange(hsv_roi, HSV_LOW, HSV_HIGH)
    # 去除噪点（小面积蓝色区域）
    kernel = np.ones((3, 3), np.uint8)
    blue_mask = cv2.morphologyEx(blue_mask, cv2.MORPH_OPEN, kernel)  # 开运算去噪
    blue_mask = cv2.morphologyEx(blue_mask, cv2.MORPH_CLOSE, kernel)  # 闭运算补全

    # 查找蓝色区域的轮廓（每个轮廓对应一个按钮）
    contours, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    buttons = []

    for cnt in contours:
        # 过滤面积过小或过大的区域（排除非按钮的蓝色元素）
        area = cv2.contourArea(cnt)
        if BUTTON_AREA_MIN < area < BUTTON_AREA_MAX:
            # 计算轮廓中心（即按钮中心）
            M = cv2.moments(cnt)
            if M["m00"] != 0:
                cX = int(M["m10"] / M["m00"])
                cY = int(M["m01"] / M["m00"])
                # 转换为屏幕坐标（加上框选区域的偏移）
                screen_x = x1 + cX
                screen_y = y1 + cY
                buttons.append((screen_x, screen_y))

    # 去重：同一按钮可能被识别为多个轮廓
    unique_buttons = []
    for btn in buttons:
        duplicate = False
        for u_btn in unique_buttons:
            if abs(btn[0] - u_btn[0]) < BUTTON_DUPLICATE_DISTANCE and abs(
                    btn[1] - u_btn[1]) < BUTTON_DUPLICATE_DISTANCE:
                duplicate = True
                break
        if not duplicate:
            unique_buttons.append(btn)

    # 按Y坐标排序（从上到下，符合网页布局）
    unique_buttons.sort(key=lambda x: x[1])

    # 保存调试图像（直观显示识别结果）
    debug_img = img.copy()
    # 标记框选区域（红色）
    cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 0, 255), 2)
    # 标记识别到的按钮（绿色圆圈）
    for i, (x, y) in enumerate(unique_buttons):
        cv2.circle(debug_img, (x, y), 6, (0, 255, 0), 2)
        cv2.putText(debug_img, f"{i + 1}", (x + 8, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
    # 保存蓝色掩码图像（方便调试颜色阈值）
    cv2.imwrite(f"debug_blue_mask_{current_page}.png", blue_mask)
    cv2.imwrite(f"debug_page_{current_page}.png", debug_img)

    print(f"\n📄 第{current_page}页：识别到{len(unique_buttons)}个蓝色按钮")
    return unique_buttons


# ==================== 下载+翻页逻辑 ====================
def download_page_buttons(buttons):
    global downloaded_total
    page_downloaded = 0
    target_count = min(len(buttons), TARGET_BUTTONS_PER_PAGE)

    print(f"\n🚀 第{current_page}页开始下载（共{target_count}个按钮）")
    for idx in range(target_count):
        if not is_running:
            break
        while is_paused:
            time.sleep(0.5)

        x, y = buttons[idx]
        print(f"\n📥 第{current_page}页 第{idx + 1}/{target_count}个（坐标：{x},{y}）")

        # 高DPI屏幕适配：直接使用计算的坐标
        pyautogui.FAILSAFE = False
        duration = random.uniform(*MOVE_DURATION)
        pyautogui.moveTo(x, y, duration=duration, tween=pyautogui.easeInOutQuad)
        time.sleep(random.uniform(*CLICK_DELAY))
        pyautogui.click()

        # 等待下载完成
        start_time = time.time()
        initial_files = set(os.listdir(DOWNLOAD_PATH))
        download_success = False

        while time.time() - start_time < DOWNLOAD_TIMEOUT:
            current_files = set(os.listdir(DOWNLOAD_PATH))
            new_files = [
                f for f in (current_files - initial_files)
                if not f.endswith(('.crdownload', '.part', '.tmp'))
            ]

            if new_files:
                new_file = new_files[0]
                f_path = os.path.join(DOWNLOAD_PATH, new_file)
                if os.path.getsize(f_path) >= FILE_MIN_SIZE:
                    print(f"✅ 下载成功：{new_file}（{os.path.getsize(f_path) / 1024:.1f}KB）")
                    downloaded_total += 1
                    page_downloaded += 1
                    download_success = True
                    time.sleep(random.uniform(*DOWNLOAD_INTERVAL))
                    break

            time.sleep(1.0)

        if not download_success:
            print(f"❌ 第{idx + 1}个按钮下载超时")

    print(f"\n📊 第{current_page}页下载统计：成功{page_downloaded}/{target_count}个")
    return page_downloaded


def auto_turn_page():
    global current_page
    print(f"\n" + "=" * 60)
    print(f"📑 第{current_page}页下载完成，准备翻到第{current_page + 1}页...")
    print("=" * 60)

    # 确保页面在前台
    pyautogui.moveTo(screen_size[0] // 2, screen_size[1] // 2, duration=0.5)
    pyautogui.click()
    time.sleep(0.5)

    for retry in range(PAGE_TURN_RETRY):
        try:
            pyautogui.press('right')
            print("⏸️ 按下向右方向键翻页")
            time.sleep(random.uniform(*PAGE_TURN_DELAY))
            time.sleep(PAGE_LOAD_DELAY)  # 等待页面加载

            if take_screenshot():
                current_page += 1
                print(f"✅ 翻页成功，当前第{current_page}页")
                return True
        except Exception as e:
            print(f"⚠️  翻页重试{retry + 1}次失败: {str(e)}")
            time.sleep(2)

    print(f"❌ 翻页失败（已重试{PAGE_TURN_RETRY}次）")
    return False


# ==================== 键盘控制 ====================
def on_key_press(key):
    global is_running, is_paused
    try:
        if key == keyboard.Key.esc:
            print("\n⚠️  按ESC停止下载")
            is_running = False
            return False
        elif key == keyboard.Key.space:
            is_paused = not is_paused
            print(f"\n{'⏸️ 已暂停' if is_paused else '▶️ 继续下载'}")
    except:
        pass


# ==================== 主程序 ====================
def main():
    global is_running
    print("=" * 80)
    print("📌 知网下载专用版（纯颜色定位，无需模板）")
    print("✅ 核心功能：框选操作列 → 识别蓝色按钮 → 自动下载 → 向右翻页")
    print("✅ 快捷键：ESC=停止 | 空格=暂停/继续")
    print(f"✅ 屏幕尺寸：{screen_size[0]}x{screen_size[1]}像素")
    print("=" * 80)

    print("\n⚠️  请确保已以管理员身份运行脚本！")
    input("👉 确认后按回车开始...")

    init_download_path()

    # 框选区域（必须是你截图中红色框标记的操作列）
    print("\n📌 请框选右侧红色框标记的'操作'列（仅包含下载按钮的窄区域）")
    while is_running and not saved_region:
        if select_region():
            break
        print("🔄 重新尝试框选...")
        time.sleep(2)

    # 启动键盘监听
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()
    print(f"\n🚀 开始全自动循环下载（当前第{current_page}页）")

    try:
        while is_running:
            # 用颜色识别按钮
            buttons = find_buttons_by_color()
            if not buttons:
                print(f"\n📋 第{current_page}页未找到蓝色按钮，下载结束")
                break

            # 下载当前页
            page_downloaded = download_page_buttons(buttons)
            if page_downloaded == 0 and len(buttons) >= MIN_LAST_PAGE_BUTTONS:
                print(f"❌ 第{current_page}页未下载成功任何文件，停止循环")
                break

            # 翻页判断
            if len(buttons) >= TARGET_BUTTONS_PER_PAGE:
                if not auto_turn_page():
                    print("⚠️  翻页失败，尝试继续下载当前页剩余按钮...")
                    continue
            else:
                print(f"\n📋 第{current_page}页只有{len(buttons)}个按钮，为最后一页")
                break

    finally:
        listener.stop()
        listener.join()
        if os.path.exists(TEMP_SCREENSHOT):
            os.remove(TEMP_SCREENSHOT)

        print("\n" + "=" * 70)
        print(f"🎉 下载任务结束！")
        print(f"📊 总下载页数：{current_page}页")
        print(f"📊 总下载文件数：{downloaded_total}个")
        print(f"📁 下载路径：{DOWNLOAD_PATH}")
        print(f"🔍 调试图像已保存（debug_page_*.png和debug_blue_mask_*.png）")
        print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ 用户手动停止")
        if os.path.exists(TEMP_SCREENSHOT):
            os.remove(TEMP_SCREENSHOT)
        print(f"📊 总下载页数：{current_page}页，总下载文件数：{downloaded_total}个")