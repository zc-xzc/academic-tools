import pyautogui
import time
import random
import os
import cv2
import numpy as np
import pytesseract
from pynput import keyboard
from PIL import ImageGrab, Image, ImageEnhance, ImageFilter
from pathlib import Path

# ==================== 关键配置（保持不变，仅修复按钮查找）====================
DOWNLOAD_PATH = r"D:\Downloads"
TEMP_SCREENSHOT = "temp_page_screenshot.png"
DOWNLOAD_ICON_PATH = "download_icon.png"
NEXT_PAGE_ICON_PATH = "next_page_icon.png"

SCREENSHOT_REGION = (0, 0, 2560, 1680)
DEBUG_DIR = "ocr_debug"
SAVE_ALL_STEPS = True

# OCR配置（已成功，无需修改）
OCR_REGION_X_RANGE = (730, 780)
OCR_REGION_Y_RANGE = (760, 1480)  # 修正为用户指定的760，之前日志显示680是计算错误
OCR_CONTRAST = 3.0
OCR_SHARPEN_STRENGTH = 1.5
FIXED_THRESHOLD = 120
USE_ADAPTIVE_THRESH = True

# 轮廓检测配置（已成功）
CONTOUR_MIN_AREA = 15
CONTOUR_MAX_AREA = 150
CONTOUR_ASPECT_RATIO_RANGE = (0.2, 2.0)

# 技术参数
CONFIDENCE = 0.4
FILE_MIN_SIZE = 1024
DOWNLOAD_TIMEOUT = 20
DOWNLOAD_RETRY_COUNT = 2
PAGE_LOAD_DELAY = random.uniform(2.0, 3.0)
MAX_RETRY = 3

# 下载按钮配置（用户指定）
DOWNLOAD_BTN_X_RANGE = (2000, 2030)
DOWNLOAD_BTN_Y_RANGE = (760, 1480)
FALLBACK_BOX_REGION = (2000, 760, 2030, 1480)
BTN_CLICK_OFFSET_X = 0
BTN_CLICK_OFFSET_Y = 0

# 人工模拟配置
HUMAN_MOVE_DURATION = (0.2, 0.4)
HUMAN_STAY_DURATION = (0.5, 0.8)
HUMAN_CLICK_INTERVAL = (0.1, 0.2)
HUMAN_DOWNLOAD_INTERVAL = (1.2, 1.8)
HUMAN_PAUSE_INTERVAL = (2, 4)
HUMAN_PAUSE_TRIGGER = 10

# 颜色判断配置
BLUE_THRESHOLD = (110, 160)
YELLOW_THRESHOLD = (190, 255)
GRAY_THRESHOLD = (150, 200)

# 全局状态
is_running = True
is_paused = False
current_page = 1
downloaded_count = 0
initial_files = set()
next_page_icon = None
selected_region = None
target_count = 10
download_btn_size = (26, 26)


# ==================== 工具函数（保持不变）====================
def init_all():
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
    Path(DEBUG_DIR).mkdir(exist_ok=True)
    Path(f"{DEBUG_DIR}/steps").mkdir(exist_ok=True)
    Path(f"{DEBUG_DIR}/screenshots").mkdir(exist_ok=True)
    Path(f"{DEBUG_DIR}/contours").mkdir(exist_ok=True)

    global initial_files
    initial_files = get_file_list(DOWNLOAD_PATH)
    print(f"✅ 下载路径：{DOWNLOAD_PATH}（初始文件数：{len(initial_files)}）")

    global next_page_icon, download_btn_size
    download_img = load_icon(DOWNLOAD_ICON_PATH, "下载按钮")
    next_page_icon = load_icon(NEXT_PAGE_ICON_PATH, "下一页按钮")
    download_btn_size = (download_img.shape[1], download_img.shape[0])
    print(f"✅ 下载按钮真实尺寸：{download_btn_size[0]}x{download_btn_size[1]}像素")
    return download_img


def load_icon(path, name):
    if not os.path.exists(path):
        print(f"❌ 未找到 {name} 截图：{path}！")
        exit(1)
    img = cv2.imread(path)
    if img is None or img.shape[0] == 0 or img.shape[1] == 0:
        print(f"❌ {name} 截图无效")
        exit(1)
    h, w = img.shape[:2]
    print(f"✅ 加载{name}截图：{w}x{h}像素")
    return img


def get_file_list(folder):
    files = set()
    for f in os.listdir(folder):
        f_path = os.path.join(folder, f)
        if os.path.isfile(f_path) and os.path.getsize(f_path) >= FILE_MIN_SIZE:
            mtime = os.path.getmtime(f_path)
            files.add((f, os.path.getsize(f_path), mtime))
    return files


def capture_high_res_screen(page_num):
    print(f"\n📸 第{page_num}页：高清晰截图...")
    screen_img = ImageGrab.grab(bbox=SCREENSHOT_REGION)
    screenshot_path = f"{DEBUG_DIR}/screenshots/page_{page_num}_original.png"
    screen_img.save(screenshot_path, format="PNG", quality=100)
    print(f"✅ 原始截图保存到：{screenshot_path}")
    return screen_img, screenshot_path


def enhance_image_for_ocr(img):
    # 1. 锐化
    sharpened = img.filter(ImageFilter.SHARPEN)
    enhancer = ImageEnhance.Sharpness(sharpened)
    sharpened = enhancer.enhance(OCR_SHARPEN_STRENGTH)

    # 2. 转换为numpy数组
    img_np = np.array(sharpened)
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY) if len(img_np.shape) == 3 else img_np

    # 3. 双去噪
    denoised = cv2.GaussianBlur(gray, (3, 3), 0)
    denoised = cv2.medianBlur(denoised, 3)

    # 4. 阈值处理
    if USE_ADAPTIVE_THRESH:
        thresh = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=17, C=4
        )
    else:
        _, thresh = cv2.threshold(denoised, FIXED_THRESHOLD, 255, cv2.THRESH_BINARY_INV)

    # 5. 形态学操作
    kernel = np.ones((2, 2), np.uint8)
    dilated = cv2.dilate(thresh, kernel, iterations=1)
    eroded = cv2.erode(dilated, kernel, iterations=1)

    # 6. 对比度增强
    enhancer = ImageEnhance.Contrast(Image.fromarray(eroded))
    final_img = enhancer.enhance(OCR_CONTRAST)

    return final_img, {
        "sharpened": sharpened,
        "gray": gray,
        "denoised": denoised,
        "thresh": thresh,
        "dilated": dilated,
        "eroded": eroded
    }


def detect_number_contours(processed_img, page_num):
    print(f"\n🔍 第{page_num}页：轮廓检测定位序号...")
    img_np = np.array(processed_img)

    contours, _ = cv2.findContours(img_np, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    print(f"📝 找到轮廓数：{len(contours)}")

    number_contours = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        x, y, w, h = cv2.boundingRect(cnt)
        aspect_ratio = w / h if h != 0 else 0

        if (CONTOUR_MIN_AREA <= area <= CONTOUR_MAX_AREA and
                CONTOUR_ASPECT_RATIO_RANGE[0] <= aspect_ratio <= CONTOUR_ASPECT_RATIO_RANGE[1]):
            number_contours.append((x, y, w, h, area))

    print(f"📝 筛选后序号轮廓数：{len(number_contours)}")

    # 绘制轮廓
    contour_img = cv2.cvtColor(img_np, cv2.COLOR_GRAY2BGR)
    for (x, y, w, h, area) in number_contours:
        cv2.rectangle(contour_img, (x, y), (x + w, y + h), (0, 255, 0), 1)
        cv2.putText(contour_img, f"{area:.0f}", (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 0, 0))

    contour_save_path = f"{DEBUG_DIR}/contours/page_{page_num}_contours.png"
    cv2.imwrite(contour_save_path, contour_img)
    print(f"📸 轮廓检测图保存到：{contour_save_path}")

    contour_y_coords = [y + h / 2 for (x, y, w, h, area) in number_contours]
    return number_contours, contour_y_coords


# ==================== OCR识别（已成功，无需修改）====================
def ocr_literature_numbers_ultimate(page_num):
    print(f"\n🎯 第{page_num}页：终极OCR识别（轮廓辅助）...")

    # 1. 高清晰截图
    original_screen_img, _ = capture_high_res_screen(page_num)

    # 2. 裁剪OCR区域（修正为用户指定的760-1480）
    ocr_bbox = (
        OCR_REGION_X_RANGE[0],
        OCR_REGION_Y_RANGE[0],  # 760
        OCR_REGION_X_RANGE[1],
        OCR_REGION_Y_RANGE[1]  # 1480
    )
    print(
        f"📌 OCR识别区域：x[{OCR_REGION_X_RANGE[0]}-{OCR_REGION_X_RANGE[1]}] y[{OCR_REGION_Y_RANGE[0]}-{OCR_REGION_Y_RANGE[1]}]")

    ocr_crop_img = original_screen_img.crop(ocr_bbox)
    crop_save_path = f"{DEBUG_DIR}/steps/page_{page_num}_crop.png"
    ocr_crop_img.save(crop_save_path)
    print(f"✅ OCR裁剪图保存到：{crop_save_path}")

    try:
        # 3. 图像增强
        enhanced_img, intermediate_imgs = enhance_image_for_ocr(ocr_crop_img)

        # 保存中间图
        step = 1
        for name, img in intermediate_imgs.items():
            img_pil = Image.fromarray(img) if isinstance(img, np.ndarray) else img
            save_path = f"{DEBUG_DIR}/steps/page_{page_num}_step{step}_{name}.png"
            img_pil.save(save_path)
            print(f"  - 处理步骤{step}：{name} → {save_path}")
            step += 1
        final_save_path = f"{DEBUG_DIR}/steps/page_{page_num}_final_enhanced.png"
        enhanced_img.save(final_save_path)
        print(f"  - 最终增强图 → {final_save_path}")

        # 4. 轮廓检测
        number_contours, contour_y_coords = detect_number_contours(enhanced_img, page_num)

        # 5. 多模式OCR
        ocr_results = []
        # 模式1：单行识别
        ocr_text_7 = pytesseract.image_to_string(
            enhanced_img,
            config="--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789. -c dpi=600 -c min_char_height=12"
        ).strip()
        ocr_results.append(("单行模式", ocr_text_7))

        # 模式2：块识别
        ocr_text_6 = pytesseract.image_to_string(
            enhanced_img,
            config="--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789. -c dpi=600 -c min_char_height=12"
        ).strip()
        ocr_results.append(("块模式", ocr_text_6))

        # 模式3：单字符识别
        ocr_text_10 = pytesseract.image_to_string(
            enhanced_img,
            config="--psm 10 --oem 3 -c tessedit_char_whitelist=0123456789. -c dpi=600 -c min_char_height=12"
        ).strip()
        ocr_results.append(("单字符模式", ocr_text_10))

        # 打印OCR结果
        print(f"\n📄 多模式OCR结果：")
        for mode, text in ocr_results:
            print(f"  - {mode}：{text if text else '空'}")

        # 选择最优结果
        best_ocr_text = max([text for (mode, text) in ocr_results if text], key=len, default="")
        print(f"📄 最优OCR文本：{best_ocr_text if best_ocr_text else '空'}")

        # 6. 提取有效数字
        number_info = []
        # 从OCR文本提取
        import re
        numbers_from_ocr = re.findall(r'\d+', best_ocr_text)
        print(f"📝 从OCR提取数字：{numbers_from_ocr}")

        # 从轮廓提取
        img_np = np.array(enhanced_img)
        for (x, y, w, h, area) in number_contours:
            roi = img_np[y:y + h, x:x + w]
            roi_pil = Image.fromarray(roi)
            roi_ocr = pytesseract.image_to_string(
                roi_pil,
                config="--psm 10 --oem 3 -c tessedit_char_whitelist=0123456789 -c dpi=600"
            ).strip()
            if roi_ocr and roi_ocr.isdigit():
                screen_y = OCR_REGION_Y_RANGE[0] + y + h // 2
                number_info.append((int(roi_ocr), screen_y))
                print(f"  - 轮廓OCR：{roi_ocr}（屏幕y：{screen_y:.0f}）")

        # 合并结果
        all_numbers = list(
            set([int(num) for num in numbers_from_ocr if num.isdigit()] + [num for (num, y) in number_info]))
        all_numbers.sort()
        print(f"📝 合并后有效序号：{all_numbers}")

        if not number_info and not all_numbers:
            print("⚠️ 未识别到任何有效序号")
            return None

        # 7. 确定首末y坐标
        if number_info:
            y_coords = [y for (num, y) in number_info]
        else:
            y_coords = contour_y_coords

        # 过滤超出范围的y坐标
        y_coords = [y for y in y_coords if OCR_REGION_Y_RANGE[0] <= y <= OCR_REGION_Y_RANGE[1]]
        if not y_coords:
            print("⚠️ 序号y坐标超出范围")
            return None

        first_y = min(y_coords)
        last_y = max(y_coords)
        print(f"✅ OCR识别成功：序号{all_numbers} | 首行y={round(first_y)} | 末行y={round(last_y)}")
        return (first_y, last_y)

    except Exception as e:
        print(f"❌ OCR识别异常：{str(e)}")
        import traceback
        traceback.print_exc()
        return None


# ==================== 核心修复：按钮查找函数（解决解包错误）====================
def find_download_buttons_precise(download_img):
    """修复：存储二元组坐标，避免解包错误"""
    global selected_region, current_page
    if not selected_region:
        selected_region = FALLBACK_BOX_REGION
    x1, y1, x2, y2 = selected_region
    print(f"\n🎯 在区域（{x1}~{x2},{y1}~{y2}）精准查找下载按钮...")

    try:
        # 1. 截图按钮区域
        region_img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        region_np = np.array(region_img)
        region_bgr = cv2.cvtColor(region_np, cv2.COLOR_RGB2BGR)

        # 保存截图
        region_save_path = f"{DEBUG_DIR}/steps/page_{current_page}_btn_region.png"
        Image.fromarray(cv2.cvtColor(region_bgr, cv2.COLOR_BGR2RGB)).save(region_save_path)
        print(f"📸 按钮区域截图保存到：{region_save_path}")

        # 2. 多尺度模板匹配（修复：先存三元组，再转二元组）
        temp_buttons = []  # 临时存储(x, y, scale)
        h, w = download_img.shape[:2]
        scales = [0.9, 1.0, 1.1]  # 多尺度适配
        for scale in scales:
            scaled_h, scaled_w = int(h * scale), int(w * scale)
            scaled_img = cv2.resize(download_img, (scaled_w, scaled_h))
            result = cv2.matchTemplate(region_bgr, scaled_img, cv2.TM_CCOEFF_NORMED)
            locations = np.where(result >= CONFIDENCE)

            for pt in zip(*locations[::-1]):
                # 计算真实坐标
                center_x = x1 + pt[0] + scaled_w // 2 + BTN_CLICK_OFFSET_X
                center_y = y1 + pt[1] + scaled_h // 2 + BTN_CLICK_OFFSET_Y

                # 验证坐标在用户指定范围内
                if (DOWNLOAD_BTN_X_RANGE[0] <= center_x <= DOWNLOAD_BTN_X_RANGE[1] and
                        DOWNLOAD_BTN_Y_RANGE[0] <= center_y <= DOWNLOAD_BTN_Y_RANGE[1]):
                    temp_buttons.append((center_x, center_y, scale))

        # 3. 去重并转换为二元组（仅保留x,y）
        button_coords = []
        for (x, y, scale) in temp_buttons:
            duplicate = False
            for (bx, by) in button_coords:
                if abs(x - bx) < 30 and abs(y - by) < 30:
                    duplicate = True
                    break
            if not duplicate:
                button_coords.append((x, y))  # 修复：只存二元组

        # 4. 排序并统计数量
        button_coords.sort(key=lambda p: p[1])  # 按y坐标从上到下排序
        button_count = len(button_coords)
        print(f"📝 精准匹配到下载按钮：{button_count}个（去重后）")
        for i, (x, y) in enumerate(button_coords):
            print(f"  - 按钮{i + 1}：({int(x)},{int(y)})")

        # 5. 验证数量
        if 7 <= button_count <= 14:
            print(f"✅ 按钮数量验证通过，取前{target_count}个下载")
            return button_coords[:target_count]
        else:
            print(f"⚠️ 按钮数量不达标（{button_count}个），降低置信度重试...")
            # 降低置信度重试（同样修复二元组问题）
            result = cv2.matchTemplate(region_bgr, download_img, cv2.TM_CCOEFF_NORMED)
            locations = np.where(result >= CONFIDENCE - 0.05)

            retry_buttons = []
            for pt in zip(*locations[::-1]):
                center_x = x1 + pt[0] + w // 2 + BTN_CLICK_OFFSET_X
                center_y = y1 + pt[1] + h // 2 + BTN_CLICK_OFFSET_Y
                if (DOWNLOAD_BTN_X_RANGE[0] <= center_x <= DOWNLOAD_BTN_X_RANGE[1] and
                        DOWNLOAD_BTN_Y_RANGE[0] <= center_y <= DOWNLOAD_BTN_Y_RANGE[1]):
                    duplicate = False
                    for (bx, by) in retry_buttons:
                        if abs(center_x - bx) < 30 and abs(center_y - by) < 30:
                            duplicate = True
                            break
                    if not duplicate:
                        retry_buttons.append((center_x, center_y))  # 修复：二元组

            retry_buttons.sort(key=lambda p: p[1])
            retry_count = len(retry_buttons)
            print(f"📝 降低置信度后匹配到：{retry_count}个")
            if 6 <= retry_count <= 15:
                return retry_buttons[:target_count]
            else:
                print(f"❌ 按钮数量仍不达标")
                return []

    except Exception as e:
        print(f"❌ 查找下载按钮异常：{str(e)}")
        import traceback
        traceback.print_exc()
        return []


# ==================== 精准点击+下载功能（保持不变）====================
def precise_button_click(btn_pos):
    x, y = btn_pos
    print(f"📌 精准点击：({int(x)},{int(y)})")

    # 1. 模拟人类移动
    pyautogui.moveTo(x, y, duration=random.uniform(*HUMAN_MOVE_DURATION))
    # 2. Hover激活
    time.sleep(random.uniform(*HUMAN_STAY_DURATION))

    # 3. 检查按钮颜色
    btn_color = get_button_color_precise(x, y)
    if btn_color == "yellow":
        print("⚠️ 检测到黄色按钮，重试激活...")
        pyautogui.moveTo(x + random.randint(5, 10), y + random.randint(5, 10), duration=0.1)
        time.sleep(0.3)
        pyautogui.moveBack(duration=0.1)
        time.sleep(random.uniform(*HUMAN_STAY_DURATION))
        btn_color = get_button_color_precise(x, y)

    # 4. 点击（单/双击自适应）
    click_count = 1 if btn_color == "blue" else 2
    if click_count == 2:
        print("🔄 尝试双击激活下载...")
        pyautogui.click(clicks=2, interval=random.uniform(*HUMAN_CLICK_INTERVAL))
    else:
        pyautogui.click()

    # 5. 验证点击结果
    time.sleep(0.5)
    after_click_color = get_button_color_precise(x, y)
    if after_click_color == "gray":
        print("✅ 按钮点击成功（颜色变灰）")
        return True
    else:
        print("⚠️ 按钮颜色未变化，重试点击...")
        pyautogui.click()
        time.sleep(0.3)
        return True


def get_button_color_precise(x, y):
    half_w = download_btn_size[0] // 2 + 2
    half_h = download_btn_size[1] // 2 + 2
    bbox = (x - half_w, y - half_h, x + half_w, y + half_h)

    try:
        screen = ImageGrab.grab(bbox=bbox)
        screen_np = np.array(screen)
        avg_r = np.mean(screen_np[:, :, 0])
        avg_g = np.mean(screen_np[:, :, 1])
        avg_b = np.mean(screen_np[:, :, 2])

        # 判断灰色
        gray_value = (avg_r + avg_g + avg_b) / 3
        if GRAY_THRESHOLD[0] <= gray_value <= GRAY_THRESHOLD[1] and abs(avg_r - avg_g) < 20 and abs(avg_g - avg_b) < 20:
            return "gray"
        # 判断蓝色
        elif BLUE_THRESHOLD[0] <= avg_b <= BLUE_THRESHOLD[1] and avg_r < 120 and avg_g < 120:
            return "blue"
        # 判断黄色
        elif YELLOW_THRESHOLD[0] <= (avg_r + avg_g) <= YELLOW_THRESHOLD[1] and avg_b < 120:
            return "yellow"
        else:
            print(f"⚠️ 未知按钮颜色：R={avg_r:.0f}, G={avg_g:.0f}, B={avg_b:.0f}")
            return "unknown"
    except Exception as e:
        print(f"❌ 颜色判断异常：{str(e)}")
        return "unknown"


def download_single_file_optimized(btn_idx, btn_pos):
    global initial_files, downloaded_count, current_page

    x, y = btn_pos
    print(f"\n📥 第{current_page}页：下载第{btn_idx + 1}/{target_count}个（坐标：{int(x)},{int(y)}）")

    # 多次重试
    for retry in range(DOWNLOAD_RETRY_COUNT + 1):
        if not is_running:
            break

        # 精准点击
        precise_button_click(btn_pos)

        # 处理弹窗（可根据实际调整坐标）
        time.sleep(1.0)
        handle_download_popup()

        # 等待下载完成
        start_time = time.time()
        while time.time() - start_time < DOWNLOAD_TIMEOUT:
            current_files = get_file_list(DOWNLOAD_PATH)
            new_files = current_files - initial_files
            if new_files:
                # 按修改时间排序，取最新文件
                new_file = sorted(new_files, key=lambda f: f[2], reverse=True)[0]
                if new_file[1] >= FILE_MIN_SIZE:
                    print(f"✅ 下载成功（重试{retry}次）：{new_file[0]}（{new_file[1] / 1024:.1f}KB）")
                    initial_files.add(new_file)
                    downloaded_count += 1

                    # 随机间歇
                    time.sleep(random.uniform(*HUMAN_DOWNLOAD_INTERVAL))
                    # 每10个休息
                    if downloaded_count % HUMAN_PAUSE_TRIGGER == 0:
                        pause_time = random.uniform(*HUMAN_PAUSE_INTERVAL)
                        print(f"\n😴 随机休息 {pause_time:.1f} 秒...")
                        time.sleep(pause_time)
                    return True
            time.sleep(random.uniform(0.3, 0.7))

        print(f"⚠️ 第{retry + 1}次下载超时")

    print(f"❌ 第{btn_idx + 1}个下载失败（已重试{DOWNLOAD_RETRY_COUNT}次）")
    return False


def handle_download_popup():
    """处理下载弹窗（示例坐标，需根据实际调整）"""
    popup_confirm_pos = (1000, 500)  # 替换为实际弹窗确认按钮坐标
    try:
        # 检查弹窗（通过区域颜色判断）
        screen = ImageGrab.grab(bbox=(900, 400, 1100, 600))
        screen_np = np.array(screen)
        avg_r = np.mean(screen_np[:, :, 0])
        avg_g = np.mean(screen_np[:, :, 1])
        avg_b = np.mean(screen_np[:, :, 2])
        # 弹窗背景通常为白色
        if avg_r > 240 and avg_g > 240 and avg_b > 240:
            print("🔄 检测到下载确认弹窗，自动点击确认...")
            pyautogui.moveTo(popup_confirm_pos[0], popup_confirm_pos[1], duration=0.2)
            time.sleep(0.3)
            pyautogui.click()
            time.sleep(0.5)
    except Exception as e:
        pass  # 无弹窗时忽略


# ==================== 自动框选+翻页（保持不变）====================
def auto_select_region_or_fallback(ocr_success, ocr_result=None):
    global current_page, selected_region
    selected_region = None

    if ocr_success and ocr_result:
        first_y, last_y = ocr_result
        box_x1 = DOWNLOAD_BTN_X_RANGE[0]
        box_x2 = DOWNLOAD_BTN_X_RANGE[1]
        # 适配用户指定的y范围
        box_y1 = max(DOWNLOAD_BTN_Y_RANGE[0], first_y - 10)
        box_y2 = min(DOWNLOAD_BTN_Y_RANGE[1], last_y + 10)

        box_height = box_y2 - box_y1
        if box_height < 200:
            print(f"⚠️ 框选区域高度不足，使用完整y范围")
            box_y1 = DOWNLOAD_BTN_Y_RANGE[0]
            box_y2 = DOWNLOAD_BTN_Y_RANGE[1]

        selected_region = (box_x1, box_y1, box_x2, box_y2)
        print(f"✅ 基于OCR的自动框选区域：")
        print(f"   坐标：({box_x1},{box_y1})→({box_x2},{box_y2}) | 宽{box_x2 - box_x1}px | 高{box_y2 - box_y1}px")
        return True
    else:
        selected_region = FALLBACK_BOX_REGION
        box_x1, box_y1, box_x2, box_y2 = selected_region
        print(f"🔄 OCR识别失败，启用降级模式：使用用户指定区域")
        print(f"   坐标：({box_x1},{box_y1})→({box_x2},{box_y2}) | 宽{box_x2 - box_x1}px | 高{box_y2 - box_y1}px")
        return True


def find_next_page_button():
    global next_page_icon
    if next_page_icon is None:
        print("❌ 未加载下一页按钮截图")
        return None

    print(f"\n📄 查找下一页按钮...")
    screen = ImageGrab.grab()
    screen_np = np.array(screen)
    screen_bgr = cv2.cvtColor(screen_np, cv2.COLOR_RGB2BGR)

    result = cv2.matchTemplate(screen_bgr, next_page_icon, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= 0.5)

    buttons = []
    h, w = next_page_icon.shape[:2]
    for pt in zip(*locations[::-1]):
        center_x = pt[0] + w // 2
        center_y = pt[1] + h // 2

        duplicate = False
        for (bx, by) in buttons:
            if abs(center_x - bx) < 30 and abs(center_y - by) < 30:
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
    global is_running, current_page

    next_btn_pos = None
    for _ in range(MAX_RETRY):
        next_btn_pos = find_next_page_button()
        if next_btn_pos:
            break
        time.sleep(random.uniform(1.0, 1.5))
    if not next_btn_pos:
        print("❌ 无法找到下一页按钮，停止脚本")
        is_running = False
        return False

    print(f"📄 点击下一页，切换到第{current_page + 1}页...")
    precise_button_click(next_btn_pos)
    time.sleep(PAGE_LOAD_DELAY)

    print(f"✅ 成功翻到第{current_page + 1}页")
    current_page += 1
    return True


def verify_page_download():
    global initial_files, downloaded_count, current_page
    current_files = get_file_list(DOWNLOAD_PATH)
    total_new_files = len(current_files) - (len(initial_files) - downloaded_count)
    current_page_new = total_new_files - (current_page - 1) * target_count
    print(f"\n📊 第{current_page}页下载统计：新增文件数={current_page_new}（目标：{target_count}个）")

    if 6 <= current_page_new <= 14:
        print("✅ 当前页下载验证通过")
        return True
    else:
        print(f"⚠️ 当前页下载数量异常，重试下载...")
        return False


# ==================== 主流程（保持不变）====================
def main():
    print("=" * 80)
    print("📌 知网全自动化下载修复版（OCR已成功+按钮查找修复）")
    print("✅ 核心配置（用户指定）：")
    print(f"  1. 序号OCR区域：x[730-780] y[760-1480]")
    print(f"  2. 下载按钮区域：x[2000-2030] y[760-1480]")
    print("✅ 已修复：")
    print("  - 按钮查找函数的参数解包错误（三元组→二元组）")
    print("  - OCR区域y坐标计算错误（修正为760-1480）")
    print("✅ 快捷键：ESC=停止 | 空格=暂停/继续")
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

            # 步骤1：OCR识别（已成功）
            ocr_result = None
            ocr_success = False
            for _ in range(MAX_RETRY):
                ocr_result = ocr_literature_numbers_ultimate(current_page)
                if ocr_result:
                    ocr_success = True
                    break
                print(f"🔄 OCR识别失败，重试第{_ + 1}/{MAX_RETRY}次...")
                time.sleep(random.uniform(1.5, 2.0))

            # 步骤2：自动框选
            box_success = auto_select_region_or_fallback(ocr_success, ocr_result)
            if not box_success:
                print("🔄 框选失败，强制使用用户指定区域...")
                box_success = auto_select_region_or_fallback(False)
                if not box_success:
                    print("❌ 框选失败，停止脚本")
                    break

            # 步骤3：查找下载按钮（已修复）
            buttons = find_download_buttons_precise(download_img)
            if len(buttons) < 6:
                print("❌ 找到的按钮不足，重试当前页...")
                time.sleep(random.uniform(2.0, 3.0))
                continue

            # 步骤4：批量下载
            print(f"\n🚀 开始下载第{current_page}页（共{len(buttons)}个文件）")
            for idx, btn_pos in enumerate(buttons):
                if not is_running:
                    break
                while is_paused:
                    time.sleep(0.5)
                download_single_file_optimized(idx, btn_pos)

            # 步骤5：验证+翻页
            if not is_running:
                break
            if verify_page_download():
                if not auto_turn_next_page():
                    break
            else:
                print(f"\n🔄 重试第{current_page}页下载...")
                time.sleep(random.uniform(2.5, 3.5))
                continue

    except Exception as e:
        print(f"\n❌ 脚本错误：{str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        listener.stop()
        listener.join()
        if os.path.exists(TEMP_SCREENSHOT):
            os.remove(TEMP_SCREENSHOT)
        print(f"\n" + "=" * 50)
        print(f"📊 最终统计：")
        print(f"   处理页数：{current_page}页")
        print(f"   总下载数：{downloaded_count}个")
        print(f"   下载路径：{DOWNLOAD_PATH}")
        print(f"   调试文件：{DEBUG_DIR}")
        print("=" * 50)
        print("👋 全自动化下载结束")


if __name__ == "__main__":
    # 配置Tesseract路径
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    # 验证Tesseract
    try:
        pytesseract.get_tesseract_version()
    except Exception as e:
        print(f"❌ Tesseract配置错误：{str(e)}")
        exit(1)

    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ 用户手动停止")
        print(f"📊 总下载：{downloaded_count}个")
        if os.path.exists(TEMP_SCREENSHOT):
            os.remove(TEMP_SCREENSHOT)