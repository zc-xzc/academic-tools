import pyautogui
import time
import random
import os
import cv2
import numpy as np
from pynput import keyboard
from PIL import ImageGrab
from pathlib import Path

# ==================== 关键配置（人工模拟+功能适配）====================
DOWNLOAD_PATH = r"D:\Downloads"
CONFIDENCE = 0.45  # 降低置信度适配不同颜色按钮
SERIAL_DOWNLOAD_DX = 0
SERIAL_DOWNLOAD_DY = 0
FILE_MIN_SIZE = 1024
DOWNLOAD_TIMEOUT = 30  # 延长超时，适配人工验证
SCROLL_STEP = 600
SCROLL_DELAY = random.uniform(1.2, 2.0)  # 随机滚动等待
PAGE_LOAD_DELAY = random.uniform(3.5, 5.0)  # 随机翻页加载时间
TEMP_SCREENSHOT = "temp_page_screenshot.png"
WINDOW_TITLE = "知网下载区域框选"

# 人工模拟配置（核心防机器人）
HUMAN_MOVE_DURATION = (0.5, 1.2)  # 鼠标移动时间范围
HUMAN_STAY_DURATION = (0.5, 1.5)  # 点击前停留时间范围
HUMAN_CLICK_INTERVAL = (0.08, 0.2)  # 双击间隔范围
HUMAN_DOWNLOAD_INTERVAL = (2.0, 5.0)  # 下载间隔范围
HUMAN_RANDOM_SCROLL = (-50, 50)  # 随机微调滚动范围
HUMAN_PAUSE_INTERVAL = (3, 8)  # 随机休息时间范围
HUMAN_PAUSE_TRIGGER = 5  # 每下载5个随机休息一次

# 颜色判断配置（蓝色/黄色按钮）
BLUE_THRESHOLD = (100, 150)  # 蓝色通道（B）阈值（RGB中B通道值）
YELLOW_THRESHOLD = (180, 255)  # 黄通道（R+G）阈值（RGB中R+G之和）

# 全局状态
is_running = True
is_paused = False
current_page = 1
downloaded_count = 0
current_page_downloaded = 0
initial_files = set()
selected_region = None
target_count = 0
last_target_count = 0  # 记录上一页目标数量，翻页复用
screen_ratio = (1.0, 1.0)
box_selected = False
retry_count = 0  # 页面重试次数
max_retry = 1  # 最大重试次数
page_nav_history = [1]  # 页面导航历史，用于回退


# ==================== 基础工具函数 ====================
def init_download_path():
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
    global initial_files
    initial_files = get_file_list(DOWNLOAD_PATH)
    print(f"✅ 下载路径：{DOWNLOAD_PATH}（初始文件数：{len(initial_files)}）")


def get_file_list(folder):
    files = set()
    for f in os.listdir(folder):
        f_path = os.path.join(folder, f)
        if os.path.isfile(f_path) and os.path.getsize(f_path) >= FILE_MIN_SIZE:
            files.add((f, os.path.getsize(f_path)))
    return files


def detect_new_file():
    current_files = get_file_list(DOWNLOAD_PATH)
    new_files = current_files - initial_files
    if new_files:
        new_file = sorted(new_files, key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_PATH, x[0])))[-1]
        print(f"✅ 新增文件：{new_file[0]}（{new_file[1] / 1024:.1f}KB）")
        initial_files.add(new_file)
        return True
    return False


def load_download_icon():
    path = "Driver_Notes/download_icon.png"
    if not os.path.exists(path):
        print(f"❌ 未找到 {path}！请截图知网下载按钮（任意颜色）并保存到脚本文件夹")
        exit(1)
    img = cv2.imread(path)
    if img is None:
        print("❌ 下载按钮截图无效")
        exit(1)
    h, w = img.shape[:2]
    print(f"✅ 加载下载按钮截图：{w}x{h}像素")
    return img


# ==================== 人工模拟工具函数 ====================
def human_like_move_to(x, y):
    """模拟人类鼠标移动（分段曲线移动）"""
    current_x, current_y = pyautogui.position()
    # 分段移动（2-3段）
    segments = random.randint(2, 3)
    step_x = (x - current_x) / segments
    step_y = (y - current_y) / segments
    duration = random.uniform(*HUMAN_MOVE_DURATION) / segments

    for i in range(segments):
        if not is_running:
            return
        next_x = current_x + step_x + random.randint(-8, 8)
        next_y = current_y + step_y + random.randint(-8, 8)
        pyautogui.moveTo(next_x, next_y, duration=duration)
        current_x, current_y = next_x, next_y
        time.sleep(random.uniform(0.05, 0.1))

    # 最终精准定位
    pyautogui.moveTo(x, y, duration=random.uniform(0.1, 0.2))


def human_like_pause():
    """随机休息（模拟人工停顿）"""
    pause_time = random.uniform(*HUMAN_PAUSE_INTERVAL)
    print(f"\n😴 随机休息 {pause_time:.1f} 秒...")
    time.sleep(pause_time)


def random_scroll_adjust():
    """随机微调页面（模拟人工调整）"""
    scroll_step = random.randint(*HUMAN_RANDOM_SCROLL)
    if scroll_step != 0:
        print(f"🔄 微调页面滚动：{scroll_step}像素")
        pyautogui.scroll(scroll_step)
        time.sleep(random.uniform(0.3, 0.7))


# ==================== 页面导航工具函数 ====================
def navigate_to_page(direction):
    """页面导航（前进/后退），返回是否导航成功"""
    global current_page
    original_page = current_page

    if direction == "next":
        # 前进一页
        print(f"\n📄 正在前进到第{current_page + 1}页...")
        pyautogui.press('right')
        current_page += 1
    elif direction == "prev" and len(page_nav_history) > 1:
        # 后退一页（需有历史记录）
        print(f"\n📄 正在回退到第{page_nav_history[-2]}页...")
        pyautogui.press('left')
        current_page = page_nav_history[-2]
        page_nav_history.pop()  # 移除当前页历史
    else:
        print("❌ 无法回退（无历史页面）")
        return False

    # 等待页面加载
    time.sleep(PAGE_LOAD_DELAY)
    print(f"✅ 已切换到第{current_page}页")
    return True


def confirm_navigation():
    """询问用户是否继续翻页，返回用户选择"""
    while True:
        choice = input("\n👉 是否继续翻页到下一页？（y=翻页/n=不翻页/prev=回退上一页）：").strip().lower()
        if choice in ["y", "n", "prev"]:
            return choice
        print("❌ 输入无效，请输入 y/n/prev")


# ==================== 颜色判断函数 ====================
def get_button_color(x, y, button_size=(26, 26)):
    """获取按钮区域颜色，判断蓝色/黄色"""
    # 截图按钮区域（中心x,y，边长button_size）
    half_w = button_size[0] // 2
    half_h = button_size[1] // 2
    bbox = (x - half_w, y - half_h, x + half_w, y + half_h)

    try:
        screen = ImageGrab.grab(bbox=bbox)
        screen_np = np.array(screen)
        # 转换为RGB（ImageGrab返回RGB，cv2默认BGR）
        avg_r = np.mean(screen_np[:, :, 0])
        avg_g = np.mean(screen_np[:, :, 1])
        avg_b = np.mean(screen_np[:, :, 2])

        print(f"🎨 按钮颜色：R={avg_r:.0f}, G={avg_g:.0f}, B={avg_b:.0f}")

        # 判断蓝色（B通道值高）
        if avg_b > BLUE_THRESHOLD[0] and avg_b < BLUE_THRESHOLD[1] and avg_r < 100 and avg_g < 100:
            return "blue"
        # 判断黄色（R+G值高，B值低）
        elif (avg_r + avg_g) > YELLOW_THRESHOLD[0] and (avg_r + avg_g) < YELLOW_THRESHOLD[1] and avg_b < 100:
            return "yellow"
        else:
            return "unknown"
    except Exception as e:
        print(f"❌ 颜色判断失败：{str(e)}")
        return "unknown"


# ==================== 截图与框选功能 ====================
def take_page_screenshot():
    """人工模拟截图（增加随机准备时间）"""
    print("\n" + "=" * 50)
    print(f"📸 正在截图第{current_page}页...")
    print("⚠️  请确保知网页面在前台、最大化、无遮挡！")
    print("=" * 50)
    time.sleep(random.uniform(0.8, 1.5))  # 随机准备时间

    try:
        screen = ImageGrab.grab()
        screen.save(TEMP_SCREENSHOT)

        if not os.path.exists(TEMP_SCREENSHOT) or os.path.getsize(TEMP_SCREENSHOT) < 10240:
            print("❌ 截图失败")
            return False

        screen_w, screen_h = pyautogui.size()
        img = cv2.imread(TEMP_SCREENSHOT)
        img_h, img_w = img.shape[:2]
        global screen_ratio
        screen_ratio = (screen_w / img_w, screen_h / img_h)

        print(f"✅ 截图成功：{TEMP_SCREENSHOT}（{os.path.getsize(TEMP_SCREENSHOT) / 1024:.1f}KB）")
        print(f"📏 屏幕：{screen_w}x{screen_h} | 截图：{img_w}x{img_h} | 比例：{screen_ratio[0]:.2f}x")
        return True
    except Exception as e:
        print(f"❌ 截图出错：{str(e)}")
        return False


def select_region_on_screenshot(screenshot_path, is_first_page=True):
    """框选功能（翻页后提示确认区域）"""
    global selected_region, box_selected
    box_selected = False
    ref_point = []
    cropping = False

    img = cv2.imread(screenshot_path)
    if img is None:
        print("❌ 无法打开截图")
        return False
    img_copy = img.copy()

    # 首次框选提示更详细，翻页后增加坐标确认提示
    if is_first_page:
        cv2.putText(img_copy, "📌 首次框选操作：", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 0), 3)
        cv2.putText(img_copy, "1. 按住左键→拖动框选下载按钮列", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255),
                    2)
        cv2.putText(img_copy, "2. 松开鼠标→按ESC关闭窗口", (30, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        cv2.putText(img_copy, "⚠️  后续翻页需重新确认框选区域", (30, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255),
                    2)
    else:
        cv2.putText(img_copy, f"📌 第{current_page}页框选：", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 0), 3)
        cv2.putText(img_copy, "1. 框选当前页下载按钮列（坐标可能变动）", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (0, 0, 255), 2)
        cv2.putText(img_copy, "2. 按ESC关闭→自动复用之前的数量", (30, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255),
                    2)
        cv2.putText(img_copy, "⚠️  若区域不对请重新框选", (30, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    def click_event(event, x, y, flags, param):
        nonlocal ref_point, cropping, img_copy
        global box_selected

        if event == cv2.EVENT_LBUTTONDOWN:
            ref_point = [(x, y)]
            cropping = True
            print(f"🔘 开始框选（坐标：{x},{y}）")
        elif event == cv2.EVENT_LBUTTONUP:
            ref_point.append((x, y))
            cropping = False
            box_selected = True
            cv2.rectangle(img_copy, ref_point[0], ref_point[1], (0, 255, 0), 4)
            cv2.putText(img_copy, f"✅ 框选完成！按ESC关闭", (30, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imshow(WINDOW_TITLE, img_copy)
            print(f"✅ 框选确认（截图坐标）：{ref_point[0]}→{ref_point[1]}")
        elif event == cv2.EVENT_MOUSEMOVE and cropping:
            temp_img = img_copy.copy()
            cv2.rectangle(temp_img, ref_point[0], (x, y), (0, 255, 0), 3)
            cv2.imshow(WINDOW_TITLE, temp_img)

    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)
    cv2.imshow(WINDOW_TITLE, img_copy)
    cv2.setMouseCallback(WINDOW_TITLE, click_event)

    # 等待操作（延长超时到90秒）
    timeout = 90
    start_time = time.time()
    while True:
        key = cv2.waitKey(1) & 0xFF
        elapsed = time.time() - start_time

        if elapsed > 60 and not box_selected:
            cv2.putText(img_copy, f"⚠️ 已等待{int(elapsed)}秒！按Alt+Tab找框选窗口", (30, 300), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 0, 255), 2)
            cv2.imshow(WINDOW_TITLE, img_copy)

        if elapsed > timeout:
            print("❌ 框选超时")
            cv2.destroyAllWindows()
            return False

        if key == 27:
            break

    cv2.destroyAllWindows()

    if len(ref_point) == 2 and box_selected:
        x1 = min(ref_point[0][0], ref_point[1][0])
        y1 = min(ref_point[0][1], ref_point[1][1])
        x2 = max(ref_point[0][0], ref_point[1][0])
        y2 = max(ref_point[0][1], ref_point[1][1])
        selected_region = (x1, y1, x2, y2)
        print(f"✅ 最终框选区域：({x1},{y1})→({x2},{y2})")

        # 翻页后增加区域确认提示
        if not is_first_page:
            confirm = input("👉 当前框选区域是否正确？（y=正确/n=重新框选）：").strip().lower()
            if confirm != "y":
                print("🔄 重新框选当前页...")
                return select_region_on_screenshot(screenshot_path, is_first_page=False)

        return True
    else:
        print("❌ 未完成有效框选")
        return False


# ==================== 补充缺失的坐标映射函数 ====================
def map_screenshot_to_screen(region):
    """将截图中的框选坐标映射到实际屏幕坐标"""
    x1, y1, x2, y2 = region
    # 截图坐标 × 屏幕比例 = 实际屏幕坐标（转换为整数）
    screen_x1 = int(x1 * screen_ratio[0])
    screen_y1 = int(y1 * screen_ratio[1])
    screen_x2 = int(x2 * screen_ratio[0])
    screen_y2 = int(y2 * screen_ratio[1])
    return (screen_x1, screen_y1, screen_x2, screen_y2)


def get_target_download_count(is_first_page=True):
    """获取目标数量（首次手动输入，后续复用）"""
    global target_count, last_target_count
    if not is_first_page and last_target_count > 0:
        # 翻页后复用之前的数量
        target_count = last_target_count
        print(f"✅ 复用前一页目标数量：{target_count}个/页")
        return True

    print("\n" + "=" * 50)
    print("📝 请输入框选区域内的文献数量")
    print("示例：框选了8个下载按钮 → 输入8")
    print("=" * 50)
    while True:
        try:
            count = input("👉 输入文献数量：")
            target_count = int(count)
            if target_count > 0:
                last_target_count = target_count  # 保存为上一页数量
                print(f"✅ 已设置：每页下载{target_count}个文献")
                return True
            else:
                print("❌ 数量必须大于0")
        except ValueError:
            print("❌ 请输入有效数字")


# ==================== 核心下载功能 ====================
def find_download_buttons_in_region(download_img):
    if not selected_region:
        print("❌ 未框选区域")
        return []

    screen_region = map_screenshot_to_screen(selected_region)
    x1, y1, x2, y2 = screen_region

    try:
        random_scroll_adjust()  # 下载前随机微调页面
        screen = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        screen_np = np.array(screen)
        screen_bgr = cv2.cvtColor(screen_np, cv2.COLOR_RGB2BGR)
    except Exception as e:
        print(f"❌ 截取屏幕区域失败：{str(e)}")
        return []

    result = cv2.matchTemplate(screen_bgr, download_img, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= CONFIDENCE)

    buttons = []
    h, w = download_img.shape[:2]
    for pt in zip(*locations[::-1]):
        center_x = x1 + pt[0] + w // 2 + random.randint(-3, 3)
        center_y = y1 + pt[1] + h // 2 + random.randint(-3, 3)

        # 去重
        duplicate = False
        for (bx, by) in buttons:
            if abs(center_x - bx) < 35 and abs(center_y - by) < 35:
                duplicate = True
                break
        if not duplicate:
            buttons.append((center_x, center_y))

    buttons.sort(key=lambda p: p[1])
    buttons = buttons[:target_count]
    print(f"🔍 找到 {len(buttons)} 个下载按钮（目标：{target_count}个）")
    return buttons


def adjust_offset():
    """简化偏移调整（默认不调整，减少人工干预）"""
    global SERIAL_DOWNLOAD_DX, SERIAL_DOWNLOAD_DY
    print(f"\n📌 当前偏移：水平{SERIAL_DOWNLOAD_DX}px | 垂直{SERIAL_DOWNLOAD_DY}px")
    choice = input("是否调整偏移？（y/n，默认n）：").lower()
    if choice == 'y':
        try:
            dx = int(input(f"水平偏移（当前{SERIAL_DOWNLOAD_DX}）："))
            dy = int(input(f"垂直偏移（当前{SERIAL_DOWNLOAD_DY}）："))
            SERIAL_DOWNLOAD_DX = dx
            SERIAL_DOWNLOAD_DY = dy
            print(f"✅ 已更新偏移")
        except:
            print("❌ 输入无效，保持原偏移")


def click_download_button(btn_idx, pos):
    """颜色适配+人工模拟点击"""
    x, y = pos
    final_x = x + SERIAL_DOWNLOAD_DX + random.randint(-8, 8)
    final_y = y + SERIAL_DOWNLOAD_DY + random.randint(-8, 8)

    screen_w, screen_h = pyautogui.size()
    final_x = max(0, min(screen_w, final_x))
    final_y = max(0, min(screen_h, final_y))

    print(f"\n📥 下载第{btn_idx + 1}/{target_count}个（坐标：{int(final_x)},{int(final_y)}）")

    # 1. 模拟人类移动
    human_like_move_to(final_x, final_y)
    time.sleep(random.uniform(*HUMAN_STAY_DURATION))  # 随机停留

    # 2. 判断按钮颜色
    button_color = get_button_color(final_x, final_y)
    if button_color == "yellow":
        print("⚠️  检测到黄色下载按钮，需要人工验证！")
        print("请手动完成验证（如滑动验证），并确保文件开始下载后按回车继续...")
        input("👉 验证完成后按回车：")
        print("✅ 继续自动下载流程")
    elif button_color == "unknown":
        print("⚠️  按钮颜色未识别，按蓝色按钮逻辑尝试自动下载...")

    # 3. 随机点击方式（单击/双击）
    click_count = random.choice([1, 2])
    if click_count == 1:
        pyautogui.click()
        print(f"👆 执行单击操作")
    else:
        pyautogui.click(clicks=2, interval=random.uniform(*HUMAN_CLICK_INTERVAL))
        print(f"👆 执行双击操作（间隔：{random.uniform(*HUMAN_CLICK_INTERVAL):.2f}秒）")

    # 4. 等待下载完成
    start_time = time.time()
    while time.time() - start_time < DOWNLOAD_TIMEOUT:
        if detect_new_file():
            # 下载完成后随机间隔
            next_interval = random.uniform(*HUMAN_DOWNLOAD_INTERVAL)
            print(f"⌛ 下一个下载间隔 {next_interval:.1f} 秒...")
            time.sleep(next_interval)
            return True
        time.sleep(random.uniform(0.8, 1.2))  # 随机检测间隔

    print(f"❌ 第{btn_idx + 1}个下载超时（{DOWNLOAD_TIMEOUT}秒）")
    return False


# ==================== 键盘控制 ====================
def on_key_press(key):
    global is_running, is_paused
    try:
        if key == keyboard.Key.esc:
            print("\n⚠️  按ESC停止下载")
            is_running = False
            return False
        elif key == keyboard.Key.space:
            is_paused = not is_paused
            print(f"\n{'⏸️ 已暂停' if is_paused else '▶️ 继续下载'}")
        elif key == keyboard.Key.right and not is_paused:
            print("\n⚠️  下载过程中禁止手动翻页！请在当前页下载完成后操作")
        elif key == keyboard.Key.left and not is_paused:
            print("\n⚠️  下载过程中禁止手动翻页！请在当前页下载完成后操作")
    except Exception as e:
        print(f"\n❌ 键盘错误：{str(e)}")


# ==================== 页面处理 ====================
def process_single_page(download_img):
    """处理单页下载（下载时禁止翻页）"""
    global current_page_downloaded, retry_count
    current_page_downloaded = 0
    retry_count = 0

    print(f"\n" + "=" * 60)
    print(f"🚀 开始第{current_page}页下载（下载过程中禁止翻页）")
    print("=" * 60)

    while retry_count <= max_retry and is_running:
        adjust_offset()
        buttons = find_download_buttons_in_region(download_img)

        if len(buttons) >= target_count or retry_count == max_retry:
            break
        else:
            retry_count += 1
            print(f"⚠️  第{retry_count}次重试当前页（按钮数量不足）")
            time.sleep(random.uniform(1.5, 2.5))

    if len(buttons) == 0 and retry_count > max_retry:
        print("❌ 未找到任何下载按钮，跳过当前页")
        return False

    for idx, btn_pos in enumerate(buttons):
        while is_paused:
            time.sleep(0.5)
            if not is_running:
                return False
        if not is_running:
            return False

        # 每下载HUMAN_PAUSE_TRIGGER个随机休息
        if (idx + 1) % HUMAN_PAUSE_TRIGGER == 0 and idx != 0:
            human_like_pause()

        if click_download_button(idx, btn_pos):
            current_page_downloaded += 1
            global downloaded_count
            downloaded_count += 1

            if (current_page_downloaded % 3 == 0) and (idx + 1 < len(buttons)):
                print("🔄 自动滚动页面...")
                pyautogui.scroll(-SCROLL_STEP)
                time.sleep(SCROLL_DELAY)

    if current_page_downloaded >= target_count * 0.8:  # 允许20%误差
        print(f"\n🎉 第{current_page}页下载完成（{current_page_downloaded}/{target_count}个）")
        return True
    else:
        print(f"\n⚠️  第{current_page}页未完成（{current_page_downloaded}/{target_count}个）")
        return False


# ==================== 主程序 ====================
def main():
    # 声明使用的全局变量（关键修复：避免UnboundLocalError）
    global is_running, is_paused, downloaded_count, current_page

    print("=" * 75)
    print("📌 知网批量下载优化版（稳定坐标+可控翻页）")
    print("✅ 核心特性：")
    print("  1. 下载过程中禁止翻页，确保坐标稳定")
    print("  2. 翻页需手动确认，支持回退上一页")
    print("  3. 翻页后重新框选并确认区域，适配坐标变动")
    print("  4. 蓝色按钮→全自动下载，黄色按钮→人工验证提示")
    print("✅ 快捷键：ESC=停止 | 空格=暂停/继续")
    print("=" * 75)

    # 初始化
    init_download_path()
    download_img = load_download_icon()

    # 首次截图+框选+输入数量
    print("\n👉 准备就绪！请：")
    print("  1. 切换到知网页面（最大化、无遮挡）")
    print("  2. 按回车键开始截图")
    input()

    while is_running:
        if take_page_screenshot():
            if select_region_on_screenshot(TEMP_SCREENSHOT, is_first_page=True):
                if get_target_download_count(is_first_page=True):
                    break
        print("❌ 截图或框选失败，请重新操作！")
        time.sleep(2.0)

    # 启动键盘监听
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()

    try:
        while is_running:
            if is_paused:
                time.sleep(0.5)
                continue

            # 处理当前页下载
            page_done = process_single_page(download_img)

            if not is_running:
                break

            # 下载完成后询问是否翻页
            nav_choice = confirm_navigation()
            if nav_choice == "n":
                # 不翻页，询问是否继续下载当前页或停止
                continue_choice = input("👉 不翻页，是否继续下载当前页？（y=继续/n=停止）：").strip().lower()
                if continue_choice != "y":
                    print("⚠️  用户选择停止下载")
                    is_running = False
                    break
                else:
                    print(f"\n🔄 重新开始下载第{current_page}页...")
                    continue
            elif nav_choice == "prev":
                # 回退上一页
                if navigate_to_page("prev"):
                    # 回退后重新截图框选
                    retry = 0
                    while is_running and retry < 3:
                        if take_page_screenshot():
                            if select_region_on_screenshot(TEMP_SCREENSHOT, is_first_page=False):
                                if get_target_download_count(is_first_page=False):
                                    break
                        retry += 1
                        print(f"🔄 第{retry}次重试截图和框选...")
                        time.sleep(2.0)
                    else:
                        print("❌ 回退后截图/框选失败，停止脚本")
                        is_running = False
                        break
            elif nav_choice == "y":
                # 翻页到下一页
                if navigate_to_page("next"):
                    # 记录导航历史
                    page_nav_history.append(current_page)
                    # 翻页后重新截图框选
                    retry = 0
                    while is_running and retry < 3:
                        if take_page_screenshot():
                            if select_region_on_screenshot(TEMP_SCREENSHOT, is_first_page=False):
                                if get_target_download_count(is_first_page=False):
                                    break
                        retry += 1
                        print(f"🔄 第{retry}次重试截图和框选...")
                        time.sleep(2.0)
                    else:
                        print("❌ 翻页后截图/框选失败，停止脚本")
                        is_running = False
                        break

    except Exception as e:
        print(f"\n❌ 脚本错误：{str(e)}")
    finally:
        # 清理资源
        listener.stop()
        listener.join()
        if os.path.exists(TEMP_SCREENSHOT):
            os.remove(TEMP_SCREENSHOT)
        print(f"\n" + "=" * 50)
        print(f"📊 统计：处理{len(page_nav_history)}页 | 总下载{downloaded_count}个")
        print(f"📁 下载路径：{DOWNLOAD_PATH}")
        print("=" * 50)
        print("👋 脚本已退出")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ 用户手动停止")
        print(f"📊 总下载：{downloaded_count}个")
        if os.path.exists(TEMP_SCREENSHOT):
            os.remove(TEMP_SCREENSHOT)