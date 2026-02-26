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
import win32gui
import win32process
import psutil
import re

# ==================== 一、核心配置（精准匹配需求） ====================
# 基础运行配置
CURRENT_PAGE_TYPE = 1  # 页面类型（1/2）
TARGET_BUTTON_COUNT = 10  # 每页必填按钮数量
DOWNLOAD_PATH = r"D:\Downloads"  # 下载目录
SCREENSHOT_PATH = "temp_screenshot.png"  # 临时截图路径
FILE_MIN_SIZE = 1024  # 最小有效文件大小（1KB）

# 识别相关配置（加强去重，避免异常间距）
INIT_CONFIDENCE = 0.45  # 初始匹配置信度
MIN_CONFIDENCE = 0.3  # 最低置信度阈值
CONFIDENCE_STEP = 0.05  # 置信度降级步长
DUPLICATE_THRESHOLD_RATIO = 0.6  # 按钮去重阈值（从30%提升到60%，避免重复识别）

# 时间延迟配置
DOWNLOAD_DETECT_DELAY = 2.5  # 下载检测延迟
NEW_PAGE_TIMEOUT = 8  # 新标签超时关闭时间
CLOSE_TAB_DELAY = 1.0  # 关闭标签后等待时间
PAGE_TURN_DELAY = random.uniform(3, 5)  # 翻页后加载时间
PAGE_RESET_DELAY = 5  # 修复：添加页面重置延迟配置
BUTTON_CLICK_DELAY = random.uniform(0.4, 0.6)  # 鼠标移动耗时
POST_CLICK_WAIT = 3.5  # 点击后等待新标签时间
POST_SUCCESS_WAIT = random.uniform(1.5, 2.5)  # 下载成功后等待时间
RETRY_WAIT = random.uniform(1.0, 1.5)  # 重试间隔

# 重试次数配置
MAX_RETRY_PER_BUTTON = 8  # 单个按钮最大重试次数
MAX_PAGE_RESET_TIMES = 2  # 最大翻页重置次数
TAB_DETECT_RETRY_TIMES = 2  # 标签页检测重试次数
WINDOW_FIND_RETRY_TIMES = 3  # 窗口查找重试次数
WINDOW_FIND_INTERVAL = 1.5  # 窗口查找间隔
TAB_DETECT_INTERVAL = 0.8  # 标签页检测间隔

# 窗口/坐标配置
MAX_ENUM_DEPTH = 20  # 子窗口枚举深度
EDGE_CLICK_OFFSET_X = -5  # Edge专属X轴偏移（避免点击边框）
EDGE_CLICK_OFFSET_Y = 0  # Y轴基础偏移

# 页面专属偏移策略（严格按需求定义）
# 页面1：补偿+3px，按钮1偏移0→±4→±8...，按钮2及以后步长6（0→±6→±12...）
PAGE1_BASE_SPACING_OFFSET = 3  # 修正：基础间距补偿从2px改为3px
PAGE1_BUTTON1_OFFSET_STEP = 4  # 按钮1偏移步长
PAGE1_BUTTON2_OFFSET_STEP = 6  # 按钮2及以后偏移步长

# 页面2：复用页面1X坐标，按钮1偏移同页面1，按钮2及以后0→±6→±12...
PAGE2_STEP1_OFFSET = 65  # 按钮2及以后基础偏移
PAGE2_OFFSET_STEP = 6  # 页面2按钮2及以后偏移步长

# Edge浏览器配置
BROWSER_CONFIG = {
    "Microsoft Edge": {
        "process_name": "msedge.exe",
        "window_classes": ["Chrome_WidgetWin_1"],
        "tab_classes": ["TabStrip"]
    }
}
SELECTED_BROWSER = "Microsoft Edge"
USE_FOREGROUND_WINDOW = True  # 强制浏览器前台激活

# 全局状态
is_running = True
is_paused = False
downloaded_total = 0
downloaded_files = set()
screen_size = pyautogui.size()
system_scaling = 1.0  # 系统缩放比例
saved_region = None  # 框选的按钮区域
page1_buttons = []  # 页面1成功按钮记录 [(base_x, final_y, offset), ...]
current_page = 1  # 当前页码
current_template = None  # 下载按钮模板
current_template_size = None  # 模板尺寸（h, w）
browser_main_handle = None  # 浏览器主窗口句柄
# 窗口缓存
tab_count_cache = 1
cache_expire_time = 3.0  # 缓存有效期（3秒）
last_tab_count_time = 0.0


# ==================== 二、基础工具函数 ====================
def get_system_scaling():
    """获取系统缩放比例，修正坐标偏差"""
    try:
        return ctypes.windll.user32.GetDpiForSystem() / 96.0
    except:
        return 1.0


def init_download_path():
    """初始化下载目录，记录初始文件"""
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
    downloaded_files.clear()
    for filename in os.listdir(DOWNLOAD_PATH):
        file_path = os.path.abspath(os.path.join(DOWNLOAD_PATH, filename))
        if (os.path.isfile(file_path) and
            not any(filename.lower().endswith(suffix) for suffix in ['.crdownload', '.part', '.tmp', '.downloading']) and
            os.path.getsize(file_path) >= FILE_MIN_SIZE):
            downloaded_files.add(file_path)
    print(f"✅ 下载路径：{DOWNLOAD_PATH} | 初始文件数：{len(downloaded_files)}")


def take_screenshot():
    """截取全屏并保存，返回是否有效"""
    try:
        ImageGrab.grab(bbox=(0, 0, screen_size[0], screen_size[1])).save(SCREENSHOT_PATH)
        return os.path.getsize(SCREENSHOT_PATH) >= 102400  # ≥100KB为有效截图
    except Exception as e:
        print(f"❌ 截图失败：{str(e)}")
        return False


def load_template():
    """加载下载按钮模板"""
    global current_template, current_template_size
    template_path = "download_icon.png"
    if not os.path.exists(template_path):
        print(f"❌ 未找到模板文件：{template_path}（请放在脚本目录）")
        exit(1)
    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    if template is None or template.size == 0:
        print(f"❌ 模板文件无效或损坏")
        exit(1)
    current_template = template
    current_template_size = template.shape[:2]
    print(f"✅ 模板尺寸：{current_template_size[0]}x{current_template_size[1]}px")


def is_valid_coordinate(x, y):
    """校验坐标是否在屏幕范围内"""
    return 0 <= x <= screen_size[0] and 0 <= y <= screen_size[1]


def detect_new_file(initial_files):
    """检测下载目录新增文件（核心判断标准）"""
    time.sleep(DOWNLOAD_DETECT_DELAY)
    current_files = set()
    for filename in os.listdir(DOWNLOAD_PATH):
        file_path = os.path.abspath(os.path.join(DOWNLOAD_PATH, filename))
        if (os.path.isfile(file_path) and
            not any(filename.lower().endswith(suffix) for suffix in ['.crdownload', '.part', '.tmp', '.downloading']) and
            os.path.getsize(file_path) >= FILE_MIN_SIZE):
            current_files.add(file_path)
    new_files = current_files - initial_files
    if new_files:
        downloaded_files.update(new_files)
        print(f"✅ 新增文件：{[os.path.basename(f) for f in new_files]}")
        return True
    return False


# ==================== 三、浏览器窗口管理 ====================
def get_browser_main_handle():
    """查找Edge主窗口句柄"""
    global browser_main_handle
    if browser_main_handle and win32gui.IsWindow(browser_main_handle) and win32gui.IsWindowVisible(browser_main_handle):
        return browser_main_handle

    browser_info = BROWSER_CONFIG[SELECTED_BROWSER]
    process_name = browser_info["process_name"].lower()
    window_classes = browser_info["window_classes"]

    for retry in range(WINDOW_FIND_RETRY_TIMES):
        print(f"📌 第{retry+1}/{WINDOW_FIND_RETRY_TIMES}次查找Edge窗口...")
        target_pids = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == process_name:
                    target_pids.append(proc.info['pid'])
                    print(f"📌 找到Edge进程：PID={proc.info['pid']}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not target_pids:
            print(f"⚠️ 未找到Edge进程，重试中...")
            time.sleep(WINDOW_FIND_INTERVAL)
            continue

        candidate_windows = []
        def enum_window(hwnd, args):
            nonlocal candidate_windows, target_pids
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                rect = win32gui.GetWindowRect(hwnd)
                if (rect[2]-rect[0] < 300) or (rect[3]-rect[1] < 200):
                    return True
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid not in target_pids:
                    return True
                if win32gui.GetClassName(hwnd) not in window_classes:
                    return True
                candidate_windows.append(hwnd)
            except:
                pass
            return True

        win32gui.EnumWindows(enum_window, {})
        if candidate_windows:
            candidate_windows.sort(key=lambda hwnd: (win32gui.GetWindowRect(hwnd)[2]-win32gui.GetWindowRect(hwnd)[0])*(win32gui.GetWindowRect(hwnd)[3]-win32gui.GetWindowRect(hwnd)[1]), reverse=True)
            browser_main_handle = candidate_windows[0]
            size = f"{win32gui.GetWindowRect(browser_main_handle)[2]-win32gui.GetWindowRect(browser_main_handle)[0]}x{win32gui.GetWindowRect(browser_main_handle)[3]-win32gui.GetWindowRect(browser_main_handle)[1]}"
            print(f"✅ 找到Edge主窗口：句柄={browser_main_handle} | 大小={size}")
            return browser_main_handle

        print(f"⚠️ 未找到匹配的Edge窗口，重试中...")
        time.sleep(WINDOW_FIND_INTERVAL)

    print(f"❌ 多次重试后仍未找到Edge窗口，程序退出")
    exit(1)


def count_browser_tabs():
    """简化标签页计数（带缓存）"""
    global tab_count_cache, last_tab_count_time
    current_time = time.time()
    if current_time - last_tab_count_time < cache_expire_time:
        return tab_count_cache

    main_handle = get_browser_main_handle()
    browser_info = BROWSER_CONFIG[SELECTED_BROWSER]
    child_handles = []
    win32gui.EnumChildWindows(main_handle, lambda h, args: args.append(h) or True, child_handles)
    print(f"📌 枚举子窗口数：{len(child_handles)}（简化枚举）")

    tab_count = 0
    for hwnd in child_handles:
        try:
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetClassName(hwnd) in browser_info["tab_classes"]:
                tab_count += 1
        except:
            continue

    tab_count_cache = max(tab_count, 1)
    last_tab_count_time = current_time
    print(f"📌 Edge标签页数量：{tab_count_cache}个（缓存3秒）")
    return tab_count_cache


def is_new_tab_opened():
    """简化新标签检测"""
    global tab_count_cache
    initial_count = count_browser_tabs()
    time.sleep(TAB_DETECT_INTERVAL)
    current_count = count_browser_tabs()
    is_opened = current_count > initial_count
    print(f"📌 标签页变化：{initial_count}→{current_count}（新增：{'是' if is_opened else '否'}）")
    return is_opened


def close_new_tab():
    """关闭新增标签页"""
    current_count = count_browser_tabs()
    if current_count <= 1:
        print(f"⚠️ 仅{current_count}个标签页，无需关闭")
        return True

    print(f"📌 关闭新增标签页（当前{current_count}个）")
    win32gui.SetForegroundWindow(get_browser_main_handle())
    time.sleep(0.5)
    pyautogui.hotkey('ctrl', 'w')
    time.sleep(CLOSE_TAB_DELAY)
    new_count = count_browser_tabs()
    print(f"✅ 关闭后标签页数量：{new_count}个")
    return new_count < current_count


# ==================== 四、核心功能模块（严格按需求实现） ====================
def select_region():
    """让用户框选下载按钮区域"""
    global saved_region
    win32gui.SetForegroundWindow(get_browser_main_handle())
    time.sleep(1)

    while not take_screenshot():
        time.sleep(2)
    img = cv2.imread(SCREENSHOT_PATH)
    img_copy = img.copy()
    img_h, img_w = img.shape[:2]
    ref_point = []
    cropping = False

    def click_event(event, x, y, flags, param):
        nonlocal ref_point, cropping
        if event == cv2.EVENT_LBUTTONDOWN:
            ref_point = [(x, y)]
            cropping = True
        elif event == cv2.EVENT_LBUTTONUP:
            ref_point.append((x, y))
            cropping = False
            cv2.rectangle(img_copy, ref_point[0], ref_point[1], (0, 255, 0), 4)
            cv2.imshow("框选所有下载按钮区域（按ESC确认）", img_copy)
        elif event == cv2.EVENT_MOUSEMOVE and cropping:
            temp_img = img_copy.copy()
            cv2.rectangle(temp_img, ref_point[0], (x, y), (0, 255, 0), 3)
            cv2.imshow("框选所有下载按钮区域（按ESC确认）", temp_img)

    cv2.namedWindow("框选所有下载按钮区域（按ESC确认）", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("框选所有下载按钮区域（按ESC确认）", img_w//2, img_h//2)
    cv2.imshow("框选所有下载按钮区域（按ESC确认）", img_copy)
    cv2.setMouseCallback("框选所有下载按钮区域（按ESC确认）", click_event)

    while cv2.waitKey(1) != 27:
        pass
    cv2.destroyAllWindows()

    if len(ref_point) == 2:
        x1, y1 = min(ref_point[0][0], ref_point[1][0]), min(ref_point[0][1], ref_point[1][1])
        x2, y2 = max(ref_point[0][0], ref_point[1][0]), max(ref_point[0][1], ref_point[1][1])
        saved_region = (x1, y1, x2, y2)
        print(f"✅ 框选区域：({x1},{y1})→({x2},{y2})（大小：{x2-x1}x{y2-y1}px）")
        return True
    else:
        print("⚠️ 框选失败，请重新尝试")
        return False


def find_buttons():
    """识别下载按钮（加强去重，避免异常间距）"""
    if not saved_region:
        print("❌ 未框选按钮区域，无法识别")
        return []

    x1, y1, x2, y2 = saved_region
    t_h, t_w = current_template_size
    take_screenshot()
    img = cv2.imread(SCREENSHOT_PATH)
    roi_gray = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)

    current_confidence = INIT_CONFIDENCE
    buttons = []
    while len(buttons) < TARGET_BUTTON_COUNT and current_confidence >= MIN_CONFIDENCE:
        result = cv2.matchTemplate(roi_gray, current_template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= current_confidence)

        current_buttons = []
        for pt in zip(*locations[::-1]):
            center_x = x1 + pt[0] + t_w // 2
            center_y = y1 + pt[1] + t_h // 2
            current_buttons.append((center_x, center_y))

        # 按Y坐标排序+严格去重（间距≥按钮高度60%）
        current_buttons.sort(key=lambda x: x[1])
        unique_buttons = []
        min_spacing = t_h * DUPLICATE_THRESHOLD_RATIO
        for btn in current_buttons:
            if not unique_buttons or btn[1] - unique_buttons[-1][1] >= min_spacing:
                unique_buttons.append(btn)

        buttons = unique_buttons[:TARGET_BUTTON_COUNT]
        if len(buttons) < TARGET_BUTTON_COUNT:
            print(f"⚠️ 置信度{current_confidence:.2f}：识别到{len(buttons)}个按钮（不足10个）")
            current_confidence -= CONFIDENCE_STEP
        else:
            break

    # 输出识别结果
    print(f"📌 第{current_page}页识别结果：{len(buttons)}个有效按钮")
    for i, (x, y) in enumerate(buttons, 1):
        print(f"   按钮{i}：({int(x)},{int(y)})")
    return buttons


def page1_offset_strategy(button_idx, attempt):
    """页面1偏移策略（严格按需求）：
    - 按钮1：0 → 4 → -4 → 8 → -8 → 12 → -12...
    - 按钮2及以后：0 → 6 → -6 → 12 → -12...
    """
    if button_idx == 0:
        # 按钮1：先0偏移，再±4递增
        if attempt == 0:
            return 0
        step = (attempt // 2) * PAGE1_BUTTON1_OFFSET_STEP
        return step if attempt % 2 == 1 else -step
    else:
        # 按钮2及以后：先0偏移，再±6递增
        if attempt == 0:
            return 0
        step = (attempt // 2) * PAGE1_BUTTON2_OFFSET_STEP
        return step if attempt % 2 == 1 else -step


def page2_offset_strategy(button_idx, attempt):
    """页面2偏移策略（严格按需求）：
    - 按钮1：同页面1按钮1（0→±4→±8...）
    - 按钮2及以后：0 → 6 → -6 → 12 → -12...（基于前一个最终Y+65px）
    """
    if button_idx == 0:
        # 按钮1：同页面1按钮1
        if attempt == 0:
            return 0
        step = (attempt // 2) * PAGE1_BUTTON1_OFFSET_STEP
        return step if attempt % 2 == 1 else -step
    else:
        # 按钮2及以后：先0偏移，再±6递增
        if attempt == 0:
            return 0
        step = (attempt // 2) * PAGE2_OFFSET_STEP
        return step if attempt % 2 == 1 else -step


def try_click(base_x, base_y, offset_strategy, button_idx):
    """尝试点击按钮（文件检测优先）"""
    win32gui.SetForegroundWindow(get_browser_main_handle())
    time.sleep(0.5)

    initial_files = set(downloaded_files)
    initial_tab_count = count_browser_tabs()

    for attempt in range(MAX_RETRY_PER_BUTTON):
        if not is_running:
            break
        while is_paused:
            time.sleep(0.5)

        # 计算点击坐标
        offset = offset_strategy(button_idx, attempt)
        click_x = int(base_x + EDGE_CLICK_OFFSET_X)
        click_y = int(base_y + EDGE_CLICK_OFFSET_Y + offset)

        if not is_valid_coordinate(click_x, click_y):
            print(f"⚠️ 尝试{attempt+1}：坐标({click_x},{click_y})超出屏幕，跳过")
            continue

        # 执行点击
        try:
            print(f"📝 尝试{attempt+1}：点击({click_x},{click_y})（偏移：{offset}px）")
            pyautogui.moveTo(click_x, click_y, duration=BUTTON_CLICK_DELAY)
            pyautogui.click()
            time.sleep(POST_CLICK_WAIT)

            # 优先检测新增文件
            if detect_new_file(initial_files):
                if count_browser_tabs() > initial_tab_count:
                    close_new_tab()
                return (True, offset)

            # 辅助：有新标签但无文件，等待超时后重试
            if is_new_tab_opened():
                print(f"⚠️ 有新标签但无文件，等待超时后重试")
                time.sleep(NEW_PAGE_TIMEOUT)
                if detect_new_file(initial_files):
                    close_new_tab()
                    return (True, offset)
                else:
                    close_new_tab()

        except Exception as e:
            print(f"⚠️ 尝试{attempt+1}失败：{str(e)}")

        time.sleep(RETRY_WAIT)

    # 清理残留标签页
    if count_browser_tabs() > initial_tab_count:
        close_new_tab()
    return (False, 0)


def download_page1(buttons):
    """页面1下载逻辑（目标Y=前一个最终Y+初始间距+3px）"""
    global downloaded_total, page1_buttons
    page1_buttons = []
    if len(buttons) < TARGET_BUTTON_COUNT:
        print("❌ 按钮数量不足，终止下载")
        return False

    # 计算相邻按钮初始间距
    initial_spacings = [buttons[i][1] - buttons[i-1][1] for i in range(1, len(buttons))]
    for i, spacing in enumerate(initial_spacings, 1):
        print(f"📏 按钮{i}与{i+1}初始间距：{int(spacing)}px（补偿+{PAGE1_BASE_SPACING_OFFSET}px）")

    # 逐个下载按钮
    for idx in range(len(buttons)):
        if not is_running:
            break
        while is_paused:
            time.sleep(0.5)

        base_x, base_y = buttons[idx]
        print(f"\n📥 第{current_page}页按钮{idx+1}（基准坐标：{int(base_x)},{int(base_y)}）")

        # 计算目标Y坐标（严格按需求）
        if idx == 0:
            target_y = base_y  # 按钮1：基准Y
        else:
            if len(page1_buttons) != idx:
                print(f"❌ 前序按钮{idx}下载失败，终止后续")
                break
            prev_final_y = page1_buttons[idx-1][1] + page1_buttons[idx-1][2]
            target_y = prev_final_y + initial_spacings[idx-1] + PAGE1_BASE_SPACING_OFFSET

        # 尝试点击
        success, offset = try_click(base_x, target_y, page1_offset_strategy, idx)
        if success:
            downloaded_total += 1
            page1_buttons.append((base_x, target_y, offset))
            print(f"✅ 按钮{idx+1}下载成功（偏移：{offset}px）")
            time.sleep(POST_SUCCESS_WAIT)
        else:
            print(f"❌ 按钮{idx+1}下载失败")
            if idx == 0:
                print("❌ 按钮1失败，终止页面1下载")
                break

    return len(page1_buttons) == TARGET_BUTTON_COUNT


def download_page2():
    """页面2下载逻辑（复用页面1X坐标，严格按需求）"""
    global downloaded_total
    if not page1_buttons:
        print("❌ 未获取页面1数据，无法下载页面2")
        return False

    button_count = min(len(page1_buttons), TARGET_BUTTON_COUNT)
    print(f"\n📋 第{current_page}页（页面2模式）下载：{button_count}个按钮（复用页面1X坐标）")
    success_count = 0

    for idx in range(button_count):
        if not is_running:
            break
        while is_paused:
            time.sleep(0.5)

        # 强制复用页面1的X坐标（忽略第2页识别的X）
        base_x = page1_buttons[idx][0]
        print(f"\n📥 第{current_page}页按钮{idx+1}（复用页面1X：{int(base_x)}）")

        # 计算目标Y坐标（严格按需求）
        if idx == 0:
            target_y = page1_buttons[0][1]  # 复用页面1按钮1的Y
        else:
            prev_final_y = page1_buttons[idx-1][1] + page1_buttons[idx-1][2]
            target_y = prev_final_y + PAGE2_STEP1_OFFSET  # 基础偏移65px

        # 尝试点击
        success, offset = try_click(base_x, target_y, page2_offset_strategy, idx)
        if success:
            downloaded_total += 1
            success_count += 1
            print(f"✅ 按钮{idx+1}下载成功（偏移：{offset}px）")
            time.sleep(POST_SUCCESS_WAIT)
        else:
            print(f"❌ 按钮{idx+1}下载失败")

    return success_count == button_count


def turn_page():
    """翻页操作"""
    global current_page
    win32gui.SetForegroundWindow(get_browser_main_handle())
    time.sleep(0.5)

    print(f"\n📖 翻页到第{current_page+1}页...")
    pyautogui.press('right')
    time.sleep(PAGE_TURN_DELAY)
    current_page += 1
    print(f"✅ 已翻到第{current_page}页")
    return True


def reset_page_by_turning():
    """翻页重置页面（修复变量引用）"""
    print(f"\n🔄 执行页面重置（当前第{current_page}页）")
    pyautogui.press('left')  # 向前翻
    time.sleep(PAGE_RESET_DELAY)
    pyautogui.press('right')  # 向后翻回原页
    time.sleep(PAGE_RESET_DELAY)
    print(f"✅ 页面重置完成")
    return True


# ==================== 五、键盘控制 ====================
def on_key_press(key):
    """键盘事件监听：ESC停止，空格暂停/继续"""
    global is_running, is_paused
    try:
        if key == keyboard.Key.esc:
            print("\n⚠️ 检测到ESC键，停止任务")
            is_running = False
            return False  # 停止监听
        elif key == keyboard.Key.space:
            is_paused = not is_paused
            print(f"\n{'⏸️  任务暂停' if is_paused else '▶️  任务继续'}")
    except Exception as e:
        print(f"⚠️ 键盘监听异常：{str(e)}")


# ==================== 六、主程序 ====================
def main():
    global system_scaling, is_running
    system_scaling = get_system_scaling()

    # 打印启动信息
    print("=" * 80)
    print(f"📌 知网下载器（页面{CURRENT_PAGE_TYPE}模式）- 需求匹配版")
    print(f"📌 核心策略：页面1补偿+3px | 按钮1偏移0→±4 | 按钮2+步长6")
    print(f"📌 适配环境：Edge浏览器（前台激活）| 分辨率：{screen_size[0]}x{screen_size[1]} | 缩放：{system_scaling:.1f}x")
    print(f"📌 快捷键：ESC=停止 | 空格=暂停/继续")
    print("=" * 80)

    # 初始化流程
    init_download_path()
    load_template()
    get_browser_main_handle()
    count_browser_tabs()

    # 框选按钮区域
    print("\n📌 请框选所有下载按钮区域（按ESC确认）")
    while not saved_region:
        if select_region():
            break
        time.sleep(2)

    # 启动键盘监听
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()
    print(f"\n✅ 初始化完成，开始识别第{current_page}页按钮...")

    # 主循环
    page_reset_count = 0
    try:
        while is_running:
            # 1. 识别按钮
            buttons = find_buttons()
            if not buttons or len(buttons) < TARGET_BUTTON_COUNT:
                if page_reset_count < MAX_PAGE_RESET_TIMES:
                    print(f"⚠️ 按钮识别不足，尝试页面重置（{page_reset_count+1}/{MAX_PAGE_RESET_TIMES}）")
                    reset_page_by_turning()
                    page_reset_count += 1
                    time.sleep(RETRY_WAIT)
                    continue
                else:
                    print("❌ 多次重置仍无法识别足够按钮，终止任务")
                    break

            # 2. 下载当前页
            print(f"\n🚀 启动第{current_page}页下载（{len(buttons)}个按钮）")
            if CURRENT_PAGE_TYPE == 1:
                download_success = download_page1(buttons)
            else:
                download_success = download_page2()

            # 3. 翻页逻辑
            if download_success and is_running:
                page_reset_count = 0
                if not turn_page():
                    print("⚠️ 翻页失败，终止任务")
                    break
            else:
                if page_reset_count < MAX_PAGE_RESET_TIMES:
                    print(f"⚠️ 第{current_page}页下载未完成，尝试重置（{page_reset_count+1}/{MAX_PAGE_RESET_TIMES}）")
                    reset_page_by_turning()
                    page_reset_count += 1
                    time.sleep(RETRY_WAIT)
                else:
                    print(f"⚠️ 多次重试仍未完成，终止任务")
                    break

    except Exception as e:
        print(f"\n❌ 程序异常：{str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理资源
        listener.stop()
        listener.join()
        if os.path.exists(SCREENSHOT_PATH):
            try:
                os.remove(SCREENSHOT_PATH)
            except:
                pass

        # 打印统计信息
        print(f"\n" + "=" * 80)
        print(f"🎉 任务结束")
        print(f"📊 统计：处理{current_page}页 | 成功下载{downloaded_total}个文件")
        print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ 用户手动中断任务")
        if os.path.exists(SCREENSHOT_PATH):
            os.remove(SCREENSHOT_PATH)
        print(f"📊 成功下载{downloaded_total}个文件")