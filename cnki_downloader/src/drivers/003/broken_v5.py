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

# ==================== 核心配置（精简优化） ====================
CURRENT_PAGE_TYPE = 1  # 页面类型（1/2）- 可根据需求切换
TARGET_BUTTON_COUNT = 10  # 每页必须识别10个按钮
DOWNLOAD_PATH = r"D:\Downloads"  # 下载目录
INIT_CONFIDENCE = 0.45  # 初始匹配置信度
MIN_CONFIDENCE = 0.3  # 最低置信度
CONFIDENCE_STEP = 0.05  # 置信度降级步长
SCREENSHOT_PATH = "temp_screenshot.png"
FILE_MIN_SIZE = 1024  # 最小文件大小（1KB）
DOWNLOAD_DETECT_DELAY = 3.5  # 下载检测延迟（适配Edge）
NEW_PAGE_TIMEOUT = 8  # 新标签超时关闭时间
CLOSE_TAB_DELAY = 1.5  # 关闭标签后等待时间
PAGE_TURN_DELAY = random.uniform(4, 6)  # 翻页后加载时间
PAGE_RESET_DELAY = 5  # 翻页重置后加载时间
DUPLICATE_THRESHOLD_RATIO = 0.3  # 按钮去重阈值（高度30%）
MAX_RETRY_PER_BUTTON = 10  # 单个按钮最大重试次数（适配长偏移序列）
MAX_PAGE_RESET_TIMES = 2  # 最大翻页重置次数
BUTTON_CLICK_DELAY = random.uniform(0.5, 0.8)  # 鼠标移动耗时（Edge适配）
POST_CLICK_WAIT = 4.5  # 点击后等待新标签时间
POST_SUCCESS_WAIT = random.uniform(2, 3)  # 下载成功后等待时间
RETRY_WAIT = random.uniform(1.5, 2.5)  # 重试间隔
RECOGNITION_RETRY_WAIT = 10  # 按钮识别失败重试间隔
PAGE_DOWNLOAD_RETRY_WAIT = 5  # 页面下载失败重试间隔
TAB_DETECT_RETRY_TIMES = 4  # 标签页检测重试次数
TAB_DETECT_INTERVAL = 1.0  # 标签页检测间隔
WINDOW_FIND_RETRY_TIMES = 5  # 窗口查找重试次数
WINDOW_FIND_INTERVAL = 1.5  # 窗口查找间隔
MAX_ENUM_DEPTH = 20  # 最大窗口枚举深度
EDGE_CLICK_OFFSET_X = -5  # Edge专属X轴偏移（避免点击边框）
EDGE_CLICK_OFFSET_Y = 0  # Y轴基础偏移

# 页面专属配置
PAGE1_BASE_SPACING_OFFSET = 2  # 页面1基础间距补偿
PAGE2_STEP1_OFFSET = 65  # 页面2初始步长偏移
PAGE2_STEP2_COUNT = 3  # 页面2第二步偏移次数
PAGE2_STEP2_STEP = 6  # 页面2第二步步长
PAGE2_STEP3_STEP = 4  # 页面2第三步步长

# 浏览器适配配置
BROWSER_CONFIG = {
    "Microsoft Edge": {
        "process_name": "msedge.exe",
        "tab_title_keywords": ["新标签页", "New Tab", "知网", "检索-中国知网"],
        "window_class": ["Chrome_WidgetWin_1"],
        "extra_title_exclude": ["设置", "下载"]
    }
}
SELECTED_BROWSER = "Microsoft Edge"
USE_FOREGROUND_WINDOW = True  # Edge必须前台激活

# 全局状态（精简必要变量）
is_running = True
is_paused = False
downloaded_total = 0
downloaded_files = set()
screen_size = pyautogui.size()
saved_region = None
page1_buttons = []  # 页面1成功按钮记录 [(base_x, 最终Y, 偏移量), ...]
page2_buttons = []  # 页面2成功按钮记录 [(base_x, 最终Y, 偏移量), ...]
current_page = 1
current_template = None
current_template_size = None
browser_main_handle = None
pre_click_tab_count = 1


# ==================== 核心工具函数（精简去冗余） ====================
def get_system_scaling():
    """获取系统缩放比例"""
    try:
        return ctypes.windll.user32.GetDpiForSystem() / 96.0
    except:
        return 1.0


def init_download_path():
    """初始化下载目录"""
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
    downloaded_files.clear()
    for filename in os.listdir(DOWNLOAD_PATH):
        file_path = os.path.abspath(os.path.join(DOWNLOAD_PATH, filename))
        if os.path.isfile(file_path) and not any(filename.lower().endswith(suffix) for suffix in ['.crdownload', '.part', '.tmp', '.downloading', '.crdownload.tmp']) and os.path.getsize(file_path) >= FILE_MIN_SIZE:
            downloaded_files.add(file_path)
    print(f"✅ 下载路径：{DOWNLOAD_PATH} | 初始文件数：{len(downloaded_files)}")


def take_screenshot():
    """截取屏幕"""
    try:
        ImageGrab.grab(bbox=(0, 0, screen_size[0], screen_size[1])).save(SCREENSHOT_PATH)
        return os.path.getsize(SCREENSHOT_PATH) >= 102400  # ≥100KB为有效
    except Exception as e:
        print(f"❌ 截图失败：{str(e)}")
        return False


def load_template():
    """加载下载按钮模板"""
    global current_template, current_template_size
    template_path = "download_icon.png"
    if not os.path.exists(template_path):
        print(f"❌ 未找到模板：{template_path}")
        exit(1)
    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    if template is None or template.size == 0:
        print(f"❌ 模板无效/损坏")
        exit(1)
    current_template = template
    current_template_size = template.shape[:2]
    print(f"✅ 模板尺寸：{current_template_size[0]}x{current_template_size[1]}px")


def is_valid_coordinate(x, y):
    """校验坐标有效性"""
    return 0 <= x <= screen_size[0] and 0 <= y <= screen_size[1]


def detect_new_file(initial_files):
    """检测新增下载文件"""
    time.sleep(DOWNLOAD_DETECT_DELAY)
    current_files = set()
    for filename in os.listdir(DOWNLOAD_PATH):
        file_path = os.path.abspath(os.path.join(DOWNLOAD_PATH, filename))
        if os.path.isfile(file_path) and not any(filename.lower().endswith(suffix) for suffix in ['.crdownload', '.part', '.tmp', '.downloading', '.crdownload.tmp']) and os.path.getsize(file_path) >= FILE_MIN_SIZE:
            current_files.add(file_path)
    new_files = current_files - initial_files
    if new_files:
        downloaded_files.update(new_files)
        print(f"✅ 新增文件：{[os.path.basename(f) for f in new_files]}")
        return True
    return False


def get_browser_main_handle():
    """查找浏览器主窗口"""
    global browser_main_handle
    if browser_main_handle and win32gui.IsWindow(browser_main_handle) and win32gui.IsWindowVisible(browser_main_handle):
        return browser_main_handle

    browser_info = BROWSER_CONFIG.get(SELECTED_BROWSER)
    if not browser_info:
        print(f"❌ 未配置浏览器：{SELECTED_BROWSER}")
        return None

    process_name = browser_info["process_name"].lower()
    window_classes = browser_info.get("window_class", [])

    for retry in range(WINDOW_FIND_RETRY_TIMES):
        print(f"📌 第{retry+1}/{WINDOW_FIND_RETRY_TIMES}次查找{SELECTED_BROWSER}窗口...")
        target_pids = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == process_name:
                    has_visible_window = False
                    def check_visible_window(hwnd, args):
                        nonlocal has_visible_window, proc
                        try:
                            if win32gui.IsWindowVisible(hwnd):
                                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                                if pid == proc.info['pid']:
                                    has_visible_window = True
                        except:
                            pass
                        return True
                    win32gui.EnumWindows(check_visible_window, proc)
                    if has_visible_window:
                        target_pids.append(proc.info['pid'])
                        print(f"📌 找到目标进程：PID={proc.info['pid']}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not target_pids:
            print(f"⚠️ 未找到有可见窗口的{process_name}进程，重试中...")
            time.sleep(WINDOW_FIND_INTERVAL)
            continue

        candidate_windows = []
        def enum_window(hwnd, args):
            nonlocal candidate_windows, target_pids, window_classes, browser_info
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                rect = win32gui.GetWindowRect(hwnd)
                width = rect[2] - rect[0]
                height = rect[3] - rect[1]
                if width < 300 or height < 200:
                    return True
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid not in target_pids:
                    return True
                hwnd_class = win32gui.GetClassName(hwnd)
                if window_classes and hwnd_class not in window_classes:
                    return True
                if SELECTED_BROWSER == "Microsoft Edge":
                    window_title = win32gui.GetWindowText(hwnd)
                    if not any(keyword in window_title for keyword in browser_info["tab_title_keywords"]):
                        return True
                candidate_windows.append(hwnd)
            except:
                pass
            return True

        win32gui.EnumWindows(enum_window, {})
        if candidate_windows:
            candidate_windows.sort(key=lambda hwnd: (win32gui.GetWindowRect(hwnd)[2]-win32gui.GetWindowRect(hwnd)[0])*(win32gui.GetWindowRect(hwnd)[3]-win32gui.GetWindowRect(hwnd)[1]), reverse=True)
            browser_main_handle = candidate_windows[0]
            window_title = win32gui.GetWindowText(browser_main_handle)
            window_rect = win32gui.GetWindowRect(browser_main_handle)
            window_size = f"{window_rect[2]-window_rect[0]}x{window_rect[3]-window_rect[1]}"
            print(f"✅ 成功找到{SELECTED_BROWSER}窗口！")
            print(f"   - 句柄：{browser_main_handle} | 标题：{window_title[:50]}... | 大小：{window_size}px")
            return browser_main_handle

        print(f"⚠️ 未找到匹配的{SELECTED_BROWSER}窗口，重试中...")
        time.sleep(WINDOW_FIND_INTERVAL)

    print(f"❌ 经过{WINDOW_FIND_RETRY_TIMES}次重试，仍未找到{SELECTED_BROWSER}可见窗口！")
    return None


def iterative_enum_child_windows(hwnd, child_handles):
    """迭代枚举子窗口（无栈溢出）"""
    try:
        window_stack = [(hwnd, 0)]
        while window_stack:
            current_hwnd, depth = window_stack.pop()
            if depth > MAX_ENUM_DEPTH:
                continue
            direct_children = []
            def enum_child(hwnd_child, args):
                args.append(hwnd_child)
                return True
            win32gui.EnumChildWindows(current_hwnd, enum_child, direct_children)
            for child_hwnd in direct_children:
                child_handles.append(child_hwnd)
                window_stack.append((child_hwnd, depth + 1))
    except Exception as e:
        print(f"⚠️ 枚举子窗口异常（已忽略）：{str(e)}")


def count_browser_tabs():
    """统计标签页数量"""
    main_handle = get_browser_main_handle()
    if not main_handle:
        print(f"⚠️ 未找到浏览器主窗口，默认标签数：{pre_click_tab_count}个")
        return pre_click_tab_count

    browser_info = BROWSER_CONFIG[SELECTED_BROWSER]
    tab_title_keywords = browser_info["tab_title_keywords"]
    extra_title_exclude = browser_info.get("extra_title_exclude", [])
    all_child_handles = []
    iterative_enum_child_windows(main_handle, all_child_handles)
    print(f"📌 枚举到{len(all_child_handles)}个子窗口")

    tab_handles = []
    for hwnd in all_child_handles:
        try:
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if any(keyword in title for keyword in tab_title_keywords) and not any(exclude in title for exclude in extra_title_exclude):
                    rect = win32gui.GetWindowRect(hwnd)
                    width = rect[2] - rect[0]
                    height = rect[3] - rect[1]
                    if 150 <= width <= 1200 and 30 <= height <= 80:
                        tab_handles.append(hwnd)
        except:
            continue

    final_tab_count = len(tab_handles)
    for retry in range(1, TAB_DETECT_RETRY_TIMES):
        time.sleep(TAB_DETECT_INTERVAL)
        temp_child_handles = []
        iterative_enum_child_windows(main_handle, temp_child_handles)
        temp_tab_count = 0
        for hwnd in temp_child_handles:
            try:
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if any(keyword in title for keyword in tab_title_keywords) and not any(exclude in title for exclude in extra_title_exclude):
                        rect = win32gui.GetWindowRect(hwnd)
                        width = rect[2] - rect[0]
                        height = rect[3] - rect[1]
                        if 150 <= width <= 1200 and 30 <= height <= 80:
                            temp_tab_count += 1
            except:
                continue
        final_tab_count = max(final_tab_count, temp_tab_count)

    final_tab_count = max(final_tab_count, 1)
    print(f"📌 {SELECTED_BROWSER}标签页数量：{final_tab_count}个")
    return final_tab_count


def is_new_tab_opened():
    """检测新标签页是否打开"""
    global pre_click_tab_count
    current_tab_counts = []
    for _ in range(TAB_DETECT_RETRY_TIMES):
        current_tab_counts.append(count_browser_tabs())
        time.sleep(TAB_DETECT_INTERVAL)
    current_tab_count = max(current_tab_counts)
    is_opened = current_tab_count > pre_click_tab_count
    print(f"📌 标签页变化：{pre_click_tab_count}→{current_tab_count}（新标签{'已弹出' if is_opened else '未弹出'}）")
    if is_opened:
        pre_click_tab_count = current_tab_count
    return is_opened


def close_new_tab():
    """关闭新标签页"""
    current_tab_count = max([count_browser_tabs() for _ in range(TAB_DETECT_RETRY_TIMES)])
    if current_tab_count <= 1:
        print(f"⚠️ 当前标签页仅{current_tab_count}个，无需关闭")
        return True

    try:
        print(f"⚠️ 新标签页{NEW_PAGE_TIMEOUT}秒无反应，关闭中...")
        main_handle = get_browser_main_handle()
        if main_handle:
            win32gui.SetForegroundWindow(main_handle)
            time.sleep(0.8)
        pyautogui.hotkey('ctrl', 'w')
        time.sleep(CLOSE_TAB_DELAY)
        new_tab_count = min([count_browser_tabs() for _ in range(TAB_DETECT_RETRY_TIMES)])
        print(f"✅ 关闭后标签页数量：{new_tab_count}个")
        global pre_click_tab_count
        pre_click_tab_count = new_tab_count
        return new_tab_count <= 1
    except Exception as e:
        print(f"❌ 关闭新标签页失败：{str(e)}")
        return False


def reset_page_by_turning():
    """翻页重置页面"""