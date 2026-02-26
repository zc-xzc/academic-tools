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

# ==================== 一、核心配置（集中管理，无冗余） ====================
# 基础运行配置
CURRENT_PAGE_TYPE = 1  # 页面类型（1/2）
TARGET_BUTTON_COUNT = 10  # 每页必填按钮数量
DOWNLOAD_PATH = r"D:\Downloads"  # 下载目录
SCREENSHOT_PATH = "temp_screenshot.png"  # 临时截图路径
FILE_MIN_SIZE = 1024  # 最小有效文件大小（1KB）

# 识别相关配置
INIT_CONFIDENCE = 0.45  # 初始匹配置信度
MIN_CONFIDENCE = 0.3  # 最低置信度阈值
CONFIDENCE_STEP = 0.05  # 置信度降级步长
DUPLICATE_THRESHOLD_RATIO = 0.3  # 按钮去重阈值（按钮高度的30%）

# 时间延迟配置（适配Edge）
DOWNLOAD_DETECT_DELAY = 3.5  # 下载检测延迟
NEW_PAGE_TIMEOUT = 10  # 新标签超时关闭时间
CLOSE_TAB_DELAY = 1.5  # 关闭标签后等待时间
PAGE_TURN_DELAY = random.uniform(4, 6)  # 翻页后加载时间
PAGE_RESET_DELAY = 5  # 页面重置等待时间
BUTTON_CLICK_DELAY = random.uniform(0.5, 0.8)  # 鼠标移动耗时
POST_CLICK_WAIT = 5.5  # 点击后等待新标签时间
POST_SUCCESS_WAIT = random.uniform(2, 3)  # 下载成功后等待时间
RETRY_WAIT = random.uniform(1.5, 2.5)  # 重试间隔
RECOGNITION_RETRY_WAIT = 10  # 按钮识别失败重试间隔
PAGE_DOWNLOAD_RETRY_WAIT = 5  # 页面下载失败重试间隔

# 重试次数配置
MAX_RETRY_PER_BUTTON = 10  # 单个按钮最大重试次数
MAX_PAGE_RESET_TIMES = 2  # 最大翻页重置次数
TAB_DETECT_RETRY_TIMES = 6  # 标签页检测重试次数
WINDOW_FIND_RETRY_TIMES = 5  # 窗口查找重试次数
WINDOW_FIND_INTERVAL = 1.5  # 窗口查找间隔
TAB_DETECT_INTERVAL = 1.2  # 标签页检测间隔

# 窗口/坐标配置
MAX_ENUM_DEPTH = 30  # 子窗口枚举深度（适配Edge标签页层级）
EDGE_CLICK_OFFSET_X = -5  # Edge专属X轴偏移（避免点击边框）
EDGE_CLICK_OFFSET_Y = 0  # Y轴基础偏移

# 页面专属偏移策略（按需求定义，无冗余）
# 页面1：双边递增偏移（4,-4,8,-8...）
PAGE1_BASE_SPACING_OFFSET = 2  # 基础间距补偿
PAGE1_OFFSET_STEP = 4  # 偏移步长

# 页面2：分步骤双边推进（复用页面1X坐标）
PAGE2_STEP1_OFFSET = 65  # 第一步基础偏移
PAGE2_STEP2_STEP = 6  # 第二步偏移步长
PAGE2_STEP2_COUNT = 3  # 第二步尝试次数
PAGE2_STEP3_STEP = 4  # 第三步偏移步长

# Edge浏览器专属配置（精准匹配标签页）
BROWSER_CONFIG = {
    "Microsoft Edge": {
        "process_name": "msedge.exe",
        "tab_title_patterns": [r"新标签页", r"New Tab", r".*知网.*", r".*中国知网.*", r".*论文.*", r".*文献.*"],
        "window_classes": ["Chrome_WidgetWin_1", "Chrome_WidgetWin_2"],
        "tab_classes": ["TabStrip", "Chrome_TabStripContainer"],
        "title_exclude_patterns": [r".*设置.*", r".*扩展.*"]
    }
}
SELECTED_BROWSER = "Microsoft Edge"
USE_FOREGROUND_WINDOW = True  # 强制浏览器前台激活

# 全局状态（仅保留必要变量，无冗余）
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
browser_pid = None  # 浏览器进程ID
pre_click_tab_count = 1  # 点击前标签页数量


# ==================== 二、基础工具函数（通用功能，无依赖冲突） ====================
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
    """加载下载按钮模板（必须放在脚本目录，命名为download_icon.png）"""
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
    """检测下载目录新增文件"""
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


# ==================== 三、浏览器窗口管理（Edge专属，精准识别标签页） ====================
def get_browser_main_handle():
    """查找并返回Edge主窗口句柄，缓存避免重复查找"""
    global browser_main_handle, browser_pid
    # 缓存有效则直接返回
    if browser_main_handle and win32gui.IsWindow(browser_main_handle) and win32gui.IsWindowVisible(browser_main_handle):
        return browser_main_handle

    browser_info = BROWSER_CONFIG[SELECTED_BROWSER]
    process_name = browser_info["process_name"].lower()
    window_classes = browser_info["window_classes"]

    # 查找Edge进程（带可见窗口）
    for retry in range(WINDOW_FIND_RETRY_TIMES):
        print(f"📌 第{retry+1}/{WINDOW_FIND_RETRY_TIMES}次查找Edge窗口...")
        target_pids = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == process_name:
                    # 验证进程是否有可见窗口
                    has_visible_window = False
                    def check_visible(hwnd, args):
                        nonlocal has_visible_window, proc
                        try:
                            if win32gui.IsWindowVisible(hwnd):
                                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                                if pid == proc.info['pid']:
                                    has_visible_window = True
                        except:
                            pass
                        return True
                    win32gui.EnumWindows(check_visible, proc)
                    if has_visible_window:
                        target_pids.append(proc.info['pid'])
                        print(f"📌 找到Edge进程：PID={proc.info['pid']}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not target_pids:
            print(f"⚠️ 未找到带可见窗口的Edge进程，重试中...")
            time.sleep(WINDOW_FIND_INTERVAL)
            continue

        # 枚举匹配的窗口
        candidate_windows = []
        def enum_window(hwnd, args):
            nonlocal candidate_windows, target_pids
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                # 过滤过小窗口
                rect = win32gui.GetWindowRect(hwnd)
                if (rect[2]-rect[0] < 300) or (rect[3]-rect[1] < 200):
                    return True
                # 匹配进程ID和窗口类名
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid not in target_pids:
                    return True
                if win32gui.GetClassName(hwnd) not in window_classes:
                    return True
                # 匹配标题关键词
                title = win32gui.GetWindowText(hwnd)
                if not any(re.search(pattern, title) for pattern in browser_info["tab_title_patterns"]):
                    return True
                candidate_windows.append(hwnd)
            except:
                pass
            return True

        win32gui.EnumWindows(enum_window, {})
        if candidate_windows:
            # 选择最大窗口作为主窗口
            candidate_windows.sort(key=lambda hwnd: (win32gui.GetWindowRect(hwnd)[2]-win32gui.GetWindowRect(hwnd)[0])*(win32gui.GetWindowRect(hwnd)[3]-win32gui.GetWindowRect(hwnd)[1]), reverse=True)
            browser_main_handle = candidate_windows[0]
            _, browser_pid = win32process.GetWindowThreadProcessId(browser_main_handle)
            title = win32gui.GetWindowText(browser_main_handle)
            size = f"{win32gui.GetWindowRect(browser_main_handle)[2]-win32gui.GetWindowRect(browser_main_handle)[0]}x{win32gui.GetWindowRect(browser_main_handle)[3]-win32gui.GetWindowRect(browser_main_handle)[1]}"
            print(f"✅ 找到Edge主窗口：句柄={browser_main_handle} | 标题={title[:50]} | 大小={size} | PID={browser_pid}")
            return browser_main_handle

        print(f"⚠️ 未找到匹配的Edge窗口，重试中...")
        time.sleep(WINDOW_FIND_INTERVAL)

    print(f"❌ 多次重试后仍未找到Edge窗口，程序退出")
    exit(1)


def iterative_enum_child_windows(hwnd):
    """迭代枚举子窗口（无栈溢出，限制深度）"""
    child_handles = []
    try:
        window_stack = [(hwnd, 0)]
        while window_stack and len(child_handles) < 1000:
            current_hwnd, depth = window_stack.pop()
            if depth > MAX_ENUM_DEPTH:
                continue
            # 枚举直接子窗口
            direct_children = []
            win32gui.EnumChildWindows(current_hwnd, lambda h, args: args.append(h) or True, direct_children)
            for child_hwnd in direct_children:
                if child_hwnd not in child_handles:
                    child_handles.append(child_hwnd)
                    window_stack.append((child_hwnd, depth + 1))
    except Exception as e:
        print(f"⚠️ 枚举子窗口异常：{str(e)}")
    return child_handles


def count_browser_tabs():
    """统计Edge标签页数量（精准匹配，去重）"""
    main_handle = get_browser_main_handle()
    browser_info = BROWSER_CONFIG[SELECTED_BROWSER]
    child_handles = iterative_enum_child_windows(main_handle)
    print(f"📌 枚举子窗口总数：{len(child_handles)}")

    # 获取浏览器所有进程ID（主进程+子进程）
    child_pids = set()
    if browser_pid:
        try:
            parent_proc = psutil.Process(browser_pid)
            child_pids = {child.pid for child in parent_proc.children(recursive=True)}
            child_pids.add(browser_pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            print("⚠️ 无法获取Edge子进程信息")

    # 筛选标签页窗口
    tab_handles = []
    for hwnd in child_handles:
        try:
            if not win32gui.IsWindowVisible(hwnd):
                continue
            # 匹配进程ID
            _, hwnd_pid = win32process.GetWindowThreadProcessId(hwnd)
            if hwnd_pid not in child_pids:
                continue
            # 匹配标签页类名
            if win32gui.GetClassName(hwnd) not in browser_info["tab_classes"]:
                continue
            # 匹配标题（排除无效标题）
            title = win32gui.GetWindowText(hwnd)
            if not title:
                continue
            if any(re.search(pattern, title) for pattern in browser_info["title_exclude_patterns"]):
                continue
            # 匹配标签页尺寸
            rect = win32gui.GetWindowRect(hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            if 100 <= width <= 1500 and 20 <= height <= 100:
                tab_handles.append(hwnd)
        except:
            continue

    # 去重（排除完全重叠的窗口）
    unique_tabs = []
    for tab in tab_handles:
        rect = win32gui.GetWindowRect(tab)
        is_duplicate = False
        for existing in unique_tabs:
            existing_rect = win32gui.GetWindowRect(existing)
            if (abs(rect[0]-existing_rect[0]) < 5 and
                abs(rect[1]-existing_rect[1]) < 5 and
                abs(rect[2]-existing_rect[2]) < 5 and
                abs(rect[3]-existing_rect[3]) < 5):
                is_duplicate = True
                break
        if not is_duplicate:
            unique_tabs.append(tab)

    # 多次检测取最大值（避免加载延迟漏检）
    final_count = len(unique_tabs)
    for _ in range(1, TAB_DETECT_RETRY_TIMES // 2):
        time.sleep(TAB_DETECT_INTERVAL / 2)
        temp_tabs = []
        for hwnd in iterative_enum_child_windows(main_handle):
            try:
                if win32gui.IsWindowVisible(hwnd) and win32gui.GetClassName(hwnd) in browser_info["tab_classes"]:
                    temp_tabs.append(hwnd)
            except:
                continue
        final_count = max(final_count, len(temp_tabs))

    final_count = max(final_count, 1)  # 至少1个标签页
    print(f"📌 Edge标签页数量：{final_count}个")
    return final_count


def is_new_tab_opened():
    """检测是否新增标签页（含容错逻辑）"""
    global pre_click_tab_count
    # 激活浏览器前台
    win32gui.SetForegroundWindow(get_browser_main_handle())
    time.sleep(0.5)

    # 多次检测取稳定值
    tab_counts = [count_browser_tabs() for _ in range(TAB_DETECT_RETRY_TIMES)]
    current_count = max(tab_counts)
    is_opened = current_count > pre_click_tab_count

    # 容错：标签数未变但有新文件，视为新增标签
    if not is_opened:
        current_files = set(os.path.abspath(os.path.join(DOWNLOAD_PATH, f)) for f in os.listdir(DOWNLOAD_PATH) if os.path.isfile(os.path.join(DOWNLOAD_PATH, f)))
        new_files = current_files - downloaded_files
        if new_files:
            is_opened = True
            print(f"📌 标签数未变，但检测到新文件，视为新增标签")

    print(f"📌 标签页变化：{pre_click_tab_count}→{current_count}（新增：{'是' if is_opened else '否'}）")
    if is_opened:
        pre_click_tab_count = current_count
    return is_opened


def close_new_tab():
    """关闭新增标签页（确保关闭成功）"""
    current_count = count_browser_tabs()
    if current_count <= 1:
        print(f"⚠️ 仅{current_count}个标签页，无需关闭")
        return True

    print(f"📌 关闭新增标签页（当前{current_count}个）")
    main_handle = get_browser_main_handle()
    win32gui.SetForegroundWindow(main_handle)
    time.sleep(0.8)

    # 尝试Ctrl+W关闭
    pyautogui.hotkey('ctrl', 'w')
    time.sleep(CLOSE_TAB_DELAY)
    new_count = count_browser_tabs()

    # 容错：关闭失败则重试
    if new_count >= current_count:
        print("⚠️ 首次关闭失败，重试...")
        pyautogui.hotkey('ctrl', 'w')
        time.sleep(CLOSE_TAB_DELAY)
        new_count = count_browser_tabs()

    print(f"✅ 关闭后标签页数量：{new_count}个")
    global pre_click_tab_count
    pre_click_tab_count = new_count
    return new_count < current_count


# ==================== 四、核心功能模块（按流程顺序） ====================
def select_region():
    """让用户框选下载按钮区域（仅执行1次）"""
    global saved_region
    # 激活浏览器，方便框选
    win32gui.SetForegroundWindow(get_browser_main_handle())
    time.sleep(1)

    # 截取全屏供框选
    while not take_screenshot():
        time.sleep(2)
    img = cv2.imread(SCREENSHOT_PATH)
    img_copy = img.copy()
    img_h, img_w = img.shape[:2]
    ref_point = []
    cropping = False

    # 鼠标事件：框选区域
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

    # 显示窗口供框选
    cv2.namedWindow("框选所有下载按钮区域（按ESC确认）", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("框选所有下载按钮区域（按ESC确认）", img_w//2, img_h//2)
    cv2.imshow("框选所有下载按钮区域（按ESC确认）", img_copy)
    cv2.setMouseCallback("框选所有下载按钮区域（按ESC确认）", click_event)

    # 等待ESC确认
    while cv2.waitKey(1) != 27:
        pass
    cv2.destroyAllWindows()

    # 保存框选区域
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
    """识别下载按钮（置信度降级+去重，确保10个）"""
    if not saved_region:
        print("❌ 未框选按钮区域，无法识别")
        return []

    x1, y1, x2, y2 = saved_region
    t_h, t_w = current_template_size
    take_screenshot()
    img = cv2.imread(SCREENSHOT_PATH)
    roi_gray = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)

    # 置信度降级策略，直到找到10个按钮
    current_confidence = INIT_CONFIDENCE
    buttons = []
    while len(buttons) < TARGET_BUTTON_COUNT and current_confidence >= MIN_CONFIDENCE:
        # 模板匹配
        result = cv2.matchTemplate(roi_gray, current_template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= current_confidence)

        # 计算按钮中心坐标（全局坐标）
        current_buttons = []
        for pt in zip(*locations[::-1]):
            center_x = x1 + pt[0] + t_w // 2
            center_y = y1 + pt[1] + t_h // 2
            current_buttons.append((center_x, center_y))

        # 按Y坐标排序+去重（间距小于按钮高度30%视为重复）
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
    """页面1偏移策略：双边递增（4,-4,8,-8...）"""
    step = (attempt // 2 + 1) * PAGE1_OFFSET_STEP
    return step if attempt % 2 == 0 else -step


def page2_offset_strategy(button_idx, attempt):
    """页面2偏移策略：分步骤双边推进"""
    if attempt == 0:
        return 0  # 第一步：基础位置
    elif 1 <= attempt <= PAGE2_STEP2_COUNT * 2:
        # 第二步：6,-6,12,-12...（3次尝试）
        step = (attempt // 2 + 1) * PAGE2_STEP2_STEP
        return step if attempt % 2 == 1 else -step
    else:
        # 第三步：22,-22,26,-26...（4px步长）
        step_idx = attempt - PAGE2_STEP2_COUNT * 2
        step = 22 + (step_idx // 2) * PAGE2_STEP3_STEP * 2
        return step if step_idx % 2 == 0 else -step


def try_click(base_x, base_y, offset_strategy, button_idx):
    """尝试点击按钮并检测下载成功（通用逻辑）"""
    # 激活浏览器前台
    win32gui.SetForegroundWindow(get_browser_main_handle())
    time.sleep(0.5)

    initial_files = set(downloaded_files)
    initial_tab_count = count_browser_tabs()
    global pre_click_tab_count
    pre_click_tab_count = initial_tab_count

    # 多次尝试偏移点击
    for attempt in range(MAX_RETRY_PER_BUTTON):
        if not is_running:
            break
        while is_paused:
            time.sleep(0.5)

        # 计算点击坐标（应用Edge专属偏移）
        offset = offset_strategy(button_idx, attempt)
        click_x = int(base_x + EDGE_CLICK_OFFSET_X)
        click_y = int(base_y + EDGE_CLICK_OFFSET_Y + offset)

        # 校验坐标有效性
        if not is_valid_coordinate(click_x, click_y):
            print(f"⚠️ 尝试{attempt+1}：坐标({click_x},{click_y})超出屏幕，跳过")
            continue

        # 执行点击
        try:
            print(f"📝 尝试{attempt+1}：点击({click_x},{click_y})（偏移：{offset}px）")
            pyautogui.moveTo(click_x, click_y, duration=BUTTON_CLICK_DELAY)
            pyautogui.click()
            time.sleep(POST_CLICK_WAIT)

            # 检测新增标签页+下载成功
            if is_new_tab_opened():
                if detect_new_file(initial_files):
                    close_new_tab()
                    return (True, offset)
                else:
                    print(f"⚠️ 新增标签页但未检测到文件，等待超时后关闭")
                    time.sleep(NEW_PAGE_TIMEOUT)
                    close_new_tab()
            else:
                # 未新增标签页，直接检测文件
                if detect_new_file(initial_files):
                    return (True, offset)

        except Exception as e:
            print(f"⚠️ 尝试{attempt+1}失败：{str(e)}")

        time.sleep(RETRY_WAIT)

    # 清理残留标签页
    if count_browser_tabs() > initial_tab_count:
        close_new_tab()
    return (False, 0)


def download_page1(buttons):
    """页面1下载逻辑：基于相邻按钮间距+双边偏移"""
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

        # 计算目标Y坐标
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
    """页面2下载逻辑：复用页面1X坐标+分步骤偏移"""
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

        base_x = page1_buttons[idx][0]  # 复用X坐标
        print(f"\n📥 第{current_page}页按钮{idx+1}（复用X：{int(base_x)}）")

        # 计算目标Y坐标
        if idx == 0:
            target_y = page1_buttons[0][1]  # 复用页面1按钮1的Y
        else:
            prev_final_y = page1_buttons[idx-1][1] + page1_buttons[idx-1][2]
            target_y = prev_final_y + PAGE2_STEP1_OFFSET  # 基础偏移

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
    """翻页操作（右键翻页，检测加载）"""
    global current_page
    # 激活浏览器前台
    win32gui.SetForegroundWindow(get_browser_main_handle())
    time.sleep(0.5)

    print(f"\n📖 翻页到第{current_page+1}页...")
    pyautogui.press('right')
    time.sleep(PAGE_TURN_DELAY)
    current_page += 1
    print(f"✅ 已翻到第{current_page}页")
    return True


def reset_page_by_turning():
    """翻页重置页面（处理加载异常）"""
    print(f"\n🔄 执行页面重置（当前第{current_page}页）")
    pyautogui.press('left')  # 向前翻
    time.sleep(PAGE_RESET_DELAY)
    pyautogui.press('right')  # 向后翻回原页
    time.sleep(PAGE_RESET_DELAY)
    print(f"✅ 页面重置完成")
    return True


# ==================== 五、键盘控制（全局快捷键） ====================
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


# ==================== 六、主程序（流程入口，逻辑清晰） ====================
def main():
    global system_scaling, is_running
    system_scaling = get_system_scaling()

    # 打印启动信息
    print("=" * 80)
    print(f"📌 知网下载器（页面{CURRENT_PAGE_TYPE}模式）- Edge专属稳定版")
    print(f"📌 核心功能：按钮识别→偏移点击→标签管理→自动翻页→异常重试")
    print(f"📌 适配环境：Edge浏览器（前台激活）| 分辨率：{screen_size[0]}x{screen_size[1]} | 缩放：{system_scaling:.1f}x")
    print(f"📌 快捷键：ESC=停止 | 空格=暂停/继续")
    print("=" * 80)

    # 初始化流程
    init_download_path()  # 初始化下载目录
    load_template()  # 加载按钮模板
    get_browser_main_handle()  # 查找Edge窗口
    pre_click_tab_count = count_browser_tabs()  # 初始化标签页计数

    # 框选按钮区域（必须完成）
    print("\n📌 请框选所有下载按钮区域（按ESC确认）")
    while not saved_region:
        if select_region():
            break
        time.sleep(2)

    # 启动键盘监听
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()
    print(f"\n✅ 初始化完成，开始识别第{current_page}页按钮...")

    # 主循环：下载→翻页→下载
    page_reset_count = 0
    try:
        while is_running:
            # 识别按钮
            buttons = find_buttons()
            if not buttons or len(buttons) < TARGET_BUTTON_COUNT:
                if page_reset_count < MAX_PAGE_RESET_TIMES:
                    print(f"⚠️ 按钮识别不足，尝试页面重置（{page_reset_count+1}/{MAX_PAGE_RESET_TIMES}）")
                    reset_page_by_turning()
                    page_reset_count += 1
                    time.sleep(RECOGNITION_RETRY_WAIT)
                    continue
                else:
                    print("❌ 多次重置仍无法识别足够按钮，终止任务")
                    break

            # 下载当前页
            print(f"\n🚀 启动第{current_page}页下载（{len(buttons)}个按钮）")
            if CURRENT_PAGE_TYPE == 1:
                download_success = download_page1(buttons)
            else:
                download_success = download_page2()

            # 翻页逻辑
            if download_success and is_running:
                page_reset_count = 0  # 下载成功，重置错误计数器
                if not turn_page():
                    print("⚠️ 翻页失败，终止任务")
                    break
            else:
                if page_reset_count < MAX_PAGE_RESET_TIMES:
                    print(f"⚠️ 第{current_page}页下载未完成，尝试重置（{page_reset_count+1}/{MAX_PAGE_RESET_TIMES}）")
                    reset_page_by_turning()
                    page_reset_count += 1
                    time.sleep(PAGE_DOWNLOAD_RETRY_WAIT)
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