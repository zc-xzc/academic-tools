import pyautogui
import time
import random
import os
import cv2
import numpy as np
from PIL import ImageGrab
from pathlib import Path
import ctypes

# ==================== 核心配置（重点调整递进值） ====================
TARGET_BUTTONS = 10  # 每页目标下载数
DOWNLOAD_PATH = r"D:\Downloads"  # 下载路径
CONFIDENCE = 0.4  # 提高匹配置信度，增强定位准确性
BUTTON_DUPLICATE_DISTANCE = 50  # 增大去重距离，避免误判

# 关键调整：第一页相邻按钮递进像素（根据实际页面文献间距设置，通常60-80）
PAGE1_STEP = 70  # 原5像素→70像素（核心修复）

# 其他参数保持不变
NEXT_PAGE_FIRST_STEP = [3, 5, 7, 9, 11]
NEXT_PAGE_BTN_STEP1 = 70  # 后续页基准间距同步调整
NEXT_PAGE_BTN_STEP2 = 20
OFFSET_INCREMENT = 2
MOVE_DURATION = (0.2, 0.5)
CLICK_DELAY = (0.2, 0.4)
DOWNLOAD_INTERVAL = (1.5, 2.0)  # 延长间隔，避免操作过快
DOWNLOAD_TIMEOUT = 20
MAX_ATTEMPTS = 10

# 全局状态
is_running = True
downloaded_total = 0
current_page = 1
screen_size = pyautogui.size()
scaling_factor = 1.0
button_region = None
template = None
template_h, template_w = 0, 0
fixed_x = None
first_page_first_btn = None
last_offset = 0
downloaded_files = set()  # 记录已下载文件名，用于去重


# ==================== 高DPI适配 ====================
def get_scaling_factor():
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    physical = (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    logical = (screen_size[0], screen_size[1])
    scaling = round(logical[0] / physical[0], 2)
    print(f"✅ 系统缩放：{scaling * 100}%（物理：{physical}，逻辑：{logical}）")
    return scaling


# ==================== 图像工具 ====================
def take_screenshot():
    try:
        screen = ImageGrab.grab(bbox=(0, 0, screen_size[0], screen_size[1]))
        screen.save(SCREENSHOT_PATH)
        return os.path.getsize(SCREENSHOT_PATH) > 102400
    except Exception as e:
        print(f"❌ 截图失败：{str(e)}")
        return False


def load_template():
    global template, template_h, template_w
    if not os.path.exists(TEMPLATE_PATH):
        print(f"❌ 未找到模板：{TEMPLATE_PATH}")
        exit(1)
    template = cv2.imread(TEMPLATE_PATH, cv2.IMREAD_COLOR)
    if template is None:
        print(f"❌ 加载模板失败：{TEMPLATE_PATH}")
        exit(1)
    template_h, template_w = template.shape[:2]
    print(f"✅ 加载模板：{TEMPLATE_PATH}（尺寸：{template_w}x{template_h}）")
    return template


# ==================== 区域选择 ====================
def select_region():
    global button_region, fixed_x
    while not take_screenshot():
        print("🔄 重试截图...")
        time.sleep(1)

    img = cv2.imread(SCREENSHOT_PATH)
    img_copy = img.copy()
    img_h, img_w = img.shape[:2]
    ref_point = []
    cropping = False

    cv2.putText(img_copy, f"框选下载按钮列（宽度≥{template_w}，高度≥{template_h}）", (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    cv2.putText(img_copy, "框选后按ESC确认", (30, 100),
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
            cv2.imshow("选择区域", img_copy)
        elif event == cv2.EVENT_MOUSEMOVE and cropping:
            temp = img_copy.copy()
            cv2.rectangle(temp, ref_point[0], (x, y), (0, 255, 0), 2)
            cv2.imshow("选择区域", temp)

    cv2.namedWindow("选择区域", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("选择区域", img_w // 2, img_h // 2)
    cv2.imshow("选择区域", img_copy)
    cv2.setMouseCallback("选择区域", click_event)

    while cv2.waitKey(1) != 27:
        pass
    cv2.destroyAllWindows()

    if len(ref_point) == 2:
        x1, y1 = min(ref_point[0][0], ref_point[1][0]), min(ref_point[0][1], ref_point[1][1])
        x2, y2 = max(ref_point[0][0], ref_point[1][0]), max(ref_point[0][1], ref_point[1][1])
        roi_w = x2 - x1
        roi_h = y2 - y1

        if roi_w < template_w or roi_h < template_h:
            print(f"❌ 框选区域过小（当前{roi_w}x{roi_h}），需≥模板尺寸{template_w}x{template_h}")
            return False

        button_region = (x1, y1, x2, y2)
        fixed_x = (x1 + x2) // 2
        print(f"✅ 框选区域：({x1},{y1})-({x2},{y2})（{roi_w}x{roi_h}），固定X={fixed_x}")
        return True
    else:
        print("❌ 区域选择失败")
        return False


# ==================== 第一页按钮坐标计算（优化定位） ====================
def get_page1_buttons():
    global first_page_first_btn
    if not button_region:
        return []
    x1, y1, x2, y2 = button_region
    roi_w = x2 - x1
    roi_h = y2 - y1

    if roi_w < template_w or roi_h < template_h:
        print(f"❌ 区域尺寸不足（{roi_w}x{roi_h} < {template_w}x{template_h}）")
        return []

    if not os.path.exists(SCREENSHOT_PATH):
        print("❌ 未找到截图文件")
        return []
    img = cv2.imread(SCREENSHOT_PATH)
    roi = img[y1:y2, x1:x2]

    # 优化颜色过滤，更精准匹配知网蓝色按钮
    hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lower_blue = np.array([100, 50, 50])  # 调整蓝色阈值下限
    upper_blue = np.array([120, 255, 255])  # 调整蓝色阈值上限
    mask = cv2.inRange(hsv_roi, lower_blue, upper_blue)
    gray_roi = cv2.cvtColor(cv2.bitwise_and(roi, roi, mask=mask), cv2.COLOR_BGR2GRAY)

    # 模板预处理
    hsv_temp = cv2.cvtColor(template, cv2.COLOR_BGR2HSV)
    temp_mask = cv2.inRange(hsv_temp, lower_blue, upper_blue)
    gray_temp = cv2.cvtColor(cv2.bitwise_and(template, template, mask=temp_mask), cv2.COLOR_BGR2GRAY)

    # 多尺度匹配，确保第一个按钮定位精准
    found = False
    best_loc = None
    for scale in [0.9, 1.0, 1.1]:  # 缩小缩放范围，提高定位精度
        scaled_temp = cv2.resize(gray_temp,
                                 (int(template_w * scale), int(template_h * scale)),
                                 interpolation=cv2.INTER_AREA)
        st_w, st_h = scaled_temp.shape[1], scaled_temp.shape[0]

        if st_w > roi_w or st_h > roi_h:
            continue

        result = cv2.matchTemplate(gray_roi, scaled_temp, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= CONFIDENCE)
        if len(locations[0]) > 0:
            # 取最上方且置信度最高的匹配结果
            max_val = np.max(result)
            max_loc = np.where(result == max_val)
            best_loc = (max_loc[1][0], max_loc[0][0])  # (x,y)
            found = True
            break

    if not found:
        print("❌ 未找到第一页第一个按钮（请检查模板或区域）")
        return []

    # 计算第一个按钮的准确坐标（模板中心）
    first_y_roi = best_loc[1] + (scaled_temp.shape[0] // 2)  # 基于匹配到的模板尺寸计算中心
    first_y = y1 + first_y_roi  # 转换为屏幕坐标
    first_page_first_btn = (fixed_x, first_y)
    print(f"📌 第一页第一个按钮基准坐标：{first_page_first_btn}（已优化定位）")

    # 计算后续按钮坐标（使用调整后的递进值PAGE1_STEP）
    page1_buttons = [first_page_first_btn]
    current_y = first_y
    for i in range(1, TARGET_BUTTONS):
        current_y += PAGE1_STEP  # 核心：使用70像素递进（可根据实际页面调整）
        page1_buttons.append((fixed_x, current_y))
    print(f"📌 第一页按钮坐标计算完成（共{len(page1_buttons)}个，每步+{PAGE1_STEP}像素）")
    return page1_buttons


# ==================== 后续页按钮坐标计算 ====================
def get_next_page_buttons():
    if not first_page_first_btn:
        print("❌ 无第一页基准坐标")
        return []

    next_buttons = []
    fx, fy = first_page_first_btn

    # 找当前页第一个按钮
    first_btn = None
    print("🔍 寻找当前页第一个按钮（±3,±5...）")
    for offset in NEXT_PAGE_FIRST_STEP:
        test_y = fy + offset
        if check_download(fx, test_y):
            first_btn = (fx, test_y)
            break
        test_y = fy - offset
        if check_download(fx, test_y):
            first_btn = (fx, test_y)
            break
    if not first_btn:
        print("❌ 未找到当前页第一个按钮")
        return []
    next_buttons.append(first_btn)
    print(f"📌 当前页第一个按钮坐标：{first_btn}")

    # 找后续按钮
    prev_btn = first_btn
    for i in range(1, TARGET_BUTTONS):
        px, py = prev_btn
        curr_btn = None

        # 先尝试基准偏移（+70）
        test_y = py + NEXT_PAGE_BTN_STEP1
        if check_download(px, test_y):
            curr_btn = (px, test_y)
        # 基准失败，追加+20
        if not curr_btn:
            test_y = py + NEXT_PAGE_BTN_STEP1 + NEXT_PAGE_BTN_STEP2
            if check_download(px, test_y):
                curr_btn = (px, test_y)
        # 仍失败，尝试递增偏移
        if not curr_btn:
            for offset in [3, 5, 7, 9, 11, 13]:
                test_y = py + NEXT_PAGE_BTN_STEP1 + offset
                if check_download(px, test_y):
                    curr_btn = (px, test_y)
                    break

        if curr_btn:
            next_buttons.append(curr_btn)
            prev_btn = curr_btn
            print(f"📌 当前页第{i + 1}个按钮坐标：{curr_btn}")
        else:
            print(f"⚠️ 未找到当前页第{i + 1}个按钮")
            break

    return next_buttons


# ==================== 下载辅助函数（增加去重） ====================
def check_download(x, y):
    pyautogui.moveTo(x, y, duration=0.3)
    pyautogui.click()
    time.sleep(1)
    initial = set(os.listdir(DOWNLOAD_PATH))
    time.sleep(1)
    current = set(os.listdir(DOWNLOAD_PATH))
    new_files = [f for f in (current - initial) if f.endswith(('.crdownload', '.part', '.tmp'))]
    return len(new_files) > 0


def download_with_offset(btn_coord, start_offset):
    x, y = btn_coord
    global last_offset, downloaded_files
    current_offset = start_offset
    attempt = 0

    while attempt < MAX_ATTEMPTS:
        test_y = y + current_offset
        print(f"   尝试偏移：{current_offset} → 坐标：({x},{test_y})")

        pyautogui.moveTo(x, test_y, duration=random.uniform(*MOVE_DURATION))
        time.sleep(random.uniform(*CLICK_DELAY))
        pyautogui.click()

        # 检测新文件（增加去重）
        initial = set(os.listdir(DOWNLOAD_PATH))
        start_time = time.time()
        while time.time() - start_time < 2:
            current = set(os.listdir(DOWNLOAD_PATH))
            new_tmp = [f for f in (current - initial) if f.endswith(('.crdownload', '.part', '.tmp'))]
            if new_tmp:
                # 等待下载完成并去重
                while time.time() - start_time < DOWNLOAD_TIMEOUT:
                    current = set(os.listdir(DOWNLOAD_PATH))
                    completed = [
                        f for f in (current - initial)
                        if not f.endswith(('.crdownload', '.part', '.tmp'))
                           and os.path.getsize(os.path.join(DOWNLOAD_PATH, f)) >= 1024
                           and f not in downloaded_files  # 过滤已下载文件
                    ]

                    if completed:
                        downloaded_files.add(completed[0])  # 记录已下载
                        print(f"✅ 下载成功：{completed[0]}")
                        last_offset = current_offset
                        return True, current_offset
                    time.sleep(0.5)
                return False, 0

            time.sleep(0.3)

        current_offset += OFFSET_INCREMENT
        attempt += 1

    print(f"❌ 超过最大尝试次数（{MAX_ATTEMPTS}次）")
    return False, 0


# ==================== 页面下载逻辑 ====================
def download_page(buttons, is_first_page=True):
    global downloaded_total, last_offset
    success = 0
    target = len(buttons)
    print(f"\n🚀 第{current_page}页开始下载（目标{target}个）")

    for i in range(target):
        if not is_running:
            break

        btn = buttons[i]
        print(f"📌 第{i + 1}个按钮（基准坐标：{btn}）")

        start_offset = 0 if (is_first_page or i == 0) else (last_offset + OFFSET_INCREMENT)

        ok, offset = download_with_offset(btn, start_offset)
        if ok:
            success += 1
            downloaded_total += 1
            time.sleep(random.uniform(*DOWNLOAD_INTERVAL))

    print(f"📊 第{current_page}页下载完成：{success}/{target}")
    return success == target


# ==================== 翻页逻辑 ====================
def turn_page():
    global current_page
    print(f"\n📑 翻到第{current_page + 1}页...")
    center_x, center_y = screen_size[0] // 2, screen_size[1] // 2
    pyautogui.moveTo(center_x, center_y, duration=0.5)
    time.sleep(0.5)
    pyautogui.press('right')
    time.sleep(PAGE_TURN_DELAY)
    current_page += 1
    print(f"✅ 已翻到第{current_page}页")
    return True


# ==================== 主程序 ====================
def main():
    global scaling_factor, template, last_offset, SCREENSHOT_PATH, TEMPLATE_PATH

    # 配置路径（确保模板正确）
    SCREENSHOT_PATH = os.path.join(os.path.dirname(__file__), "full_screen.png")
    TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "download_icon.png")

    print("=" * 50)
    print("📂 下载自动化工具（修复重复下载问题）")
    print("=" * 50)

    scaling_factor = get_scaling_factor()
    template = load_template()
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)

    while not select_region():
        print("🔄 请重新框选区域...")
        time.sleep(1)

    print(f"\n===== 处理第1页 =====")
    page1_buttons = get_page1_buttons()
    if len(page1_buttons) < TARGET_BUTTONS:
        print(f"❌ 第一页按钮不足（{len(page1_buttons)}/{TARGET_BUTTONS}）")
        return

    last_offset = 0
    if not download_page(page1_buttons, is_first_page=True):
        print("❌ 第一页下载未完成，是否继续？")
        if input("继续(y/n): ").lower() != 'y':
            return

    while is_running:
        if not turn_page():
            break

        next_buttons = get_next_page_buttons()
        if len(next_buttons) < TARGET_BUTTONS:
            print(f"⚠️ 当前页按钮不足（{len(next_buttons)}/{TARGET_BUTTONS}）")
            if input("继续下载(y/n): ").lower() != 'y':
                break

        if not download_page(next_buttons, is_first_page=False):
            print("❌ 当前页下载未完成，是否翻页？")
            if input("继续翻页(y/n): ").lower() != 'y':
                break

    print("\n" + "=" * 50)
    print(f"📊 总下载完成：{downloaded_total}个文件")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ 程序被中断")
    except Exception as e:
        print(f"\n❌ 异常终止：{str(e)}")