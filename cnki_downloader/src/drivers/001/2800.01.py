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
TARGET_BUTTONS = 10  # 每页目标下载数
DOWNLOAD_PATH = r"D:\Downloads"
CONFIDENCE = 0.25  # 匹配置信度
BUTTON_DUPLICATE_DISTANCE = 50  # 按钮去重距离
SCREENSHOT_PATH = "full_screen.png"
MATCH_VISUALIZATION_PATH = "match_result.png"
TEMPLATE_PATH = "download_icon.png"  # 下载按钮模板
FILE_MIN_SIZE = 1024
# Y轴偏移量（按您要求的3,5,7...19像素，用于解决定位不准）
Y_OFFSETS = [3, 5, 7, 9, 11, 13, 15, 19, -3, -5, -7]  # 包含正负偏移，覆盖上下偏差

# 颜色过滤（知网浅蓝色按钮）
LOWER_BLUE = np.array([90, 40, 80])
UPPER_BLUE = np.array([120, 200, 255])

# 时间设置
MOVE_DURATION = (0.2, 0.5)
CLICK_DELAY = (0.2, 0.4)
DOWNLOAD_INTERVAL = (1.0, 1.5)
PAGE_TURN_DELAY = 4.0
DOWNLOAD_TIMEOUT = 10

# 全局状态
is_running = True
is_paused = False
downloaded_total = 0
current_page = 1
screen_size = pyautogui.size()
scaling_factor = 1.0
button_region = None
template = None
fixed_x = None  # 固定的X轴坐标（程序启动后确定）


# ==================== 高DPI适配 ====================
def get_scaling_factor():
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    physical = (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    logical = (screen_size[0], screen_size[1])
    scaling = round(logical[0] / physical[0], 2)
    print(f"✅ 系统缩放：{scaling * 100}%（物理：{physical}，逻辑：{logical}）")
    return scaling


# ==================== 图像工具函数 ====================
def take_screenshot():
    try:
        screen = ImageGrab.grab(bbox=(0, 0, screen_size[0], screen_size[1]))
        screen.save(SCREENSHOT_PATH)
        return os.path.getsize(SCREENSHOT_PATH) > 102400
    except Exception as e:
        print(f"❌ 截图失败：{str(e)}")
        return False


def load_download_template():
    global template
    if not os.path.exists(TEMPLATE_PATH):
        print(f"❌ 未找到模板文件：{TEMPLATE_PATH}")
        exit(1)
    template = cv2.imread(TEMPLATE_PATH, cv2.IMREAD_COLOR)
    if template is None:
        print(f"❌ 无法加载模板文件：{TEMPLATE_PATH}")
        exit(1)
    print(f"✅ 加载下载按钮模板：{TEMPLATE_PATH}（尺寸：{template.shape[1]}x{template.shape[0]}）")
    return template


# ==================== 区域选择（确定固定X轴坐标） ====================
def select_button_region():
    global button_region, fixed_x
    while not take_screenshot():
        print("🔄 重新尝试截图...")
        time.sleep(1)

    img = cv2.imread(SCREENSHOT_PATH)
    img_copy = img.copy()
    img_h, img_w = img.shape[:2]
    ref_point = []
    cropping = False

    # 提示框选信息
    cv2.putText(img_copy, "框选下载按钮所在列（宽度稍宽，确保包含X轴中心）", (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    cv2.putText(img_copy, "程序将自动提取X轴坐标，后续下载均使用此X轴", (30, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    def click_event(event, x, y, flags, param):
        nonlocal ref_point, cropping
        if event == cv2.EVENT_LBUTTONDOWN:
            ref_point = [(x, y)]
            cropping = True
        elif event == cv2.EVENT_LBUTTONUP:
            ref_point.append((x, y))
            cropping = False
            cv2.rectangle(img_copy, ref_point[0], ref_point[1], (0, 255, 0), 3)
            cv2.imshow("选择下载按钮区域", img_copy)
        elif event == cv2.EVENT_MOUSEMOVE and cropping:
            temp_img = img_copy.copy()
            cv2.rectangle(temp_img, ref_point[0], (x, y), (0, 255, 0), 2)
            cv2.imshow("选择下载按钮区域", temp_img)

    cv2.namedWindow("选择下载按钮区域", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("选择下载按钮区域", img_w // 2, img_h // 2)
    cv2.imshow("选择下载按钮区域", img_copy)
    cv2.setMouseCallback("选择下载按钮区域", click_event)

    while cv2.waitKey(1) != 27:
        pass
    cv2.destroyAllWindows()

    if len(ref_point) == 2:
        x1 = min(ref_point[0][0], ref_point[1][0])
        y1 = min(ref_point[0][1], ref_point[1][1])
        x2 = max(ref_point[0][0], ref_point[1][0])
        y2 = max(ref_point[0][1], ref_point[1][1])
        button_region = (x1, y1, x2, y2)
        # 计算固定X轴坐标（区域中心X，后续所有下载均使用此X）
        fixed_x = (x1 + x2) // 2
        print(f"✅ 已选择下载按钮区域：({x1},{y1}) 到 ({x2},{y2})")
        print(f"📌 固定下载按钮X轴坐标：{fixed_x}（后续下载均使用此X轴）")
        return True
    else:
        print("❌ 区域选择失败，请重新尝试")
        return False


# ==================== 按钮识别（固定X轴，优化Y轴定位） ====================
def find_buttons_in_region():
    if not button_region or template is None or fixed_x is None:
        return None

    x1, y1, x2, y2 = button_region
    roi_width = x2 - x1
    roi_height = y2 - y1
    template_height, template_width = template.shape[:2]

    # 检查区域宽度是否足够（允许稍窄，因为X轴已固定）
    if roi_width < template_width // 2:  # 放宽条件，只要区域宽度≥模板一半即可（因X轴固定）
        print(f"❌ 框选区域过窄（{roi_width}像素），至少需要{template_width // 2}像素")
        return []

    if not take_screenshot():
        return None

    # 读取截图并提取ROI
    img = cv2.imread(SCREENSHOT_PATH)
    roi = img[y1:y2, x1:x2]
    roi_copy = roi.copy()

    # 颜色过滤
    hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv_roi, LOWER_BLUE, UPPER_BLUE)
    blue_roi = cv2.bitwise_and(roi, roi, mask=mask)
    gray_roi = cv2.cvtColor(blue_roi, cv2.COLOR_BGR2GRAY)

    # 模板预处理
    hsv_template = cv2.cvtColor(template, cv2.COLOR_BGR2HSV)
    template_mask = cv2.inRange(hsv_template, LOWER_BLUE, UPPER_BLUE)
    blue_template = cv2.bitwise_and(template, template, mask=template_mask)
    gray_template = cv2.cvtColor(blue_template, cv2.COLOR_BGR2GRAY)

    # 保存调试图片
    cv2.imwrite("debug_roi.png", gray_roi)
    cv2.imwrite("debug_template.png", gray_template)
    print("📌 调试图片已保存：debug_roi.png、debug_template.png")

    # 多尺度匹配（重点：固定X轴，主要优化Y轴识别）
    buttons = []
    for scale in [0.8, 0.9, 1.0, 1.1, 1.2]:
        scaled_template = cv2.resize(
            gray_template,
            (int(template_width * scale), int(template_height * scale)),
            interpolation=cv2.INTER_AREA
        )
        st_height, st_width = scaled_template.shape[:2]
        if st_width > roi_width or st_height > roi_height:
            continue

        result = cv2.matchTemplate(gray_roi, scaled_template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= CONFIDENCE)

        for pt in zip(*locations[::-1]):
            # 计算Y轴坐标（X轴固定为fixed_x）
            center_y_roi = pt[1] + st_height // 2  # ROI内的Y坐标
            center_y = y1 + center_y_roi  # 转换为屏幕Y坐标
            buttons.append((fixed_x, center_y))  # X轴固定，只存Y轴

            # 标记匹配结果
            cv2.circle(roi_copy, (pt[0] + st_width // 2, center_y_roi), 10, (0, 0, 255), 2)

    # 去重并按Y轴排序
    unique_buttons = []
    for btn in buttons:
        x, y = btn
        duplicate = False
        for ux, uy in unique_buttons:
            if abs(y - uy) < BUTTON_DUPLICATE_DISTANCE:
                duplicate = True
                break
        if not duplicate:
            unique_buttons.append(btn)
    unique_buttons.sort(key=lambda x: x[1])  # 按Y轴从上到下排序

    # 保存匹配可视化结果
    cv2.imwrite(MATCH_VISUALIZATION_PATH, roi_copy)
    print(f"📌 匹配结果已保存：{MATCH_VISUALIZATION_PATH}")

    return unique_buttons


# ==================== 下载逻辑（增加Y轴偏移尝试） ====================
def download_buttons(buttons):
    global downloaded_total
    page_success = 0
    target = min(len(buttons), TARGET_BUTTONS)
    print(f"\n🚀 第{current_page}页开始下载（目标{target}个，X轴固定为{fixed_x}）")

    for idx in range(target):
        if not is_running:
            break
        while is_paused:
            time.sleep(0.5)

        x, y = buttons[idx]
        print(f"📌 第{idx + 1}个按钮（原始坐标：{int(x)},{int(y)}）")

        # 核心优化：尝试多个Y轴偏移量，解决定位不准问题
        click_success = False
        for offset in Y_OFFSETS:
            try_y = y + offset  # 应用Y轴偏移
            print(f"   尝试偏移：{offset}像素 → 坐标：({int(x)},{int(try_y)})")

            # 移动并点击
            pyautogui.moveTo(x, try_y, duration=random.uniform(*MOVE_DURATION))
            time.sleep(random.uniform(*CLICK_DELAY))
            pyautogui.click()

            # 检查是否点击成功（通过下载文件判断）
            initial_files = set(os.listdir(DOWNLOAD_PATH))
            start_time = time.time()
            while time.time() - start_time < 2:  # 短时间检测是否触发下载
                current_files = set(os.listdir(DOWNLOAD_PATH))
                new_files = [f for f in (current_files - initial_files) if f.endswith(('.crdownload', '.part'))]
                if new_files:  # 检测到临时文件，说明点击成功
                    click_success = True
                    break
            if click_success:
                break  # 找到正确偏移，退出偏移尝试

        # 等待下载完成
        if click_success:
            initial_files = set(os.listdir(DOWNLOAD_PATH))
            start_time = time.time()
            success = False
            while time.time() - start_time < DOWNLOAD_TIMEOUT:
                current_files = set(os.listdir(DOWNLOAD_PATH))
                new_files = [
                    f for f in (current_files - initial_files)
                    if not any(f.endswith(ext) for ext in ('.crdownload', '.part', '.tmp'))
                ]
                if new_files:
                    new_file = new_files[0]
                    file_path = os.path.join(DOWNLOAD_PATH, new_file)
                    time.sleep(1)
                    if os.path.getsize(file_path) > FILE_MIN_SIZE:
                        print(f"✅ 下载成功：{new_file}")
                        downloaded_total += 1
                        page_success += 1
                        success = True
                        break
                time.sleep(0.5)
            if not success:
                print(f"❌ 偏移尝试成功，但下载超时")
        else:
            print(f"❌ 所有偏移尝试均失败，未触发下载")

        time.sleep(random.uniform(*DOWNLOAD_INTERVAL))

    print(f"📊 第{current_page}页下载统计：成功{page_success}/{target}个")
    return page_success


# ==================== 翻页与键盘控制 ====================
def turn_to_next_page():
    global current_page
    print(f"\n📑 准备翻到第{current_page + 1}页")
    pyautogui.moveTo(fixed_x, screen_size[1] // 2, duration=0.5)  # 基于固定X轴定位页面
    pyautogui.click()
    time.sleep(1)
    pyautogui.press('right')
    time.sleep(PAGE_TURN_DELAY)
    current_page += 1
    print(f"✅ 已翻到第{current_page}页")
    return True


def on_key_press(key):
    global is_running, is_paused
    try:
        if key == keyboard.Key.esc:
            print("\n⚠️ 接收到停止信号")
            is_running = False
            return False
        elif key == keyboard.Key.space:
            is_paused = not is_paused
            print(f"\n{'⏸️ 已暂停' if is_paused else '▶️ 继续下载'}")
    except:
        pass


# ==================== 主程序 ====================
def main():
    global scaling_factor, template
    print("=" * 80)
    print("📌 知网下载按钮自动识别下载器（固定X轴+Y偏移版）")
    print("✅ 功能：固定X轴坐标 + Y轴多偏移尝试（3,5,7...19像素）")
    print("✅ 快捷键：ESC=停止 | 空格=暂停/继续")
    print("=" * 80)

    scaling_factor = get_scaling_factor()
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
    print(f"✅ 下载路径：{DOWNLOAD_PATH}")

    template = load_download_template()

    print("\n请框选下载按钮所在的列（宽度稍宽，确保包含按钮中心）")
    while not select_button_region():
        print("🔄 请重新选择区域...")
        time.sleep(1)

    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()

    try:
        while is_running:
            buttons = find_buttons_in_region()

            if not buttons or len(buttons) < TARGET_BUTTONS:
                print(f"⚠️ 第{current_page}页未找到足够的按钮（{len(buttons) if buttons else 0}/{TARGET_BUTTONS}）")
                if input("是否继续到下一页？(y/n) ").lower() != 'y':
                    break

            print(f"📄 第{current_page}页识别到{len(buttons)}个按钮（均使用X轴：{fixed_x}）")
            success_count = download_buttons(buttons)

            if success_count != TARGET_BUTTONS:
                print(f"⚠️ 第{current_page}页下载数量不匹配（预期{TARGET_BUTTONS}，实际{success_count}）")
                if input("是否继续到下一页？(y/n) ").lower() != 'y':
                    break

            turn_to_next_page()

    finally:
        listener.stop()
        for f in [SCREENSHOT_PATH, MATCH_VISUALIZATION_PATH]:
            if os.path.exists(f):
                os.remove(f)
        print("\n" + "=" * 70)
        print(f"🎉 下载任务结束")
        print(f"📊 总页数：{current_page}页")
        print(f"📊 总下载文件数：{downloaded_total}个")
        print(f"📁 下载路径：{DOWNLOAD_PATH}")
        print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ 用户手动中断")
        print(f"📊 总下载文件数：{downloaded_total}个")