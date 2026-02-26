import pyautogui
import time
import random
import os
import cv2
import numpy as np
from PIL import ImageGrab
from pathlib import Path
import ctypes

# ==================== 核心配置 ====================
TARGET_BUTTONS = 10  # 每页目标下载数
DOWNLOAD_PATH = r"D:\Downloads"  # 下载路径
CONFIDENCE = 0.3  # 匹配置信度
BUTTON_DUPLICATE_DISTANCE = 30  # 按钮去重距离
SCREENSHOT_PATH = "full_screen.png"
TEMPLATE_PATH = "download_icon.png"  # 下载按钮模板
FILE_MIN_SIZE = 1024  # 最小文件大小(字节)

# 坐标与偏移配置
MIN_Y_NEXT_PAGE = 300  # 后续页面第一个按钮最小Y坐标
MAX_Y_NEXT_PAGE = 650  # 后续页面第一个按钮最大Y坐标
PER_STEP_ERROR = 5  # 每页内相邻按钮的固定误差（第n个 = 第n-1个 +5）
BASE_OFFSET_STEPS = 2  # 基础偏移步长（失败后递增2、4、6...）
MAX_ATTEMPTS_PER_BUTTON = 10  # 单个按钮最大尝试次数

# 时间设置
MOVE_DURATION = (0.2, 0.5)
CLICK_DELAY = (0.2, 0.4)
DOWNLOAD_INTERVAL = (1.0, 1.5)
PAGE_TURN_DELAY = 2.0  # 翻页后等待时间
DOWNLOAD_TIMEOUT = 15  # 单个文件下载超时时间

# 全局状态
is_running = True
downloaded_total = 0
current_page = 1
screen_size = pyautogui.size()
scaling_factor = 1.0
button_region = None
template = None
fixed_x = None  # 固定X轴坐标（全程不变）


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
        return os.path.getsize(SCREENSHOT_PATH) > 102400  # 确保截图有效
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


# ==================== 区域选择 ====================
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

    cv2.putText(img_copy, "框选下载按钮所在列（宽度约30像素）", (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    cv2.putText(img_copy, "框选后按ESC键确认", (30, 100),
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
        fixed_x = (x1 + x2) // 2  # 固定X轴坐标（全程不变）
        print(f"✅ 已选择下载按钮区域：({x1},{y1}) 到 ({x2},{y2})")
        print(f"📌 固定X轴坐标：{fixed_x}（所有页面共用）")
        return True
    else:
        print("❌ 区域选择失败，请重新尝试")
        return False


# ==================== 按钮识别与坐标调整 ====================
def find_buttons_in_region():
    """识别当前页按钮，并按规则调整坐标（第n个 = 第n-1个 +5像素）"""
    if not button_region or template is None or fixed_x is None:
        return None

    x1, y1, x2, y2 = button_region
    roi_width = x2 - x1
    roi_height = y2 - y1
    template_height, template_width = template.shape[:2]

    if roi_width < template_width // 2:
        print(f"❌ 框选区域过窄（{roi_width}像素），至少需要{template_width // 2}像素")
        return []

    if not take_screenshot():
        return None

    # 图像识别（适配知网蓝色按钮）
    img = cv2.imread(SCREENSHOT_PATH)
    roi = img[y1:y2, x1:x2]
    hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lower_blue = np.array([90, 40, 80])
    upper_blue = np.array([120, 200, 255])
    mask = cv2.inRange(hsv_roi, lower_blue, upper_blue)
    blue_roi = cv2.bitwise_and(roi, roi, mask=mask)
    gray_roi = cv2.cvtColor(blue_roi, cv2.COLOR_BGR2GRAY)

    hsv_template = cv2.cvtColor(template, cv2.COLOR_BGR2HSV)
    template_mask = cv2.inRange(hsv_template, lower_blue, upper_blue)
    blue_template = cv2.bitwise_and(template, template, mask=template_mask)
    gray_template = cv2.cvtColor(blue_template, cv2.COLOR_BGR2GRAY)

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
            center_y_roi = pt[1] + st_height // 2
            center_y = y1 + center_y_roi  # 原始识别的Y坐标
            buttons.append((fixed_x, center_y))  # X固定为全局值

    # 去重并按Y轴排序（从上到下）
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
    unique_buttons.sort(key=lambda x: x[1])

    # 核心：调整坐标（第1个不变，第n个 = 第n-1个 +5像素）
    if len(unique_buttons) >= 2:
        adjusted_buttons = [unique_buttons[0]]  # 第一个按钮保持原始坐标
        for i in range(1, len(unique_buttons)):
            prev_x, prev_y = adjusted_buttons[i - 1]
            # 当前按钮Y坐标 = 上一个按钮Y坐标 +5（固定误差）
            current_y = prev_y + PER_STEP_ERROR
            adjusted_buttons.append((prev_x, current_y))
        unique_buttons = adjusted_buttons
        print(f"📌 坐标调整完成：第2个及以后按钮比前一个+{PER_STEP_ERROR}像素")

    # 过滤后续页面第一个按钮的Y范围
    if current_page > 1 and unique_buttons:
        first_y = unique_buttons[0][1]
        if not (MIN_Y_NEXT_PAGE <= first_y <= MAX_Y_NEXT_PAGE):
            print(f"⚠️ 第一个按钮Y坐标({first_y})超出范围[{MIN_Y_NEXT_PAGE},{MAX_Y_NEXT_PAGE}]，可能识别错误")

    print(f"📌 第{current_page}页匹配到{len(unique_buttons)}个下载按钮")
    return unique_buttons


# ==================== 下载逻辑（每页独立偏移计算） ====================
def download_buttons(buttons):
    """下载当前页按钮，偏移量规则：失败后从2开始，每页重新计算（2→4→6...）"""
    global downloaded_total
    page_success = 0
    target = min(len(buttons), TARGET_BUTTONS)
    print(f"\n🚀 第{current_page}页开始下载（目标{target}个，X轴={fixed_x}）")

    for idx in range(target):
        if not is_running:
            break

        x, y = buttons[idx]
        print(f"📌 第{idx + 1}个按钮（调整后坐标：{int(x)},{int(y)}）")

        # 核心：偏移量从2开始，每次+2（每页独立计算，不继承上一页）
        click_success = False
        offset_step = 0  # 记录当前是第几步偏移（0→2→4→...）

        while offset_step < MAX_ATTEMPTS_PER_BUTTON:
            # 计算当前偏移量（第1次尝试0，失败后2、4、6...）
            current_offset = offset_step * BASE_OFFSET_STEPS
            try_y = y + current_offset  # 应用偏移
            print(f"   尝试偏移：{current_offset}像素 → 坐标：({int(x)},{int(try_y)})")

            # 移动并点击
            pyautogui.moveTo(x, try_y, duration=random.uniform(*MOVE_DURATION))
            time.sleep(random.uniform(*CLICK_DELAY))
            pyautogui.click()

            # 检测是否触发下载（通过临时文件）
            initial_files = set(os.listdir(DOWNLOAD_PATH))
            start_time = time.time()
            while time.time() - start_time < 2:  # 2秒内检测临时文件
                current_files = set(os.listdir(DOWNLOAD_PATH))
                new_files = [f for f in (current_files - initial_files) if f.endswith(('.crdownload', '.part', '.tmp'))]
                if new_files:
                    click_success = True
                    break

            if click_success:
                # 等待下载完成
                start_time = time.time()
                while time.time() - start_time < DOWNLOAD_TIMEOUT:
                    current_files = set(os.listdir(DOWNLOAD_PATH))
                    completed_files = [
                        f for f in (current_files - initial_files)
                        if not f.endswith(('.crdownload', '.part', '.tmp')) and
                           os.path.getsize(os.path.join(DOWNLOAD_PATH, f)) >= FILE_MIN_SIZE
                    ]

                    if completed_files:
                        print(f"✅ 下载成功：{completed_files[0]}")
                        page_success += 1
                        downloaded_total += 1
                        time.sleep(random.uniform(*DOWNLOAD_INTERVAL))
                        break

                    time.sleep(0.5)

                if click_success:
                    break  # 成功后退出当前按钮的偏移尝试

            offset_step += 1  # 下一步偏移（2→4→6...）

        if not click_success:
            print(f"❌ 超过最大尝试次数（{MAX_ATTEMPTS_PER_BUTTON}次），跳过此按钮")

    print(f"📊 第{current_page}页下载完成：成功{page_success}/{target}个")
    return page_success == target


# ==================== 翻页逻辑 ====================
def turn_to_next_page():
    global current_page
    print(f"\n📑 准备翻到第{current_page + 1}页...")

    # 点击页面中间位置确保右键翻页有效
    center_x = screen_size[0] // 2
    center_y = screen_size[1] // 2

    pyautogui.moveTo(center_x, center_y, duration=0.5)
    time.sleep(0.5)
    pyautogui.press('right')  # 右键翻页
    time.sleep(PAGE_TURN_DELAY)  # 等待页面加载

    current_page += 1
    print(f"✅ 已翻到第{current_page}页")
    return True


# ==================== 主程序 ====================
def main():
    global scaling_factor, template

    print("=" * 50)
    print("📂 知网下载自动化工具（每页独立计算模型）")
    print("=" * 50)

    # 初始化
    scaling_factor = get_scaling_factor()
    template = load_download_template()
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)  # 确保下载目录存在

    # 选择下载按钮区域（确定固定X轴）
    if not select_button_region():
        return

    # 循环处理所有页面
    while is_running:
        # 识别当前页按钮并调整坐标
        buttons = find_buttons_in_region()
        if not buttons:
            print("❌ 未找到下载按钮，可能已到达最后一页")
            break

        if len(buttons) < TARGET_BUTTONS:
            print(f"⚠️ 第{current_page}页找到{len(buttons)}个按钮，少于目标数量{TARGET_BUTTONS}个")
            if input("是否继续下载当前页？(y/n)：").lower() != 'y':
                break

        # 下载当前页
        if not download_buttons(buttons):
            print(f"❌ 第{current_page}页下载未完成目标数量")
            if input("是否继续翻页？(y/n)：").lower() != 'y':
                break

        # 翻页（用户中断则停止）
        try:
            turn_to_next_page()
        except KeyboardInterrupt:
            print("\n⚠️ 用户中断翻页")
            break

    print("\n" + "=" * 50)
    print(f"📊 下载完成！总下载数量：{downloaded_total}个")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ 程序被用户中断")
    except Exception as e:
        print(f"\n❌ 程序异常终止：{str(e)}")