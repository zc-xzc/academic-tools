import pyautogui
import time
import random
import os
import cv2
import numpy as np
from pynput import keyboard
from PIL import ImageGrab
from pathlib import Path
import ctypes

# ==================== 核心配置（精准+自动循环） ====================
TARGET_BUTTONS_PER_PAGE = 10  # 每页目标10个
MIN_LAST_PAGE_BUTTONS = 1  # 最后一页至少1个就下载
DOWNLOAD_PATH = r"D:\Downloads"
CONFIDENCE = 0.35  # 精准匹配置信度
BUTTON_DUPLICATE_DISTANCE = 40  # 按钮去重距离
EDGE_THRESHOLD = 100  # 边缘检测阈值
FLOAT_RANGE = 15  # 后续页面坐标浮动适配
TEMP_SCREENSHOT = "temp_screenshot.png"
WINDOW_TITLE = "第一次框选下载按钮区域"
FILE_MIN_SIZE = 2048
DOWNLOAD_TIMEOUT = 30
PAGE_LOAD_DELAY = 4  # 翻页后加载时间（网速慢可调大）
PAGE_TURN_DELAY = (1.0, 1.5)  # 翻页操作间隔

# 时间设置（保持精准操作）
MOVE_DURATION = (0.4, 0.7)
CLICK_DELAY = (0.6, 0.9)
DOWNLOAD_INTERVAL = (1.2, 1.8)

# 全局状态
is_running = True
is_paused = False
saved_region = None  # 保存第一次框选区域（复用）
downloaded_total = 0  # 总下载数
current_page = 1  # 当前页码
screen_size = pyautogui.size()
system_scaling = 1.0


# ==================== 工具函数 ====================
def get_system_scaling():
    """获取系统缩放，用于坐标校准"""
    try:
        user32 = ctypes.windll.user32
        dpi = user32.GetDpiForSystem()
        return dpi / 96.0
    except:
        return 1.0


def init_download_path():
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
    print(f"✅ 下载路径：{DOWNLOAD_PATH}")


def load_template():
    """加载并预处理按钮模板（边缘检测+灰度化）"""
    template_path = "download_icon.png"
    if not os.path.exists(template_path):
        print(f"❌ 未找到 {template_path}！")
        print("请截图25-30像素的下载按钮（无背景），保存到脚本文件夹")
        exit(1)
    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    template_edge = cv2.Canny(template, EDGE_THRESHOLD // 2, EDGE_THRESHOLD)
    return template_edge, template.shape[:2]


def take_screenshot():
    """精准截图整个屏幕"""
    try:
        screen = ImageGrab.grab(bbox=(0, 0, screen_size[0], screen_size[1]))
        screen.save(TEMP_SCREENSHOT)
        return True
    except Exception as e:
        print(f"❌ 截图失败：{str(e)}")
        return False


# ==================== 第一次手动框选（仅执行一次） ====================
def first_time_select_region():
    """第一次框选区域并保存，后续页面自动复用"""
    global saved_region
    ref_point = []
    cropping = False

    # 第一次截图
    if not take_screenshot():
        return False

    img = cv2.imread(TEMP_SCREENSHOT)
    img_copy = img.copy()
    img_h, img_w = img.shape[:2]

    # 框选提示
    cv2.putText(img_copy, "第一次框选：按住左键框选10个下载按钮竖列 → 松开后按ESC", (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    cv2.putText(img_copy, "后续页面自动复用该区域，无需再操作！", (30, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

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

    # 等待ESC关闭框选窗口
    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
    cv2.destroyAllWindows()

    # 处理并保存区域（预留浮动范围）
    if len(ref_point) == 2:
        x1 = min(ref_point[0][0], ref_point[1][0]) - FLOAT_RANGE
        y1 = min(ref_point[0][1], ref_point[1][1]) - FLOAT_RANGE
        x2 = max(ref_point[0][0], ref_point[1][0]) + FLOAT_RANGE
        y2 = max(ref_point[0][1], ref_point[1][1]) + FLOAT_RANGE
        # 确保区域不超出屏幕
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(screen_size[0], x2)
        y2 = min(screen_size[1], y2)
        saved_region = (x1, y1, x2, y2)
        print(f"✅ 已保存区域：({x1},{y1})→({x2},{y2})（含±{FLOAT_RANGE}像素浮动适配）")
        return True
    else:
        print("❌ 框选失败，请重新尝试")
        return False


# ==================== 自动匹配按钮（后续页面复用区域） ====================
def auto_find_buttons(template_edge, template_size):
    """在保存的区域内自动匹配按钮（适配坐标浮动）"""
    x1, y1, x2, y2 = saved_region
    template_h, template_w = template_size

    # 截图当前页面
    if not take_screenshot():
        return None

    # 读取截图并预处理（与模板一致）
    img = cv2.imread(TEMP_SCREENSHOT)
    roi = img[y1:y2, x1:x2]  # 截取保存的区域
    roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    roi_edge = cv2.Canny(roi_gray, EDGE_THRESHOLD // 2, EDGE_THRESHOLD)

    # 精准匹配
    result = cv2.matchTemplate(roi_edge, template_edge, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= CONFIDENCE)

    buttons = []
    for pt in zip(*locations[::-1]):
        # 计算按钮中心坐标
        center_x = x1 + pt[0] + template_w // 2
        center_y = y1 + pt[1] + template_h // 2
        # 去重（避免同一按钮多次匹配）
        duplicate = False
        for (bx, by) in buttons:
            if abs(center_x - bx) < BUTTON_DUPLICATE_DISTANCE and abs(center_y - by) < BUTTON_DUPLICATE_DISTANCE:
                duplicate = True
                break
        if not duplicate:
            buttons.append((center_x, center_y))
            print(f"🔍 第{current_page}页匹配到按钮：({center_x:.0f},{center_y:.0f})")

    # 按Y坐标排序（从上到下下载）
    buttons.sort(key=lambda x: x[1])
    print(f"📄 第{current_page}页共匹配到{len(buttons)}个按钮")
    return buttons


# ==================== 下载+翻页核心逻辑 ====================
def download_page_buttons(buttons):
    """下载当前页按钮（最多10个），返回成功下载数"""
    global downloaded_total
    page_downloaded = 0
    target_count = min(len(buttons), TARGET_BUTTONS_PER_PAGE)

    for idx in range(target_count):
        if not is_running:
            break
        while is_paused:
            time.sleep(0.5)

        x, y = buttons[idx]
        print(f"\n📥 第{current_page}页 第{idx + 1}/{target_count}个（坐标：{x},{y}）")

        # 精准移动并点击
        pyautogui.FAILSAFE = False
        duration = random.uniform(*MOVE_DURATION)
        pyautogui.moveTo(x, y, duration=duration, tween=pyautogui.easeInOutQuad)
        time.sleep(random.uniform(*CLICK_DELAY))
        pyautogui.click()

        # 等待下载完成并校验
        start_time = time.time()
        initial_files = set(os.listdir(DOWNLOAD_PATH))
        download_success = False

        while time.time() - start_time < DOWNLOAD_TIMEOUT:
            current_files = set(os.listdir(DOWNLOAD_PATH))
            # 过滤临时文件和小文件
            new_files = [
                f for f in (current_files - initial_files)
                if not f.endswith(('.crdownload', '.part', '.tmp'))
            ]

            if new_files:
                new_file = new_files[0]
                f_path = os.path.join(DOWNLOAD_PATH, new_file)
                file_size = os.path.getsize(f_path)
                if file_size >= FILE_MIN_SIZE:
                    print(f"✅ 下载成功：{new_file}（{file_size / 1024:.1f}KB）")
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
    """自动翻页（优先pagedown，失败则点击底部备用）"""
    global current_page
    print(f"\n" + "=" * 50)
    print(f"📑 第{current_page}页下载完成，准备翻到第{current_page + 1}页...")
    print("=" * 50)

    try:
        # 方法1：按pagedown翻页（知网通用）
        pyautogui.press('pagedown')
        time.sleep(random.uniform(*PAGE_TURN_DELAY))
        # 等待页面加载完成
        time.sleep(PAGE_LOAD_DELAY)
        current_page += 1
        print(f"✅ 翻页成功，当前第{current_page}页")
        return True
    except:
        try:
            # 方法2：点击页面底部空白处翻页（备用方案）
            pyautogui.moveTo(screen_size[0] // 2, screen_size[1] - 50, duration=0.5)
            pyautogui.click()
            time.sleep(PAGE_LOAD_DELAY)
            current_page += 1
            print(f"✅ 备用翻页成功，当前第{current_page}页")
            return True
        except:
            print(f"❌ 翻页失败，请检查页面是否支持自动翻页")
            return False


# ==================== 键盘控制（保持可控性） ====================
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


# ==================== 主程序（精准+自动循环） ====================
def main():
    global is_running, system_scaling
    system_scaling = get_system_scaling()
    print("=" * 75)
    print("📌 知网精准自动循环下载器（最终版）")
    print("✅ 核心功能：一次框选 → 精准匹配 → 自动下载 → 数量核对 → 自动翻页")
    print("✅ 快捷键：ESC=停止 | 空格=暂停/继续")
    print(f"✅ 系统信息：屏幕{screen_size[0]}x{screen_size[1]}像素，缩放{system_scaling:.2f}x")
    print("=" * 75)

    # 管理员提示（必须）
    print("\n⚠️  请确保已以管理员身份运行脚本！")
    input("👉 确认后按回车开始...")

    # 初始化
    init_download_path()
    template_edge, template_size = load_template()

    # 第一次框选区域（仅执行一次）
    print("\n📌 第一次框选操作（后续页面自动复用）")
    while is_running and not saved_region:
        if first_time_select_region():
            break
        print("🔄 重新尝试框选...")
        time.sleep(2)

    # 启动键盘监听
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()
    print(f"\n🚀 开始全自动循环下载（当前第{current_page}页）")

    try:
        while is_running:
            # 1. 自动匹配当前页按钮
            buttons = auto_find_buttons(template_edge, template_size)
            if not buttons:
                print(f"\n📋 第{current_page}页未找到按钮，下载结束")
                break

            # 2. 下载当前页按钮（不足10个判定为最后一页）
            page_downloaded = download_page_buttons(buttons)
            if page_downloaded == 0 and len(buttons) >= MIN_LAST_PAGE_BUTTONS:
                print(f"❌ 第{current_page}页未下载成功任何文件，停止循环")
                break

            # 3. 数量核对+自动翻页（下载10个说明有下一页）
            if len(buttons) >= TARGET_BUTTONS_PER_PAGE and page_downloaded >= TARGET_BUTTONS_PER_PAGE:
                if not auto_turn_page():
                    break
            else:
                print(f"\n📋 第{current_page}页只有{len(buttons)}个按钮（不足10个），判定为最后一页")
                break

    finally:
        # 清理资源+统计结果
        listener.stop()
        listener.join()
        if os.path.exists(TEMP_SCREENSHOT):
            os.remove(TEMP_SCREENSHOT)

        print("\n" + "=" * 60)
        print(f"🎉 下载任务结束！")
        print(f"📊 总下载页数：{current_page}页")
        print(f"📊 总下载文件数：{downloaded_total}个")
        print(f"📁 下载路径：{DOWNLOAD_PATH}")
        print("=" * 60)
        print("👋 脚本退出")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ 用户手动停止")
        if os.path.exists(TEMP_SCREENSHOT):
            os.remove(TEMP_SCREENSHOT)
        print(f"📊 总下载页数：{current_page}页，总下载文件数：{downloaded_total}个")