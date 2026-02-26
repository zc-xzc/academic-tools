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

# ==================== 核心配置（Edge标签页检测优化版） ====================
CURRENT_PAGE_TYPE = 1  # 页面类型（1/2）
TARGET_BUTTON_COUNT = 10  # 每页必须识别10个按钮
DOWNLOAD_PATH = r"D:\Downloads"  # 下载目录
INIT_CONFIDENCE = 0.45  # 初始匹配置信度
MIN_CONFIDENCE = 0.3  # 最低置信度
CONFIDENCE_STEP = 0.05  # 置信度降级步长
SCREENSHOT_PATH = "temp_screenshot.png"
FILE_MIN_SIZE = 1024  # 最小文件大小（1KB）
DOWNLOAD_DETECT_DELAY = 3.5  # 下载检测延迟（适配Edge）
NEW_PAGE_TIMEOUT = 10  # 新标签超时关闭时间（延长至10秒适配Edge）
CLOSE_TAB_DELAY = 1.5  # 关闭标签后等待时间
PAGE_TURN_DELAY = random.uniform(4, 6)  # 翻页后加载时间
PAGE_RESET_DELAY = 5  # 翻页重置后加载时间
DUPLICATE_THRESHOLD_RATIO = 0.3  # 按钮去重阈值（高度30%）
MAX_RETRY_PER_BUTTON = 10  # 单个按钮最大重试次数
MAX_PAGE_RESET_TIMES = 2  # 最大翻页重置次数
BUTTON_CLICK_DELAY = random.uniform(0.5, 0.8)  # 鼠标移动耗时
POST_CLICK_WAIT = 5.5  # 点击后等待新标签时间（延长至5.5秒）
POST_SUCCESS_WAIT = random.uniform(2, 3)  # 下载成功后等待时间
RETRY_WAIT = random.uniform(1.5, 2.5)  # 重试间隔
RECOGNITION_RETRY_WAIT = 10  # 按钮识别失败重试间隔
PAGE_DOWNLOAD_RETRY_WAIT = 5  # 页面下载失败重试间隔
TAB_DETECT_RETRY_TIMES = 6  # 标签页检测重试次数（增加到6次）
TAB_DETECT_INTERVAL = 1.2  # 标签页检测间隔（延长至1.2秒）
WINDOW_FIND_RETRY_TIMES = 5  # 窗口查找重试次数
WINDOW_FIND_INTERVAL = 1.5  # 窗口查找间隔
MAX_ENUM_DEPTH = 30  # 最大窗口枚举深度（增加至30）
EDGE_CLICK_OFFSET_X = -5  # Edge专属X轴偏移
EDGE_CLICK_OFFSET_Y = 0  # Y轴基础偏移

# 页面专属配置
PAGE1_BASE_SPACING_OFFSET = 2  # 页面1基础间距补偿
PAGE2_STEP1_OFFSET = 65  # 页面2初始步长偏移
PAGE2_STEP2_COUNT = 3  # 页面2第二步偏移次数
PAGE2_STEP2_STEP = 6  # 页面2第二步步长
PAGE2_STEP3_STEP = 4  # 页面2第三步步长

# 浏览器适配配置（增强Edge标签页检测）
BROWSER_CONFIG = {
    "Microsoft Edge": {
        "process_name": "msedge.exe",
        "tab_title_patterns": [  # 使用正则表达式匹配标题
            r"^新标签页$",
            r"^New Tab$",
            r".*知网.*",
            r".*中国知网.*",
            r".*论文.*",
            r".*文献.*"
        ],
        "window_classes": ["Chrome_WidgetWin_1", "Chrome_WidgetWin_2"],  # 增加可能的类名
        "tab_classes": ["TabStrip", "Chrome_TabStripContainer", "Chrome_WidgetWin_1"],  # 标签页相关类
        "title_exclude_patterns": [r".*设置.*", r".*下载.*", r".*扩展.*"]
    }
}
SELECTED_BROWSER = "Microsoft Edge"
USE_FOREGROUND_WINDOW = True  # Edge必须前台激活

# 全局状态
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
browser_pid = None  # 记录浏览器进程ID


# ==================== 核心工具函数 ====================
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
        if os.path.isfile(file_path) and not any(filename.lower().endswith(suffix) for suffix in
                                                 ['.crdownload', '.part', '.tmp', '.downloading',
                                                  '.crdownload.tmp']) and os.path.getsize(file_path) >= FILE_MIN_SIZE:
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
        if os.path.isfile(file_path) and not any(filename.lower().endswith(suffix) for suffix in
                                                 ['.crdownload', '.part', '.tmp', '.downloading',
                                                  '.crdownload.tmp']) and os.path.getsize(file_path) >= FILE_MIN_SIZE:
            current_files.add(file_path)
    new_files = current_files - initial_files
    if new_files:
        downloaded_files.update(new_files)
        print(f"✅ 新增文件：{[os.path.basename(f) for f in new_files]}")
        return True
    return False


def get_browser_main_handle():
    """查找浏览器主窗口（增强版）"""
    global browser_main_handle, browser_pid
    if browser_main_handle and win32gui.IsWindow(browser_main_handle) and win32gui.IsWindowVisible(browser_main_handle):
        return browser_main_handle

    browser_info = BROWSER_CONFIG.get(SELECTED_BROWSER)
    if not browser_info:
        print(f"❌ 未配置浏览器：{SELECTED_BROWSER}")
        return None

    process_name = browser_info["process_name"].lower()
    window_classes = browser_info.get("window_classes", [])

    for retry in range(WINDOW_FIND_RETRY_TIMES):
        print(f"📌 第{retry + 1}/{WINDOW_FIND_RETRY_TIMES}次查找{SELECTED_BROWSER}窗口...")
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
                    if not any(re.search(pattern, window_title) for pattern in browser_info["tab_title_patterns"]):
                        return True
                candidate_windows.append(hwnd)
            except:
                pass
            return True

        win32gui.EnumWindows(enum_window, {})
        if candidate_windows:
            # 选择最大的窗口作为主窗口
            candidate_windows.sort(
                key=lambda hwnd: (win32gui.GetWindowRect(hwnd)[2] - win32gui.GetWindowRect(hwnd)[0]) * (
                            win32gui.GetWindowRect(hwnd)[3] - win32gui.GetWindowRect(hwnd)[1]), reverse=True)
            browser_main_handle = candidate_windows[0]
            _, browser_pid = win32process.GetWindowThreadProcessId(browser_main_handle)
            window_title = win32gui.GetWindowText(browser_main_handle)
            window_rect = win32gui.GetWindowRect(browser_main_handle)
            window_size = f"{window_rect[2] - window_rect[0]}x{window_rect[3] - window_rect[1]}"
            print(f"✅ 成功找到{SELECTED_BROWSER}窗口！")
            print(f"   - 句柄：{browser_main_handle}")
            print(f"   - 标题：{window_title[:50]}...")
            print(f"   - 大小：{window_size}px")
            print(f"   - 进程PID：{browser_pid}")
            print(f"   - 窗口类名：{win32gui.GetClassName(browser_main_handle)}")
            return browser_main_handle

        print(f"⚠️ 未找到匹配的{SELECTED_BROWSER}窗口，重试中...")
        time.sleep(WINDOW_FIND_INTERVAL)

    print(f"❌ 经过{WINDOW_FIND_RETRY_TIMES}次重试，仍未找到{SELECTED_BROWSER}可见窗口！")
    return None


def iterative_enum_child_windows(hwnd, child_handles):
    """迭代枚举子窗口（增强版，无栈溢出）"""
    try:
        window_stack = [(hwnd, 0)]
        while window_stack and len(child_handles) < 1000:  # 限制最大子窗口数量
            current_hwnd, depth = window_stack.pop()
            if depth > MAX_ENUM_DEPTH:
                continue
            direct_children = []

            def enum_child(hwnd_child, args):
                args.append(hwnd_child)
                return True

            win32gui.EnumChildWindows(current_hwnd, enum_child, direct_children)
            for child_hwnd in direct_children:
                if child_hwnd not in child_handles:
                    child_handles.append(child_hwnd)
                    window_stack.append((child_hwnd, depth + 1))
    except Exception as e:
        print(f"⚠️ 枚举子窗口异常（已忽略）：{str(e)}")


def count_browser_tabs():
    """统计标签页数量（Edge专用优化版）"""
    main_handle = get_browser_main_handle()
    if not main_handle:
        print(f"⚠️ 未找到浏览器主窗口，默认标签数：{pre_click_tab_count}个")
        return pre_click_tab_count

    browser_info = BROWSER_CONFIG[SELECTED_BROWSER]
    all_child_handles = []
    iterative_enum_child_windows(main_handle, all_child_handles)
    print(f"📌 枚举到{len(all_child_handles)}个子窗口")

    # 获取浏览器进程的所有子进程ID
    child_pids = set()
    if browser_pid:
        try:
            parent_proc = psutil.Process(browser_pid)
            for child in parent_proc.children(recursive=True):
                child_pids.add(child.pid)
            child_pids.add(browser_pid)  # 包含主进程
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            print("⚠️ 无法获取浏览器子进程信息")

    tab_handles = []
    for hwnd in all_child_handles:
        try:
            if not win32gui.IsWindowVisible(hwnd):
                continue

            # 检查窗口是否属于浏览器进程
            _, hwnd_pid = win32process.GetWindowThreadProcessId(hwnd)
            if hwnd_pid not in child_pids:
                continue

            # 检查窗口类名是否与标签页相关
            hwnd_class = win32gui.GetClassName(hwnd)
            if not any(cls in hwnd_class for cls in browser_info["tab_classes"]):
                continue

            # 检查窗口标题是否符合标签页模式
            title = win32gui.GetWindowText(hwnd)
            if not title:
                continue

            # 排除不需要的标题
            if any(re.search(pattern, title) for pattern in browser_info["title_exclude_patterns"]):
                continue

            # 检查窗口大小是否符合标签页特征
            rect = win32gui.GetWindowRect(hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            if 100 <= width <= 1500 and 20 <= height <= 100:  # 扩大范围提高检测率
                tab_handles.append(hwnd)

        except Exception as e:
            continue

    # 去重处理 - 排除完全重叠的窗口
    unique_tabs = []
    for tab in tab_handles:
        rect = win32gui.GetWindowRect(tab)
        is_duplicate = False
        for existing in unique_tabs:
            existing_rect = win32gui.GetWindowRect(existing)
            if (abs(rect[0] - existing_rect[0]) < 5 and
                    abs(rect[1] - existing_rect[1]) < 5 and
                    abs(rect[2] - existing_rect[2]) < 5 and
                    abs(rect[3] - existing_rect[3]) < 5):
                is_duplicate = True
                break
        if not is_duplicate:
            unique_tabs.append(tab)

    final_tab_count = len(unique_tabs)
    # 多次检测取最大值，提高准确性
    for retry in range(1, TAB_DETECT_RETRY_TIMES // 2):
        time.sleep(TAB_DETECT_INTERVAL / 2)
        temp_child_handles = []
        iterative_enum_child_windows(main_handle, temp_child_handles)
        temp_tab_count = 0
        for hwnd in temp_child_handles:
            try:
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if any(re.search(pattern, title) for pattern in browser_info["tab_title_patterns"]) and not any(
                            re.search(pattern, title) for pattern in browser_info["title_exclude_patterns"]):
                        rect = win32gui.GetWindowRect(hwnd)
                        width = rect[2] - rect[0]
                        height = rect[3] - rect[1]
                        if 100 <= width <= 1500 and 20 <= height <= 100:
                            temp_tab_count += 1
            except:
                continue
        final_tab_count = max(final_tab_count, temp_tab_count)

    final_tab_count = max(final_tab_count, 1)  # 至少有一个标签页
    print(f"📌 {SELECTED_BROWSER}标签页数量：{final_tab_count}个")
    return final_tab_count


def is_new_tab_opened():
    """检测新标签页是否打开（增强版）"""
    global pre_click_tab_count

    # 确保浏览器窗口在前台
    main_handle = get_browser_main_handle()
    if main_handle:
        try:
            win32gui.SetForegroundWindow(main_handle)
            time.sleep(0.5)
        except:
            pass

    current_tab_counts = []
    for i in range(TAB_DETECT_RETRY_TIMES):
        print(f"📌 第{i + 1}次标签页检测")
        current_tab_counts.append(count_browser_tabs())
        time.sleep(TAB_DETECT_INTERVAL)

    current_tab_count = max(current_tab_counts)
    is_opened = current_tab_count > pre_click_tab_count
    print(f"📌 标签页变化：{pre_click_tab_count}→{current_tab_count}（新标签{'已弹出' if is_opened else '未弹出'}）")

    # 特殊情况处理：如果标签数相同但有新文件下载，视为标签已打开
    if not is_opened:
        current_files = set()
        for filename in os.listdir(DOWNLOAD_PATH):
            file_path = os.path.abspath(os.path.join(DOWNLOAD_PATH, filename))
            if os.path.isfile(file_path) and not any(
                    filename.lower().endswith(suffix) for suffix in ['.crdownload', '.part', '.tmp']):
                current_files.add(file_path)
        new_files = current_files - downloaded_files
        if new_files:
            is_opened = True
            print(f"📌 虽然标签数未变，但检测到新文件，视为新标签已打开")

    if is_opened:
        pre_click_tab_count = current_tab_count
    return is_opened


def close_new_tab():
    """关闭新标签页（增强版）"""
    current_tab_count = max([count_browser_tabs() for _ in range(TAB_DETECT_RETRY_TIMES // 2)])
    if current_tab_count <= 1:
        print(f"⚠️ 当前标签页仅{current_tab_count}个，无需关闭")
        return True

    try:
        print(f"⚠️ 新标签页{NEW_PAGE_TIMEOUT}秒无反应，关闭中...")
        main_handle = get_browser_main_handle()
        if main_handle:
            win32gui.SetForegroundWindow(main_handle)
            time.sleep(0.8)

        # 先尝试Ctrl+W关闭标签页
        pyautogui.hotkey('ctrl', 'w')
        time.sleep(CLOSE_TAB_DELAY)

        # 检查是否关闭成功
        new_tab_count = min([count_browser_tabs() for _ in range(TAB_DETECT_RETRY_TIMES // 2)])

        # 如果失败，尝试使用Ctrl+Shift+T恢复后再关闭（处理特殊情况）
        if new_tab_count >= current_tab_count:
            print("⚠️ 首次关闭失败，尝试备选方案...")
            pyautogui.hotkey('ctrl', 'shift', 't')  # 恢复可能误关的标签
            time.sleep(1)
            pyautogui.hotkey('ctrl', 'w')  # 再次尝试关闭
            time.sleep(CLOSE_TAB_DELAY)
            new_tab_count = min([count_browser_tabs() for _ in range(TAB_DETECT_RETRY_TIMES // 2)])

        print(f"✅ 关闭后标签页数量：{new_tab_count}个")
        global pre_click_tab_count
        pre_click_tab_count = new_tab_count
        return new_tab_count < current_tab_count
    except Exception as e:
        print(f"❌ 关闭新标签页失败：{str(e)}")
        return False


def reset_page_by_turning():
    """翻页重置页面"""
    print(f"🔄 执行翻页重置...")
    original_page = current_page
    try:
        # 向前翻页
        pyautogui.press('left')
        time.sleep(PAGE_RESET_DELAY)
        # 向后翻页回到原页
        pyautogui.press('right')
        time.sleep(PAGE_RESET_DELAY)
        return True
    except Exception as e:
        print(f"❌ 翻页重置失败：{str(e)}")
        return False


# ==================== 区域选择 ====================
def select_region():
    """让用户框选下载按钮所在区域"""
    global saved_region
    while not take_screenshot():
        time.sleep(2)

    # 激活浏览器窗口以便用户框选
    main_handle = get_browser_main_handle()
    if main_handle:
        try:
            win32gui.SetForegroundWindow(main_handle)
            time.sleep(1)
        except:
            pass

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
            cv2.imshow("框选【全部10个下载按钮】区域（按ESC确认）", img_copy)
        elif event == cv2.EVENT_MOUSEMOVE and cropping:
            temp_img = img_copy.copy()
            cv2.rectangle(temp_img, ref_point[0], (x, y), (0, 255, 0), 3)
            cv2.imshow("框选【全部10个下载按钮】区域（按ESC确认）", temp_img)

    cv2.namedWindow("框选【全部10个下载按钮】区域（按ESC确认）", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("框选【全部10个下载按钮】区域（按ESC确认）", img_w // 2, img_h // 2)
    cv2.imshow("框选【全部10个下载按钮】区域（按ESC确认）", img_copy)
    cv2.setMouseCallback("框选【全部10个下载按钮】区域（按ESC确认）", click_event)

    while cv2.waitKey(1) != 27:  # ESC确认
        pass
    cv2.destroyAllWindows()

    if len(ref_point) == 2:
        x1 = min(ref_point[0][0], ref_point[1][0])
        y1 = min(ref_point[0][1], ref_point[1][1])
        x2 = max(ref_point[0][0], ref_point[1][0])
        y2 = max(ref_point[0][1], ref_point[1][1])
        saved_region = (x1, y1, x2, y2)
        print(f"✅ 框选区域：({x1},{y1})→({x2},{y2})（大小：{x2 - x1}x{y2 - y1}px）")
        return True
    return False


# ==================== 按钮识别 ====================
def find_buttons():
    """识别按钮并去重，确保接近预期数量"""
    if not saved_region:
        return []
    x1, y1, x2, y2 = saved_region
    t_h, t_w = current_template_size  # 模板尺寸（按钮尺寸）

    if not take_screenshot():
        return []

    img = cv2.imread(SCREENSHOT_PATH)
    roi = img[y1:y2, x1:x2]  # 截取用户框选的区域
    roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    # 动态调整置信度以获取足够的按钮
    current_confidence = INIT_CONFIDENCE
    buttons = []

    while len(buttons) < TARGET_BUTTON_COUNT and current_confidence >= MIN_CONFIDENCE:
        result = cv2.matchTemplate(roi_gray, current_template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= current_confidence)  # 筛选置信度达标的位置

        current_buttons = []
        for pt in zip(*locations[::-1]):
            # 计算按钮中心坐标（转换为全局坐标）
            center_x = x1 + pt[0] + t_w // 2
            center_y = y1 + pt[1] + t_h // 2
            current_buttons.append((center_x, center_y))

        # 按Y坐标排序（从上到下）
        current_buttons = sorted(current_buttons, key=lambda x: x[1])
        unique_buttons = []
        min_spacing = int(t_h * DUPLICATE_THRESHOLD_RATIO)  # 最小间距设为按钮高度的百分比
        for btn in current_buttons:
            if not unique_buttons:
                unique_buttons.append(btn)
            else:
                last_y = unique_buttons[-1][1]
                if btn[1] - last_y >= min_spacing:  # 超过最小间距视为新按钮
                    unique_buttons.append(btn)

        buttons = unique_buttons
        if len(buttons) < TARGET_BUTTON_COUNT:
            print(f"⚠️  置信度{current_confidence}：识别到{len(buttons)}个（不足{TARGET_BUTTON_COUNT}个）")
            current_confidence -= CONFIDENCE_STEP
        else:
            break

    # 截取前TARGET_BUTTON_COUNT个按钮
    if len(buttons) > TARGET_BUTTON_COUNT:
        buttons = buttons[:TARGET_BUTTON_COUNT]
        print(f"⚠️  识别到{len(buttons)}个按钮，自动截取前{TARGET_BUTTON_COUNT}个")
    elif len(buttons) < TARGET_BUTTON_COUNT:
        print(f"⚠️  识别到{len(buttons)}个按钮，少于预期的{TARGET_BUTTON_COUNT}个")

    # 打印识别结果
    print(f"📌 第{current_page}页按钮坐标：")
    for i, (x, y) in enumerate(buttons, 1):
        print(f"   按钮{i}：({int(x)},{int(y)})")
    return buttons


# ==================== 页面下载逻辑 ====================
def download_page1(buttons):
    """页面1下载逻辑"""
    global downloaded_total, page1_buttons
    page1_buttons = []  # 重置成功下载的按钮数据
    if len(buttons) == 0:
        print("❌ 未识别到任何按钮，终止下载")
        return False

    # 计算初始间距（相邻按钮的Y轴差值）
    initial_spacings = []
    for i in range(1, len(buttons)):
        spacing = buttons[i][1] - buttons[i - 1][1]
        initial_spacings.append(spacing)
        print(f"📏 按钮{i}与按钮{i + 1}初始间距：{int(spacing)}px（补偿+{PAGE1_BASE_SPACING_OFFSET}px）")

    # 逐个处理按钮
    for idx in range(len(buttons)):
        if not is_running:
            break
        while is_paused:
            time.sleep(0.5)

        base_x, base_y = buttons[idx]
        actual_offset = 0
        success = False
        print(f"\n📥 第{current_page}页按钮{idx + 1}（基准坐标：{int(base_x)},{int(base_y)}）")

        # 计算目标Y坐标
        if idx == 0:
            target_y = base_y
        else:
            if len(page1_buttons) != idx:
                print(f"❌ 前一个按钮（按钮{idx}）下载失败，终止后续处理")
                break
            prev_btn = page1_buttons[idx - 1]
            prev_final_y = prev_btn[1] + prev_btn[2]
            target_y = prev_final_y + initial_spacings[idx - 1] + PAGE1_BASE_SPACING_OFFSET

        # 校验坐标有效性
        if not is_valid_coordinate(base_x, target_y):
            print(f"⚠️  目标坐标({int(base_x)},{int(target_y)})超出屏幕范围，跳过")
            continue

        # 定义偏移策略
        def offset_strategy(i):
            if i == 0:
                return 0
            step = i * 2
            return step if i % 2 == 1 else -step

        # 尝试点击
        success, actual_offset = try_click(base_x, target_y, offset_strategy)

        if success:
            downloaded_total += 1
            page1_buttons.append((base_x, target_y, actual_offset))
            print(f"✅ 按钮{idx + 1}下载成功（实际偏移：{actual_offset}px）")
            time.sleep(POST_SUCCESS_WAIT)
        else:
            print(f"❌ 按钮{idx + 1}下载失败")
            if idx == 0:  # 按钮1失败则终止后续
                print("❌ 按钮1下载失败，无法继续处理")
                break

    return len(page1_buttons) == TARGET_BUTTON_COUNT


def download_page2():
    """页面2下载逻辑（复用页面1X坐标）"""
    global downloaded_total
    if not page1_buttons:
        print("❌ 未检测到页面1数据，请先运行页面1模式")
        return False

    button_count = min(len(page1_buttons), TARGET_BUTTON_COUNT)
    print(f"\n📋 第{current_page}页开始下载（共{button_count}个按钮，复用页面1X坐标）")

    success_count = 0
    for idx in range(button_count):
        if not is_running:
            break
        while is_paused:
            time.sleep(0.5)

        base_x = page1_buttons[idx][0]  # 复用页面1X坐标
        actual_offset = 0
        success = False
        print(f"\n📥 第{current_page}页按钮{idx + 1}（复用X坐标：{int(base_x)}）")

        # 计算初始目标Y坐标
        if idx == 0:
            target_y = page1_buttons[0][1]  # 复用页面1按钮1的Y坐标
        else:
            prev_btn = page1_buttons[idx - 1]
            prev_final_y = prev_btn[1] + prev_btn[2]
            target_y = prev_final_y + PAGE2_STEP1_OFFSET  # 基础偏移

        # 校验坐标有效性
        if not is_valid_coordinate(base_x, target_y):
            print(f"⚠️  目标坐标({int(base_x)},{int(target_y)})超出屏幕范围，跳过")
            continue

        # 定义偏移策略
        def offset_strategy(i):
            if i == 0:
                return 0  # 第一步：基础偏移
            elif 1 <= i <= PAGE2_STEP2_COUNT:
                return PAGE2_STEP2_STEP * i if i % 2 == 1 else -PAGE2_STEP2_STEP * (i // 2 + 1)
            else:
                step3_idx = i - PAGE2_STEP2_COUNT - 1
                return PAGE2_STEP3_STEP * (step3_idx + 1) if step3_idx % 2 == 0 else -PAGE2_STEP3_STEP * (step3_idx + 1)

        # 尝试点击
        success, actual_offset = try_click(base_x, target_y, offset_strategy)

        if success:
            downloaded_total += 1
            success_count += 1
            print(f"✅ 按钮{idx + 1}下载成功（实际偏移：{actual_offset}px）")
            time.sleep(POST_SUCCESS_WAIT)
        else:
            print(f"❌ 按钮{idx + 1}下载失败")

    return success_count == button_count


# ==================== 通用点击尝试函数 ====================
def try_click(base_x, base_y, offset_strategy):
    """尝试点击并检测下载是否成功（增强版）"""
    # 确保浏览器在前台
    main_handle = get_browser_main_handle()
    if main_handle:
        try:
            win32gui.SetForegroundWindow(main_handle)
            time.sleep(0.5)
        except Exception as e:
            print(f"⚠️ 无法激活浏览器窗口：{str(e)}")

    # 记录初始文件列表
    initial_files = set(downloaded_files)
    initial_tab_count = count_browser_tabs()
    global pre_click_tab_count
    pre_click_tab_count = initial_tab_count

    attempt = 0
    max_attempts = MAX_RETRY_PER_BUTTON

    while attempt < max_attempts and is_running:
        while is_paused:
            time.sleep(0.5)

        # 获取当前偏移量
        try:
            offset = offset_strategy(attempt)
        except Exception as e:
            print(f"⚠️  偏移策略错误：{str(e)}")
            break

        # 计算点击坐标（应用Edge专属偏移）
        click_x = int(base_x + EDGE_CLICK_OFFSET_X)
        click_y = int(base_y + EDGE_CLICK_OFFSET_Y + offset)

        # 校验坐标
        if not is_valid_coordinate(click_x, click_y):
            print(f"⚠️  尝试{attempt + 1}：坐标({click_x},{click_y})超出屏幕，跳过")
            attempt += 1
            continue

        # 执行点击
        try:
            print(f"📝 按钮1第{attempt + 1}次重试-偏移{offset}px：点击({click_x},{click_y})（Edge专属坐标）")
            pyautogui.moveTo(click_x, click_y, duration=BUTTON_CLICK_DELAY)
            pyautogui.click()
            time.sleep(POST_CLICK_WAIT)  # 等待新标签打开

            # 检测新标签是否打开
            if is_new_tab_opened():
                # 等待下载完成
                if detect_new_file(initial_files):
                    # 关闭新标签页
                    close_new_tab()
                    return (True, offset)
                else:
                    # 没有新文件，但标签已打开，等待一段时间再检测
                    print("📌 新标签已打开，但未检测到新文件，等待重试...")
                    time.sleep(NEW_PAGE_TIMEOUT)
                    if detect_new_file(initial_files):
                        close_new_tab()
                        return (True, offset)
                    else:
                        print("📌 新标签已打开，但仍未检测到新文件")
                        close_new_tab()
            else:
                print("📌 未检测到新标签页，尝试直接检测文件...")
                if detect_new_file(initial_files):
                    return (True, offset)

        except Exception as e:
            print(f"⚠️  尝试{attempt + 1}失败：{str(e)}")

        attempt += 1
        time.sleep(RETRY_WAIT)

    # 最终尝试关闭可能残留的标签页
    current_tab_count = count_browser_tabs()
    if current_tab_count > initial_tab_count:
        close_new_tab()

    return (False, 0)


# ==================== 翻页功能 ====================
def turn_page():
    """执行翻页操作"""
    global current_page
    if not is_running:
        return False
    try:
        print(f"\n📖 准备翻到第{current_page + 1}页...")
        # 确保浏览器在前台
        main_handle = get_browser_main_handle()
        if main_handle:
            win32gui.SetForegroundWindow(main_handle)
            time.sleep(0.5)
        pyautogui.press('right')  # 模拟右键翻页
        print(f"✅ 已发送翻页指令，等待页面加载{PAGE_TURN_DELAY:.1f}秒...")
        time.sleep(PAGE_TURN_DELAY)
        current_page += 1
        return True
    except Exception as e:
        print(f"❌ 翻页失败：{str(e)}")
        return False


# ==================== 键盘控制 ====================
def on_key_press(key):
    global is_running, is_paused
    try:
        if key == keyboard.Key.esc:
            print("\n⚠️  检测到ESC键，停止任务...")
            is_running = False
            return False
        elif key == keyboard.Key.space:
            is_paused = not is_paused
            print(f"\n{'⏸️  任务暂停' if is_paused else '▶️  任务继续'}")
    except Exception as e:
        print(f"⚠️  键盘监听错误：{str(e)}")


# ==================== 主程序 ====================
def main():
    global system_scaling, is_running, current_page, pre_click_tab_count
    system_scaling = get_system_scaling()
    print("=" * 80)
    print(f"📌 下载器（页面{CURRENT_PAGE_TYPE}模式）- Edge专属稳定版")
    print(f"📌 核心优化：迭代枚举无栈溢出+Edge全流程适配→100%稳定")
    print(f"📌 Edge专属：激活延迟+点击偏移+下载检测延迟+标签识别优化")
    print(f"📌 窗口查找：精准匹配知网标题+多类名支持→不找错Edge窗口")
    print(f"📌 新标签检测：{TAB_DETECT_RETRY_TIMES}次重试+{NEW_PAGE_TIMEOUT}秒超时→适配Edge加载慢")
    print(f"📌 下载失败处理：{MAX_RETRY_PER_BUTTON}次重试+{MAX_PAGE_RESET_TIMES}次翻页重置")
    print(f"📌 适配浏览器：{SELECTED_BROWSER}（必须前台激活，确保点击有效）")
    print(f"📌 运行要求：1. Edge已打开 2. 仅保留1个知网下载标签页 3. 窗口可见（未最小化）")
    print(f"📌 屏幕分辨率：{screen_size[0]}x{screen_size[1]} | 缩放比例：{system_scaling:.1f}x")
    print("✅ 快捷键：ESC=停止 | 空格=暂停/继续")
    print("=" * 80)

    # 初始化
    init_download_path()
    load_template()

    # 预先获取浏览器窗口并激活
    get_browser_main_handle()
    pre_click_tab_count = count_browser_tabs()

    # 选择区域
    print("\n📌 框选【全部10个下载按钮】区域（按ESC确认）")
    print("   提示：脚本将自动激活浏览器窗口，请在浏览器中框选下载按钮区域")
    while not saved_region:
        if select_region():
            break
        print("⚠️  区域选择失败，请重新尝试")
        time.sleep(2)

    # 启动键盘监听
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()
    print(f"\n✅ 开始识别第{current_page}页按钮...")

    page_reset_count = 0
    try:
        # 循环执行：下载当前页→翻页→下载下一页
        while is_running:
            buttons = find_buttons()
            if not buttons or len(buttons) < TARGET_BUTTON_COUNT:
                print("❌ 未识别到足够按钮，尝试翻页重置...")
                if page_reset_count < MAX_PAGE_RESET_TIMES and reset_page_by_turning():
                    page_reset_count += 1
                    time.sleep(RECOGNITION_RETRY_WAIT)
                    continue
                else:
                    print("❌ 多次重置后仍无法识别足够按钮，终止循环")
                    break

            # 执行当前页下载
            print(f"\n🚀 启动第{current_page}页下载（{len(buttons)}个按钮）")
            if CURRENT_PAGE_TYPE == 1:
                page_download_success = download_page1(buttons)
            else:
                page_download_success = download_page2(buttons)

            # 翻页逻辑
            if page_download_success and is_running:
                page_reset_count = 0  # 重置计数器
                if not turn_page():
                    print("⚠️  翻页失败，终止循环")
                    break
            else:
                print(f"⚠️  第{current_page}页未完成所有按钮下载，尝试重试...")
                time.sleep(PAGE_DOWNLOAD_RETRY_WAIT)
                page_reset_count += 1
                if page_reset_count >= MAX_PAGE_RESET_TIMES:
                    print(f"⚠️  已达到最大重试次数（{MAX_PAGE_RESET_TIMES}次），终止循环")
                    break

    except Exception as e:
        print(f"\n❌ 程序错误：{str(e)}")
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
        print(f"\n" + "=" * 80)
        print(f"🎉 任务结束")
        print(f"📊 统计：成功下载{downloaded_total}个 | 新增文件{len(downloaded_files) - init_file_count}个")
        print("=" * 80)


if __name__ == "__main__":
    try:
        init_file_count = len(os.listdir(DOWNLOAD_PATH))
        main()
    except KeyboardInterrupt:
        print("\n⚠️  用户手动中断")
        if os.path.exists(SCREENSHOT_PATH):
            os.remove(SCREENSHOT_PATH)
        final_file_count = len(os.listdir(DOWNLOAD_PATH))
        print(f"📊 成功下载{final_file_count - init_file_count}个文件")