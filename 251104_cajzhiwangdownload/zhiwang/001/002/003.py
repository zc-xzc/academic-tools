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

# ==================== 核心配置 ====================
CURRENT_PAGE_TYPE = 1  # 页面类型（1/2）
TARGET_BUTTON_COUNT = 10  # 每页预期按钮数量（用户指定）
DOWNLOAD_PATH = r"D:\Downloads"
CONFIDENCE = 0.45  # 提高置信度，减少误识别
SCREENSHOT_PATH = "temp_screenshot.png"
FILE_MIN_SIZE = 1024  # 降低最小文件大小阈值（适配小文件）
DOWNLOAD_TIMEOUT = 20  # 下载超时时间（秒）

# 页面一专属配置
PAGE1_BASE_SPACING_OFFSET = 4  # 基础间距补偿
PAGE1_BUTTON1_OFFSETS = [0, 2, -2, 4, -4]  # 按钮1偏移策略（提高成功率）
PAGE1_BUTTON2_OFFSET_STEP = 4  # 按钮2及以后偏移步长（4的倍数）

# 页面二专属配置
PAGE2_BUTTON1_OFFSETS = [3, 5, 7, 10]  # 按钮1双向偏移序列
PAGE2_STEP1_OFFSET = 65  # 第一步基础偏移
PAGE2_STEP2_OFFSET = 7   # 第二步偏移步长
PAGE2_STEP2_COUNT = 3    # 第二步尝试次数
PAGE2_STEP3_OFFSET = 4   # 第三步偏移步长

# 全局状态
is_running = True
is_paused = False
downloaded_total = 0
screen_size = pyautogui.size()
system_scaling = 1.0
saved_region = None  # 框选区域
page1_buttons = []   # 存储页面一成功下载的按钮数据 [(x, y, actual_offset), ...]


# ==================== 工具函数 ====================
def get_system_scaling():
    """获取系统缩放比例，修正坐标偏差"""
    try:
        user32 = ctypes.windll.user32
        dpi = user32.GetDpiForSystem()
        return dpi / 96.0
    except:
        return 1.0


def init_download_path():
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
    print(f"✅ 下载路径：{DOWNLOAD_PATH}")


def take_screenshot():
    """截取屏幕并保存"""
    try:
        screen = ImageGrab.grab(bbox=(0, 0, screen_size[0], screen_size[1]))
        screen.save(SCREENSHOT_PATH)
        return os.path.getsize(SCREENSHOT_PATH) > 102400  # 确保截图有效
    except Exception as e:
        print(f"❌ 截图失败：{str(e)}")
        return False


def load_template():
    """加载下载按钮模板"""
    template_path = "download_icon.png"
    if not os.path.exists(template_path):
        print(f"❌ 未找到 {template_path}！请将下载按钮截图命名为该文件并放在脚本目录")
        exit(1)
    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    return template, template.shape[:2]


def is_valid_coordinate(x, y):
    """校验坐标是否在屏幕范围内"""
    return 0 <= x <= screen_size[0] and 0 <= y <= screen_size[1]


# ==================== 区域选择 ====================
def select_region():
    """让用户框选下载按钮所在区域"""
    global saved_region
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
            cv2.imshow("框选下载按钮区域（按ESC确认）", img_copy)
        elif event == cv2.EVENT_MOUSEMOVE and cropping:
            temp_img = img_copy.copy()
            cv2.rectangle(temp_img, ref_point[0], (x, y), (0, 255, 0), 3)
            cv2.imshow("框选下载按钮区域（按ESC确认）", temp_img)

    cv2.namedWindow("框选下载按钮区域（按ESC确认）", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("框选下载按钮区域（按ESC确认）", img_w // 2, img_h // 2)
    cv2.imshow("框选下载按钮区域（按ESC确认）", img_copy)
    cv2.setMouseCallback("框选下载按钮区域（按ESC确认）", click_event)

    while cv2.waitKey(1) != 27:  # ESC确认
        pass
    cv2.destroyAllWindows()

    if len(ref_point) == 2:
        x1 = min(ref_point[0][0], ref_point[1][0])
        y1 = min(ref_point[0][1], ref_point[1][1])
        x2 = max(ref_point[0][0], ref_point[1][0])
        y2 = max(ref_point[0][1], ref_point[1][1])
        saved_region = (x1, y1, x2, y2)
        print(f"✅ 已保存区域：({x1},{y1})→({x2},{y2})")
        return True
    return False


# ==================== 按钮识别（优化去重） ====================
def find_buttons(template, template_size):
    """识别按钮并去重，确保接近预期数量（10个）"""
    if not saved_region:
        return []
    x1, y1, x2, y2 = saved_region
    t_h, t_w = template_size  # 模板尺寸（按钮尺寸）

    if not take_screenshot():
        return []

    img = cv2.imread(SCREENSHOT_PATH)
    roi = img[y1:y2, x1:x2]
    roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(roi_gray, template, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= CONFIDENCE)

    buttons = []
    for pt in zip(*locations[::-1]):
        center_x = x1 + pt[0] + t_w // 2
        center_y = y1 + pt[1] + t_h // 2
        buttons.append((center_x, center_y))

    # 按Y坐标排序（从上到下）
    buttons = sorted(buttons, key=lambda x: x[1])
    unique_buttons = []
    min_spacing = t_h  # 最小间距设为按钮高度（减少重复识别）
    for btn in buttons:
        if not unique_buttons:
            unique_buttons.append(btn)
        else:
            last_y = unique_buttons[-1][1]
            if btn[1] - last_y >= min_spacing:  # 超过按钮高度视为新按钮
                unique_buttons.append(btn)

    # 截取前10个按钮（用户指定每页10个）
    if len(unique_buttons) > TARGET_BUTTON_COUNT:
        unique_buttons = unique_buttons[:TARGET_BUTTON_COUNT]
        print(f"⚠️  识别到{len(unique_buttons)+(len(unique_buttons)-TARGET_BUTTON_COUNT)}个按钮，自动截取前{TARGET_BUTTON_COUNT}个")
    elif len(unique_buttons) < TARGET_BUTTON_COUNT:
        print(f"⚠️  识别到{len(unique_buttons)}个按钮，少于预期的{TARGET_BUTTON_COUNT}个")

    # 打印识别结果
    print(f"📌 最终识别到{len(unique_buttons)}个有效按钮")
    for i, (x, y) in enumerate(unique_buttons, 1):
        print(f"   按钮{i}：({x:.0f}, {y:.0f})")
    return unique_buttons


# ==================== 页面一下载逻辑（核心修复） ====================
def download_page1(buttons):
    """页面一下载逻辑（修复索引越界+优化按钮1成功率）"""
    global downloaded_total, page1_buttons
    page1_buttons = []  # 重置成功下载的按钮数据
    if len(buttons) == 0:
        print("❌ 未识别到任何按钮，终止下载")
        return

    # 计算初始间距（相邻按钮的Y轴差值）
    initial_spacings = []
    for i in range(1, len(buttons)):
        spacing = buttons[i][1] - buttons[i-1][1]
        initial_spacings.append(spacing)
        print(f"📏 按钮{i}与按钮{i+1}初始间距：{spacing:.0f}px（补偿+{PAGE1_BASE_SPACING_OFFSET}px）")

    # 逐个处理按钮（核心修复：前一个按钮失败则终止后续）
    for idx in range(len(buttons)):
        if not is_running:
            break
        while is_paused:
            time.sleep(0.5)

        base_x, base_y = buttons[idx]
        actual_offset = 0
        success = False
        print(f"\n📥 页面一 按钮{idx+1}（基准坐标：{base_x:.0f},{base_y:.0f}）")

        # 计算目标Y坐标（修复：仅当前一个按钮成功时才承接偏移）
        if idx == 0:
            # 按钮1：使用基准坐标
            target_y = base_y
        else:
            # 检查前一个按钮是否成功下载（避免索引越界）
            if len(page1_buttons) != idx:
                print(f"❌ 前一个按钮（按钮{idx}）下载失败，无法承接偏移，终止后续按钮处理")
                break
            # 前一个按钮的最终坐标 = 基准Y + 实际偏移
            prev_btn = page1_buttons[idx-1]
            prev_final_y = prev_btn[1] + prev_btn[2]
            # 目标Y = 前一个最终Y + 初始间距 + 5px补偿
            target_y = prev_final_y + initial_spacings[idx-1] + PAGE1_BASE_SPACING_OFFSET

        # 校验坐标有效性
        if not is_valid_coordinate(base_x, target_y):
            print(f"⚠️  目标坐标({base_x:.0f},{target_y:.0f})超出屏幕范围，跳过")
            continue

        # 定义偏移策略（优化按钮1成功率）
        def offset_strategy(i):
            if idx == 0:
                # 按钮1：偏移序列[0, ±2, ±4]（优先无偏移，再微调）
                if i < len(PAGE1_BUTTON1_OFFSETS):
                    return PAGE1_BUTTON1_OFFSETS[i]
                else:
                    return None
            else:
                # 按钮2及以后：4的倍数序列（4、8、12...）
                return PAGE1_BUTTON1_OFFSETS[i] if i < len(PAGE1_BUTTON1_OFFSETS) else PAGE1_BUTTON2_OFFSET_STEP * (i - len(PAGE1_BUTTON1_OFFSETS) + 1)

        # 尝试点击
        success, actual_offset = try_click(base_x, target_y, offset_strategy)

        if success:
            downloaded_total += 1
            page1_buttons.append((base_x, target_y, actual_offset))  # 仅成功的按钮加入列表
            print(f"✅ 按钮{idx+1}下载成功（实际偏移：{actual_offset}px）")
            time.sleep(random.uniform(1.5, 2.5))  # 延长等待，避免触发反爬
        else:
            print(f"❌ 按钮{idx+1}下载失败")
            # 按钮1失败则直接终止（后续无法承接）
            if idx == 0:
                print("❌ 按钮1下载失败，无法继续处理后续按钮")
                break


# ==================== 页面二下载逻辑 ====================
def download_page2():
    """页面二下载逻辑（复用页面一X坐标，修复索引依赖）"""
    global downloaded_total
    if not page1_buttons:
        print("❌ 未检测到页面一成功下载的按钮数据，请先运行页面一模式")
        return

    # 确保页面二按钮数量与页面一一致（最多10个）
    button_count = min(len(page1_buttons), TARGET_BUTTON_COUNT)
    print(f"\n📋 页面二开始下载（共{button_count}个按钮，复用页面一X坐标）")

    for idx in range(button_count):
        if not is_running:
            break
        while is_paused:
            time.sleep(0.5)

        base_x = page1_buttons[idx][0]  # 复用页面一X坐标
        actual_offset = 0
        success = False
        print(f"\n📥 页面二 按钮{idx+1}（复用X坐标：{base_x:.0f}）")

        # 计算初始目标Y坐标
        if idx == 0:
            # 按钮1：使用页面一按钮1的Y坐标
            target_y = page1_buttons[0][1]
        else:
            # 按钮2及后续：上一个按钮最终Y + 65px基础偏移
            prev_btn = page1_buttons[idx-1]
            prev_final_y = prev_btn[1] + prev_btn[2]
            target_y = prev_final_y + PAGE2_STEP1_OFFSET

        # 校验坐标有效性
        if not is_valid_coordinate(base_x, target_y):
            print(f"⚠️  目标坐标({base_x:.0f},{target_y:.0f})超出屏幕范围，跳过")
            continue

        # 定义偏移策略
        def offset_strategy(i):
            if idx == 0:
                # 按钮1：双向偏移±3→±5→±7→±10
                if i < len(PAGE2_BUTTON1_OFFSETS) * 2:
                    offset_idx = i // 2
                    sign = -1 if i % 2 == 0 else 1
                    return sign * PAGE2_BUTTON1_OFFSETS[offset_idx]
                else:
                    return None
            else:
                # 按钮2及后续：65→7*3→4的倍数递增
                if i == 0:
                    return 0  # 第一步：基础偏移
                elif 1 <= i <= PAGE2_STEP2_COUNT:
                    return PAGE2_STEP2_OFFSET * i  # 第二步：7px递增3次
                else:
                    # 第三步：4的倍数递增，承接上一个按钮偏移
                    prev_offset = page1_buttons[idx-1][2]
                    step3_idx = i - PAGE2_STEP2_COUNT - 1
                    return prev_offset + PAGE2_STEP3_OFFSET * (step3_idx + 1)

        # 尝试点击
        success, actual_offset = try_click(base_x, target_y, offset_strategy)

        if success:
            downloaded_total += 1
            print(f"✅ 按钮{idx+1}下载成功（实际偏移：{actual_offset}px）")
            time.sleep(random.uniform(1.5, 2.5))
        else:
            print(f"❌ 按钮{idx+1}下载失败")


# ==================== 通用点击尝试函数（优化文件检测） ====================
def try_click(base_x, base_y, offset_strategy):
    """尝试点击并检测下载是否成功（优化文件检测逻辑）"""
    # 记录初始文件列表（排除临时文件）
    initial_files = set()
    for f in os.listdir(DOWNLOAD_PATH):
        f_path = os.path.join(DOWNLOAD_PATH, f)
        if os.path.isfile(f_path) and not f.endswith(('.crdownload', '.part', '.tmp', '.download')):
            initial_files.add(f)

    attempt = 0
    max_attempts = 20  # 最大尝试次数
    last_file_count = len(initial_files)

    while attempt < max_attempts and is_running:
        # 获取当前偏移量
        try:
            offset = offset_strategy(attempt)
            if offset is None:
                print(f"📝 偏移策略已用尽（尝试{attempt}次）")
                break
        except Exception as e:
            print(f"⚠️  偏移策略错误：{str(e)}")
            break

        # 计算点击坐标
        click_x = int(base_x)
        click_y = int(base_y + offset)

        # 校验坐标
        if not is_valid_coordinate(click_x, click_y):
            print(f"⚠️  尝试{attempt+1}：坐标({click_x},{click_y})超出屏幕，跳过")
            attempt += 1
            continue

        # 执行点击
        try:
            print(f"📝 尝试{attempt+1}：点击({click_x},{click_y})（偏移：{offset}px）")
            pyautogui.moveTo(click_x, click_y, duration=random.uniform(0.3, 0.6))  # 放慢移动速度
            pyautogui.click()
            time.sleep(2)  # 延长点击后等待时间

            # 检测新文件（优化：允许文件计数增加或大小变化）
            current_files = set()
            new_file = None
            for f in os.listdir(DOWNLOAD_PATH):
                f_path = os.path.join(DOWNLOAD_PATH, f)
                if os.path.isfile(f_path) and not f.endswith(('.crdownload', '.part', '.tmp', '.download')):
                    current_files.add(f)
                    # 检测是否是新文件
                    if f not in initial_files:
                        new_file = f_path

            # 新文件判断：要么是新文件，要么文件计数增加
            if len(current_files) > last_file_count:
                # 等待文件下载完成
                timeout_start = time.time()
                while time.time() - timeout_start < DOWNLOAD_TIMEOUT:
                    if os.path.exists(new_file) and os.path.getsize(new_file) >= FILE_MIN_SIZE:
                        print(f"📥 新文件下载成功：{os.path.basename(new_file)}（{os.path.getsize(new_file)/1024:.1f}KB）")
                        return (True, offset)
                    time.sleep(1)
            elif new_file:
                # 处理已存在但被覆盖的文件
                if os.path.getsize(new_file) >= FILE_MIN_SIZE:
                    print(f"📥 文件更新成功：{os.path.basename(new_file)}（{os.path.getsize(new_file)/1024:.1f}KB）")
                    return (True, offset)

        except Exception as e:
            print(f"⚠️  尝试{attempt+1}失败：{str(e)}")

        attempt += 1
        time.sleep(0.8)  # 延长重试间隔

    return (False, 0)


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
    global system_scaling, is_running
    system_scaling = get_system_scaling()
    print("=" * 80)
    print(f"📌 知网下载器（页面{CURRENT_PAGE_TYPE}模式）")
    print(f"📌 屏幕分辨率：{screen_size[0]}x{screen_size[1]} | 系统缩放：{system_scaling:.1f}x")
    print(f"📌 预期按钮数量：{TARGET_BUTTON_COUNT}个 | 置信度：{CONFIDENCE}")
    print("✅ 快捷键：ESC=停止 | 空格=暂停/继续")
    print("=" * 80)

    # 初始化
    init_download_path()
    template, template_size = load_template()
    print(f"✅ 加载模板：{template_size[0]}x{template_size[1]}px")

    # 选择区域
    print("\n📌 请框选下载按钮区域（按ESC确认）")
    while not saved_region:
        if select_region():
            break
        print("⚠️  区域选择失败，请重新尝试")
        time.sleep(2)

    # 启动键盘监听
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()
    print("\n✅ 开始识别按钮...")

    try:
        buttons = find_buttons(template, template_size)
        if not buttons:
            print("❌ 未识别到按钮，终止")
            return

        # 执行下载逻辑
        print(f"\n🚀 启动页面{CURRENT_PAGE_TYPE}下载（{len(buttons)}个按钮）")
        if CURRENT_PAGE_TYPE == 1:
            download_page1(buttons)
        else:
            download_page2()

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
        print(f"📊 统计：处理{len(buttons) if 'buttons' in locals() else 0}个按钮 | 成功{downloaded_total}个")
        print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  用户手动中断")
        if os.path.exists(SCREENSHOT_PATH):
            os.remove(SCREENSHOT_PATH)
        print(f"📊 成功下载{downloaded_total}个文件")