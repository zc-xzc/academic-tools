import pyautogui
import time
import random
import os
import cv2
import numpy as np
from pynput import keyboard
from PIL import ImageGrab
from pathlib import Path

# ==================== 关键配置（简单明了）====================
DOWNLOAD_PATH = r"D:\Downloads"  # 下载路径
CONFIDENCE = 0.5  # 下载按钮识别置信度
SERIAL_DOWNLOAD_DX = 0  # 水平偏移（精准框选可设0）
SERIAL_DOWNLOAD_DY = 0  # 垂直偏移
FILE_MIN_SIZE = 1024  # 有效文件最小大小（1KB）
DOWNLOAD_TIMEOUT = 20  # 下载超时（秒）
SCROLL_STEP = 600  # 滚动距离
SCROLL_DELAY = 1.5  # 滚动等待时间
PAGE_LOAD_DELAY = 4.0  # 翻页加载时间
TEMP_SCREENSHOT = "temp_page_screenshot.png"  # 临时截图

# 全局状态
is_running = True
is_paused = False
current_page = 1
downloaded_count = 0
current_page_downloaded = 0
initial_files = set()
selected_region = None  # 框选区域（截图坐标）
target_count = 0  # 每页目标下载数
screen_ratio = (1.0, 1.0)  # 截图与屏幕比例
box_selected = False  # 框选完成标记


# ==================== 基础工具函数 ====================
def init_download_path():
    """初始化下载路径"""
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
    global initial_files
    initial_files = get_file_list(DOWNLOAD_PATH)
    print(f"✅ 下载路径：{DOWNLOAD_PATH}（初始文件数：{len(initial_files)}）")


def get_file_list(folder):
    """获取有效文件列表"""
    files = set()
    for f in os.listdir(folder):
        f_path = os.path.join(folder, f)
        if os.path.isfile(f_path) and os.path.getsize(f_path) >= FILE_MIN_SIZE:
            files.add((f, os.path.getsize(f_path)))
    return files


def detect_new_file():
    """检测新增下载文件"""
    current_files = get_file_list(DOWNLOAD_PATH)
    new_files = current_files - initial_files
    if new_files:
        new_file = sorted(new_files, key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_PATH, x[0])))[-1]
        print(f"✅ 新增文件：{new_file[0]}（{new_file[1] / 1024:.1f}KB）")
        initial_files.add(new_file)
        return True
    return False


def load_download_icon():
    """加载下载按钮截图（必须准备）"""
    path = "download_icon.png"
    if not os.path.exists(path):
        print(f"❌ 未找到 {path}！请截图知网下载按钮并保存到脚本文件夹")
        exit(1)
    img = cv2.imread(path)
    if img is None:
        print("❌ 下载按钮截图无效（格式错误或损坏）")
        exit(1)
    h, w = img.shape[:2]
    print(f"✅ 加载下载按钮截图：{w}x{h}像素")
    return img


# ==================== 截图与框选核心功能 ====================
def take_page_screenshot():
    """全屏截图并验证有效性"""
    print("\n" + "=" * 50)
    print("📸 正在截图当前页面...")
    print("⚠️  请确保知网页面在前台、最大化、无遮挡！")
    print("=" * 50)
    time.sleep(1.5)  # 给用户切换窗口的时间

    try:
        # 全屏截图
        screen = ImageGrab.grab()
        screen.save(TEMP_SCREENSHOT)

        # 验证截图
        if not os.path.exists(TEMP_SCREENSHOT) or os.path.getsize(TEMP_SCREENSHOT) < 10240:
            print("❌ 截图失败（文件过小或未生成）")
            return False

        # 计算截图与屏幕比例（确保坐标映射准确）
        screen_w, screen_h = pyautogui.size()
        img = cv2.imread(TEMP_SCREENSHOT)
        img_h, img_w = img.shape[:2]
        global screen_ratio
        screen_ratio = (screen_w / img_w, screen_h / img_h)

        print(f"✅ 截图成功：{TEMP_SCREENSHOT}（大小：{os.path.getsize(TEMP_SCREENSHOT) / 1024:.1f}KB）")
        print(f"📏 屏幕：{screen_w}x{screen_h} | 截图：{img_w}x{img_h} | 比例：{screen_ratio[0]:.2f}x")
        return True
    except Exception as e:
        print(f"❌ 截图出错：{str(e)}")
        return False


def select_region_on_screenshot(screenshot_path):
    """截图二次框选（无ctypes，稳定运行）"""
    global selected_region, box_selected
    box_selected = False
    ref_point = []  # 存储框选坐标：[(x1,y1), (x2,y2)]
    cropping = False

    # 读取截图
    img = cv2.imread(screenshot_path)
    if img is None:
        print("❌ 无法打开截图文件")
        return False
    img_copy = img.copy()  # 备份原始截图用于绘制提示

    # 绘制清晰的操作说明（避免用户不知道该做什么）
    cv2.putText(
        img_copy,
        "📌 框选操作说明：",
        (30, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (255, 0, 0),
        3
    )
    cv2.putText(
        img_copy,
        "1. 按住鼠标左键 → 拖动框选下载按钮区域",
        (30, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 0, 255),
        2
    )
    cv2.putText(
        img_copy,
        "2. 松开鼠标 → 按 ESC 键关闭窗口",
        (30, 150),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 0, 255),
        2
    )
    cv2.putText(
        img_copy,
        "⚠️  窗口可能在后台，按 Alt+Tab 切换",
        (30, 200),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2
    )

    def click_event(event, x, y, flags, param):
        """鼠标点击回调函数"""
        nonlocal ref_point, cropping, img_copy
        global box_selected

        # 左键按下：开始框选
        if event == cv2.EVENT_LBUTTONDOWN:
            ref_point = [(x, y)]
            cropping = True
            print(f"🔘 开始框选（坐标：{x},{y}）")

        # 左键松开：结束框选
        elif event == cv2.EVENT_LBUTTONUP:
            ref_point.append((x, y))
            cropping = False
            box_selected = True

            # 绘制绿色粗体框选矩形
            cv2.rectangle(img_copy, ref_point[0], ref_point[1], (0, 255, 0), 4)
            cv2.putText(
                img_copy,
                f"✅ 框选完成！区域：{ref_point[0]}→{ref_point[1]}",
                (30, 250),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2
            )
            cv2.imshow("知网下载区域框选", img_copy)
            print(f"✅ 框选确认（截图坐标）：{ref_point[0]}→{ref_point[1]}")

        # 鼠标移动：实时预览框选
        elif event == cv2.EVENT_MOUSEMOVE and cropping:
            temp_img = img_copy.copy()
            cv2.rectangle(temp_img, ref_point[0], (x, y), (0, 255, 0), 3)
            cv2.imshow("知网下载区域框选", temp_img)

    # 创建并显示框选窗口
    cv2.namedWindow("知网下载区域框选", cv2.WINDOW_NORMAL)
    cv2.imshow("知网下载区域框选", img_copy)
    cv2.setMouseCallback("知网下载区域框选", click_event)

    # 等待用户操作（60秒超时）
    timeout = 60
    start_time = time.time()
    while True:
        key = cv2.waitKey(1) & 0xFF
        elapsed = time.time() - start_time

        # 30秒超时提示
        if elapsed > 30 and not box_selected:
            cv2.putText(
                img_copy,
                f"⚠️ 已等待{int(elapsed)}秒！按 Alt+Tab 找到框选窗口",
                (30, 300),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2
            )
            cv2.imshow("知网下载区域框选", img_copy)

        # 60秒超时退出
        if elapsed > timeout:
            print("❌ 框选超时（60秒未操作）")
            cv2.destroyAllWindows()
            return False

        # ESC键关闭窗口
        if key == 27:
            break

    cv2.destroyAllWindows()

    # 处理框选结果
    if len(ref_point) == 2 and box_selected:
        x1 = min(ref_point[0][0], ref_point[1][0])
        y1 = min(ref_point[0][1], ref_point[1][1])
        x2 = max(ref_point[0][0], ref_point[1][0])
        y2 = max(ref_point[0][1], ref_point[1][1])

        selected_region = (x1, y1, x2, y2)
        print(f"✅ 最终框选区域：({x1},{y1})→({x2},{y2})")
        return True
    else:
        print("❌ 未完成有效框选")
        return False


def map_screenshot_to_screen(region):
    """将截图坐标映射到实际屏幕坐标"""
    x1, y1, x2, y2 = region
    screen_x1 = int(x1 * screen_ratio[0])
    screen_y1 = int(y1 * screen_ratio[1])
    screen_x2 = int(x2 * screen_ratio[0])
    screen_y2 = int(y2 * screen_ratio[1])
    print(f"📌 映射屏幕坐标：({screen_x1},{screen_y1})→({screen_x2},{screen_y2})")
    return (screen_x1, screen_y1, screen_x2, screen_y2)


def get_target_download_count():
    """让用户输入框选区域内的文献数量"""
    global target_count
    print("\n" + "=" * 50)
    print("📝 请输入框选区域内的文献数量")
    print("示例：框选了10个文献的下载按钮 → 输入10")
    print("=" * 50)
    while True:
        try:
            count = input("👉 输入文献数量：")
            target_count = int(count)
            if target_count > 0:
                print(f"✅ 已设置：每页下载{target_count}个文献")
                return True
            else:
                print("❌ 数量必须大于0，请重新输入")
        except ValueError:
            print("❌ 输入无效！请输入数字（如10）")


# ==================== 下载核心功能 ====================
def find_download_buttons_in_region(download_img):
    """在框选区域内查找下载按钮"""
    if not selected_region:
        print("❌ 未框选下载区域")
        return []

    # 映射截图坐标到屏幕坐标
    screen_region = map_screenshot_to_screen(selected_region)
    x1, y1, x2, y2 = screen_region

    try:
        # 截取屏幕上的目标区域
        screen = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        screen_np = np.array(screen)
        screen_bgr = cv2.cvtColor(screen_np, cv2.COLOR_RGB2BGR)
    except Exception as e:
        print(f"❌ 截取屏幕区域失败：{str(e)}")
        return []

    # 模板匹配查找下载按钮
    result = cv2.matchTemplate(screen_bgr, download_img, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= CONFIDENCE)

    # 提取按钮坐标并去重
    buttons = []
    h, w = download_img.shape[:2]
    for pt in zip(*locations[::-1]):
        center_x = x1 + pt[0] + w // 2
        center_y = y1 + pt[1] + h // 2

        # 去重：距离<30px视为同一按钮
        duplicate = False
        for (bx, by) in buttons:
            if abs(center_x - bx) < 30 and abs(center_y - by) < 30:
                duplicate = True
                break
        if not duplicate:
            buttons.append((center_x, center_y))

    # 按从上到下排序，取目标数量
    buttons.sort(key=lambda p: p[1])
    buttons = buttons[:target_count]
    print(f"🔍 找到 {len(buttons)} 个下载按钮（目标：{target_count}个）")
    return buttons


def adjust_offset():
    """调整下载按钮偏移（精准度优化）"""
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
    """点击下载按钮并验证下载结果"""
    x, y = pos
    # 应用偏移和随机微调（模拟人类操作）
    final_x = x + SERIAL_DOWNLOAD_DX + random.randint(-5, 5)
    final_y = y + SERIAL_DOWNLOAD_DY + random.randint(-3, 3)

    # 确保坐标在屏幕内
    screen_w, screen_h = pyautogui.size()
    final_x = max(0, min(screen_w, final_x))
    final_y = max(0, min(screen_h, final_y))

    print(f"\n📥 下载第{btn_idx + 1}/{target_count}个（坐标：{int(final_x)},{int(final_y)}）")

    # 模拟人类操作：平滑移动+停留+双击
    pyautogui.moveTo(final_x, final_y, duration=random.uniform(0.3, 0.7))
    time.sleep(random.uniform(0.3, 0.5))  # 停留确认位置
    pyautogui.click(clicks=2, interval=0.1)  # 双击确保触发下载

    # 等待下载完成并检测新增文件
    start_time = time.time()
    while time.time() - start_time < DOWNLOAD_TIMEOUT:
        if detect_new_file():
            print(f"✅ 第{btn_idx + 1}个下载成功")
            return True
        time.sleep(1.0)

    print(f"❌ 第{btn_idx + 1}个下载超时（{DOWNLOAD_TIMEOUT}秒未检测到文件）")
    return False


# ==================== 键盘控制 ====================
def on_key_press(key):
    """键盘快捷键控制"""
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
            print("\n📄 手动翻页...")
            next_page(manual=True)
    except Exception as e:
        print(f"\n❌ 键盘错误：{str(e)}")


# ==================== 页面处理 ====================
def process_single_page(download_img):
    """处理单页下载"""
    global current_page_downloaded
    current_page_downloaded = 0

    # 可选：调整偏移量
    adjust_offset()

    # 查找下载按钮
    buttons = find_download_buttons_in_region(download_img)
    if len(buttons) < target_count:
        print(f"⚠️ 找到的按钮数（{len(buttons)}）少于目标数（{target_count}）")
        print("建议：1. 扩大框选区域 2. 降低CONFIDENCE值 3. 重新截取下载按钮截图")
        return False

    # 按顺序下载每个按钮
    for idx, btn_pos in enumerate(buttons):
        # 处理暂停
        while is_paused:
            time.sleep(0.5)
            if not is_running:
                return False
        if not is_running:
            return False

        # 点击下载
        if click_download_button(idx, btn_pos):
            current_page_downloaded += 1
            global downloaded_count
            downloaded_count += 1

            # 每下载3个滚动一次页面（避免按钮超出可视区）
            if (current_page_downloaded % 3 == 0) and (idx + 1 < len(buttons)):
                print("🔄 自动滚动页面...")
                pyautogui.scroll(-SCROLL_STEP)
                time.sleep(SCROLL_DELAY)

    # 检查是否完成当前页
    if current_page_downloaded == target_count:
        print(f"\n🎉 第{current_page}页下载完成（{current_page_downloaded}/{target_count}个）")
        return True
    else:
        print(f"\n⚠️ 第{current_page}页未完成（{current_page_downloaded}/{target_count}个）")
        return False


def next_page(manual=False):
    """翻页并重置状态"""
    global current_page, selected_region, current_page_downloaded, box_selected
    print(f"\n📄 {'手动' if manual else '自动'}翻到第{current_page + 1}页...")

    # 翻页操作
    pyautogui.press('right')
    time.sleep(PAGE_LOAD_DELAY)

    # 重置当前页状态
    current_page += 1
    current_page_downloaded = 0
    selected_region = None
    box_selected = False

    # 删除旧截图
    if os.path.exists(TEMP_SCREENSHOT):
        os.remove(TEMP_SCREENSHOT)
        print(f"🗑️ 删除旧截图：{TEMP_SCREENSHOT}")

    print(f"✅ 已切换到第{current_page}页")

    # 新页面重新截图+框选
    if is_running and not manual:
        while is_running:
            if take_page_screenshot():
                if select_region_on_screenshot(TEMP_SCREENSHOT):
                    if get_target_download_count():
                        break
            print("🔄 重新尝试截图和框选...")
            time.sleep(2.0)
    return True


# ==================== 主程序 ====================
def main():
    print("=" * 75)
    print("📌 知网批量下载脚本（极简稳定版）")
    print("✅ 核心流程：截图 → 框选 → 输入数量 → 精准下载")
    print("✅ 解决问题：彻底移除ctypes错误，保证脚本稳定运行")
    print("✅ 快捷键：ESC=停止 | 空格=暂停/继续 | 右箭头=手动翻页")
    print("=" * 75)

    # 初始化
    init_download_path()
    download_img = load_download_icon()

    # 首次截图+框选（循环直到成功）
    print("\n👉 准备就绪！请按以下步骤操作：")
    print("  1. 切换到知网页面（最大化、无遮挡）")
    print("  2. 按回车键开始截图")
    input()

    # 确保截图和框选成功
    while is_running:
        if take_page_screenshot():
            if select_region_on_screenshot(TEMP_SCREENSHOT):
                if get_target_download_count():
                    break
        print("❌ 截图或框选失败，请重新操作！")
        time.sleep(2.0)

    # 启动键盘监听
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()
    print("\n🚀 开始第1页下载（按空格暂停，ESC停止）")

    try:
        while is_running:
            if is_paused:
                time.sleep(0.5)
                continue

            # 处理当前页
            page_done = process_single_page(download_img)

            if not is_running:
                break

            # 完成则自动翻页
            if page_done:
                print(f"\n👉 3秒后自动翻页（按ESC停止）")
                time.sleep(3.0)
                if not is_running:
                    break
                next_page()
            else:
                choice = input("\n是否重试当前页？（y/n，默认n）：").lower()
                if choice != 'y':
                    print("❌ 停止脚本")
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
        print(f"📊 统计：处理{current_page}页 | 总下载{downloaded_count}个")
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