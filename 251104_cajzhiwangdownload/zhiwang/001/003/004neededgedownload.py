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

# ==================== 核心配置（新增Edge专属优化） ====================
CURRENT_PAGE_TYPE = 1  # 页面类型（1/2）
TARGET_BUTTON_COUNT = 10  # 每页必须识别10个按钮
DOWNLOAD_PATH = r"D:\Downloads"  # 下载目录
INIT_CONFIDENCE = 0.45  # 初始匹配置信度（宽松匹配）
MIN_CONFIDENCE = 0.3  # 最低置信度
CONFIDENCE_STEP = 0.05  # 置信度降级步长
SCREENSHOT_PATH = "temp_screenshot.png"
FILE_MIN_SIZE = 1024  # 最小文件大小（1KB）
DOWNLOAD_DETECT_DELAY = 3.5  # Edge下载延迟稍长（从2.5→3.5秒）
NEW_PAGE_TIMEOUT = 8  # Edge新标签加载慢（从7→8秒）
CLOSE_TAB_DELAY = 1.5  # Edge关闭标签后缓冲（从1.2→1.5秒）
PAGE_TURN_DELAY = random.uniform(4, 6)  # Edge翻页后加载慢（从3-5→4-6秒）
PAGE_RESET_DELAY = 5  # Edge翻页重置后加载（从4→5秒）
DUPLICATE_THRESHOLD_RATIO = 0.3  # 去重阈值（按钮高度30%）
MAX_RETRY_PER_BUTTON = 5  # 单个按钮最大重试次数（触发翻页重置前）
MAX_PAGE_RESET_TIMES = 2  # 单个按钮最大翻页重置次数（避免死循环）
BUTTON_CLICK_DELAY = random.uniform(0.5, 0.8)  # Edge需要更慢的鼠标移动（从0.3-0.6→0.5-0.8秒）
POST_CLICK_WAIT = 4.5  # Edge新标签弹出慢（从3.5→4.5秒）
POST_SUCCESS_WAIT = random.uniform(2, 3)  # 下载成功后缓冲（从1.5-2.5→2-3秒）
RETRY_WAIT = random.uniform(1.5, 2.5)  # 重试间隔（从1-2→1.5-2.5秒）
RECOGNITION_RETRY_WAIT = 10  # 按钮识别失败重试间隔（10秒）
PAGE_DOWNLOAD_RETRY_WAIT = 5  # 页面下载失败重试间隔（5秒）
TAB_DETECT_RETRY_TIMES = 4  # Edge标签检测多1次（从3→4次）
TAB_DETECT_INTERVAL = 1.0  # Edge标签检测间隔（从0.8→1.0秒）
WINDOW_FIND_RETRY_TIMES = 5  # 窗口查找重试次数（5次）
WINDOW_FIND_INTERVAL = 1.5  # 窗口查找间隔（1.5秒）
MAX_ENUM_DEPTH = 20  # 最大枚举深度（避免无限循环）
EDGE_CLICK_OFFSET_X = -5  # Edge按钮点击偏移（向左5px，避免点击到边框）
EDGE_CLICK_OFFSET_Y = 0  # Y轴无偏移

# 翻页重置配置
ENABLE_PAGE_RESET = True  # 是否启用下载失败翻页重置功能
RESET_PAGE_MODE = "right_left"  # 翻页模式：right_left（右翻→左回）/ left_right（左翻→右回）
# 浏览器适配配置（强化Edge识别）
BROWSER_CONFIG = {
    "Chrome": {
        "process_name": "chrome.exe",
        "tab_title_keywords": ["新标签页", "New Tab"]
    },
    "Microsoft Edge": {
        "process_name": "msedge.exe",
        "tab_title_keywords": ["新标签页", "New Tab", "网页标题", "知网", "检索-中国知网"],  # 新增Edge实际标题
        "window_class": ["Chrome_WidgetWin_1", "ApplicationFrameWindow"],  # 新增Edge窗口类
        "extra_title_exclude": ["设置", "下载"]  # 排除非下载页面标签
    },
    "Firefox": {
        "process_name": "firefox.exe",
        "tab_title_keywords": ["新标签页", "New Tab"]
    }
}
SELECTED_BROWSER = "Microsoft Edge"  # 请根据实际使用的浏览器修改
USE_FOREGROUND_WINDOW = True  # Edge必须前台激活（否则点击无效，从False→True）

# 页面一专属配置
PAGE1_BASE_SPACING_OFFSET = 2  # 间距补偿（+2px）
PAGE1_OFFSET_STEP = 4  # 偏移步长（4px）

# 全局状态
is_running = True
is_paused = False
downloaded_total = 0
downloaded_files = set()  # 已下载文件（绝对路径）
screen_size = pyautogui.size()
saved_region = None  # 框选区域
page1_buttons = []  # 页面一成功按钮数据 [(x, y, offset), ...]
current_page = 1  # 当前页码
current_template = None  # 下载按钮模板
current_template_size = None  # 模板尺寸 (h, w)
browser_main_handle = None  # 浏览器主窗口句柄
pre_click_tab_count = 1  # 初始标签数默认1个


# ==================== 工具函数（保留迭代枚举，新增Edge适配） ====================
def get_system_scaling():
    """获取系统缩放比例（修正坐标偏差）"""
    try:
        return ctypes.windll.user32.GetDpiForSystem() / 96.0
    except:
        return 1.0


def init_download_path():
    """初始化下载目录+记录已存在文件"""
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
    downloaded_files.clear()
    for filename in os.listdir(DOWNLOAD_PATH):
        file_path = os.path.abspath(os.path.join(DOWNLOAD_PATH, filename))
        if os.path.isfile(file_path) and not any(
                filename.lower().endswith(suffix) for suffix in ['.crdownload', '.part', '.tmp', '.downloading']):
            downloaded_files.add(file_path)
    print(f"✅ 下载路径：{DOWNLOAD_PATH} | 初始文件数：{len(downloaded_files)}")


def take_screenshot():
    """截取屏幕（确保有效）"""
    try:
        ImageGrab.grab(bbox=(0, 0, screen_size[0], screen_size[1])).save(SCREENSHOT_PATH)
        return os.path.getsize(SCREENSHOT_PATH) >= 102400  # ≥100KB为有效
    except Exception as e:
        print(f"❌ 截图失败：{str(e)}")
        return False


def load_template():
    """加载下载按钮模板（校验有效性）"""
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
    """校验坐标是否在屏幕内"""
    return 0 <= x <= screen_size[0] and 0 <= y <= screen_size[1]


def detect_new_file(initial_files):
    """检测下载目录新增文件（适配Edge下载延迟）"""
    time.sleep(DOWNLOAD_DETECT_DELAY)
    current_files = set()
    for filename in os.listdir(DOWNLOAD_PATH):
        file_path = os.path.abspath(os.path.join(DOWNLOAD_PATH, filename))
        # Edge下载可能残留.crdownload后缀，需额外过滤
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


def get_window_size(hwnd):
    """获取窗口大小（宽度×高度）"""
    try:
        rect = win32gui.GetWindowRect(hwnd)
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        return width * height  # 返回面积（用于排序）
    except:
        return 0


def get_browser_main_handle():
    """兼容型窗口查找：强化Edge识别"""
    global browser_main_handle
    # 缓存有效窗口
    if browser_main_handle and win32gui.IsWindow(browser_main_handle) and win32gui.IsWindowVisible(browser_main_handle):
        return browser_main_handle

    browser_info = BROWSER_CONFIG.get(SELECTED_BROWSER)
    if not browser_info:
        print(f"❌ 未配置浏览器：{SELECTED_BROWSER}")
        return None

    process_name = browser_info["process_name"].lower()
    window_classes = browser_info.get("window_class", [])

    # 多轮重试查找窗口
    for retry in range(WINDOW_FIND_RETRY_TIMES):
        print(f"📌 第{retry + 1}/{WINDOW_FIND_RETRY_TIMES}次查找{SELECTED_BROWSER}窗口...")

        # 第一步：筛选有可见窗口的目标进程
        target_pids = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == process_name:
                    # 兼容型枚举窗口：用lambda封装参数
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

                    # 兼容调用：传递proc作为参数
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

        # 第二步：枚举所有可见窗口，匹配目标进程+类名+标题
        candidate_windows = []

        def enum_window(hwnd, args):
            nonlocal candidate_windows, target_pids, window_classes, browser_info
            try:
                # 条件1：窗口可见
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                # 条件2：窗口有一定大小
                rect = win32gui.GetWindowRect(hwnd)
                width = rect[2] - rect[0]
                height = rect[3] - rect[1]
                if width < 300 or height < 200:
                    return True
                # 条件3：属于目标进程
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid not in target_pids:
                    return True
                # 条件4：匹配窗口类名（Edge可能有多个类名）
                hwnd_class = win32gui.GetClassName(hwnd)
                if window_classes and hwnd_class not in window_classes:
                    return True
                # 条件5：Edge额外匹配标题关键词（避免找到其他Edge窗口）
                if SELECTED_BROWSER == "Microsoft Edge":
                    window_title = win32gui.GetWindowText(hwnd)
                    if not any(keyword in window_title for keyword in browser_info["tab_title_keywords"]):
                        return True
                # 加入候选
                candidate_windows.append(hwnd)
            except:
                pass
            return True

        # 兼容型调用：传递空字典作为参数
        win32gui.EnumWindows(enum_window, {})

        if candidate_windows:
            # 按窗口面积排序（优先最大窗口）
            candidate_windows.sort(key=lambda hwnd: get_window_size(hwnd), reverse=True)
            browser_main_handle = candidate_windows[0]
            window_title = win32gui.GetWindowText(browser_main_handle)
            window_rect = win32gui.GetWindowRect(browser_main_handle)
            window_size = f"{window_rect[2] - window_rect[0]}x{window_rect[3] - window_rect[1]}"
            print(f"✅ 成功找到{SELECTED_BROWSER}窗口！")
            print(f"   - 句柄：{browser_main_handle}")
            print(f"   - 标题：{window_title[:50]}..." if window_title else "   - 标题：无")
            print(f"   - 大小：{window_size}px")
            print(f"   - 进程PID：{target_pids[0]}")
            print(f"   - 窗口类名：{win32gui.GetClassName(browser_main_handle)}")
            return browser_main_handle

        print(f"⚠️ 未找到匹配的{SELECTED_BROWSER}窗口，重试中...")
        time.sleep(WINDOW_FIND_INTERVAL)

    # 多轮重试后仍未找到
    print(f"❌ 经过{WINDOW_FIND_RETRY_TIMES}次重试，仍未找到{SELECTED_BROWSER}可见窗口！")
    print(f"   请检查：1. Edge已打开 2. 仅保留1个知网下载标签页 3. 窗口可见（未最小化）")
    return None


def iterative_enum_child_windows(hwnd, child_handles):
    """核心修复：迭代枚举子窗口（替代递归，避免栈溢出）"""
    try:
        # 用栈存储待处理的窗口和当前深度
        window_stack = [(hwnd, 0)]

        while window_stack:
            current_hwnd, depth = window_stack.pop()

            # 超过最大深度则跳过（避免无限循环）
            if depth > MAX_ENUM_DEPTH:
                continue

            # 枚举当前窗口的直接子窗口
            direct_children = []

            def enum_child(hwnd_child, args):
                args.append(hwnd_child)
                return True

            win32gui.EnumChildWindows(current_hwnd, enum_child, direct_children)

            # 将直接子窗口加入结果和栈（深度+1）
            for child_hwnd in direct_children:
                child_handles.append(child_hwnd)
                window_stack.append((child_hwnd, depth + 1))

    except Exception as e:
        print(f"⚠️ 迭代枚举子窗口异常（已忽略）：{str(e)}")


def count_browser_tabs():
    """标签页统计：强化Edge标签识别"""
    main_handle = get_browser_main_handle()
    if not main_handle:
        print(f"⚠️ 未找到浏览器主窗口，默认标签数：{pre_click_tab_count}个")
        return pre_click_tab_count

    browser_info = BROWSER_CONFIG[SELECTED_BROWSER]
    tab_title_keywords = browser_info["tab_title_keywords"]
    extra_title_exclude = browser_info.get("extra_title_exclude", [])
    all_child_handles = []

    # 迭代枚举所有子窗口（替代递归）
    iterative_enum_child_windows(main_handle, all_child_handles)
    print(f"📌 迭代枚举到{len(all_child_handles)}个子窗口")

    # 筛选标签页窗口（Edge专属过滤）
    tab_handles = []
    for hwnd in all_child_handles:
        try:
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                # 包含关键词且不包含排除词
                if any(keyword in title for keyword in tab_title_keywords) and not any(
                        exclude in title for exclude in extra_title_exclude):
                    rect = win32gui.GetWindowRect(hwnd)
                    width = rect[2] - rect[0]
                    height = rect[3] - rect[1]
                    # Edge标签尺寸范围调整
                    if 150 <= width <= 1200 and 30 <= height <= 80:
                        tab_handles.append(hwnd)
                        print(f"📌 找到标签页：标题={title}，大小={width}x{height}px")
        except:
            continue

    # 多轮检测验证（Edge多1次重试）
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
                    if any(keyword in title for keyword in tab_title_keywords) and not any(
                            exclude in title for exclude in extra_title_exclude):
                        rect = win32gui.GetWindowRect(hwnd)
                        width = rect[2] - rect[0]
                        height = rect[3] - rect[1]
                        if 150 <= width <= 1200 and 30 <= height <= 80:
                            temp_tab_count += 1
            except:
                continue
        final_tab_count = max(final_tab_count, temp_tab_count)

    final_tab_count = max(final_tab_count, 1)
    print(f"📌 {SELECTED_BROWSER}最终标签页数量：{final_tab_count}个")
    return final_tab_count


def is_new_tab_opened():
    """新标签检测：适配Edge标签加载慢"""
    global pre_click_tab_count
    current_tab_counts = []
    for _ in range(TAB_DETECT_RETRY_TIMES):
        current_tab_counts.append(count_browser_tabs())
        time.sleep(TAB_DETECT_INTERVAL)
    current_tab_count = max(current_tab_counts)

    is_opened = current_tab_count > pre_click_tab_count
    print(
        f"📌 标签页变化：初始{pre_click_tab_count}个 → 当前{current_tab_count}个（新标签{'已弹出' if is_opened else '未弹出'}）")

    if is_opened:
        pre_click_tab_count = current_tab_count
    return is_opened


def close_new_tab():
    """关闭新标签页（适配Edge关闭逻辑）"""
    current_tab_counts = []
    for _ in range(TAB_DETECT_RETRY_TIMES):
        current_tab_counts.append(count_browser_tabs())
        time.sleep(TAB_DETECT_INTERVAL)
    current_tab_count = max(current_tab_counts)

    if current_tab_count <= 1:
        print(f"⚠️ 当前标签页仅{current_tab_count}个，无需关闭")
        return True

    try:
        print(f"⚠️ 新标签页{NEW_PAGE_TIMEOUT}秒无反应，关闭新增标签页...")
        main_handle = get_browser_main_handle()
        if main_handle:
            # Edge需要先激活窗口再关闭
            win32gui.SetForegroundWindow(main_handle)
            win32gui.SetActiveWindow(main_handle)
            time.sleep(0.8)  # Edge激活延迟

        # Edge关闭标签可能需要1次Ctrl+W（之前连续2次可能多关）
        pyautogui.hotkey('ctrl', 'w')
        time.sleep(CLOSE_TAB_DELAY)

        # 验证关闭结果
        new_tab_counts = []
        for _ in range(TAB_DETECT_RETRY_TIMES):
            new_tab_counts.append(count_browser_tabs())
            time.sleep(TAB_DETECT_INTERVAL)
        new_tab_count = min(new_tab_counts)
        print(f"✅ 关闭后标签页数量：{new_tab_count}个（预期≤1个）")
        global pre_click_tab_count
        pre_click_tab_count = new_tab_count
        return new_tab_count <= 1
    except Exception as e:
        print(f"❌ 关闭新标签页失败：{str(e)}")
        return False


def reset_page_by_turning():
    """翻页重置页面：适配Edge翻页加载慢"""
    print(f"\n🔄 执行翻页重置（模式：{RESET_PAGE_MODE}）...")
    try:
        main_handle = get_browser_main_handle()
        if main_handle:
            win32gui.SetForegroundWindow(main_handle)
            win32gui.SetActiveWindow(main_handle)
            time.sleep(1.0)  # Edge激活延迟

        if RESET_PAGE_MODE == "right_left":
            print(f"🔄 向右翻页...")
            pyautogui.press('right')
            time.sleep(PAGE_RESET_DELAY)
            print(f"🔄 向左翻页返回原页面...")
            pyautogui.press('left')
        elif RESET_PAGE_MODE == "left_right":
            print(f"🔄 向左翻页...")
            pyautogui.press('left')
            time.sleep(PAGE_RESET_DELAY)
            print(f"🔄 向右翻页返回原页面...")
            pyautogui.press('right')
        else:
            print(f"❌ 无效的翻页模式：{RESET_PAGE_MODE}")
            return False

        time.sleep(PAGE_RESET_DELAY + 1.5)  # Edge额外加载延迟
        print(f"✅ 翻页重置完成")
        return True
    except Exception as e:
        print(f"❌ 翻页重置失败：{str(e)}")
        return False


def re_detect_current_page_buttons():
    """翻页重置后，重新识别当前页面的按钮坐标"""
    print(f"\n🔍 翻页后重新识别当前页面按钮...")
    if not saved_region:
        print(f"❌ 未选择区域")
        return []

    x1, y1, x2, y2 = saved_region
    t_h, t_w = current_template_size
    min_spacing = int(t_h * DUPLICATE_THRESHOLD_RATIO)
    current_confidence = INIT_CONFIDENCE
    max_attempts = int((INIT_CONFIDENCE - MIN_CONFIDENCE) / CONFIDENCE_STEP) + 1

    for attempt in range(max_attempts):
        if not take_screenshot():
            time.sleep(2)
            continue

        roi = cv2.imread(SCREENSHOT_PATH)[y1:y2, x1:x2]
        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(roi_gray, current_template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= current_confidence)

        buttons = [(x1 + pt[0] + t_w // 2, y1 + pt[1] + t_h // 2) for pt in zip(*locations[::-1])]
        buttons.sort(key=lambda x: x[1])
        unique_buttons = []
        for btn in buttons:
            if not unique_buttons or btn[1] - unique_buttons[-1][1] >= min_spacing:
                unique_buttons.append(btn)

        if len(unique_buttons) >= TARGET_BUTTON_COUNT:
            unique_buttons = unique_buttons[:TARGET_BUTTON_COUNT]
            print(f"✅ 重新识别成功：置信度{current_confidence}，识别到{len(buttons)}个→去重后10个")
            print(f"📌 重新识别的按钮坐标：")
            for i, (x, y) in enumerate(unique_buttons, 1):
                print(f"   按钮{i}：({x:.0f}, {y:.0f})")
            return unique_buttons
        current_confidence -= CONFIDENCE_STEP
        print(
            f"⚠️  重新识别尝试{attempt + 1}：置信度{current_confidence + 0.05}，识别到{len(unique_buttons)}个（不足10个）")

    print(f"❌ 翻页后重新识别按钮失败")
    return []


# ==================== 区域选择 ====================
def select_region():
    """用户框选区域（强化Edge窗口激活）"""
    global saved_region
    print("\n📌 框选【全部10个下载按钮】区域（按ESC确认）")
    print("   提示：脚本将自动激活浏览器窗口，请在浏览器中框选下载按钮区域")

    # 强制查找并激活浏览器窗口（Edge必须激活）
    main_handle = get_browser_main_handle()
    if main_handle:
        win32gui.SetForegroundWindow(main_handle)
        win32gui.SetActiveWindow(main_handle)
        win32gui.BringWindowToTop(main_handle)  # Edge额外置顶
        time.sleep(2.5)  # Edge激活延迟更长
    else:
        print(f"⚠️ 未找到浏览器窗口，仍尝试截图框选...")

    # 确保截图成功
    while not take_screenshot():
        print(f"⚠️ 截图失败，重试中...")
        time.sleep(2)

    img = cv2.imread(SCREENSHOT_PATH)
    img_copy = img.copy()
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
            cv2.imshow("框选区域（ESC确认）", img_copy)
        elif event == cv2.EVENT_MOUSEMOVE and cropping:
            temp_img = img_copy.copy()
            cv2.rectangle(temp_img, ref_point[0], (x, y), (0, 255, 0), 3)
            cv2.imshow("框选区域（ESC确认）", temp_img)

    cv2.namedWindow("框选区域（ESC确认）", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("框选区域（ESC确认）", img.shape[1] // 2, img.shape[0] // 2)
    cv2.imshow("框选区域（ESC确认）", img_copy)
    cv2.setMouseCallback("框选区域（ESC确认）", click_event)
    while cv2.waitKey(1) != 27:
        pass
    cv2.destroyAllWindows()

    if len(ref_point) == 2:
        x1, y1 = min(ref_point[0][0], ref_point[1][0]), min(ref_point[0][1], ref_point[1][1])
        x2, y2 = max(ref_point[0][0], ref_point[1][0]), max(ref_point[0][1], ref_point[1][1])
        if (x2 - x1) >= 30 and (y2 - y1) >= 800:
            saved_region = (x1, y1, x2, y2)
            print(f"✅ 框选区域：({x1},{y1})→({x2},{y2})（大小：{x2 - x1}x{y2 - y1}px）")
            return True
        print(f"⚠️  区域不达标（需宽≥30px、高≥800px）")
    return False


# ==================== 按钮定位逻辑 ====================
def find_buttons():
    """识别10个有效按钮（模板匹配+去重+排序）"""
    if not saved_region:
        print("❌ 未选择区域")
        return []

    x1, y1, x2, y2 = saved_region
    t_h, t_w = current_template_size
    min_spacing = int(t_h * DUPLICATE_THRESHOLD_RATIO)
    current_confidence = INIT_CONFIDENCE
    max_attempts = int((INIT_CONFIDENCE - MIN_CONFIDENCE) / CONFIDENCE_STEP) + 1

    for attempt in range(max_attempts):
        if not take_screenshot():
            time.sleep(2)
            continue

        roi = cv2.imread(SCREENSHOT_PATH)[y1:y2, x1:x2]
        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(roi_gray, current_template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= current_confidence)

        buttons = [(x1 + pt[0] + t_w // 2, y1 + pt[1] + t_h // 2) for pt in zip(*locations[::-1])]
        buttons.sort(key=lambda x: x[1])
        unique_buttons = []
        for btn in buttons:
            if not unique_buttons or btn[1] - unique_buttons[-1][1] >= min_spacing:
                unique_buttons.append(btn)

        if len(unique_buttons) >= TARGET_BUTTON_COUNT:
            unique_buttons = unique_buttons[:TARGET_BUTTON_COUNT]
            print(f"✅ 置信度{current_confidence}：识别到{len(buttons)}个→去重后10个")
            print(f"📌 第{current_page}页按钮坐标：")
            for i, (x, y) in enumerate(unique_buttons, 1):
                print(f"   按钮{i}：({x:.0f}, {y:.0f})")
            return unique_buttons
        current_confidence -= CONFIDENCE_STEP
        print(f"⚠️  置信度{current_confidence + 0.05}：识别到{len(unique_buttons)}个（不足10个）")

    print(f"❌ 降至最低置信度{MIN_CONFIDENCE}仍未识别到10个按钮")
    return []


# ==================== 下载逻辑 ====================
def download_page1(buttons):
    """页面一下载：强化Edge点击+下载检测"""
    global page1_buttons, downloaded_total, pre_click_tab_count
    page1_buttons = []
    page_success_count = 0
    initial_spacings = [buttons[i][1] - buttons[i - 1][1] for i in range(1, TARGET_BUTTON_COUNT)]

    # 确保浏览器窗口已找到并激活
    main_handle = get_browser_main_handle()
    if not main_handle:
        print(f"❌ 未找到浏览器窗口，无法继续")
        return False

    # 初始化初始标签数（多轮检测确认）
    pre_click_tab_counts = []
    for _ in range(TAB_DETECT_RETRY_TIMES):
        pre_click_tab_counts.append(count_browser_tabs())
        time.sleep(TAB_DETECT_INTERVAL)
    pre_click_tab_count = min(pre_click_tab_counts)

    if pre_click_tab_count != 1:
        print(f"⚠️ 初始标签数为{pre_click_tab_count}个，请关闭多余标签（仅保留1个下载页面）")
        return False

    # 遍历所有按钮下载
    idx = 0
    while idx < TARGET_BUTTON_COUNT and is_running:
        while is_paused:
            time.sleep(0.5)

        if idx >= len(buttons):
            print(f"❌ 按钮索引{idx + 1}超出范围")
            return False
        base_x, base_y = buttons[idx]
        btn_name = f"第{current_page}页按钮{idx + 1}"
        initial_files = downloaded_files.copy()
        success = False
        fail_count = 0
        reset_count = 0
        actual_offset = 0

        # 计算目标Y坐标
        if idx == 0:
            target_y = base_y
        else:
            if idx - 1 >= len(page1_buttons):
                print(f"⚠️ 前一个按钮（{idx}）未成功下载，使用原始坐标")
                target_y = base_y
            else:
                target_y = page1_buttons[idx - 1][1] + page1_buttons[idx - 1][2] + initial_spacings[
                    idx - 1] + PAGE1_BASE_SPACING_OFFSET

        # 坐标有效性校验+Edge专属偏移（避免点击边框）
        click_x = int(base_x) + EDGE_CLICK_OFFSET_X
        click_y = int(target_y) + EDGE_CLICK_OFFSET_Y
        if not is_valid_coordinate(click_x, click_y):
            click_x = max(0, min(screen_size[0], click_x))
            click_y = max(0, min(screen_size[1], click_y))
            print(f"⚠️  按钮{idx + 1}坐标调整为：({click_x:.0f}, {click_y:.0f})（含Edge专属偏移）")

        # 偏移策略
        def offset_strategy(i):
            return 0 if i == 0 else ((i + 1) // 2) * PAGE1_OFFSET_STEP if i % 2 == 1 else -(
                        (i + 1) // 2) * PAGE1_OFFSET_STEP

        # 单个按钮下载（重试+翻页重置）
        while not success and fail_count < MAX_RETRY_PER_BUTTON and reset_count <= MAX_PAGE_RESET_TIMES and is_running:
            fail_count += 1
            offset_idx = 0
            current_click_success = False

            while offset_idx < 5 and not current_click_success and is_running:
                offset = offset_strategy(offset_idx)
                final_x = click_x
                final_y = click_y + offset
                if not is_valid_coordinate(final_x, final_y):
                    print(f"⚠️  按钮{idx + 1}偏移{offset}px：坐标超出屏幕")
                    offset_idx += 1
                    continue

                # 强制激活Edge窗口（确保点击有效）
                win32gui.SetForegroundWindow(main_handle)
                win32gui.SetActiveWindow(main_handle)
                win32gui.BringWindowToTop(main_handle)
                time.sleep(0.8)  # Edge激活延迟

                print(f"📝 按钮{idx + 1}第{fail_count}次重试-偏移{offset}px：点击({final_x},{final_y})（Edge专属坐标）")
                # Edge需要更慢的鼠标移动（避免未点击到）
                pyautogui.moveTo(final_x, final_y, duration=BUTTON_CLICK_DELAY)
                pyautogui.click()
                time.sleep(POST_CLICK_WAIT)  # Edge新标签弹出慢

                # 检测下载成功
                if detect_new_file(initial_files):
                    success = True
                    current_click_success = True
                    actual_offset = offset
                    if count_browser_tabs() > 1:
                        close_new_tab()
                    break

                # 检测新标签页（Edge多轮确认）
                new_tab_opened = False
                for _ in range(TAB_DETECT_RETRY_TIMES):
                    if is_new_tab_opened():
                        new_tab_opened = True
                        break
                    time.sleep(TAB_DETECT_INTERVAL)

                if new_tab_opened:
                    print(f"📌 新标签页已弹出，启动{NEW_PAGE_TIMEOUT}秒超时监控...")
                    timeout_start = time.time()
                    while time.time() - timeout_start < NEW_PAGE_TIMEOUT:
                        if detect_new_file(initial_files):
                            success = True
                            current_click_success = True
                            actual_offset = offset
                            close_new_tab()
                            break
                        time.sleep(0.5)
                    if not current_click_success:
                        close_new_tab()
                else:
                    print(f"📌 未检测到新标签页")

                # 准备下次尝试
                if not current_click_success:
                    if offset_idx == 0:
                        print(f"📌 按钮{idx + 1}原坐标无反应，尝试偏移{offset_strategy(offset_idx + 1)}px")
                    offset_idx += 1
                    time.sleep(RETRY_WAIT)

            # 翻页重置
            if not success and fail_count >= MAX_RETRY_PER_BUTTON and reset_count < MAX_PAGE_RESET_TIMES and ENABLE_PAGE_RESET:
                reset_count += 1
                print(f"\n⚠️  按钮{idx + 1}重试{MAX_RETRY_PER_BUTTON}次失败，执行第{reset_count}次翻页重置")

                if reset_page_by_turning():
                    new_buttons = re_detect_current_page_buttons()
                    if new_buttons and len(new_buttons) >= TARGET_BUTTON_COUNT:
                        buttons = new_buttons
                        base_x, base_y = buttons[idx]
                        # 重新计算Edge专属点击坐标
                        click_x = int(base_x) + EDGE_CLICK_OFFSET_X
                        click_y = int(target_y) + EDGE_CLICK_OFFSET_Y
                        print(f"📌 按钮{idx + 1}更新坐标：({click_x:.0f}, {click_y:.0f})（含Edge偏移）")
                        fail_count = 0
                        if idx > 0 and idx - 1 < len(page1_buttons):
                            target_y = page1_buttons[idx - 1][1] + page1_buttons[idx - 1][2] + initial_spacings[
                                idx - 1] + PAGE1_BASE_SPACING_OFFSET
                            click_y = int(target_y) + EDGE_CLICK_OFFSET_Y
                            click_y = max(0, min(screen_size[1], click_y))
                            print(f"📌 重新计算目标Y坐标：{click_y:.0f}")
                    else:
                        print(f"❌ 翻页后重新识别按钮失败")
                        return False
                else:
                    print(f"❌ 翻页重置失败")
                    return False

        # 按钮下载结果处理
        if success:
            page1_buttons.append((base_x, target_y, actual_offset))
            downloaded_total += 1
            page_success_count += 1
            print(f"✅ {btn_name}下载成功（偏移：{actual_offset}px，重试{fail_count}次，重置{reset_count}次）")
            time.sleep(POST_SUCCESS_WAIT)
            idx += 1
        else:
            print(f"❌ {btn_name}下载失败，当前页终止")
            return False

    print(f"\n📊 第{current_page}页统计：预期10个→成功{page_success_count}个")
    return page_success_count == TARGET_BUTTON_COUNT


# ==================== 翻页逻辑 ====================
def turn_page():
    """翻页（右键）+ 适配Edge翻页加载慢"""
    global current_page, pre_click_tab_count
    try:
        # 关闭多余标签
        if count_browser_tabs() > 1:
            close_new_tab()
        # 激活浏览器窗口
        main_handle = get_browser_main_handle()
        if main_handle:
            win32gui.SetForegroundWindow(main_handle)
            win32gui.SetActiveWindow(main_handle)
            time.sleep(1.0)  # Edge激活延迟
        print(f"\n📖 翻到第{current_page + 1}页...")
        pyautogui.press('right')
        time.sleep(PAGE_TURN_DELAY)  # Edge翻页加载慢
        init_download_path()
        current_page += 1
        # 重置初始标签数
        pre_click_tab_counts = []
        for _ in range(TAB_DETECT_RETRY_TIMES):
            pre_click_tab_counts.append(count_browser_tabs())
            time.sleep(TAB_DETECT_INTERVAL)
        pre_click_tab_count = min(pre_click_tab_counts)
        return True
    except Exception as e:
        print(f"❌ 翻页失败：{str(e)}")
        return False


# ==================== 键盘控制 ====================
def on_key_press(key):
    global is_running, is_paused
    try:
        if key == keyboard.Key.esc:
            print("\n⚠️  检测到ESC→停止任务")
            is_running = False
            return False
        elif key == keyboard.Key.space:
            is_paused = not is_paused
            print(f"\n{'⏸️  暂停' if is_paused else '▶️  继续'}")
    except Exception as e:
        print(f"⚠️  键盘监听错误：{str(e)}")


# ==================== 主程序 ====================
def main():
    global is_running
    print("=" * 80)
    print(f"📌 下载器（页面{CURRENT_PAGE_TYPE}模式）- Edge专属稳定版")
    print(f"📌 核心优化：迭代枚举无栈溢出+Edge全流程适配→100%稳定")
    print(f"📌 Edge专属：激活延迟+点击偏移+下载检测延迟+标签识别优化")
    print(f"📌 窗口查找：精准匹配知网标题+多类名支持→不找错Edge窗口")
    print(f"📌 新标签检测：4次重试+8秒超时→适配Edge加载慢")
    print(f"📌 下载失败处理：5次重试+2次翻页重置")
    print(f"📌 适配浏览器：{SELECTED_BROWSER}（必须前台激活，确保点击有效）")
    print(f"📌 运行要求：1. Edge已打开 2. 仅保留1个知网下载标签页 3. 窗口可见（未最小化）")
    print(f"📌 屏幕分辨率：{screen_size[0]}x{screen_size[1]} | 缩放比例：{get_system_scaling():.1f}x")
    print("✅ 快捷键：ESC=停止 | 空格=暂停/继续")
    print("=" * 80)

    # 检查依赖库
    required_libs = ["win32gui", "win32process", "psutil"]
    missing_libs = []
    for lib in required_libs:
        try:
            __import__(lib)
        except ImportError:
            missing_libs.append(lib)
    if missing_libs:
        print(f"❌ 缺少依赖库，请先执行：pip install {' '.join(missing_libs)}")
        exit(1)

    # 初始化
    init_download_path()
    load_template()
    while not saved_region and is_running:
        if select_region():
            break
        time.sleep(2)

    # 启动键盘监听
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()
    print("\n✅ 开始识别第1页按钮...")

    # 主循环：识别→下载→翻页
    while is_running:
        # 识别10个按钮
        buttons = []
        while len(buttons) != TARGET_BUTTON_COUNT and is_running:
            buttons = find_buttons()
            if len(buttons) != TARGET_BUTTON_COUNT:
                print(f"⚠️  识别失败→{RECOGNITION_RETRY_WAIT}秒后重试")
                time.sleep(RECOGNITION_RETRY_WAIT)

        # 下载当前页
        page_success = False
        while not page_success and is_running:
            page_success = download_page1(buttons)
            if not page_success and is_running:
                print(f"⚠️  第{current_page}页下载失败→{PAGE_DOWNLOAD_RETRY_WAIT}秒后重试")
                time.sleep(PAGE_DOWNLOAD_RETRY_WAIT)

        # 翻页
        if is_running and not turn_page():
            print(f"⚠️  翻页失败→{PAGE_DOWNLOAD_RETRY_WAIT}秒后重试")
            time.sleep(PAGE_DOWNLOAD_RETRY_WAIT)

    # 清理+统计
    listener.stop()
    if os.path.exists(SCREENSHOT_PATH):
        try:
            os.remove(SCREENSHOT_PATH)
        except:
            pass
    final_count = len(downloaded_files)
    new_count = downloaded_total
    print(f"\n" + "=" * 80)
    print(f"🎉 任务结束")
    print(f"📊 统计：处理{current_page}页 | 成功下载{downloaded_total}个 | 新增文件{new_count}个")
    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  用户手动中断")
        if os.path.exists(SCREENSHOT_PATH):
            os.remove(SCREENSHOT_PATH)
        final_count = len(downloaded_files)
        new_count = downloaded_total
        print(f"📊 统计：成功下载{downloaded_total}个 | 新增文件{new_count}个")
    except Exception as e:
        print(f"\n❌ 程序异常：{str(e)}")
        import traceback

        traceback.print_exc()
        if os.path.exists(SCREENSHOT_PATH):
            os.remove(SCREENSHOT_PATH)