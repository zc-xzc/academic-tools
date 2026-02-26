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
TARGET_BUTTON_COUNT = 10  # 每页预期按钮数量（用户指定）
DOWNLOAD_PATH = r"D:\Downloads"
CONFIDENCE = 0.45  # 置信度，减少误识别
SCREENSHOT_PATH = "temp_screenshot.png"
FILE_MIN_SIZE = 1024  # 最小文件大小阈值
DOWNLOAD_TIMEOUT = 20  # 下载超时时间（秒）
PAGE_TURN_DELAY = random.uniform(3, 5)  # 翻页后等待时间
PAGE_STAY_TIMEOUT = 5  # 页面停留超时时间（秒）

# 按钮识别与偏移配置
BASE_SPACING_OFFSET = 3  # 基础间距补偿（固定+3像素）
BUTTON1_OFFSETS = [0, 2, -2, 4, -4, 6, -6]  # 按钮1偏移策略：0、±2、±4、±6（双边推进）
BUTTON2_OFFSET_STEP = 4  # 按钮2及以后偏移步长（4像素）

# 全局状态变量（全局暂停控制）
is_running = True  # 程序是否运行
is_paused = False  # 全局暂停标志
downloaded_total = 0
screen_size = pyautogui.size()
system_scaling = 1.0
saved_region = None  # 框选区域（所有页面共用）
current_buttons = []  # 存储当前页成功下载的按钮数据 [(x, y, actual_offset), ...]
current_page = 1  # 当前页码计数
last_action_time = time.time()  # 记录最后一次操作时间（用于超时检测）

# 快捷键配置（修改为 Ctrl+Shift+P 避免与浏览器打印冲突）
PAUSE_HOTKEY = {
    'ctrl': True,
    'shift': True,
    'key': 'p'
}
STOP_HOTKEY = keyboard.Key.esc  # ESC键停止程序

# 用于跟踪按键状态
current_keys = set()


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


def check_page_stay_timeout():
    """检查页面是否停留超时（超过PAGE_STAY_TIMEOUT秒无操作）"""
    global last_action_time
    if time.time() - last_action_time > PAGE_STAY_TIMEOUT:
        print(f"⚠️  页面停留超过{PAGE_STAY_TIMEOUT}秒，执行关闭并返回操作")
        # 模拟关闭当前页面（根据实际场景调整快捷键，此处假设Esc关闭）
        pyautogui.press('esc')
        time.sleep(1)
        # 返回原下载区域（点击框选区域中心，确保回到原页面）
        if saved_region:
            x1, y1, x2, y2 = saved_region
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2
            pyautogui.moveTo(center_x, center_y, duration=0.5)
            pyautogui.click()
            time.sleep(1)
        last_action_time = time.time()  # 重置计时
        return True
    return False


# ==================== 区域选择 ====================
def select_region():
    """让用户框选下载按钮所在区域（所有页面共用此区域）"""
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
    """识别按钮并去重，所有页面都使用同一框选区域进行比对"""
    global last_action_time
    last_action_time = time.time()  # 更新操作时间
    if not saved_region:
        return []
    x1, y1, x2, y2 = saved_region
    t_h, t_w = template_size  # 模板尺寸（按钮尺寸）

    if not take_screenshot():
        return []

    img = cv2.imread(SCREENSHOT_PATH)
    roi = img[y1:y2, x1:x2]  # 截取用户框选的区域（所有页面共用）
    roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(roi_gray, template, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= CONFIDENCE)  # 筛选置信度达标的位置

    buttons = []
    for pt in zip(*locations[::-1]):
        # 计算按钮中心坐标（转换为全局坐标）
        center_x = x1 + pt[0] + t_w // 2
        center_y = y1 + pt[1] + t_h // 2
        buttons.append((center_x, center_y))

    # 按Y坐标排序（从上到下）
    buttons = sorted(buttons, key=lambda x: x[1])
    unique_buttons = []
    min_spacing = t_h  # 最小间距设为按钮高度（避免重复识别）
    for btn in buttons:
        if not unique_buttons:
            unique_buttons.append(btn)
        else:
            last_y = unique_buttons[-1][1]
            if btn[1] - last_y >= min_spacing:  # 超过按钮高度视为新按钮
                unique_buttons.append(btn)

    # 截取前TARGET_BUTTON_COUNT个按钮
    if len(unique_buttons) > TARGET_BUTTON_COUNT:
        unique_buttons = unique_buttons[:TARGET_BUTTON_COUNT]
        print(f"⚠️  识别到{len(buttons)}个按钮，自动截取前{TARGET_BUTTON_COUNT}个")
    elif len(unique_buttons) < TARGET_BUTTON_COUNT:
        print(f"⚠️  识别到{len(unique_buttons)}个按钮，少于预期的{TARGET_BUTTON_COUNT}个")

    # 打印识别结果
    print(f"📌 最终识别到{len(unique_buttons)}个有效按钮")
    for i, (x, y) in enumerate(unique_buttons, 1):
        print(f"   按钮{i}：({x:.0f}, {y:.0f})")
    return unique_buttons


# ==================== 页面下载逻辑（所有页面共用） ====================
def download_page(buttons):
    """页面下载逻辑（所有页面共用同一逻辑）"""
    global downloaded_total, current_buttons, last_action_time
    current_buttons = []  # 重置当前页成功下载的按钮数据
    if len(buttons) == 0:
        print("❌ 未识别到任何按钮，终止下载")
        return False

    # 计算初始间距（相邻按钮的Y轴差值）
    initial_spacings = []
    for i in range(1, len(buttons)):
        spacing = buttons[i][1] - buttons[i - 1][1]
        initial_spacings.append(spacing)
        print(f"📏 按钮{i}与按钮{i + 1}初始间距：{spacing:.0f}px（补偿+{BASE_SPACING_OFFSET}px）")

    # 逐个处理按钮
    for idx in range(len(buttons)):
        # 检查程序是否运行
        if not is_running:
            break

        # 全局暂停检测（在每个关键步骤都检查）
        while is_paused:
            print("⏸️  程序已暂停，按 Ctrl+Shift+P 继续...")
            time.sleep(1)

        # 检查页面停留超时
        if check_page_stay_timeout():
            print("🔄 超时后重新尝试当前按钮")

        base_x, base_y = buttons[idx]
        actual_offset = 0
        success = False
        print(f"\n📥 第{current_page}页 按钮{idx + 1}（基准坐标：{base_x:.0f},{base_y:.0f}）")
        last_action_time = time.time()  # 更新操作时间

        # 计算目标Y坐标（已知距离+3px补偿）
        if idx == 0:
            # 按钮1：使用基准坐标
            target_y = base_y
        else:
            # 前一个按钮成功时才承接偏移
            if len(current_buttons) != idx:
                print(f"❌ 前一个按钮（按钮{idx}）下载失败，终止后续处理")
                break
            prev_btn = current_buttons[idx - 1]
            prev_final_y = prev_btn[1] + prev_btn[2]
            # 目标Y = 前一个最终Y + 初始间距 + 3px补偿
            target_y = prev_final_y + initial_spacings[idx - 1] + BASE_SPACING_OFFSET

        # 校验坐标有效性
        if not is_valid_coordinate(base_x, target_y):
            print(f"⚠️  目标坐标({base_x:.0f},{target_y:.0f})超出屏幕范围，跳过")
            continue

        # 定义偏移策略（按钮2及以后：0、4、-4、8、-8...）
        def offset_strategy(i):
            if idx == 0:
                # 按钮1：使用预设的双边推进序列
                if i < len(BUTTON1_OFFSETS):
                    return BUTTON1_OFFSETS[i]
                else:
                    # 序列用尽后继续按±2递增（如8,-8,10,-10...）
                    step = (i - len(BUTTON1_OFFSETS) + 1) * 2 + 6
                    return step if i % 2 == 0 else -step
            else:
                # 按钮2及以后：0、4、-4、8、-8...
                if i == 0:
                    return 0
                else:
                    # i=1→4, i=2→-4, i=3→8, i=4→-8...
                    step = ((i + 1) // 2) * BUTTON2_OFFSET_STEP
                    return step if i % 2 == 1 else -step

        # 尝试点击
        success, actual_offset = try_click(base_x, target_y, offset_strategy)

        if success:
            downloaded_total += 1
            current_buttons.append((base_x, target_y, actual_offset))
            print(f"✅ 按钮{idx + 1}下载成功（实际偏移：{actual_offset}px）")
            time.sleep(random.uniform(1.5, 2.5))
        else:
            print(f"❌ 按钮{idx + 1}下载失败")
            if idx == 0:  # 按钮1失败则终止后续
                print("❌ 按钮1下载失败，无法继续处理")
                break

    return len(current_buttons) == TARGET_BUTTON_COUNT


# ==================== 通用点击尝试函数 ====================
def try_click(base_x, base_y, offset_strategy):
    """尝试点击并检测下载是否成功，包含超时检查"""
    global last_action_time
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
        # 全局暂停检测（点击尝试中也需要响应暂停）
        while is_paused:
            print("⏸️  程序已暂停，按 Ctrl+Shift+P 继续...")
            time.sleep(1)

        # 检查页面停留超时
        if check_page_stay_timeout():
            print(f"🔄 重试尝试{attempt + 1}")

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
            print(f"⚠️  尝试{attempt + 1}：坐标({click_x},{click_y})超出屏幕，跳过")
            attempt += 1
            continue

        # 执行点击
        try:
            print(f"📝 尝试{attempt + 1}：点击({click_x},{click_y})（偏移：{offset}px）")
            pyautogui.moveTo(click_x, click_y, duration=random.uniform(0.3, 0.6))
            pyautogui.click()
            last_action_time = time.time()  # 更新操作时间
            time.sleep(2)  # 等待点击响应

            # 检测新文件
            current_files = set()
            new_file = None
            for f in os.listdir(DOWNLOAD_PATH):
                f_path = os.path.join(DOWNLOAD_PATH, f)
                if os.path.isfile(f_path) and not f.endswith(('.crdownload', '.part', '.tmp', '.download')):
                    current_files.add(f)
                    if f not in initial_files:
                        new_file = f_path

            # 新文件判断
            if len(current_files) > last_file_count:
                # 等待文件下载完成
                timeout_start = time.time()
                while time.time() - timeout_start < DOWNLOAD_TIMEOUT:
                    # 暂停检测
                    while is_paused:
                        print("⏸️  程序已暂停，按 Ctrl+Shift+P 继续...")
                        time.sleep(1)

                    if check_page_stay_timeout():
                        continue  # 超时处理后继续等待
                    if os.path.exists(new_file) and os.path.getsize(new_file) >= FILE_MIN_SIZE:
                        print(
                            f"📥 新文件下载成功：{os.path.basename(new_file)}（{os.path.getsize(new_file) / 1024:.1f}KB）")
                        return (True, offset)
                    time.sleep(1)
            elif new_file and os.path.getsize(new_file) >= FILE_MIN_SIZE:
                # 处理覆盖文件
                print(f"📥 文件更新成功：{os.path.basename(new_file)}（{os.path.getsize(new_file) / 1024:.1f}KB）")
                return (True, offset)

        except Exception as e:
            print(f"⚠️  尝试{attempt + 1}失败：{str(e)}")

        attempt += 1
        time.sleep(0.8)

    return (False, 0)


# ==================== 翻页功能 ====================
def turn_page():
    """执行翻页操作（按右键），包含超时检查"""
    global current_page, last_action_time
    if not is_running:
        return False
    try:
        # 暂停检测
        while is_paused:
            print("⏸️  程序已暂停，按 Ctrl+Shift+P 继续...")
            time.sleep(1)

        print(f"\n📖 准备翻到第{current_page + 1}页...")
        pyautogui.press('right')  # 模拟右键翻页
        last_action_time = time.time()  # 更新操作时间
        print(f"✅ 已发送翻页指令，等待页面加载{PAGE_TURN_DELAY:.1f}秒...")
        # 等待期间检查超时和暂停
        start_wait = time.time()
        while time.time() - start_wait < PAGE_TURN_DELAY:
            # 暂停检测
            while is_paused:
                print("⏸️  程序已暂停，按 Ctrl+Shift+P 继续...")
                time.sleep(1)

            if check_page_stay_timeout():
                # 超时后重新等待剩余时间
                start_wait = time.time()
            time.sleep(0.5)
        current_page += 1
        return True
    except Exception as e:
        print(f"❌ 翻页失败：{str(e)}")
        return False


# ==================== 键盘控制（优化快捷键检测） ====================
def on_key_press(key):
    """键盘按下事件处理"""
    global current_keys
    try:
        # 将按键添加到当前按键集合
        if hasattr(key, 'char') and key.char:
            current_keys.add(key.char.lower())
        elif key in [keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r]:
            current_keys.add('ctrl')
        elif key in [keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r]:
            current_keys.add('shift')
        elif key == keyboard.Key.alt:
            current_keys.add('alt')

        # 检查暂停快捷键（Ctrl+Shift+P）
        check_pause_hotkey()

        # 检查停止快捷键（ESC）
        if key == STOP_HOTKEY:
            print("\n⚠️  检测到ESC键，停止任务...")
            global is_running
            is_running = False
            return False

    except Exception as e:
        print(f"⚠️  键盘监听错误：{str(e)}")


def on_key_release(key):
    """键盘释放事件处理"""
    global current_keys
    try:
        # 从当前按键集合中移除按键
        if hasattr(key, 'char') and key.char:
            current_keys.discard(key.char.lower())
        elif key in [keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r]:
            current_keys.discard('ctrl')
        elif key in [keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r]:
            current_keys.discard('shift')
        elif key == keyboard.Key.alt:
            current_keys.discard('alt')
    except Exception as e:
        print(f"⚠️  键盘释放处理错误：{str(e)}")


def check_pause_hotkey():
    """检查是否按下了暂停快捷键组合"""
    global is_paused, last_action_time
    # 检查是否同时按下了所有必要的键
    required_keys = set()
    if PAUSE_HOTKEY['ctrl']:
        required_keys.add('ctrl')
    if PAUSE_HOTKEY['shift']:
        required_keys.add('shift')
    required_keys.add(PAUSE_HOTKEY['key'].lower())

    # 检查所有必要键是否都在当前按下的键集合中
    if required_keys.issubset(current_keys):
        # 切换暂停状态
        is_paused = not is_paused
        last_action_time = time.time()  # 暂停/继续时更新计时
        print(f"\n{'⏸️  任务暂停' if is_paused else '▶️  任务继续'}")
        # 短暂延迟避免重复触发
        time.sleep(0.3)


# ==================== 主程序 ====================
def main():
    global system_scaling, is_running, current_page, last_action_time
    system_scaling = get_system_scaling()
    print("=" * 80)
    print(f"📌 下载器（所有页面共用同一识别区域）")
    print(f"📌 屏幕分辨率：{screen_size[0]}x{screen_size[1]} | 系统缩放：{system_scaling:.1f}x")
    print(f"📌 预期按钮数量：{TARGET_BUTTON_COUNT}个 | 置信度：{CONFIDENCE}")
    print(f"📌 页面停留超时：{PAGE_STAY_TIMEOUT}秒")
    # 显示快捷键信息
    hotkey_str = "Ctrl+Shift+P"
    print(f"✅ 快捷键：ESC=停止 | {hotkey_str}=暂停/继续")
    print("⚠️  提示：使用组合快捷键可避免与浏览器默认功能冲突")
    print("=" * 80)

    # 初始化
    init_download_path()
    template, template_size = load_template()
    print(f"✅ 加载模板：{template_size[0]}x{template_size[1]}px")

    # 选择区域（所有页面共用此区域）
    print("\n📌 请框选下载按钮区域（按ESC确认）")
    while not saved_region:
        if select_region():
            break
        print("⚠️  区域选择失败，请重新尝试")
        time.sleep(2)

    # 启动键盘监听（同时监听按下和释放事件）
    listener = keyboard.Listener(
        on_press=on_key_press,
        on_release=on_key_release
    )
    listener.start()
    print("\n✅ 开始识别按钮...")
    last_action_time = time.time()  # 初始化操作时间

    try:
        # 循环执行：下载当前页→翻页→下载下一页
        while is_running:
            # 全局暂停检测
            while is_paused:
                print("⏸️  程序已暂停，按 Ctrl+Shift+P 继续...")
                time.sleep(1)

            buttons = find_buttons(template, template_size)
            if not buttons:
                print("❌ 未识别到按钮，终止循环")
                break

            # 执行当前页下载
            print(f"\n🚀 启动第{current_page}页下载（{len(buttons)}个按钮）")
            page_download_success = download_page(buttons)

            # 翻页逻辑
            if page_download_success and is_running:
                if not turn_page():
                    print("⚠️  翻页失败，终止循环")
                    break
            else:
                print(f"⚠️  第{current_page}页未完成所有按钮下载，终止循环")
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
        print(f"📊 统计：共处理{current_page}页 | 成功下载{downloaded_total}个文件")
        print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  用户手动中断")
        if os.path.exists(SCREENSHOT_PATH):
            os.remove(SCREENSHOT_PATH)
        print(f"📊 成功下载{downloaded_total}个文件")