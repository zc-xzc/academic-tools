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
import traceback

# ==================== 核心配置（回归原识别逻辑，保留修复） ====================
CURRENT_PAGE_TYPE = 1  # 页面类型（1/2）
TARGET_BUTTON_COUNT = 10  # 每页必须识别10个按钮
DOWNLOAD_PATH = r"D:\Downloads"  # 下载目录（绝对路径）
INIT_CONFIDENCE = 0.45  # 回归原初始置信度（宽松匹配）
MIN_CONFIDENCE = 0.3  # 最低置信度（保持宽松）
CONFIDENCE_STEP = 0.05  # 置信度降级步长
SCREENSHOT_PATH = "temp_screenshot.png"
FILE_MIN_SIZE = 1024  # 最小文件大小阈值（1KB）
DOWNLOAD_TIMEOUT = 3  # 下载超时时间
PAGE_TURN_DELAY = random.uniform(3, 5)  # 翻页后等待时间
DUPLICATE_THRESHOLD_RATIO = 0.3  # 回归原去重阈值（按钮高度的30%，不过滤真实按钮）
MAX_RETRY_BEFORE_REFRESH = 5  # 单个按钮最大重试次数
DOWNLOAD_WAIT_AFTER_CLICK = 3  # 点击后等待下载启动时间

# 页面一专属配置
PAGE1_BASE_SPACING_OFFSET = 2  # 基础间距补偿
PAGE1_OFFSET_STEP = 4  # 按钮偏移步长（0→4→-4→8→-8...）

# 全局状态
is_running = True
is_paused = False
downloaded_total = 0
downloaded_files = set()  # 记录已下载文件（绝对路径）
screen_size = pyautogui.size()
system_scaling = 1.0
saved_region = None  # 框选区域
page1_buttons = []  # 存储页面一成功下载的按钮数据
current_page = 1  # 当前页码
current_template = None  # 缓存模板
current_template_size = None  # 模板尺寸（h, w）


# ==================== 工具函数（保留numpy错误修复） ====================
def get_system_scaling():
    """获取系统缩放比例"""
    try:
        user32 = ctypes.windll.user32
        dpi = user32.GetDpiForSystem()
        return dpi / 96.0
    except Exception as e:
        print(f"⚠️ 获取系统缩放失败：{str(e)}")
        return 1.0


def init_download_path():
    """初始化下载目录，记录已存在文件（绝对路径）"""
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
    downloaded_files.clear()
    try:
        for filename in os.listdir(DOWNLOAD_PATH):
            file_path = os.path.abspath(os.path.join(DOWNLOAD_PATH, filename))
            if os.path.isfile(file_path):
                # 排除临时文件
                temp_suffixes = ['.crdownload', '.part', '.tmp', '.temp', '.downloading']
                if not any(filename.lower().endswith(suffix) for suffix in temp_suffixes):
                    downloaded_files.add(file_path)
        print(f"✅ 下载路径：{DOWNLOAD_PATH}")
        print(f"✅ 初始已存在文件数：{len(downloaded_files)}")
        return len(downloaded_files)
    except Exception as e:
        print(f"❌ 初始化下载目录失败：{str(e)}")
        return 0


def take_screenshot():
    """截取屏幕并保存"""
    try:
        screen = ImageGrab.grab(bbox=(0, 0, screen_size[0], screen_size[1]))
        screen.save(SCREENSHOT_PATH)
        if os.path.getsize(SCREENSHOT_PATH) < 102400:  # 小于100KB视为无效
            print(f"⚠️  截图无效（文件过小）")
            return False
        return True
    except Exception as e:
        print(f"❌ 截图失败：{str(e)}")
        return False


def load_template():
    """加载下载按钮模板（保留有效性校验，修复numpy错误）"""
    global current_template, current_template_size
    template_path = "download_icon.png"
    if not os.path.exists(template_path):
        print(f"❌ 未找到模板文件：{template_path}（请放在脚本目录）")
        exit(1)
    # 读取模板并校验（避免无效数组）
    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    if template is None or template.size == 0:
        print(f"❌ 模板文件损坏或无效")
        exit(1)
    t_h, t_w = template.shape[:2]
    if t_h < 10 or t_w < 10:  # 模板最小10x10px（兼容小按钮）
        print(f"⚠️  模板尺寸较小（{t_h}x{t_w}px），建议重新截取清晰按钮截图")
    current_template = template
    current_template_size = (t_h, t_w)
    print(f"✅ 加载模板：{t_h}x{t_w}px")
    return template, (t_h, t_w)


def is_valid_coordinate(x, y):
    """校验坐标是否在屏幕范围内"""
    return 0 <= x <= screen_size[0] and 0 <= y <= screen_size[1]


def verify_download_success(initial_file_count):
    """保留修复后的下载判定：检测新增文件"""
    time.sleep(DOWNLOAD_WAIT_AFTER_CLICK)  # 等待下载启动
    timeout_start = time.time()

    while time.time() - timeout_start < DOWNLOAD_TIMEOUT:
        current_files = set()
        try:
            # 遍历当前下载目录
            for filename in os.listdir(DOWNLOAD_PATH):
                file_path = os.path.abspath(os.path.join(DOWNLOAD_PATH, filename))
                if os.path.isfile(file_path):
                    temp_suffixes = ['.crdownload', '.part', '.tmp', '.temp', '.downloading']
                    if not any(filename.lower().endswith(suffix) for suffix in temp_suffixes):
                        current_files.add(file_path)
        except Exception as e:
            print(f"⚠️  检测文件时出错：{str(e)}")
            time.sleep(1)
            continue

        # 计算新增文件数
        new_files = current_files - downloaded_files
        if len(new_files) > 0:
            downloaded_files.update(new_files)
            print(f"✅ 检测到新增文件（下载成功）：{[os.path.basename(f) for f in new_files]}")
            return True
        else:
            current_count = len(current_files)
            print(f"🔍 等待下载：当前文件数={current_count}，初始={initial_file_count}（无新增）")
            time.sleep(2)

    print(f"❌ 下载超时（{DOWNLOAD_TIMEOUT}秒），未检测到新增文件")
    return False


def is_button_exist_safe(target_x, target_y):
    """安全检测按钮是否存在（彻底避免numpy布尔错误）"""
    global current_template, current_template_size
    # 修复：不用not判断numpy数组，用is None+size==0
    if current_template is None or current_template.size == 0:
        print(f"⚠️  模板未加载或无效，无法检测按钮")
        return False
    if not take_screenshot():
        return False

    t_h, t_w = current_template_size
    # 限定检测范围（目标坐标±30px）
    detect_x1 = max(0, int(target_x - 30 - t_w // 2))
    detect_x2 = min(screen_size[0], int(target_x + 30 + t_w // 2))
    detect_y1 = max(0, int(target_y - 30 - t_h // 2))
    detect_y2 = min(screen_size[1], int(target_y + 30 + t_h // 2))

    try:
        img = cv2.imread(SCREENSHOT_PATH)
        if detect_y1 >= detect_y2 or detect_x1 >= detect_x2:
            return False
        detect_roi = img[detect_y1:detect_y2, detect_x1:detect_x2]
        detect_roi_gray = cv2.cvtColor(detect_roi, cv2.COLOR_BGR2GRAY)
        # 模板匹配（TM_SQDIFF_NORMED，避免置信度判断错误）
        result = cv2.matchTemplate(detect_roi_gray, current_template, cv2.TM_SQDIFF_NORMED)
        min_val = result.min() if result.size > 0 else 1.0
        return min_val < 0.1  # 匹配值越小越相似
    except Exception as e:
        print(f"⚠️  按钮检测失败：{str(e)}")
        return False


# ==================== 区域选择（保留原逻辑） ====================
def select_region():
    """让用户框选下载按钮区域（宽度≥30px、高度≥800px）"""
    global saved_region
    print("\n📌 请框选【全部10个下载按钮】的完整区域（从上到下覆盖所有按钮），按ESC确认")
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
            cv2.imshow("框选区域（按ESC确认）", img_copy)
        elif event == cv2.EVENT_MOUSEMOVE and cropping:
            temp_img = img_copy.copy()
            cv2.rectangle(temp_img, ref_point[0], (x, y), (0, 255, 0), 3)
            cv2.imshow("框选区域（按ESC确认）", temp_img)

    cv2.namedWindow("框选区域（按ESC确认）", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("框选区域（按ESC确认）", img_w // 2, img_h // 2)
    cv2.imshow("框选区域（按ESC确认）", img_copy)
    cv2.setMouseCallback("框选区域（按ESC确认）", click_event)

    while cv2.waitKey(1) != 27:  # ESC确认
        pass
    cv2.destroyAllWindows()

    if len(ref_point) == 2:
        x1 = min(ref_point[0][0], ref_point[1][0])
        y1 = min(ref_point[0][1], ref_point[1][1])
        x2 = max(ref_point[0][0], ref_point[1][0])
        y2 = max(ref_point[0][1], ref_point[1][1])
        region_width = x2 - x1
        region_height = y2 - y1
        if region_width < 30 or region_height < 800:
            print(f"⚠️  框选区域不达标（{region_width}x{region_height}px），要求宽度≥30px、高度≥800px")
            return False
        saved_region = (x1, y1, x2, y2)
        print(f"✅ 已保存区域：({x1},{y1})→({x2},{y2})（大小：{region_width}x{region_height}px）")
        return True
    return False


# ==================== 按钮识别（回归原逻辑，确保识别10个） ====================
def find_buttons(template, template_size):
    """回归最初的宽松识别逻辑：低置信度+合理去重，确保识别10个按钮"""
    if not saved_region:
        print("❌ 未选择区域，无法识别按钮")
        return []

    x1, y1, x2, y2 = saved_region
    t_h, t_w = template_size  # 模板尺寸（按钮高度/宽度）
    min_spacing = int(t_h * DUPLICATE_THRESHOLD_RATIO)  # 去重阈值：按钮高度的30%（原逻辑）
    current_confidence = INIT_CONFIDENCE
    max_attempts = int((INIT_CONFIDENCE - MIN_CONFIDENCE) / CONFIDENCE_STEP) + 1  # 置信度降级次数

    for attempt in range(max_attempts):
        if not take_screenshot():
            time.sleep(2)
            continue

        # 截取框选区域并匹配模板（原逻辑）
        img = cv2.imread(SCREENSHOT_PATH)
        roi = img[y1:y2, x1:x2]  # 只在框选区域内搜索
        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        # 模板匹配（回归原TM_CCOEFF_NORMED算法，宽松匹配）
        result = cv2.matchTemplate(roi_gray, template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= current_confidence)  # 按置信度筛选

        # 转换为全局坐标（按钮中心位置）
        buttons = []
        for pt in zip(*locations[::-1]):
            center_x = x1 + pt[0] + t_w // 2  # 全局X坐标
            center_y = y1 + pt[1] + t_h // 2  # 全局Y坐标
            buttons.append((center_x, center_y))

        # 按Y坐标排序（从上到下），去重（间距≥最小阈值）
        buttons = sorted(buttons, key=lambda x: x[1])
        unique_buttons = []
        for btn in buttons:
            if not unique_buttons:
                unique_buttons.append(btn)
            else:
                last_y = unique_buttons[-1][1]
                # 与上一个按钮的Y间距≥最小阈值，视为新按钮（原逻辑）
                if btn[1] - last_y >= min_spacing:
                    unique_buttons.append(btn)

        # 截取前10个按钮（确保数量达标）
        if len(unique_buttons) >= TARGET_BUTTON_COUNT:
            unique_buttons = unique_buttons[:TARGET_BUTTON_COUNT]
            print(f"✅ 置信度{current_confidence}：识别到{len(buttons)}个按钮，去重后{len(unique_buttons)}个（符合预期）")
            print(f"📌 第{current_page}页按钮坐标（从上到下）：")
            for i, (x, y) in enumerate(unique_buttons, 1):
                print(f"   按钮{i}：({x:.0f}, {y:.0f})")
            # 打印间距（供核对）
            print("📏 按钮间距（从上到下）：")
            for i in range(1, TARGET_BUTTON_COUNT):
                spacing = unique_buttons[i][1] - unique_buttons[i - 1][1]
                print(f"   按钮{i}-{i + 1}：{spacing:.0f}px（补偿+{PAGE1_BASE_SPACING_OFFSET}px）")
            return unique_buttons
        else:
            print(f"⚠️  置信度{current_confidence}：识别到{len(unique_buttons)}个按钮（不足10个），尝试降低置信度...")
            current_confidence -= CONFIDENCE_STEP
            current_confidence = round(current_confidence, 2)

    # 所有置信度尝试后仍不足10个
    print(f"❌ 已降至最低置信度{MIN_CONFIDENCE}，仍只识别到{len(unique_buttons)}个按钮")
    print("⚠️  请检查：1. 模板是否与按钮完全匹配 2. 框选区域是否覆盖所有10个按钮 3. 按钮是否清晰可见")
    return []


# ==================== 页面一下载逻辑（保留偏移+下载判定修复） ====================
def download_page1(buttons):
    """页面一下载：保留原偏移逻辑+修复后的下载判定"""
    global downloaded_total, page1_buttons
    page1_buttons = []
    page_downloaded_count = 0
    idx = 0

    # 计算初始间距（原逻辑）
    initial_spacings = []
    for i in range(1, TARGET_BUTTON_COUNT):
        spacing = buttons[i][1] - buttons[i - 1][1]
        initial_spacings.append(spacing)

    while idx < TARGET_BUTTON_COUNT and is_running:
        while is_paused:
            time.sleep(0.5)

        base_x, base_y = buttons[idx]
        actual_offset = 0
        success = False
        fail_count = 0
        btn_name = f"第{current_page}页按钮{idx + 1}"

        print(f"\n📥 开始下载 {btn_name}（基准坐标：{base_x:.0f},{base_y:.0f}）")
        initial_file_count = len(downloaded_files)

        # 计算目标Y坐标（原逻辑）
        if idx == 0:
            target_y = base_y  # 按钮1直接用基准Y坐标
        else:
            # 等待前一个按钮下载成功
            while len(page1_buttons) != idx and is_running:
                print(f"🔄 等待前一个按钮（按钮{idx}）下载完成...")
                time.sleep(1)
            if not is_running:
                break
            prev_btn = page1_buttons[idx - 1]
            prev_final_y = prev_btn[1] + prev_btn[2]  # 前一个按钮的最终Y坐标
            target_y = prev_final_y + initial_spacings[idx - 1] + PAGE1_BASE_SPACING_OFFSET  # 加固定补偿

        # 循环重试当前按钮
        while not success and is_running:
            fail_count += 1
            if fail_count > 1:
                print(f"🔄 {btn_name}第{fail_count}次重试（最多{MAX_RETRY_BEFORE_REFRESH}次）")

            # 达到最大重试次数，刷新页面
            if fail_count > MAX_RETRY_BEFORE_REFRESH:
                print(f"⚠️  {btn_name}重试{MAX_RETRY_BEFORE_REFRESH}次失败，刷新页面...")
                pyautogui.press('f5')
                time.sleep(5)
                new_buttons = find_buttons(current_template, current_template_size)
                if len(new_buttons) == TARGET_BUTTON_COUNT:
                    buttons = new_buttons
                    base_x, base_y = buttons[idx]
                else:
                    print(f"❌ 刷新后仍未识别到10个按钮，5秒后重试...")
                    time.sleep(5)
                fail_count = 0
                continue

            # 坐标校验
            if not is_valid_coordinate(base_x, target_y):
                print(f"⚠️  坐标({base_x:.0f},{target_y:.0f})超出屏幕，自动调整")
                target_y = max(0, min(screen_size[1], target_y))
                time.sleep(1)
                continue

            # 偏移策略（原逻辑：0→4→-4→8→-8...）
            def offset_strategy(i):
                if i == 0:
                    return 0
                else:
                    step = ((i + 1) // 2) * PAGE1_OFFSET_STEP
                    return step if i % 2 == 1 else -step

            # 尝试点击下载
            success, actual_offset = try_click(base_x, target_y, offset_strategy, btn_name, initial_file_count)

            if not success:
                time.sleep(random.uniform(1, 2))
            else:
                # 下载成功，记录并进入下一个按钮
                page1_buttons.append((base_x, target_y, actual_offset))
                downloaded_total += 1
                page_downloaded_count += 1
                print(f"✅ {btn_name}下载成功（偏移：{actual_offset}px，尝试{fail_count}次）")
                time.sleep(random.uniform(1.5, 2.5))
                idx += 1
                break

    # 页面统计
    print(f"\n📊 第{current_page}页下载统计：预期10个，实际成功{page_downloaded_count}个")
    print(f"📊 下载目录当前文件数：{len(downloaded_files)}（新增：{len(downloaded_files) - initial_file_count}）")
    return page_downloaded_count == TARGET_BUTTON_COUNT


# ==================== 通用点击尝试函数（保留修复） ====================
def try_click(base_x, base_y, offset_strategy, btn_name, initial_file_count):
    """尝试点击并检测下载成功（保留偏移逻辑+下载判定）"""
    attempt = 0
    max_attempts = 20  # 单个按钮的偏移尝试次数

    while attempt < max_attempts and is_running:
        # 获取偏移量
        try:
            offset = offset_strategy(attempt)
        except Exception as e:
            print(f"⚠️  偏移策略错误：{str(e)}")
            attempt += 1
            continue

        # 计算点击坐标
        click_x = int(base_x)
        click_y = int(base_y + offset)

        # 坐标校验
        if not is_valid_coordinate(click_x, click_y):
            print(f"⚠️  尝试{attempt + 1}：坐标({click_x},{click_y})超出屏幕，跳过")
            attempt += 1
            continue

        # 执行点击
        try:
            print(f"📝 尝试{attempt + 1}：点击({click_x},{click_y})（偏移：{offset}px）")
            pyautogui.moveTo(click_x, click_y, duration=random.uniform(0.3, 0.6))
            pyautogui.click()
            time.sleep(1)  # 等待页面响应

            # 核心：检测下载是否成功（修复后的逻辑）
            if verify_download_success(initial_file_count):
                return True, offset

        except Exception as e:
            print(f"⚠️  尝试{attempt + 1}失败：{str(e)}")
            traceback.print_exc()

        attempt += 1
        time.sleep(0.8)

    return False, 0


# ==================== 翻页功能（原逻辑） ====================
def turn_page():
    """执行翻页（右键）"""
    global current_page
    if not is_running:
        return False
    try:
        print(f"\n📖 准备翻到第{current_page + 1}页...")
        pyautogui.press('right')
        print(f"✅ 已发送翻页指令，等待{PAGE_TURN_DELAY:.1f}秒...")
        time.sleep(PAGE_TURN_DELAY)
        init_download_path()  # 重新初始化文件计数
        current_page += 1
        return True
    except Exception as e:
        print(f"❌ 翻页失败：{str(e)}")
        return False


# ==================== 键盘控制（原逻辑） ====================
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
    global system_scaling, is_running, current_page, init_file_count
    system_scaling = get_system_scaling()
    print("=" * 80)
    print(f"📌 下载器（页面{CURRENT_PAGE_TYPE}模式）- 强制10个按钮/页")
    print(f"📌 核心配置：回归原识别逻辑（低置信度+宽松去重）+ 保留numpy错误修复")
    print(f"📌 识别策略：置信度0.45起步→最低0.3，去重阈值30%模板高度")
    print(f"📌 偏移逻辑：0→4→-4→8→-8...（4px步长）")
    print(f"📌 下载判定：点击后3秒检测新增文件，成功立即跳转")
    print(f"📌 屏幕分辨率：{screen_size[0]}x{screen_size[1]} | 系统缩放：{system_scaling:.1f}x")
    print("✅ 快捷键：ESC=停止 | 空格=暂停/继续")
    print("=" * 80)

    # 初始化
    init_file_count = init_download_path()
    template, template_size = load_template()

    # 选择区域
    while not saved_region:
        if select_region():
            break
        print("⚠️  区域选择无效，请重新尝试")
        time.sleep(2)

    # 启动键盘监听
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()
    print("\n✅ 开始识别第1页按钮...")

    try:
        # 循环：识别→下载→翻页
        while is_running:
            # 识别10个按钮（回归原逻辑）
            buttons = []
            while len(buttons) != TARGET_BUTTON_COUNT and is_running:
                buttons = find_buttons(template, template_size)
                if len(buttons) != TARGET_BUTTON_COUNT:
                    print("⚠️  按钮识别失败，10秒后重试...")
                    time.sleep(10)

            # 下载当前页
            page_download_success = False
            while not page_download_success and is_running:
                if CURRENT_PAGE_TYPE == 1:
                    page_download_success = download_page1(buttons)
                else:
                    print("❌ 页面二模式未启用")
                    page_download_success = True
                if not page_download_success and is_running:
                    print(f"⚠️  第{current_page}页下载未完成，5秒后重试...")
                    time.sleep(5)

            # 翻页
            if is_running:
                turn_success = False
                while not turn_success and is_running:
                    turn_success = turn_page()
                    if not turn_success:
                        print("⚠️  翻页失败，5秒后重试...")
                        time.sleep(5)

    except Exception as e:
        print(f"\n❌ 程序错误：{str(e)}")
        traceback.print_exc()
    finally:
        # 清理资源
        listener.stop()
        listener.join()
        if os.path.exists(SCREENSHOT_PATH):
            try:
                os.remove(SCREENSHOT_PATH)
            except:
                print(f"⚠️  无法删除临时截图")
        # 最终统计
        final_file_count = len(downloaded_files)
        new_downloaded_count = final_file_count - init_file_count
        print(f"\n" + "=" * 80)
        print(f"🎉 任务结束")
        print(f"📊 统计：共处理{current_page}页 | 预期下载{current_page * 10}个 | 实际新增{new_downloaded_count}个")
        print(f"📊 下载目录最终文件数：{final_file_count}")
        print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  用户手动中断")
        if os.path.exists(SCREENSHOT_PATH):
            os.remove(SCREENSHOT_PATH)
        final_file_count = len(downloaded_files)
        new_downloaded_count = final_file_count - init_file_count
        print(
            f"📊 统计：成功下载{downloaded_total}个 | 下载目录最终文件数：{final_file_count} | 实际新增{new_downloaded_count}个")