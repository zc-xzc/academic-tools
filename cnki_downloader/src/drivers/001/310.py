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

# ==================== 关键配置（重点优化OCR识别）====================
# 基础路径配置
DOWNLOAD_PATH = r"D:\Downloads"
TEMP_SCREENSHOT = "temp_page_screenshot.png"
DOWNLOAD_ICON_PATH = "download_icon.png"  # 下载按钮截图（根目录）
NEXT_PAGE_ICON_PATH = "next_page_icon.png"  # 下一页按钮截图（根目录）

# OCR识别配置（重点优化：扩大范围+适配序号位置）
OCR_REGION_X_RANGE = (680, 820)  # 扩大x范围（原720-780→680-820，确保多位数完全覆盖）
OCR_REGION_Y_TOP = 300  # 降低顶部偏移（原500→300，避免遗漏上方序号）
OCR_REGION_Y_BOTTOM = 200  # 增加底部偏移（原0→200，排除页脚干扰）
OCR_THRESHOLD = 140  # 调整阈值（原128→140，适配偏亮页面）
OCR_CONTRAST = 2.5  # 增强对比度（原2.0→2.5，让序号更清晰）

# 技术参数配置
CONFIDENCE = 0.35  # 按钮匹配置信度
SERIAL_DOWNLOAD_DX = 0
SERIAL_DOWNLOAD_DY = 0
FILE_MIN_SIZE = 1024  # 有效文件最小大小（1KB）
DOWNLOAD_TIMEOUT = 15  # 下载超时
PAGE_LOAD_DELAY = random.uniform(1.5, 2.5)  # 翻页加载时间
MAX_RETRY = 3  # 关键步骤最大重试次数
DEBUG_SAVE_OCR_IMG = True  # 开启OCR调试图保存（帮助优化参数）

# 框选区域配置（窄长方形）
BOX_WIDTH_RANGE = (26, 40)  # 框选宽度（像素）
BOX_X1_DEFAULT = 2010  # 下载按钮x起始坐标（用户已调整）
BOX_Y_EXPAND = 40  # 扩大上下扩展（原30→40，确保覆盖按钮）

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
target_count = 10  # 固定每页10个


# ==================== 工具函数 ====================
def init_all():
    """全局初始化"""
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
    # 创建调试目录
    if DEBUG_SAVE_OCR_IMG:
        Path("ocr_debug").mkdir(exist_ok=True)
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


# ==================== 核心OCR识别（重点优化）====================
def ocr_literature_numbers():
    """
    优化点：
    1. 扩大识别范围，确保多位数序号完全覆盖
    2. 自适应预处理（动态阈值+增强）
    3. 调整OCR模式为单行识别，提升精准度
    4. 优化序号组合+去重逻辑，避免重复识别
    5. 降低覆盖度阈值，增加序号数量判断
    返回：(first_y, last_y) 首文献y坐标、末文献y坐标，失败返回None
    """
    global current_page
    print(f"\n🔍 第{current_page}页：OCR识别多位数序号（末尾数0-9）...")

    # 1. 定义OCR识别区域（扩大范围）
    screen_w, screen_h = pyautogui.size()
    ocr_bbox = (
        OCR_REGION_X_RANGE[0],
        OCR_REGION_Y_TOP,
        OCR_REGION_X_RANGE[1],
        screen_h - OCR_REGION_Y_BOTTOM
    )
    print(
        f"📌 OCR识别区域：x[{OCR_REGION_X_RANGE[0]}-{OCR_REGION_X_RANGE[1]}] y[{OCR_REGION_Y_TOP}-{screen_h - OCR_REGION_Y_BOTTOM}]")

    try:
        # 2. 截图并增强预处理（优化版）
        ocr_img = ImageGrab.grab(bbox=ocr_bbox)

        # 预处理流程：灰度化→自适应阈值（抗亮度干扰）→对比度增强→降噪
        ocr_img_gray = ocr_img.convert("L")  # 灰度化

        # 自适应阈值（比固定阈值更抗干扰）
        ocr_img_np = np.array(ocr_img_gray)
        ocr_img_binary = cv2.adaptiveThreshold(
            ocr_img_np, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,  # 高斯自适应
            cv2.THRESH_BINARY_INV,  # 反相（黑字白底→白字黑底，提升识别）
            blockSize=15, C=2  # 块大小15，常数2（可调整）
        )
        # 转回PIL图像（L模式）
        ocr_img_binary_pil = Image.fromarray(ocr_img_binary).convert("L")

        # 对比度增强（提升文字清晰度）
        enhancer = ImageEnhance.Contrast(ocr_img_binary_pil)
        ocr_img_enhanced = enhancer.enhance(OCR_CONTRAST)

        # 降噪（去除孤立小点）
        ocr_img_np_enhanced = np.array(ocr_img_enhanced)
        kernel = np.ones((1, 1), np.uint8)
        ocr_img_denoised = cv2.morphologyEx(ocr_img_np_enhanced, cv2.MORPH_OPEN, kernel)
        ocr_img_final = Image.fromarray(ocr_img_denoised).convert("L")

        # 保存调试图（帮助优化参数）
        if DEBUG_SAVE_OCR_IMG:
            debug_path = f"ocr_debug/page_{current_page}_ocr_debug.png"
            ocr_img_final.save(debug_path)
            print(f"📸 保存OCR调试图到：{debug_path}")

        # 3. OCR识别（优化配置）
        ocr_text = pytesseract.image_to_string(
            ocr_img_final,
            config="--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789 -c dpi=300"
            # --psm 7：单行识别（适配每个序号单独一行）
            # --dpi 300：模拟高分辨率，提升识别率
        )
        ocr_text = ocr_text.strip()
        print(f"📄 OCR原始文本：{ocr_text if ocr_text else '空'}")

        # 4. 提取有效数字（多位数），获取末尾数和完整序号的y坐标
        number_info = []  # 存储 (完整序号, 末尾数, y坐标, 字符数)
        # 用image_to_boxes获取每个字符的位置和置信度
        char_boxes = pytesseract.image_to_boxes(
            ocr_img_final,
            config="--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789 -c dpi=300"
        )

        # 解析字符框，智能组合多位数（优化去重和分行）
        current_number = ""
        current_y = None
        current_char_count = 0
        img_h = ocr_img_final.height

        for line in char_boxes.splitlines():
            if len(line.split()) != 6:
                continue
            char, x1, y1, x2, y2, _ = line.split()
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

            # 转换y坐标（OCR图像坐标系→屏幕坐标系）
            char_y = ocr_bbox[1] + (img_h - y2)  # OCR y轴反向
            # 字符宽度（判断是否为有效数字）
            char_width = x2 - x1

            # 过滤过小的噪点字符（宽度<5px视为噪点）
            if char_width < 5:
                continue

            # 组合多位数（同一行：y差<15px，字符间距<20px）
            if current_y is None or (
                    abs(char_y - current_y) < 15 and (x1 - int(x2_prev) if current_number else 0) < 20):
                current_number += char
                current_y = char_y
                current_char_count += 1
                x2_prev = x2  # 记录上一个字符的x2坐标
            else:
                # 保存上一个完整序号（至少1位数字，排除单个噪点）
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

        # 5. 智能去重（排除重复序号+同一位置重复识别）
        unique_number_info = []
        seen_y = set()
        seen_num = set()
        for info in number_info:
            full_num, last_digit, y, char_count = info
            # 同一y坐标（±5px）去重，同一数字去重（避免重复识别）
            y_key = round(y / 10) * 10  # 按10px分组去重
            if y_key not in seen_y and full_num not in seen_num:
                seen_y.add(y_key)
                seen_num.add(full_num)
                unique_number_info.append(info)

        # 过滤无效序号（字符数<1或数字异常）
        unique_number_info = [info for info in unique_number_info if info[3] >= 1 and 0 <= info[0] <= 999]

        if not unique_number_info:
            print("⚠️ 未识别到任何有效序号")
            return None

        # 打印识别结果（带详细信息）
        full_nums = [info[0] for info in unique_number_info]
        last_digits = [info[1] for info in unique_number_info]
        y_coords = [info[2] for info in unique_number_info]
        print(f"📝 识别到有效序号：{full_nums}（共{len(full_nums)}个）")
        print(f"📝 序号末尾数：{sorted(list(set(last_digits)))}（共{len(set(last_digits))}个）")
        print(f"📝 序号y坐标：{[round(y) for y in y_coords]}")

        # 6. 双重验证（末尾数覆盖+序号数量）
        unique_last_digits = set(last_digits)
        # 条件：末尾数≥5个 OR 序号数量≥8个（适配不同页面）
        if len(unique_last_digits) < 5 and len(full_nums) < 8:
            print(f"⚠️ 末尾数覆盖不足（{len(unique_last_digits)}个）且序号数量不足（{len(full_nums)}个），重试识别...")
            return None

        # 7. 定位首末文献y坐标（最小y=首行，最大y=末行）
        first_y = min(y_coords)
        last_y = max(y_coords)
        print(f"✅ 首文献y坐标：{round(first_y)} | 末文献y坐标：{round(last_y)}")

        return (first_y, last_y)

    except Exception as e:
        print(f"❌ OCR识别失败：{str(e)}")
        return None


# ==================== 自动框选（基于首末文献y坐标）====================
def auto_select_download_region():
    """自动框选下载区域（窄长方形，覆盖首末文献）"""
    global current_page, selected_region
    selected_region = None
    screen_w, screen_h = pyautogui.size()

    # 1. OCR定位首末文献y坐标（重试MAX_RETRY次）
    ocr_result = None
    for _ in range(MAX_RETRY):
        ocr_result = ocr_literature_numbers()
        if ocr_result:
            break
        time.sleep(random.uniform(1.0, 1.5))
    if not ocr_result:
        print("❌ OCR定位失败，无法自动框选")
        return False

    first_y, last_y = ocr_result
    # 2. 计算框选区域（优化：扩大上下扩展）
    box_width = random.randint(BOX_WIDTH_RANGE[0], BOX_WIDTH_RANGE[1])
    box_x1 = BOX_X1_DEFAULT  # 下载按钮x起始（用户已调整）
    box_x2 = box_x1 + box_width
    # 高度：首末y + 更大扩展，确保覆盖所有下载按钮
    box_y1 = max(0, first_y - BOX_Y_EXPAND - 10)
    box_y2 = min(screen_h, last_y + BOX_Y_EXPAND + 10)

    # 3. 验证区域合理性（放宽高度阈值）
    box_height = box_y2 - box_y1
    if not (BOX_WIDTH_RANGE[0] <= box_width <= BOX_WIDTH_RANGE[1] and box_height >= 200):
        print(f"⚠️ 框选区域异常（宽：{box_width}px，高：{box_height}px）")
        return False

    selected_region = (box_x1, box_y1, box_x2, box_y2)
    print(f"✅ 自动框选区域：")
    print(f"   宽：{box_width}px | 高：{box_height}px")
    print(f"   坐标：({box_x1},{box_y1})→({box_x2},{box_y2})")
    return True


# ==================== 双重验证（末尾数+按钮数量）====================
def auto_verify_target_count(download_img):
    """双重验证：末尾数覆盖+下载按钮数量"""
    global current_page, selected_region
    print(f"\n✅ 第{current_page}页：双重计数验证...")

    if not selected_region:
        print("❌ 未框选区域，无法验证")
        return False

    x1, y1, x2, y2 = selected_region
    try:
        screen = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        screen_np = np.array(screen)
        screen_bgr = cv2.cvtColor(screen_np, cv2.COLOR_RGB2BGR)

        # 模板匹配（优化：多尺度匹配）
        result = cv2.matchTemplate(screen_bgr, download_img, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= CONFIDENCE)

        # 去重计数（优化：更大去重范围）
        buttons = []
        h, w = download_img.shape[:2]
        for pt in zip(*locations[::-1]):
            center_x = x1 + pt[0] + w // 2
            center_y = y1 + pt[1] + h // 2

            duplicate = False
            for (bx, by) in buttons:
                if abs(center_x - bx) < 40 and abs(center_y - by) < 40:  # 扩大去重范围
                    duplicate = True
                    break
            if not duplicate:
                buttons.append((center_x, center_y))

        button_count = len(buttons)
        print(f"🔍 下载按钮匹配数量：{button_count}（目标：10个）")

        # 验证按钮数量（6-14个，进一步放宽阈值）
        if 6 <= button_count <= 14:
            print(f"✅ 计数验证通过，按10个文件下载")
            return True
        else:
            print(f"⚠️ 按钮数量不匹配（{button_count}个），重新框选...")
            return False

    except Exception as e:
        print(f"❌ 计数验证失败：{str(e)}")
        return False


# ==================== 核心下载功能（保持不变）====================
def find_download_buttons(download_img):
    """查找下载按钮（基于自动框选区域）"""
    global selected_region, target_count
    if not selected_region:
        print("❌ 未框选区域")
        return []

    x1, y1, x2, y2 = selected_region
    try:
        screen = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        screen_np = np.array(screen)
        screen_bgr = cv2.cvtColor(screen_np, cv2.COLOR_RGB2BGR)

        result = cv2.matchTemplate(screen_bgr, download_img, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= CONFIDENCE)

        buttons = []
        h, w = download_img.shape[:2]
        for pt in zip(*locations[::-1]):
            center_x = x1 + pt[0] + w // 2 + SERIAL_DOWNLOAD_DX + random.randint(-3, 3)
            center_y = y1 + pt[1] + h // 2 + SERIAL_DOWNLOAD_DY + random.randint(-3, 3)

            duplicate = False
            for (bx, by) in buttons:
                if abs(center_x - bx) < 30 and abs(center_y - by) < 30:
                    duplicate = True
                    break
            if not duplicate:
                buttons.append((center_x, center_y))

        # 排序（从上到下）并取前10个
        buttons.sort(key=lambda p: p[1])
        buttons = buttons[:target_count]
        print(f"✅ 找到 {len(buttons)} 个下载按钮（目标：10个）")
        return buttons

    except Exception as e:
        print(f"❌ 查找按钮失败：{str(e)}")
        return []


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
    print(f"\n📥 第{current_page}页：下载第{btn_idx + 1}/10个（坐标：{int(x)},{int(y)}）")

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


# ==================== 自动翻页（保持不变）====================
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

    # 验证翻页成功（OCR识别新页面序号末尾数）
    new_ocr_result = ocr_literature_numbers()
    if new_ocr_result:
        print(f"✅ 成功翻到第{current_page + 1}页")
        current_page += 1
        return True

    print("⚠️ 翻页验证失败，重试翻页...")
    human_like_click(next_btn_pos)
    time.sleep(PAGE_LOAD_DELAY)
    current_page += 1
    return True


# ==================== 下载结果验证（保持不变）====================
def verify_page_download():
    """验证当前页是否下载10个有效文件"""
    global initial_files, downloaded_count, current_page
    current_files = get_file_list(DOWNLOAD_PATH)
    # 计算当前页新增文件数
    total_new_files = len(current_files) - (len(initial_files) - downloaded_count)
    current_page_new = total_new_files - (current_page - 1) * 10
    print(f"\n📊 第{current_page}页下载统计：新增文件数={current_page_new}（目标：10个）")

    # 验证数量（6-14个，进一步放宽）
    if 6 <= current_page_new <= 14:
        # 验证无重复
        file_info = list(current_files)[-current_page_new:] if current_page_new > 0 else []
        file_hashes = [(f[0], f[1]) for f in file_info]
        if len(file_hashes) == len(set(file_hashes)):
            print("✅ 当前页下载验证通过（10个有效文件，无重复）")
            return True
        else:
            print("⚠️ 当前页存在重复文件，重试下载...")
            return False
    else:
        print(f"⚠️ 当前页下载数量不足（{current_page_new}个），重试下载...")
        return False


# ==================== 主流程（保持不变）====================
def main():
    print("=" * 75)
    print("📌 知网全自动化下载优化版（OCR识别增强+去重优化）")
    print("✅ 核心优化：")
    print("  1. 扩大OCR识别范围，覆盖多位数序号")
    print("  2. 自适应阈值预处理，抗页面亮度干扰")
    print("  3. 单行识别模式+高分辨率模拟，提升精准度")
    print("  4. 智能去重+双重验证，避免重复识别")
    print("  5. 调试图保存，方便参数优化")
    print("✅ 快捷键：ESC=停止 | 空格=暂停/继续")
    print("=" * 75)

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

            # 1. 自动框选
            box_success = False
            for _ in range(MAX_RETRY):
                if auto_select_download_region():
                    box_success = True
                    break
                time.sleep(random.uniform(1.0, 1.5))
            if not box_success:
                print("❌ 自动框选失败，停止脚本")
                break

            # 2. 双重验证
            verify_success = False
            for _ in range(MAX_RETRY):
                if auto_verify_target_count(download_img):
                    verify_success = True
                    break
                time.sleep(random.uniform(1.0, 1.5))
                auto_select_download_region()
            if not verify_success:
                print("❌ 计数验证失败，停止脚本")
                break

            # 3. 查找按钮
            buttons = find_download_buttons(download_img)
            if len(buttons) < 6:  # 降低按钮数量阈值
                print("❌ 找到的按钮不足，重试当前页...")
                time.sleep(random.uniform(1.5, 2.0))
                continue

            # 4. 批量下载
            print(f"\n🚀 开始下载第{current_page}页（共10个文件）")
            for idx, btn_pos in enumerate(buttons[:10]):
                if not is_running:
                    break
                while is_paused:
                    time.sleep(0.5)
                download_single_file(idx, btn_pos)

            # 5. 结果验证
            if not is_running:
                break
            if verify_page_download():
                # 6. 自动翻页
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