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
TARGET_BUTTONS_PER_PAGE = 10  # 每页下载数量
MIN_LAST_PAGE_BUTTONS = 1  # 最后一页最小按钮数
DOWNLOAD_PATH = r"D:\Downloads"
BASE_CONFIDENCE = 0.4  # 基础匹配置信度
CLUSTER_THRESHOLD = 150  # 按钮聚类最大间隔（像素）
EDGE_THRESHOLD1 = 50  # 边缘检测参数1
EDGE_THRESHOLD2 = 150  # 边缘检测参数2
TEMP_SCREENSHOT = "temp_screenshot.png"
TEMPLATE_NAMES = ["template1.png", "template2.png", "template3.png"]

# 时间设置（补全翻页延迟变量定义）
MOVE_DURATION = (0.3, 0.6)
CLICK_DELAY = (0.4, 0.7)
DOWNLOAD_INTERVAL = (1.0, 1.5)
PAGE_TURN_DELAY = (1.5, 2.0)  # 修复未定义问题
PAGE_LOAD_DELAY = 6  # 页面加载延迟
PAGE_TURN_RETRY = 3  # 翻页重试次数

# y轴偏移重试参数（等差数列：2,4,6...px）
MAX_RETRY = 5  # 最大重试次数
INITIAL_OFFSET = 2  # 初始偏移量（px）
OFFSET_STEP = 2  # 每次递增偏移量（px）

# 全局状态
is_running = True
is_paused = False
x_range = None
scaling_factor = 1.0
downloaded_total = 0
current_page = 1
screen_size = pyautogui.size()
templates = []  # 预处理后的模板


# ==================== 高DPI适配 ====================
def get_scaling_factor():
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    screen_physical = (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    screen_logical = (screen_size[0], screen_size[1])
    scaling = round(screen_logical[0] / screen_physical[0], 2)
    print(f"✅ 系统缩放比例：{scaling * 100}%（物理分辨率：{screen_physical}，逻辑分辨率：{screen_logical}）")
    return scaling


def convert_to_actual_coords(screenshot_x, screenshot_y):
    actual_x = int(screenshot_x * scaling_factor)
    actual_y = int(screenshot_y * scaling_factor)
    return (actual_x, actual_y)


# ==================== 图像预处理 ====================
def preprocess_image(img):
    """边缘检测增强按钮特征"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, EDGE_THRESHOLD1, EDGE_THRESHOLD2)
    return edges


# ==================== 工具函数 ====================
def init_download_path():
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
    print(f"✅ 下载路径：{DOWNLOAD_PATH}")


def load_templates():
    """加载并预处理模板"""
    global templates
    templates = []
    missing = []
    for name in TEMPLATE_NAMES:
        if not os.path.exists(name):
            missing.append(name)
            continue
        template = cv2.imread(name)
        if template is None:
            print(f"❌ 模板{name}无法读取")
            continue
        template_edges = preprocess_image(template)
        templates.append((template_edges, name))

    if missing:
        print(f"❌ 缺少模板：{', '.join(missing)}")
        print("请保存3张下载按钮图片为template1-3.png（建议20x20像素）")
        exit(1)
    print(f"✅ 成功加载{len(templates)}张预处理模板")


def take_screenshot():
    try:
        screen = ImageGrab.grab(bbox=(0, 0, screen_size[0], screen_size[1]))
        screen.save(TEMP_SCREENSHOT)
        if os.path.getsize(TEMP_SCREENSHOT) < 102400:
            print("❌ 截图过小，可能未捕获完整页面")
            return False
        return True
    except Exception as e:
        print(f"❌ 截图失败：{str(e)}")
        return False


# ==================== 选取X轴范围 ====================
def select_x_range():
    global x_range
    ref_point = []
    cropping = False

    while not take_screenshot():
        print("🔄 重新尝试截图...")
        time.sleep(2)

    img = cv2.imread(TEMP_SCREENSHOT)
    img_copy = img.copy()
    img_h, img_w = img.shape[:2]

    cv2.putText(img_copy, "选取下载按钮的X轴范围（横向）→ 按ESC确认", (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    cv2.putText(img_copy, "参考右侧红色下载按钮区域", (30, 100),
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
            cv2.imshow("选取X轴范围", img_copy)
        elif event == cv2.EVENT_MOUSEMOVE and cropping:
            temp_img = img_copy.copy()
            cv2.rectangle(temp_img, ref_point[0], (x, y), (0, 255, 0), 2)
            cv2.imshow("选取X轴范围", temp_img)

    cv2.namedWindow("选取X轴范围", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("选取X轴范围", img_w // 2, img_h // 2)
    cv2.imshow("选取X轴范围", img_copy)
    cv2.setMouseCallback("选取X轴范围", click_event)

    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
    cv2.destroyAllWindows()

    if len(ref_point) == 2:
        x_min = min(ref_point[0][0], ref_point[1][0])
        x_max = max(ref_point[0][0], ref_point[1][0])
        x_min = max(0, x_min - 5)
        x_max = min(img_w, x_max + 5)
        x_range = (x_min, x_max)
        actual_x_min, _ = convert_to_actual_coords(x_min, 0)
        actual_x_max, _ = convert_to_actual_coords(x_max, 0)
        print(f"✅ 已保存X轴范围（截图坐标）：{x_min} ~ {x_max}")
        print(f"   转换为实际屏幕坐标：{actual_x_min} ~ {actual_x_max}")
        return True
    else:
        print("❌ 选取失败，请重新尝试")
        return False


# ==================== 按钮识别 ====================
def find_buttons():
    if not x_range:
        return None
    x_min, x_max = x_range

    # 截取当前页面
    for _ in range(3):
        if take_screenshot():
            break
        time.sleep(1)
    else:
        return None

    img = cv2.imread(TEMP_SCREENSHOT)
    img_h, img_w = img.shape[:2]
    roi = img[:, x_min:x_max]
    roi_edges = preprocess_image(roi)

    # 多模板匹配
    candidates = []
    for (template_edges, template_name) in templates:
        t_h, t_w = template_edges.shape[:2]
        result = cv2.matchTemplate(roi_edges, template_edges, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= BASE_CONFIDENCE)
        for pt, score in zip(zip(*locations[::-1]), result[locations]):
            s_x = x_min + pt[0] + t_w // 2
            s_y = pt[1] + t_h // 2
            actual_x, actual_y = convert_to_actual_coords(s_x, s_y)
            candidates.append((actual_x, actual_y, float(score), template_name))

    if not candidates:
        print(f"📄 第{current_page}页：未找到候选按钮")
        return None

    # 去重并排序
    candidates_sorted = sorted(candidates, key=lambda x: x[2], reverse=True)
    unique_candidates = []
    seen = set()
    for c in candidates_sorted:
        x, y = c[0], c[1]
        key = (round(x / 10), round(y / 10))  # 10px精度去重
        if key not in seen:
            seen.add(key)
            unique_candidates.append(c)

    # 聚类（保留连续按钮）
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
    print(f"📄 第{current_page}页：候选按钮{len(unique_candidates)}个，最大聚类包含{len(largest_cluster)}个")

    # 最终按钮坐标（按y排序）
    final_buttons = [(c[0], c[1]) for c in largest_cluster]
    final_buttons.sort(key=lambda x: x[1])

    # 保存调试图
    debug_img = img.copy()
    cv2.line(debug_img, (x_min, 0), (x_min, img_h), (0, 0, 255), 2)
    cv2.line(debug_img, (x_max, 0), (x_max, img_h), (0, 0, 255), 2)
    template_colors = {"template1.png": (255, 0, 0), "template2.png": (0, 255, 0), "template3.png": (0, 0, 255)}
    for c in unique_candidates:
        x, y, score, t_name = c
        s_x, s_y = int(x / scaling_factor), int(y / scaling_factor)
        color = template_colors.get(t_name, (255, 255, 0))
        cv2.circle(debug_img, (s_x, s_y), max(3, int(score * 10)), color, 2)
        cv2.putText(debug_img, f"{score:.2f}", (s_x + 5, s_y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
    for i, (x, y) in enumerate(final_buttons):
        s_x, s_y = int(x / scaling_factor), int(y / scaling_factor)
        cv2.circle(debug_img, (s_x, s_y), 8, (0, 255, 0), 3)
        cv2.putText(debug_img, f"# {i + 1}", (s_x + 10, s_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.imwrite(f"debug_page_{current_page}.png", debug_img)

    return final_buttons


# ==================== 下载逻辑（核心：y轴偏移重试） ====================
def download_page_buttons(buttons):
    global downloaded_total
    page_downloaded = 0
    target_count = min(len(buttons), TARGET_BUTTONS_PER_PAGE)

    print(f"\n🚀 第{current_page}页开始下载（共{target_count}个按钮）")
    for idx in range(target_count):
        if not is_running:
            break
        while is_paused:
            time.sleep(0.5)

        base_x, base_y = buttons[idx]
        print(f"\n📥 第{current_page}页 第{idx + 1}/{target_count}个（基准坐标：{base_x},{base_y}）")

        # 等差数列偏移重试（初始偏移=2*idx px，每次递增2px）
        success = False
        for retry in range(MAX_RETRY):
            # 偏移量：第n个按钮初始偏移2*idx px，每次重试+2px（等差序列）
            offset = 2 * idx + retry * OFFSET_STEP
            current_x = base_x
            current_y = base_y + offset  # 向下偏移
            print(f"🔍 重试{retry + 1}/{MAX_RETRY}（偏移{offset}px）：坐标({current_x},{current_y})")

            # 移动并点击
            pyautogui.moveTo(current_x, current_y, duration=0.5)
            time.sleep(1.0)  # 观察时间
            pyautogui.click()
            time.sleep(random.uniform(*CLICK_DELAY))

            # 检查下载是否成功
            start_time = time.time()
            initial_files = set(os.listdir(DOWNLOAD_PATH))
            while time.time() - start_time < 30:
                current_files = set(os.listdir(DOWNLOAD_PATH))
                new_files = [f for f in (current_files - initial_files)
                             if not f.endswith(('.crdownload', '.part', '.tmp'))]
                if new_files and os.path.getsize(os.path.join(DOWNLOAD_PATH, new_files[0])) > 1024:
                    print(f"✅ 下载成功：{new_files[0]}")
                    downloaded_total += 1
                    page_downloaded += 1
                    success = True
                    time.sleep(random.uniform(*DOWNLOAD_INTERVAL))
                    break
                time.sleep(1.0)
            if success:
                break

        if not success:
            print(f"❌ 第{idx + 1}个按钮下载失败（已重试{MAX_RETRY}次）")

    print(f"\n📊 第{current_page}页下载统计：成功{page_downloaded}/{target_count}个")
    return page_downloaded


# ==================== 翻页逻辑（仅向右方向键） ====================
def auto_turn_page():
    global current_page
    print(f"\n" + "=" * 60)
    print(f"📑 第{current_page}页下载完成，准备翻到第{current_page + 1}页...")
    print("=" * 60)

    # 激活页面
    center_x, center_y = screen_size[0] // 2, screen_size[1] // 2
    pyautogui.moveTo(center_x, center_y, duration=0.5)
    pyautogui.click()
    time.sleep(0.5)

    for retry in range(PAGE_TURN_RETRY):
        try:
            # 严格限制仅使用向右方向键
            pyautogui.press('right')
            print(f"⏸️ 按下向右方向键翻页（重试{retry + 1}/{PAGE_TURN_RETRY}）")
            time.sleep(random.uniform(*PAGE_TURN_DELAY))  # 使用已定义的翻页延迟
            time.sleep(PAGE_LOAD_DELAY)

            if take_screenshot():
                current_page += 1
                print(f"✅ 翻页成功，当前第{current_page}页")
                return True
        except Exception as e:
            print(f"⚠️  翻页重试{retry + 1}次失败: {str(e)}")
            time.sleep(2)

    print(f"❌ 翻页失败（已重试{PAGE_TURN_RETRY}次）")
    return False


# ==================== 键盘控制（限制功能键） ====================
def on_key_press(key):
    global is_running, is_paused
    try:
        # 仅响应ESC和空格，屏蔽其他键
        if key == keyboard.Key.esc:
            print("\n⚠️  按ESC停止下载")
            is_running = False
            return False
        elif key == keyboard.Key.space:
            is_paused = not is_paused
            print(f"\n{'⏸️ 已暂停' if is_paused else '▶️ 继续下载'}")
    except:
        pass  # 忽略其他按键


# ==================== 主程序 ====================
def main():
    global is_running, scaling_factor
    print("=" * 80)
    print("📌 下载器（y轴自适应补偿版）")
    print("✅ 核心功能：y轴等差偏移重试，仅向右键翻页")
    print("✅ 快捷键：ESC=停止 | 空格=暂停/继续")
    print(f"✅ 屏幕尺寸：{screen_size[0]}x{screen_size[1]}像素")
    print("=" * 80)

    scaling_factor = get_scaling_factor()

    print("\n⚠️  请确保已以管理员身份运行脚本！")
    input("👉 确认后按回车开始...")

    init_download_path()

    # 选取X轴范围
    print("\n📌 第一步：选取下载按钮的横向（X轴）范围")
    while is_running and not x_range:
        if select_x_range():
            break
        print("🔄 重新尝试选取X轴范围...")
        time.sleep(2)

    # 加载模板
    print("\n📌 第二步：加载下载按钮模板图片")
    load_templates()

    # 启动键盘监听
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()
    print(f"\n🚀 开始全自动循环下载（当前第{current_page}页）")

    try:
        while is_running:
            buttons = find_buttons()
            if not buttons:
                print(f"\n📋 第{current_page}页未找到有效按钮，下载结束")
                break

            page_downloaded = download_page_buttons(buttons)
            if page_downloaded == 0 and len(buttons) >= MIN_LAST_PAGE_BUTTONS:
                print(f"❌ 第{current_page}页未下载成功任何文件，停止循环")
                break

            # 翻页判断
            if len(buttons) >= TARGET_BUTTONS_PER_PAGE:
                if not auto_turn_page():
                    print("⚠️  翻页失败，尝试继续下载当前页剩余按钮...")
                    # 若翻页失败，强制重新识别当前页（避免重复下载）
                    buttons = find_buttons()
                    if not buttons:
                        break
            else:
                print(f"\n📋 第{current_page}页只有{len(buttons)}个按钮，为最后一页")
                break

    finally:
        listener.stop()
        listener.join()
        if os.path.exists(TEMP_SCREENSHOT):
            os.remove(TEMP_SCREENSHOT)

        print("\n" + "=" * 70)
        print(f"🎉 下载任务结束！")
        print(f"📊 总下载页数：{current_page}页")
        print(f"📊 总下载文件数：{downloaded_total}个")
        print(f"📁 下载路径：{DOWNLOAD_PATH}")
        print(f"🔍 调试图像已保存（debug_page_*.png）")
        print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ 用户手动停止")
        if os.path.exists(TEMP_SCREENSHOT):
            os.remove(TEMP_SCREENSHOT)
        print(f"📊 总下载页数：{current_page}页，总下载文件数：{downloaded_total}个")