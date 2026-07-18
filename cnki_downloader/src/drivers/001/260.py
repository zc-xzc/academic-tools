import pyautogui
import time
import random
import os
import cv2
import numpy as np
from pynput import keyboard
from PIL import ImageGrab
from pathlib import Path
import pytesseract
from fuzzywuzzy import fuzz
import re

# ==================== 核心配置 ====================
# OCR识别配置
OCR_REGION_OFFSET = (-60, -10, -10, 10)  # 文献编号区域相对下载按钮的偏移 (左,上,右,下)
DUPLICATE_THRESHOLD = 80  # 编号相似度阈值
FILE_DUPLICATE_THRESHOLD = 0.95  # 文件大小相似度阈值（95%以上判定为重复）
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# 时间设置（默认自动模式，可手动调整）
TIME_MODE = "auto"
HUMAN_MOVE_DURATION = (0.5, 1.2)
HUMAN_STAY_DURATION = (0.5, 1.5)
HUMAN_CLICK_INTERVAL = (0.08, 0.2)
HUMAN_DOWNLOAD_INTERVAL = (2.0, 5.0)
HUMAN_PAUSE_INTERVAL = (3, 8)
HUMAN_PAUSE_TRIGGER = 5  # 每下载5个休息一次

# 下载配置
DOWNLOAD_PATH = r"D:\Downloads"
CONFIDENCE = 0.45
SERIAL_DOWNLOAD_DX = 0
SERIAL_DOWNLOAD_DY = 0
FILE_MIN_SIZE = 1024  # 最小有效文件大小（字节）
DOWNLOAD_TIMEOUT = 30
PAGE_LOAD_DELAY = random.uniform(3.5, 5.0)
TEMP_SCREENSHOT = "temp_page_screenshot.png"
WINDOW_TITLE = "知网下载区域框选"

# 滚动配置（核心：页面内滚动参数）
SCROLL_STEP = 600  # 每次滚动距离（像素）
MAX_PAGE_SCROLL = 15  # 单页最大滚动次数（防止无限滚动）
SCROLL_CONFIRM_TIMES = 2  # 连续N次识别不到新按钮则判定页面结束

# 颜色判断配置
BLUE_THRESHOLD = (100, 150)
YELLOW_THRESHOLD = (180, 255)

# 全局状态
is_running = True
is_paused = False
current_page = 1
downloaded_count = 0
initial_files = set()
selected_region = None
screen_ratio = (1.0, 1.0)
box_selected = False
page_nav_history = [1]
downloaded_ids = set()  # 已下载文献编号
downloaded_files_info = set()  # 已下载文件信息（名称+大小）
last_download_y = 0  # 最后一个下载按钮的Y坐标（用于滚动定位）
page_scroll_count = 0  # 当前页滚动次数
no_new_button_count = 0  # 连续识别不到新按钮的次数


# ==================== OCR识别与去重函数 ====================
def init_ocr():
    """初始化OCR引擎"""
    global TESSERACT_PATH
    if not os.path.exists(TESSERACT_PATH):
        print("\n❌ 未找到Tesseract-OCR，请安装并配置路径")
        print("   下载地址：https://github.com/UB-Mannheim/tesseract/wiki")
        new_path = input("   请输入安装路径（tesseract.exe）：").strip()
        if os.path.exists(new_path):
            TESSERACT_PATH = new_path
            print("✅ OCR路径已更新")
        else:
            print("❌ 无效路径，仅启用文件去重")
            return False
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
    return True


def get_document_id(button_pos):
    """获取文献编号（优化识别精度）"""
    x, y = button_pos
    left = max(0, x + OCR_REGION_OFFSET[0])
    top = max(0, y + OCR_REGION_OFFSET[1])
    right = min(pyautogui.size()[0], x + OCR_REGION_OFFSET[2])
    bottom = min(pyautogui.size()[1], y + OCR_REGION_OFFSET[3])

    try:
        # 截图并预处理
        id_region = ImageGrab.grab(bbox=(left, top, right, bottom))
        id_np = np.array(id_region)
        gray = cv2.cvtColor(id_np, cv2.COLOR_RGB2GRAY)
        _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)

        # OCR识别（只保留数字、字母、中文）
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ一二三四五六七八九十百千万亿'
        text = pytesseract.image_to_string(thresh, config=custom_config)
        text = re.sub(r'\s+', '', text.strip())  # 去除所有空白字符
        print(f"🔍 识别文献编号：{text} (区域: {left},{top},{right},{bottom})")
        return text if len(text) >= 2 else None
    except Exception as e:
        print(f"❌ 编号识别失败：{str(e)}")
        return None


def get_file_key(file_name, file_size):
    """生成文件唯一标识（用于去重）"""
    # 提取文件名中的数字和关键字符
    file_numbers = re.findall(r'\d+', file_name)
    key = ''.join(file_numbers) if file_numbers else file_name[:20]  # 取前20个字符
    return (key, round(file_size / 1024))  # 按KB取整，减少精度影响


def is_file_duplicate(new_file_name, new_file_size):
    """判断文件是否重复（名称+大小双重校验）"""
    new_key = get_file_key(new_file_name, new_file_size)

    for (exist_key, exist_size_kb) in downloaded_files_info:
        # 名称相似度匹配
        if fuzz.ratio(new_key[0], exist_key) > DUPLICATE_THRESHOLD:
            # 大小相似度匹配
            size_ratio = min(new_key[1], exist_size_kb) / max(new_key[1], exist_size_kb)
            if size_ratio > FILE_DUPLICATE_THRESHOLD:
                print(f"⚠️ 文件重复：{new_file_name} 与已下载文件相似度达标")
                return True
    return False


def is_duplicate(id_str):
    """综合判定是否重复（编号优先，文件为辅）"""
    # 编号去重
    if id_str:
        for existing_id in downloaded_ids:
            if fuzz.ratio(id_str, existing_id) > DUPLICATE_THRESHOLD:
                print(f"⚠️ 编号重复：{id_str} 与 {existing_id} 相似")
                return True
    return False


# ==================== 时间设置函数 ====================
def setup_time_parameters():
    """设置时间参数模式"""
    global TIME_MODE, HUMAN_MOVE_DURATION, HUMAN_STAY_DURATION
    global HUMAN_CLICK_INTERVAL, HUMAN_DOWNLOAD_INTERVAL, HUMAN_PAUSE_INTERVAL

    print("\n" + "=" * 50)
    print("⏱️  时间设置")
    print("=" * 50)

    while True:
        choice = input("请选择时间模式（1=自动模式/2=手动设置）：").strip()
        if choice == "1":
            TIME_MODE = "auto"
            print("✅ 已选择自动模式，使用随机时间参数")
            break
        elif choice == "2":
            TIME_MODE = "manual"
            print("\n请设置各项时间参数（单位：秒）")

            # 依次设置各项时间参数
            params = [
                ("鼠标移动最小时间", "鼠标移动最大时间", HUMAN_MOVE_DURATION),
                ("点击前最小停留时间", "点击前最大停留时间", HUMAN_STAY_DURATION),
                ("下载间隔最小时间", "下载间隔最大时间", HUMAN_DOWNLOAD_INTERVAL),
                ("随机休息最小时间", "随机休息最大时间", HUMAN_PAUSE_INTERVAL)
            ]

            for min_prompt, max_prompt, var in params:
                while True:
                    try:
                        min_val = float(input(f"{min_prompt}："))
                        max_val = float(input(f"{max_prompt}："))
                        if min_val >= 0 and max_val > min_val:
                            if var == HUMAN_MOVE_DURATION:
                                HUMAN_MOVE_DURATION = (min_val, max_val)
                            elif var == HUMAN_STAY_DURATION:
                                HUMAN_STAY_DURATION = (min_val, max_val)
                            elif var == HUMAN_DOWNLOAD_INTERVAL:
                                HUMAN_DOWNLOAD_INTERVAL = (min_val, max_val)
                            elif var == HUMAN_PAUSE_INTERVAL:
                                HUMAN_PAUSE_INTERVAL = (min_val, max_val)
                            break
                        print("❌ 请确保最大时间大于最小时间")
                    except ValueError:
                        print("❌ 请输入有效数字")

            print("✅ 手动时间参数设置完成")
            break
        else:
            print("❌ 请输入1或2选择模式")


# ==================== 基础工具函数 ====================
def init_download_path():
    """初始化下载路径并记录初始文件"""
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
    global initial_files, downloaded_files_info
    for f in os.listdir(DOWNLOAD_PATH):
        f_path = os.path.join(DOWNLOAD_PATH, f)
        if os.path.isfile(f_path) and os.path.getsize(f_path) >= FILE_MIN_SIZE:
            file_size = os.path.getsize(f_path)
            initial_files.add((f, file_size))
            downloaded_files_info.add(get_file_key(f, file_size))
    print(f"✅ 下载路径：{DOWNLOAD_PATH}（初始文件数：{len(initial_files)}）")


def get_current_files():
    """获取当前下载目录的文件列表"""
    files = set()
    for f in os.listdir(DOWNLOAD_PATH):
        f_path = os.path.join(DOWNLOAD_PATH, f)
        if os.path.isfile(f_path) and os.path.getsize(f_path) >= FILE_MIN_SIZE:
            files.add((f, os.path.getsize(f_path)))
    return files


def detect_new_file():
    """检测并返回新下载的文件"""
    current_files = get_current_files()
    new_files = current_files - initial_files
    if new_files:
        # 按修改时间排序，取最新的
        new_file = sorted(new_files, key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_PATH, x[0])))[-1]
        new_file_name, new_file_size = new_file

        # 检查文件是否重复
        if is_file_duplicate(new_file_name, new_file_size):
            print(f"❌ 新文件是重复文件，跳过记录：{new_file_name}")
            return False

        print(f"✅ 新增文件：{new_file_name}（{new_file_size / 1024:.1f}KB）")
        initial_files.add(new_file)
        downloaded_files_info.add(get_file_key(new_file_name, new_file_size))
        return True
    return False


def load_download_icon():
    """加载下载按钮截图"""
    path = "download_icon.png"
    if not os.path.exists(path):
        print(f"❌ 未找到 {path}！请截图知网下载按钮并保存到脚本文件夹")
        exit(1)
    img = cv2.imread(path)
    if img is None:
        print("❌ 下载按钮截图无效")
        exit(1)
    h, w = img.shape[:2]
    print(f"✅ 加载下载按钮截图：{w}x{h}像素")
    return img


# ==================== 人工模拟函数 ====================
def human_like_move_to(x, y):
    """模拟人类鼠标移动"""
    current_x, current_y = pyautogui.position()
    segments = random.randint(2, 3)
    step_x = (x - current_x) / segments
    step_y = (y - current_y) / segments
    duration = random.uniform(*HUMAN_MOVE_DURATION) / segments

    for i in range(segments):
        if not is_running:
            return
        next_x = current_x + step_x + random.randint(-8, 8)
        next_y = current_y + step_y + random.randint(-8, 8)
        pyautogui.moveTo(next_x, next_y, duration=duration)
        current_x, current_y = next_x, next_y
        time.sleep(random.uniform(0.05, 0.1))

    pyautogui.moveTo(x, y, duration=random.uniform(0.1, 0.2))


def human_like_pause():
    """随机休息"""
    pause_time = random.uniform(*HUMAN_PAUSE_INTERVAL)
    print(f"\n😴 随机休息 {pause_time:.1f} 秒...")
    time.sleep(pause_time)


# ==================== 页面导航与滚动函数 ====================
def navigate_to_page(direction):
    """页面导航（前进/后退）"""
    global current_page
    original_page = current_page

    if direction == "next":
        print(f"\n📄 正在前进到第{current_page + 1}页...")
        success = False

        # 多种翻页方式尝试
        methods = [
            lambda: pyautogui.press('right'),
            lambda: pyautogui.press('pagedown'),
            lambda: pyautogui.click(x=pyautogui.size()[0] - 50, y=pyautogui.size()[1] - 50)  # 点击右下角
        ]

        for method in methods:
            try:
                method()
                success = True
                break
            except:
                continue

        if not success:
            print("❌ 自动翻页失败，请手动翻页后按回车继续...")
            input()

        current_page += 1
        page_nav_history.append(current_page)

    elif direction == "prev" and len(page_nav_history) > 1:
        print(f"\n📄 正在回退到第{page_nav_history[-2]}页...")
        pyautogui.press('left')
        current_page = page_nav_history[-2]
        page_nav_history.pop()
    else:
        print("❌ 无法回退（无历史页面）")
        return False

    time.sleep(PAGE_LOAD_DELAY)
    print(f"✅ 已切换到第{current_page}页")
    # 重置当前页滚动状态
    global page_scroll_count, no_new_button_count, last_download_y
    page_scroll_count = 0
    no_new_button_count = 0
    last_download_y = 0
    return True


def scroll_page():
    """向下滚动页面（基于最后一个下载按钮位置定位）"""
    global page_scroll_count
    page_scroll_count += 1

    if page_scroll_count > MAX_PAGE_SCROLL:
        print(f"⚠️  当前页已滚动{MAX_PAGE_SCROLL}次，即将判定页面结束")
        return False

    # 滚动逻辑：如果有最后下载位置，以该位置为基准
    if last_download_y > 0:
        # 滚动到最后一个下载按钮下方SCROLL_STEP距离
        current_y = pyautogui.position()[1]
        target_y = last_download_y + SCROLL_STEP
        pyautogui.scroll(-SCROLL_STEP)
        print(f"📜 滚动页面（基于最后下载位置）：{last_download_y} → {target_y}")
    else:
        # 首次滚动，默认距离
        pyautogui.scroll(-SCROLL_STEP)
        print(f"📜 滚动页面（默认距离）：{SCROLL_STEP}像素")

    time.sleep(random.uniform(1.5, 2.5))  # 等待页面加载
    return True


def is_current_page_complete():
    """判断当前页是否下载完成"""
    global no_new_button_count
    no_new_button_count += 1
    print(f"⚠️  未识别到新的下载按钮（连续{no_new_button_count}次）")
    return no_new_button_count >= SCROLL_CONFIRM_TIMES


# ==================== 颜色判断与截图框选函数 ====================
def get_button_color(x, y):
    """判断按钮颜色（蓝色/黄色）"""
    button_size = (26, 26)
    half_w = button_size[0] // 2
    half_h = button_size[1] // 2
    bbox = (x - half_w, y - half_h, x + half_w, y + half_h)

    try:
        screen = ImageGrab.grab(bbox=bbox)
        screen_np = np.array(screen)
        avg_r = np.mean(screen_np[:, :, 0])
        avg_g = np.mean(screen_np[:, :, 1])
        avg_b = np.mean(screen_np[:, :, 2])

        print(f"🎨 按钮颜色：R={avg_r:.0f}, G={avg_g:.0f}, B={avg_b:.0f}")

        if avg_b > BLUE_THRESHOLD[0] and avg_b < BLUE_THRESHOLD[1] and avg_r < 100 and avg_g < 100:
            return "blue"
        elif (avg_r + avg_g) > YELLOW_THRESHOLD[0] and (avg_r + avg_g) < YELLOW_THRESHOLD[1] and avg_b < 100:
            return "yellow"
        else:
            return "unknown"
    except Exception as e:
        print(f"❌ 颜色判断失败：{str(e)}")
        return "unknown"


def take_page_screenshot():
    """截图当前页面"""
    print("\n" + "=" * 50)
    print(f"📸 正在截图第{current_page}页（滚动次数：{page_scroll_count}）...")
    print("⚠️  请确保知网页面在前台、最大化、无遮挡！")
    print("=" * 50)
    time.sleep(random.uniform(0.8, 1.5))

    try:
        screen = ImageGrab.grab()
        screen.save(TEMP_SCREENSHOT)

        if not os.path.exists(TEMP_SCREENSHOT) or os.path.getsize(TEMP_SCREENSHOT) < 10240:
            print("❌ 截图失败")
            return False

        screen_w, screen_h = pyautogui.size()
        img = cv2.imread(TEMP_SCREENSHOT)
        img_h, img_w = img.shape[:2]
        global screen_ratio
        screen_ratio = (screen_w / img_w, screen_h / img_h)

        print(f"✅ 截图成功：{TEMP_SCREENSHOT}（{os.path.getsize(TEMP_SCREENSHOT) / 1024:.1f}KB）")
        return True
    except Exception as e:
        print(f"❌ 截图出错：{str(e)}")
        return False


def select_region_on_screenshot(screenshot_path, is_first_page=True):
    """框选下载按钮区域"""
    global selected_region, box_selected
    box_selected = False
    ref_point = []
    cropping = False

    img = cv2.imread(screenshot_path)
    if img is None:
        print("❌ 无法打开截图")
        return False
    img_copy = img.copy()

    # 框选提示
    prompt_text = [
        "📌 框选操作说明：",
        "1. 按住左键→拖动框选下载按钮列（尽量包含所有可能出现的按钮）",
        "2. 松开鼠标→按ESC关闭窗口",
        "⚠️  脚本会自动滚动加载并下载区域内所有按钮"
    ]
    y_offset = 50
    for text in prompt_text:
        cv2.putText(img_copy, text, (30, y_offset), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8 if "说明" in text else 0.7, (255, 0, 0) if "说明" in text else (0, 0, 255),
                    3 if "说明" in text else 2)
        y_offset += 50

    def click_event(event, x, y, flags, param):
        nonlocal ref_point, cropping, img_copy
        global box_selected

        if event == cv2.EVENT_LBUTTONDOWN:
            ref_point = [(x, y)]
            cropping = True
            print(f"🔘 开始框选（坐标：{x},{y}）")
        elif event == cv2.EVENT_LBUTTONUP:
            ref_point.append((x, y))
            cropping = False
            box_selected = True
            cv2.rectangle(img_copy, ref_point[0], ref_point[1], (0, 255, 0), 4)
            cv2.putText(img_copy, f"✅ 框选完成！按ESC关闭", (30, y_offset + 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imshow(WINDOW_TITLE, img_copy)
            print(f"✅ 框选确认（截图坐标）：{ref_point[0]}→{ref_point[1]}")
        elif event == cv2.EVENT_MOUSEMOVE and cropping:
            temp_img = img_copy.copy()
            cv2.rectangle(temp_img, ref_point[0], (x, y), (0, 255, 0), 3)
            cv2.imshow(WINDOW_TITLE, temp_img)

    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)
    cv2.imshow(WINDOW_TITLE, img_copy)
    cv2.setMouseCallback(WINDOW_TITLE, click_event)

    # 等待操作（超时90秒）
    timeout = 90
    start_time = time.time()
    while True:
        key = cv2.waitKey(1) & 0xFF
        elapsed = time.time() - start_time

        if elapsed > 60 and not box_selected:
            cv2.putText(img_copy, f"⚠️ 已等待{int(elapsed)}秒！按Alt+Tab找框选窗口",
                        (30, y_offset + 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.imshow(WINDOW_TITLE, img_copy)

        if elapsed > timeout:
            print("❌ 框选超时")
            cv2.destroyAllWindows()
            return False

        if key == 27:
            break

    cv2.destroyAllWindows()

    if len(ref_point) == 2 and box_selected:
        x1 = min(ref_point[0][0], ref_point[1][0])
        y1 = min(ref_point[0][1], ref_point[1][1])
        x2 = max(ref_point[0][0], ref_point[1][0])
        y2 = max(ref_point[0][1], ref_point[1][1])
        selected_region = (x1, y1, x2, y2)
        print(f"✅ 最终框选区域：({x1},{y1})→({x2},{y2})")

        # 翻页后确认区域
        if not is_first_page:
            confirm = input("👉 当前框选区域是否正确？（y=正确/n=重新框选）：").strip().lower()
            if confirm != "y":
                print("🔄 重新框选当前页...")
                return select_region_on_screenshot(screenshot_path, is_first_page=False)

        return True
    else:
        print("❌ 未完成有效框选")
        return False


# ==================== 坐标映射与按钮识别函数 ====================
def map_screenshot_to_screen(region):
    """截图坐标映射到屏幕坐标"""
    x1, y1, x2, y2 = region
    screen_x1 = int(x1 * screen_ratio[0])
    screen_y1 = int(y1 * screen_ratio[1])
    screen_x2 = int(x2 * screen_ratio[0])
    screen_y2 = int(y2 * screen_ratio[1])
    return (screen_x1, screen_y1, screen_x2, screen_y2)


def find_download_buttons_in_region(download_img):
    """识别当前区域内的下载按钮（去重+过滤已下载）"""
    if not selected_region:
        print("❌ 未框选区域")
        return []

    screen_region = map_screenshot_to_screen(selected_region)
    x1, y1, x2, y2 = screen_region

    try:
        # 截取框选区域
        screen = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        screen_np = np.array(screen)
        screen_bgr = cv2.cvtColor(screen_np, cv2.COLOR_RGB2BGR)
    except Exception as e:
        print(f"❌ 截取屏幕区域失败：{str(e)}")
        return []

    # 模板匹配
    result = cv2.matchTemplate(screen_bgr, download_img, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= CONFIDENCE)

    buttons = []
    h, w = download_img.shape[:2]
    for pt in zip(*locations[::-1]):
        center_x = x1 + pt[0] + w // 2 + random.randint(-3, 3)
        center_y = y1 + pt[1] + h // 2 + random.randint(-3, 3)

        # 按钮去重（避免同一按钮被多次识别）
        duplicate_btn = False
        for (bx, by) in buttons:
            if abs(center_x - bx) < 35 and abs(center_y - by) < 35:
                duplicate_btn = True
                break
        if duplicate_btn:
            continue

        # 过滤已下载的按钮（基于位置和编号）
        buttons.append((center_x, center_y))

    # 按Y坐标排序（从上到下下载）
    buttons.sort(key=lambda p: p[1])
    print(f"🔍 找到 {len(buttons)} 个下载按钮（当前区域）")

    # 重置连续无新按钮计数
    global no_new_button_count
    if len(buttons) > 0:
        no_new_button_count = 0

    return buttons


# ==================== 核心下载函数 ====================
def click_download_button(btn_idx, pos, total_in_batch):
    """下载单个文件（含重复检测、颜色适配）"""
    x, y = pos
    final_x = x + SERIAL_DOWNLOAD_DX + random.randint(-8, 8)
    final_y = y + SERIAL_DOWNLOAD_DY + random.randint(-8, 8)

    # 边界检查
    screen_w, screen_h = pyautogui.size()
    final_x = max(0, min(screen_w, final_x))
    final_y = max(0, min(screen_h, final_y))

    print(f"\n📥 下载文件 {btn_idx + 1}/{total_in_batch}（坐标：{int(final_x)},{int(final_y)}）")

    # 1. 重复检测
    doc_id = get_document_id((final_x, final_y))
    if is_duplicate(doc_id):
        print(f"❌ 检测到重复文献，跳过下载")
        return False

    # 2. 模拟人类操作
    human_like_move_to(final_x, final_y)
    time.sleep(random.uniform(*HUMAN_STAY_DURATION))

    # 3. 颜色判断与人工验证
    button_color = get_button_color(final_x, final_y)
    if button_color == "yellow":
        print("⚠️  检测到黄色下载按钮，需要人工验证！")
        print("请手动完成验证（如滑动验证），确保文件开始下载后按回车继续...")
        input("👉 验证完成后按回车：")
        print("✅ 继续自动下载流程")
    elif button_color == "unknown":
        print("⚠️  按钮颜色未识别，按蓝色按钮逻辑尝试下载...")

    # 4. 随机点击方式
    click_count = random.choice([1, 2])
    if click_count == 1:
        pyautogui.click()
        print(f"👆 执行单击操作")
    else:
        pyautogui.click(clicks=2, interval=random.uniform(*HUMAN_CLICK_INTERVAL))
        print(f"👆 执行双击操作（间隔：{random.uniform(*HUMAN_CLICK_INTERVAL):.2f}秒）")

    # 5. 等待下载完成
    start_time = time.time()
    while time.time() - start_time < DOWNLOAD_TIMEOUT:
        if detect_new_file():
            # 记录下载信息
            if doc_id:
                downloaded_ids.add(doc_id)
                print(f"📝 已记录文献编号：{doc_id}")

            # 更新最后下载位置
            global last_download_y
            last_download_y = final_y

            # 下载间隔
            next_interval = random.uniform(*HUMAN_DOWNLOAD_INTERVAL)
            print(f"⌛ 下一个下载间隔 {next_interval:.1f} 秒...")
            time.sleep(next_interval)
            return True
        time.sleep(random.uniform(0.8, 1.2))

    print(f"❌ 下载超时（{DOWNLOAD_TIMEOUT}秒）")
    return False


def process_current_view(download_img):
    """处理当前可视区域的下载"""
    # 关键修复：将global声明移到函数开头
    global downloaded_count
    buttons = find_download_buttons_in_region(download_img)
    if not buttons:
        return 0  # 无按钮可下载

    downloaded_in_batch = 0
    total_buttons = len(buttons)

    for idx, btn_pos in enumerate(buttons):
        # 暂停检查
        while is_paused:
            time.sleep(0.5)
            if not is_running:
                return downloaded_in_batch

        if not is_running:
            break

        # 每下载HUMAN_PAUSE_TRIGGER个休息一次
        if (downloaded_count + downloaded_in_batch + 1) % HUMAN_PAUSE_TRIGGER == 0:
            human_like_pause()

        # 下载单个文件
        if click_download_button(idx, btn_pos, total_buttons):
            downloaded_in_batch += 1
            downloaded_count += 1

    return downloaded_in_batch


def process_single_page(download_img):
    """处理整页下载（滚动加载+完整下载）"""
    print(f"\n" + "=" * 60)
    print(f"🚀 开始第{current_page}页下载（滚动次数限制：{MAX_PAGE_SCROLL}次）")
    print("=" * 60)

    total_downloaded_in_page = 0

    while is_running:
        # 检查当前页是否已完成
        if is_current_page_complete():
            print(f"\n🎉 第{current_page}页下载完成（共下载{total_downloaded_in_page}个文件）")
            return True

        # 处理当前可视区域
        batch_downloaded = process_current_view(download_img)
        total_downloaded_in_page += batch_downloaded

        # 如果当前区域下载完成，滚动页面
        if batch_downloaded == 0 or len(find_download_buttons_in_region(download_img)) == 0:
            if not scroll_page():
                break  # 滚动达到上限，退出当前页

        # 暂停检查
        while is_paused:
            time.sleep(0.5)

    return total_downloaded_in_page > 0


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
        elif key in [keyboard.Key.right, keyboard.Key.left, keyboard.Key.page_up, keyboard.Key.page_down]:
            print("\n⚠️  下载过程中禁止手动翻页/滚动！请在当前页下载完成后操作")
    except Exception as e:
        print(f"\n❌ 键盘错误：{str(e)}")


# ==================== 主程序 ====================
def main():
    global is_running, is_paused, downloaded_count

    print("=" * 75)
    print("📌 知网批量下载终极版（动态滚动+完整页下载+双重去重）")
    print("✅ 核心特性：")
    print("  1. 无需设置目标数量，自动识别并下载当前页所有文件")
    print("  2. 页面内滚动加载，下载完可视区域自动滚动继续下载")
    print("  3. 双重去重：文献编号OCR识别 + 文件名称+大小校验")
    print("  4. 支持自动/手动时间设置，模拟人类操作防检测")
    print("  5. 翻页后自动重新框选，确保每一页完整下载")
    print("✅ 快捷键：ESC=停止 | 空格=暂停/继续")
    print("=" * 75)

    # 初始化
    init_ocr()
    setup_time_parameters()
    init_download_path()
    download_img = load_download_icon()

    # 首次截图+框选
    print("\n👉 准备就绪！请：")
    print("  1. 切换到知网页面（最大化、无遮挡）")
    print("  2. 按回车键开始截图和框选")
    input()

    while is_running:
        if take_page_screenshot():
            if select_region_on_screenshot(TEMP_SCREENSHOT, is_first_page=True):
                break
        print("❌ 截图/框选失败，请重新操作！")
        time.sleep(2.0)

    # 启动键盘监听
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()

    try:
        while is_running:
            if is_paused:
                time.sleep(0.5)
                continue

            # 处理当前页下载
            page_done = process_single_page(download_img)

            if not is_running:
                break

            # 询问是否翻页
            while True:
                choice = input(
                    f"\n👉 第{current_page}页下载完成！是否继续翻页？（y=翻页/n=停止/prev=回退）：").strip().lower()
                if choice in ["y", "n", "prev"]:
                    break
                print("❌ 输入无效，请输入 y/n/prev")

            if choice == "n":
                print("⚠️  用户选择停止下载")
                is_running = False
                break
            elif choice == "prev":
                # 回退上一页
                if navigate_to_page("prev"):
                    # 重新截图框选
                    retry = 0
                    while is_running and retry < 3:
                        if take_page_screenshot():
                            if select_region_on_screenshot(TEMP_SCREENSHOT, is_first_page=False):
                                break
                        retry += 1
                        print(f"🔄 第{retry}次重试截图/框选...")
                        time.sleep(2.0)
                    else:
                        print("❌ 回退后初始化失败，停止脚本")
                        is_running = False
                        break
            elif choice == "y":
                # 前进到下一页
                if navigate_to_page("next"):
                    # 重新截图框选
                    retry = 0
                    while is_running and retry < 3:
                        if take_page_screenshot():
                            if select_region_on_screenshot(TEMP_SCREENSHOT, is_first_page=False):
                                break
                        retry += 1
                        print(f"🔄 第{retry}次重试截图/框选...")
                        time.sleep(2.0)
                    else:
                        print("❌ 翻页后初始化失败，停止脚本")
                        is_running = False
                        break

    except Exception as e:
        print(f"\n❌ 脚本错误：{str(e)}")
    finally:
        # 清理资源
        listener.stop()
        listener.join()
        if os.path.exists(TEMP_SCREENSHOT):
            os.remove(TEMP_SCREENSHOT)

        # 输出统计信息
        print(f"\n" + "=" * 50)
        print(f"📊 下载统计：")
        print(f"   总处理页数：{len(page_nav_history)}页")
        print(f"   总下载文件数：{downloaded_count}个")
        print(f"   已下载文献编号：{', '.join(downloaded_ids) if downloaded_ids else '无'}")
        print(f"   下载路径：{DOWNLOAD_PATH}")
        print("=" * 50)
        print("👋 脚本已退出")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ 用户手动停止")
        print(f"📊 总下载：{downloaded_count}个")
        if os.path.exists(TEMP_SCREENSHOT):
            os.remove(TEMP_SCREENSHOT)