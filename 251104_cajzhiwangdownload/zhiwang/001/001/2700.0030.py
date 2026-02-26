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

# ==================== 核心配置（蓝色按钮适配） ====================
TARGET_BUTTONS = 10           # 每页目标下载数
MIN_BUTTONS = 3               # 最低有效按钮数
DOWNLOAD_PATH = r"D:\Downloads"
BASE_CONFIDENCE = 0.3         # 基础置信度（降低门槛）
CLUSTER_THRESHOLD = 250       # 聚类间隔（扩大范围）
RECOGNIZE_RETRY = 3           # 识别重试次数
SINGLE_CLICK_TIMEOUT = 1      # 点击失败判断时间
PAGE_TOTAL_TIMEOUT = 15       # 单页总超时
SINGLE_CLICK_DELAY = (0.1, 0.25)  # 点击间隔
BUTTON_INTERVAL = (0.5, 1.0)  # 按钮间间隔

# 蓝色下载按钮的HSV范围（知网蓝色按钮特征）
BLUE_LOWER = np.array([100, 120, 50])   # 蓝色低阈值（H:100-130, S:120+, V:50+）
BLUE_UPPER = np.array([130, 255, 255])  # 蓝色高阈值

# 偏移策略
OFFSET_STRATEGY = [
    (3, "down"), (5, "down"), (3, "up"), (5, "up"),
    (8, "down"), (8, "up"), (12, "reverse"), (15, "reverse")
]

# 全局状态
is_running = True
is_paused = False
x_range = None
scaling_factor = 1.0
downloaded_total = 0
current_page = 1
screen_size = pyautogui.size()
templates = []


# ==================== 高DPI适配 ====================
def get_scaling_factor():
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    screen_physical = (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    screen_logical = (screen_size[0], screen_size[1])
    scaling = round(screen_logical[0] / screen_physical[0], 2)
    print(f"✅ 系统缩放：{scaling * 100}%（物理：{screen_physical}，逻辑：{screen_logical}）")
    return scaling


def convert_coords(screenshot_x, screenshot_y):
    return (int(screenshot_x * scaling_factor), int(screenshot_y * scaling_factor))


# ==================== 图像预处理（蓝色特征强化） ====================
def preprocess_image(img):
    """通过HSV过滤蓝色区域，增强按钮特征"""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # 提取蓝色区域
    blue_mask = cv2.inRange(hsv, BLUE_LOWER, BLUE_UPPER)
    # 蓝色区域与原图叠加
    blue_img = cv2.bitwise_and(img, img, mask=blue_mask)
    # 边缘检测
    gray = cv2.cvtColor(blue_img, cv2.COLOR_BGR2GRAY)
    return cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 30, 120)


def load_templates():
    """加载蓝色按钮模板"""
    global templates
    templates = []
    template_names = ["template1.png", "template2.png", "template3.png"]
    missing = [name for name in template_names if not os.path.exists(name)]
    if missing:
        print(f"❌ 缺少模板：{', '.join(missing)}")
        print("⚠️ 请截取蓝色下载按钮作为模板（建议尺寸20x20，包含完整按钮）")
        exit(1)
    for name in template_names:
        img = cv2.imread(name)
        templates.append((preprocess_image(img), name))
    print(f"✅ 加载{len(templates)}张蓝色特征模板")


# ==================== 截图与按钮识别 ====================
def take_screenshot(save_path="temp.png"):
    try:
        screen = ImageGrab.grab(bbox=(0, 0, screen_size[0], screen_size[1]))
        screen.save(save_path)
        return os.path.getsize(save_path) > 102400
    except Exception as e:
        print(f"❌ 截图失败：{str(e)}")
        return False


def find_buttons(debug=True):
    if not x_range:
        return None
    x_min, x_max = x_range
    if not take_screenshot():
        return None

    img = cv2.imread("temp.png")
    img_h, img_w = img.shape[:2]
    roi = img[:, x_min:x_max]
    roi_preprocessed = preprocess_image(roi)

    candidates = []
    for (template, t_name) in templates:
        t_h, t_w = template.shape[:2]
        result = cv2.matchTemplate(roi_preprocessed, template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= BASE_CONFIDENCE)
        for pt, score in zip(zip(*locations[::-1]), result[locations]):
            s_x = x_min + pt[0] + t_w // 2
            s_y = pt[1] + t_h // 2
            actual_x, actual_y = convert_coords(s_x, s_y)
            candidates.append((actual_x, actual_y, float(score), t_name, s_x, s_y))

    if not candidates:
        print("⚠️ 未找到蓝色按钮候选（检查模板或X范围）")
        return None

    # 去重与聚类
    candidates_sorted = sorted(candidates, key=lambda x: x[2], reverse=True)
    unique_candidates = []
    seen = set()
    for c in candidates_sorted:
        x, y = c[0], c[1]
        key = (round(x / 10), round(y / 10))
        if key not in seen:
            seen.add(key)
            unique_candidates.append(c)

    unique_candidates.sort(key=lambda x: x[1])
    clusters = []
    current_cluster = [unique_candidates[0]] if unique_candidates else []
    for c in unique_candidates[1:]:
        if c[1] - current_cluster[-1][1] < CLUSTER_THRESHOLD:
            current_cluster.append(c)
        else:
            clusters.append(current_cluster)
            current_cluster = [c]
    if current_cluster:
        clusters.append(current_cluster)

    if not clusters:
        return None

    largest_cluster = max(clusters, key=len)
    print(f"📊 识别结果：候选{len(unique_candidates)}个，最大聚类{len(largest_cluster)}个")

    # 生成调试图
    if debug:
        debug_img = img.copy()
        cv2.line(debug_img, (x_min, 0), (x_min, img_h), (0, 0, 255), 2)
        cv2.line(debug_img, (x_max, 0), (x_max, img_h), (0, 0, 255), 2)
        for c in unique_candidates:
            s_x, s_y = c[4], c[5]
            cv2.circle(debug_img, (s_x, s_y), 5, (255, 0, 0), 2)
        for c in largest_cluster:
            s_x, s_y = c[4], c[5]
            cv2.circle(debug_img, (s_x, s_y), 8, (0, 255, 0), 3)
        cv2.imwrite(f"debug_buttons_page_{current_page}.png", debug_img)
        print(f"📌 调试图已保存：debug_buttons_page_{current_page}.png")

    return [(c[0], c[1]) for c in largest_cluster]


# ==================== 下载与翻页逻辑 ====================
def download_page(buttons):
    global downloaded_total
    page_start = time.time()
    page_success = 0
    target = min(len(buttons), TARGET_BUTTONS)
    print(f"\n🚀 第{current_page}页（目标{target}个，限时{PAGE_TOTAL_TIMEOUT}s）")

    for idx in range(target):
        if time.time() - page_start > PAGE_TOTAL_TIMEOUT:
            print(f"⏰ 单页超时，剩余{target-idx}个未下载")
            break
        if not is_running:
            break
        while is_paused:
            time.sleep(0.1)

        base_x, base_y = buttons[idx]
        print(f"\n📌 第{idx+1}个（基准：{base_x},{base_y}）")
        success = False
        last_offset_dir = None

        for (offset, mode) in OFFSET_STRATEGY:
            current_x = base_x
            if mode == "reverse":
                current_y = base_y - offset if last_offset_dir == "down" else base_y + offset
            else:
                current_y = base_y + offset if mode == "down" else base_y - offset
                last_offset_dir = mode

            pyautogui.moveTo(current_x, current_y, duration=0.1)
            pyautogui.click()
            time.sleep(random.uniform(*SINGLE_CLICK_DELAY))

            initial_files = set(os.listdir(DOWNLOAD_PATH))
            time.sleep(SINGLE_CLICK_TIMEOUT)
            new_files = [f for f in (set(os.listdir(DOWNLOAD_PATH)) - initial_files)
                         if not f.endswith(('.crdownload', '.part', '.tmp'))]

            if new_files and os.path.getsize(os.path.join(DOWNLOAD_PATH, new_files[0])) > 1024:
                print(f"✅ 成功（偏移{offset}{mode}）：{new_files[0]}")
                downloaded_total += 1
                page_success += 1
                success = True
                break

        if not success:
            print(f"❌ 第{idx+1}个下载失败")

        time.sleep(random.uniform(*BUTTON_INTERVAL))

    print(f"📊 第{current_page}页：成功{page_success}/{target}个")
    return page_success


def turn_page():
    global current_page
    print(f"\n📑 翻页到第{current_page+1}页")
    pyautogui.moveTo(screen_size[0]//2, screen_size[1]//2, duration=0.1)
    pyautogui.click()
    time.sleep(0.2)
    pyautogui.press('right')
    time.sleep(1)
    current_page += 1
    print(f"✅ 已翻到第{current_page}页")
    return True


# ==================== 键盘控制与X范围选取 ====================
def on_key_press(key):
    global is_running, is_paused
    try:
        if key == keyboard.Key.esc:
            print("\n⚠️ 按ESC停止下载")
            is_running = False
            return False
        elif key == keyboard.Key.space:
            is_paused = not is_paused
            print(f"\n{'⏸️ 暂停' if is_paused else '▶️ 继续'}")
    except:
        pass


def select_x_range():
    global x_range
    if not take_screenshot("x_range_temp.png"):
        return False
    img = cv2.imread("x_range_temp.png")
    img_h, img_w = img.shape[:2]
    ref_point = []

    cv2.putText(img, "请框选右侧蓝色下载按钮的横向范围（ESC确认）", (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)  # 蓝色提示文字
    cv2.putText(img, "示例：从按钮左侧到右侧（尽量窄但完全包含）", (30, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    def click_event(event, x, y, flags, param):
        nonlocal ref_point
        if event == cv2.EVENT_LBUTTONDOWN:
            ref_point = [(x, y)]
        elif event == cv2.EVENT_LBUTTONUP:
            ref_point.append((x, y))
            cv2.rectangle(img, ref_point[0], ref_point[1], (0, 255, 0), 3)
            cv2.imshow("选取下载按钮X范围", img)

    cv2.namedWindow("选取下载按钮X范围", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("选取下载按钮X范围", img_w//2, img_h//2)
    cv2.imshow("选取下载按钮X范围", img)
    cv2.setMouseCallback("选取下载按钮X范围", click_event)
    while cv2.waitKey(1) != 27:
        pass
    cv2.destroyAllWindows()

    if len(ref_point) == 2:
        x_min = min(ref_point[0][0], ref_point[1][0])
        x_max = max(ref_point[0][0], ref_point[1][0])
        x_range = (x_min, x_max)
        print(f"✅ 已选取X范围：{x_min}~{x_max}（截图坐标）")
        return True
    return False


# ==================== 主程序 ====================
def main():
    global scaling_factor
    print("="*80)
    print("📌 知网下载器（蓝色按钮专用版）")
    print("✅ 核心：蓝色特征识别 | 强制重试 | 可视化调试")
    print("✅ 快捷键：ESC停止 | 空格暂停")
    print("="*80)

    scaling_factor = get_scaling_factor()
    input("👉 请确认已以管理员身份运行（回车继续）...")
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
    print(f"✅ 下载路径：{DOWNLOAD_PATH}")

    while not select_x_range():
        print("🔄 请重新选取X范围（必须包含蓝色下载按钮）...")

    load_templates()

    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()
    print(f"\n🚀 开始下载（第{current_page}页）")

    try:
        while is_running:
            buttons = None
            for retry in range(RECOGNIZE_RETRY):
                buttons = find_buttons()
                if buttons and len(buttons) >= MIN_BUTTONS:
                    break
                print(f"🔄 按钮识别重试（{retry+1}/{RECOGNIZE_RETRY}）")
                time.sleep(1)

            if not buttons or len(buttons) < MIN_BUTTONS:
                print("📋 未找到足够有效按钮，结束下载")
                break

            retry_count = 0
            while len(buttons) < TARGET_BUTTONS and retry_count < 2:
                print(f"🔄 按钮不足{TARGET_BUTTONS}个，重新识别（{retry_count+1}/2）")
                buttons = find_buttons()
                retry_count += 1
            if not buttons:
                break

            download_page(buttons)
            turn_page()

    finally:
        listener.stop()
        for f in ["temp.png", "x_range_temp.png"]:
            if os.path.exists(f):
                os.remove(f)
        print("\n" + "="*70)
        print(f"🎉 任务结束：共{current_page}页，下载{downloaded_total}个文件")
        print(f"📁 下载路径：{DOWNLOAD_PATH}")
        print("="*70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ 用户手动停止")
        print(f"📊 总下载：{downloaded_total}个文件")