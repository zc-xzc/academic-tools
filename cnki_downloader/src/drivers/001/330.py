import pyautogui
import time
import random
import os
import cv2
import numpy as np
import pytesseract
from pynput import keyboard
from PIL import ImageGrab, Image, ImageEnhance
from pathlib import Path

# ==================== 关键配置（按用户指定坐标精准调整）====================
# 基础路径配置
DOWNLOAD_PATH = r"D:\Downloads"
TEMP_SCREENSHOT = "temp_page_screenshot.png"
DOWNLOAD_ICON_PATH = "download_icon.png"
NEXT_PAGE_ICON_PATH = "next_page_icon.png"

# 截图+可视化配置
SCREENSHOT_REGION = (0, 0, 2560, 1680)  # 按实际屏幕分辨率调整（默认2560x1680）
DEBUG_DIR = "ocr_debug"  # 调试目录（保存截图和处理图）
SAVE_ALL_STEPS = True  # 保存所有图像处理步骤（可视化）

# OCR识别配置（用户指定：序号x=730~780，y=760~1480）
OCR_REGION_X_RANGE = (730, 780)  # 用户明确序号x范围
OCR_REGION_Y_TOP = 760  # 用户明确y起始
OCR_REGION_Y_BOTTOM = pyautogui.size()[1] - 1480  # 计算y结束（确保y≤1480）
OCR_THRESHOLD = 140
OCR_CONTRAST = 2.5

# 技术参数配置
CONFIDENCE = 0.35
SERIAL_DOWNLOAD_DX = 0
SERIAL_DOWNLOAD_DY = 0
FILE_MIN_SIZE = 1024
DOWNLOAD_TIMEOUT = 15
PAGE_LOAD_DELAY = random.uniform(1.5, 2.5)
MAX_RETRY = 3

# 框选区域配置（用户指定：下载按钮x=2000~2030，y=760~1480）
BOX_X1_DEFAULT = 2000  # 下载按钮x起始（用户指定）
BOX_WIDTH_RANGE = (20, 30)  # 下载按钮宽度范围（2000~2030，宽度30px）
BOX_Y_EXPAND = 5  # 无需大幅扩展（用户已指定精准y范围）
# 降级模式默认框选区域（直接使用用户指定坐标）
FALLBACK_BOX_REGION = (2000, 760, 2030, 1480)  # (x1,y1,x2,y2) 完全匹配用户指定

# 提速无规律间歇配置
HUMAN_MOVE_DURATION = (0.1, 0.3)
HUMAN_STAY_DURATION = (0.2, 0.5)
HUMAN_CLICK_INTERVAL = (0.05, 0.15)
HUMAN_DOWNLOAD_INTERVAL = (0.8, 1.5)
HUMAN_PAUSE_INTERVAL = (2, 4)
HUMAN_PAUSE_TRIGGER = 10

# 颜色判断配置
BLUE_THRESHOLD = (100, 150)
YELLOW_THRESHOLD = (180, 255)

# 全局状态
is_running = True
is_paused = False
current_page = 1
downloaded_count = 0
initial_files = set()
next_page_icon = None
selected_region = None
target_count = 10


# ==================== 工具函数（保持不变，适配精准坐标）====================
def init_all():
    """全局初始化（创建调试目录）"""
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
    # 创建调试目录（含子目录保存步骤图）
    Path(DEBUG_DIR).mkdir(exist_ok=True)
    Path(f"{DEBUG_DIR}/steps").mkdir(exist_ok=True)
    Path(f"{DEBUG_DIR}/screenshots").mkdir(exist_ok=True)

    global initial_files
    initial_files = get_file_list(DOWNLOAD_PATH)
    print(f"✅ 下载路径：{DOWNLOAD_PATH}（初始文件数：{len(initial_files)}）")

    global next_page_icon
    download_img = load_icon(DOWNLOAD_ICON_PATH, "下载按钮")
    next_page_icon = load_icon(NEXT_PAGE_ICON_PATH, "下一页按钮")
    return download_img


def load_icon(path, name):
    """加载按钮截图"""
    if not os.path.exists(path):
        print(f"❌ 未找到 {name} 截图：{path}！请截图后保存到根目录")
        exit(1)
    img = cv2.imread(path)
    if img is None:
        print(f"❌ {name} 截图无效")
        exit(1)
    h, w = img.shape[:2]
    print(f"✅ 加载{name}截图：{w}x{h}像素")
    return img


def get_file_list(folder):
    """获取有效文件列表（去重+过滤小文件）"""
    files = set()
    for f in os.listdir(folder):
        f_path = os.path.join(folder, f)
        if os.path.isfile(f_path) and os.path.getsize(f_path) >= FILE_MIN_SIZE:
            files.add((f, os.path.getsize(f_path)))
    return files


def capture_screen(page_num):
    """自动截图（保存原始截图，可视化第一步）"""
    print(f"\n📸 第{page_num}页：开始自动截图...")
    # 截图整个页面（按实际屏幕分辨率调整）
    screen_img = ImageGrab.grab(bbox=SCREENSHOT_REGION)
    # 保存原始截图
    screenshot_path = f"{DEBUG_DIR}/screenshots/page_{page_num}_original.png"
    screen_img.save(screenshot_path)
    print(f"✅ 原始截图保存到：{screenshot_path}")
    return screen_img, screenshot_path


def process_image_visualized(original_img, page_num, ocr_bbox):
    """可视化图像处理（每步保存结果，返回最终处理图）"""
    step = 1
    process_paths = []

    # 1. 裁剪OCR识别区域（精准匹配用户指定范围）
    ocr_img = original_img.crop(ocr_bbox)
    crop_path = f"{DEBUG_DIR}/steps/page_{page_num}_step{step}_crop.png"
    ocr_img.save(crop_path)
    process_paths.append(("裁剪OCR区域（730~780,760~1480）", crop_path))
    step += 1

    # 2. 灰度化
    gray_img = ocr_img.convert("L")
    gray_path = f"{DEBUG_DIR}/steps/page_{page_num}_step{step}_gray.png"
    gray_img.save(gray_path)
    process_paths.append(("灰度化", gray_path))
    step += 1

    # 3. 自适应阈值处理（反相，提升序号识别）
    gray_np = np.array(gray_img)
    threshold_img = cv2.adaptiveThreshold(
        gray_np, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=13, C=3  # 微调参数，适配精准区域
    )
    threshold_pil = Image.fromarray(threshold_img).convert("L")
    threshold_path = f"{DEBUG_DIR}/steps/page_{page_num}_step{step}_threshold.png"
    threshold_pil.save(threshold_path)
    process_paths.append(("自适应阈值（反相）", threshold_path))
    step += 1

    # 4. 降噪
    denoise_img = cv2.morphologyEx(threshold_img, cv2.MORPH_OPEN, np.ones((1, 1), np.uint8))
    denoise_pil = Image.fromarray(denoise_img).convert("L")
    denoise_path = f"{DEBUG_DIR}/steps/page_{page_num}_step{step}_denoise.png"
    denoise_pil.save(denoise_path)
    process_paths.append(("降噪", denoise_path))
    step += 1

    # 5. 对比度增强
    enhancer = ImageEnhance.Contrast(denoise_pil)
    final_img = enhancer.enhance(OCR_CONTRAST)
    final_path = f"{DEBUG_DIR}/steps/page_{page_num}_step{step}_final.png"
    final_img.save(final_path)
    process_paths.append(("对比度增强（最终图）", final_path))

    # 打印处理步骤日志
    print(f"\n🎨 第{page_num}页图像处理步骤：")
    for name, path in process_paths:
        print(f"  - {name}：{path}")

    return final_img


# ==================== 核心OCR识别（精准坐标适配）====================
def ocr_literature_numbers(page_num):
    """
    按用户指定坐标（730~780,760~1480）识别序号
    返回：(first_y, last_y) 成功 | None 失败
    """
    print(f"\n🔍 第{page_num}页：OCR识别序号（x:730~780, y:760~1480）...")

    # 1. 先自动截图
    original_screen_img, _ = capture_screen(page_num)

    # 2. 定义OCR识别区域（完全按用户指定）
    screen_w, screen_h = pyautogui.size()
    # 确保y结束坐标严格为1480（用户指定）
    ocr_bbox = (
        OCR_REGION_X_RANGE[0],  # 730
        OCR_REGION_Y_TOP,  # 760
        OCR_REGION_X_RANGE[1],  # 780
        1480  # 用户指定y结束
    )
    print(f"📌 OCR识别区域：x[{730}-{780}] y[{760}-{1480}]（用户指定）")

    try:
        # 3. 可视化图像处理
        ocr_img_final = process_image_visualized(original_screen_img, page_num, ocr_bbox)

        # 4. OCR识别（优化参数适配窄区域序号）
        ocr_text = pytesseract.image_to_string(
            ocr_img_final,
            config="--psm 10 --oem 3 -c tessedit_char_whitelist=0123456789 -c dpi=300 -c min_char_height=10"
            # --psm 10：单字符识别（适配窄区域的单个/多位数序号）
            # min_char_height=10：过滤过小噪点
        )
        ocr_text = ocr_text.strip()
        print(f"📄 OCR原始文本：{ocr_text if ocr_text else '空'}")

        # 5. 提取有效数字（适配窄区域多位数识别）
        number_info = []
        char_boxes = pytesseract.image_to_boxes(
            ocr_img_final,
            config="--psm 10 --oem 3 -c tessedit_char_whitelist=0123456789 -c dpi=300 -c min_char_height=10"
        )

        current_number = ""
        current_y = None
        current_char_count = 0
        img_h = ocr_img_final.height

        for line in char_boxes.splitlines():
            if len(line.split()) != 6:
                continue
            char, x1, y1, x2, y2, _ = line.split()
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

            # 转换y坐标到屏幕坐标系（基于用户指定的y起始760）
            char_y = OCR_REGION_Y_TOP + (img_h - y2)
            char_width = x2 - x1

            # 过滤过小噪点（窄区域更易出现）
            if char_width < 4 or (y2 - y1) < 8:
                continue

            # 组合多位数（窄区域字符间距小，调整判断条件）
            if current_y is None or (abs(char_y - current_y) < 8 and (x1 - int(x2_prev) if current_number else 0) < 15):
                current_number += char
                current_y = char_y
                current_char_count += 1
                x2_prev = x2
            else:
                if current_number.isdigit() and len(current_number) >= 1:
                    full_num = int(current_number)
                    last_digit = full_num % 10
                    number_info.append((full_num, last_digit, current_y, current_char_count))
                current_number = char
                current_y = char_y
                current_char_count = 1
                x2_prev = x2

        # 保存最后一个序号
        if current_number.isdigit() and len(current_number) >= 1:
            full_num = int(current_number)
            last_digit = full_num % 10
            number_info.append((full_num, last_digit, current_y, current_char_count))

        # 去重（适配窄区域重复识别）
        unique_number_info = []
        seen_y = set()
        seen_num = set()
        for info in number_info:
            full_num, last_digit, y, char_count = info
            y_key = round(y / 8) * 8  # 更精细的y轴去重（窄区域行间距小）
            if y_key not in seen_y and full_num not in seen_num and 0 <= full_num <= 999:
                seen_y.add(y_key)
                seen_num.add(full_num)
                unique_number_info.append(info)

        if not unique_number_info:
            print("⚠️ OCR未识别到任何有效序号")
            return None

        # 验证并返回首末y坐标（严格在760~1480内）
        full_nums = [info[0] for info in unique_number_info]
        last_digits = [info[1] for info in unique_number_info]
        y_coords = [info[2] for info in unique_number_info]
        # 过滤超出用户指定y范围的异常值
        y_coords = [y for y in y_coords if 760 <= y <= 1480]
        if not y_coords:
            print("⚠️ 识别到的序号y坐标超出用户指定范围")
            return None

        print(f"📝 识别到有效序号：{full_nums}（共{len(full_nums)}个）")
        print(f"📝 序号末尾数：{sorted(list(set(last_digits)))}")

        first_y = min(y_coords)
        last_y = max(y_coords)
        print(f"✅ OCR识别成功：首行y={round(first_y)} | 末行y={round(last_y)}")
        return (first_y, last_y)

    except Exception as e:
        print(f"❌ OCR识别异常：{str(e)}")
        return None


# ==================== 自动框选（精准坐标适配）====================
def auto_select_region_or_fallback(ocr_success, ocr_result=None):
    """
    OCR成功：按首末y坐标+用户指定x范围框选
    OCR失败：使用用户指定的下载按钮区域（2000~2030,760~1480）
    返回：True（框选成功）| False（失败）
    """
    global current_page, selected_region
    selected_region = None
    screen_w, screen_h = pyautogui.size()

    if ocr_success and ocr_result:
        # OCR成功：按识别结果+用户指定x范围框选
        first_y, last_y = ocr_result
        # 下载按钮x范围固定为2000~2030（用户指定）
        box_x1 = 2000
        box_x2 = 2030
        box_width = box_x2 - box_x1
        # y范围：识别的首末y + 小幅扩展（用户指定范围足够精准）
        box_y1 = max(760, first_y - BOX_Y_EXPAND)  # 不小于760
        box_y2 = min(1480, last_y + BOX_Y_EXPAND)  # 不大于1480

        box_height = box_y2 - box_y1
        if box_height < 200:
            print(f"⚠️ OCR框选区域高度不足（{box_height}px），使用用户指定完整y范围")
            box_y1 = 760
            box_y2 = 1480
            box_height = 1480 - 760

        selected_region = (box_x1, box_y1, box_x2, box_y2)
        print(f"✅ 基于OCR的自动框选区域（用户指定x范围）：")
        print(f"   坐标：({box_x1},{box_y1})→({box_x2},{box_y2}) | 宽{box_width}px | 高{box_height}px")
        return True
    else:
        # OCR失败：直接使用用户指定的下载按钮区域
        selected_region = FALLBACK_BOX_REGION  # (2000,760,2030,1480)
        box_x1, box_y1, box_x2, box_y2 = selected_region
        box_width = box_x2 - box_x1
        box_height = box_y2 - box_y1
        print(f"🔄 OCR识别失败，启用降级模式：使用用户指定下载区域")
        print(f"   坐标：({box_x1},{box_y1})→({box_x2},{box_y2}) | 宽{box_width}px | 高{box_height}px")
        return True


# ==================== 下载按钮查找+数量验证（精准坐标适配）====================
def find_and_verify_buttons(download_img):
    """
    在用户指定的下载区域（2000~2030,760~1480）查找按钮
    返回：buttons列表（成功）| []（失败）
    """
    global selected_region, target_count
    if not selected_region:
        print("❌ 未框选区域，无法查找按钮")
        return []

    x1, y1, x2, y2 = selected_region
    print(f"\n🔍 在区域（{x1}~{x2},{y1}~{y2}）查找下载按钮...")
    try:
        # 截图框选区域（精准匹配用户指定范围）
        region_img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        region_np = np.array(region_img)
        region_bgr = cv2.cvtColor(region_np, cv2.COLOR_RGB2BGR)

        # 保存框选区域截图（可视化验证）
        region_save_path = f"{DEBUG_DIR}/steps/page_{current_page}_region_screenshot.png"
        Image.fromarray(cv2.cvtColor(region_bgr, cv2.COLOR_BGR2RGB)).save(region_save_path)
        print(f"📸 框选区域截图保存到：{region_save_path}")

        # 模板匹配（适配窄区域按钮）
        result = cv2.matchTemplate(region_bgr, download_img, cv2.TM_CCOEFF_NORMED)
        # 窄区域按钮匹配更严格，置信度范围调整为0.38~0.6
        locations = np.where((result >= 0.38) & (result <= 0.6))

        # 去重计数（窄区域按钮间距小，去重范围缩小）
        buttons = []
        h, w = download_img.shape[:2]
        for pt in zip(*locations[::-1]):
            center_x = x1 + pt[0] + w // 2 + random.randint(-2, 2)  # 微调偏移
            center_y = y1 + pt[1] + h // 2 + random.randint(-2, 2)

            duplicate = False
            for (bx, by) in buttons:
                if abs(center_x - bx) < 25 and abs(center_y - by) < 25:  # 缩小去重范围
                    duplicate = True
                    break
            if not duplicate:
                buttons.append((center_x, center_y))

        # 排序并验证数量
        buttons.sort(key=lambda p: p[1])
        button_count = len(buttons)
        print(f"🔍 找到下载按钮数量：{button_count}（目标范围：8-12个，用户指定每页10个）")

        if 8 <= button_count <= 12:
            print(f"✅ 按钮数量验证通过，取前{target_count}个下载")
            return buttons[:target_count]
        else:
            print(f"⚠️ 按钮数量不达标（{button_count}个），微调置信度重试...")
            # 微调置信度范围
            locations = np.where((result >= 0.35) & (result <= 0.65))
            buttons = []
            for pt in zip(*locations[::-1]):
                center_x = x1 + pt[0] + w // 2 + random.randint(-2, 2)
                center_y = y1 + pt[1] + h // 2 + random.randint(-2, 2)
                duplicate = False
                for (bx, by) in buttons:
                    if abs(center_x - bx) < 25 and abs(center_y - by) < 25:
                        duplicate = True
                        break
                if not duplicate:
                    buttons.append((center_x, center_y))
            buttons.sort(key=lambda p: p[1])
            button_count = len(buttons)
            print(f"🔍 微调后找到：{button_count}个按钮")
            if 7 <= button_count <= 13:
                print(f"✅ 按钮数量验证通过，取前{target_count}个下载")
                return buttons[:target_count]
            else:
                print(f"❌ 按钮数量仍不达标，无法继续")
                return []

    except Exception as e:
        print(f"❌ 查找按钮失败：{str(e)}")
        return []


# ==================== 核心下载功能（保持不变）====================
def get_button_color(x, y, button_size=(26, 26)):
    """判断按钮颜色（蓝色/黄色）"""
    half_w = button_size[0] // 2
    half_h = button_size[1] // 2
    bbox = (x - half_w, y - half_h, x + half_w, y + half_h)

    try:
        screen = ImageGrab.grab(bbox=bbox)
        screen_np = np.array(screen)
        avg_r = np.mean(screen_np[:, :, 0])
        avg_g = np.mean(screen_np[:, :, 1])
        avg_b = np.mean(screen_np[:, :, 2])

        if avg_b > BLUE_THRESHOLD[0] and avg_b < BLUE_THRESHOLD[1] and avg_r < 100 and avg_g < 100:
            return "blue"
        elif (avg_r + avg_g) > YELLOW_THRESHOLD[0] and (avg_r + avg_g) < YELLOW_THRESHOLD[1] and avg_b < 100:
            print("⚠️ 检测到黄色按钮，自动重试点击...")
            return "yellow"
        else:
            return "unknown"
    except Exception as e:
        print(f"❌ 颜色判断失败：{str(e)}")
        return "unknown"


def human_like_click(pos):
    """无规律人工模拟点击"""
    x, y = pos
    pyautogui.moveTo(x, y, duration=random.uniform(*HUMAN_MOVE_DURATION))
    time.sleep(random.uniform(*HUMAN_STAY_DURATION))

    click_count = random.choice([1, 2])
    if click_count == 1:
        pyautogui.click()
    else:
        pyautogui.click(clicks=2, interval=random.uniform(*HUMAN_CLICK_INTERVAL))
    return True


def download_single_file(btn_idx, btn_pos):
    """下载单个文件+验证"""
    global initial_files, downloaded_count, current_page

    x, y = btn_pos
    print(f"\n📥 第{current_page}页：下载第{btn_idx + 1}/{target_count}个（坐标：{int(x)},{int(y)}）")

    # 处理黄色按钮
    button_color = get_button_color(x, y)
    if button_color == "yellow":
        human_like_click(btn_pos)
        time.sleep(random.uniform(0.3, 0.5))

    # 核心点击下载
    human_like_click(btn_pos)

    # 等待下载完成
    start_time = time.time()
    while time.time() - start_time < DOWNLOAD_TIMEOUT:
        current_files = get_file_list(DOWNLOAD_PATH)
        new_files = current_files - initial_files
        if new_files:
            new_file = list(new_files)[-1]
            if new_file[1] >= FILE_MIN_SIZE:
                print(f"✅ 下载成功：{new_file[0]}（{new_file[1] / 1024:.1f}KB）")
                initial_files.add(new_file)
                downloaded_count += 1

                # 随机间歇
                time.sleep(random.uniform(*HUMAN_DOWNLOAD_INTERVAL))
                # 每10个休息一次
                if downloaded_count % HUMAN_PAUSE_TRIGGER == 0:
                    pause_time = random.uniform(*HUMAN_PAUSE_INTERVAL)
                    print(f"\n😴 随机休息 {pause_time:.1f} 秒...")
                    time.sleep(pause_time)
                return True
        time.sleep(random.uniform(0.2, 0.5))

    print(f"❌ 第{btn_idx + 1}个下载超时（15秒）")
    return False


# ==================== 自动翻页+结果验证（保持不变）====================
def find_next_page_button():
    """匹配下一页按钮坐标"""
    global next_page_icon
    if next_page_icon is None:
        print("❌ 未加载下一页按钮截图")
        return None

    print(f"\n📄 查找下一页按钮...")
    screen = ImageGrab.grab()
    screen_np = np.array(screen)
    screen_bgr = cv2.cvtColor(screen_np, cv2.COLOR_RGB2BGR)

    result = cv2.matchTemplate(screen_bgr, next_page_icon, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= 0.45)

    buttons = []
    h, w = next_page_icon.shape[:2]
    for pt in zip(*locations[::-1]):
        center_x = pt[0] + w // 2
        center_y = pt[1] + h // 2

        duplicate = False
        for (bx, by) in buttons:
            if abs(center_x - bx) < 20 and abs(center_y - by) < 20:
                duplicate = True
                break
        if not duplicate:
            buttons.append((center_x, center_y))

    if len(buttons) == 1:
        print(f"✅ 找到下一页按钮（坐标：{buttons[0][0]},{buttons[0][1]}）")
        return buttons[0]
    else:
        print(f"⚠️ 找到 {len(buttons)} 个下一页按钮（需1个）")
        return None


def auto_turn_next_page():
    """自动点击下一页并验证"""
    global is_running, current_page

    # 查找下一页按钮
    next_btn_pos = None
    for _ in range(MAX_RETRY):
        next_btn_pos = find_next_page_button()
        if next_btn_pos:
            break
        time.sleep(random.uniform(0.5, 1.0))
    if not next_btn_pos:
        print("❌ 无法找到下一页按钮，停止脚本")
        is_running = False
        return False

    # 点击翻页
    print(f"📄 点击下一页，切换到第{current_page + 1}页...")
    human_like_click(next_btn_pos)
    time.sleep(PAGE_LOAD_DELAY)

    # 翻页后直接进入下一页流程
    print(f"✅ 成功翻到第{current_page + 1}页")
    current_page += 1
    return True


def verify_page_download():
    """验证当前页是否下载有效文件"""
    global initial_files, downloaded_count, current_page
    current_files = get_file_list(DOWNLOAD_PATH)
    total_new_files = len(current_files) - (len(initial_files) - downloaded_count)
    current_page_new = total_new_files - (current_page - 1) * target_count
    print(f"\n📊 第{current_page}页下载统计：新增文件数={current_page_new}（目标：{target_count}个）")

    if 8 <= current_page_new <= 12:
        file_info = list(current_files)[-current_page_new:] if current_page_new > 0 else []
        file_hashes = [(f[0], f[1]) for f in file_info]
        if len(file_hashes) == len(set(file_hashes)):
            print("✅ 当前页下载验证通过")
            return True
        else:
            print("⚠️ 当前页存在重复文件，重试下载...")
            return False
    elif 7 <= current_page_new <= 13:
        print("⚠️ 当前页下载数量略偏离目标，但仍视为有效")
        return True
    else:
        print(f"⚠️ 当前页下载数量不足（{current_page_new}个），重试下载...")
        return False


# ==================== 主流程（保持不变）====================
def main():
    print("=" * 80)
    print("📌 知网全自动化下载精准版（按用户指定坐标优化）")
    print("✅ 核心配置（用户指定）：")
    print(f"  1. 序号OCR区域：x[730-780] y[760-1480]")
    print(f"  2. 下载按钮区域：x[2000-2030] y[760-1480]")
    print("✅ 核心特性：")
    print("  1. 精准适配用户指定坐标，识别更高效")
    print("  2. 截图可视化+步骤保存，方便调试")
    print("  3. OCR失败自动降级，不中断下载")
    print("  4. 快捷键：ESC=停止 | 空格=暂停/继续")
    print("=" * 80)

    # 初始化
    download_img = init_all()

    # 键盘监听
    def on_key(key):
        global is_running, is_paused
        try:
            if key == keyboard.Key.esc:
                print("\n⚠️ 按ESC停止下载")
                is_running = False
                return False
            elif key == keyboard.Key.space:
                is_paused = not is_paused
                print(f"\n{'⏸️ 已暂停' if is_paused else '▶️ 继续下载'}")
        except Exception as e:
            print(f"\n❌ 键盘错误：{str(e)}")

    listener = keyboard.Listener(on_press=on_key)
    listener.start()
    print("\n🚀 开始全自动化下载（按ESC停止，空格暂停）")

    try:
        while is_running:
            # 暂停控制
            while is_paused:
                time.sleep(0.5)
                if not is_running:
                    break
            if not is_running:
                break

            # -------------------------- 步骤1：OCR识别（精准坐标）--------------------------
            ocr_result = None
            ocr_success = False
            for _ in range(MAX_RETRY):
                ocr_result = ocr_literature_numbers(current_page)
                if ocr_result:
                    ocr_success = True
                    break
                print(f"🔄 OCR识别失败，重试第{_ + 1}/{MAX_RETRY}次...")
                time.sleep(random.uniform(1.0, 1.5))

            # -------------------------- 步骤2：框选区域（精准坐标适配）--------------------------
            box_success = auto_select_region_or_fallback(ocr_success, ocr_result)
            if not box_success:
                print("🔄 框选失败，强制使用用户指定区域...")
                box_success = auto_select_region_or_fallback(False)
                if not box_success:
                    print("❌ 框选失败，停止脚本")
                    break

            # -------------------------- 步骤3：查找并验证下载按钮--------------------------
            buttons = find_and_verify_buttons(download_img)
            if len(buttons) < 7:
                print("❌ 找到的按钮不足，重试当前页...")
                time.sleep(random.uniform(1.5, 2.0))
                continue

            # -------------------------- 步骤4：批量下载--------------------------
            print(f"\n🚀 开始下载第{current_page}页（共{len(buttons)}个文件）")
            for idx, btn_pos in enumerate(buttons):
                if not is_running:
                    break
                while is_paused:
                    time.sleep(0.5)
                download_single_file(idx, btn_pos)

            # -------------------------- 步骤5：结果验证+翻页--------------------------
            if not is_running:
                break
            if verify_page_download():
                if not auto_turn_next_page():
                    break
            else:
                print(f"\n🔄 重试第{current_page}页下载...")
                time.sleep(random.uniform(2.0, 3.0))
                continue

    except Exception as e:
        print(f"\n❌ 脚本错误：{str(e)}")
    finally:
        # 清理资源
        listener.stop()
        listener.join()
        if os.path.exists(TEMP_SCREENSHOT):
            os.remove(TEMP_SCREENSHOT)
        print(f"\n" + "=" * 50)
        print(f"📊 最终统计：")
        print(f"   处理页数：{current_page}页")
        print(f"   总下载数：{downloaded_count}个")
        print(f"   下载路径：{DOWNLOAD_PATH}")
        print(f"   调试文件：{DEBUG_DIR}（含截图+处理步骤）")
        print("=" * 50)
        print("👋 全自动化下载结束")


if __name__ == "__main__":
    # 配置Tesseract OCR路径（用户需根据实际安装位置调整）
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ 用户手动停止")
        print(f"📊 总下载：{downloaded_count}个")
        if os.path.exists(TEMP_SCREENSHOT):
            os.remove(TEMP_SCREENSHOT)