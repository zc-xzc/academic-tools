import pyautogui
import time
import random
import os
import cv2
import numpy as np
from pynput import keyboard, mouse
from PIL import ImageGrab, ImageEnhance
from pathlib import Path

# ==================== 1. 核心配置（全局变量）====================
SCREEN_WIDTH, SCREEN_HEIGHT = 2560, 1680  # 你的分辨率
DOWNLOAD_PATH = r"D:\Downloads"
DOWNLOAD_ICON_PATH = "download_icon.png"  # 同目录模板

# 识别参数（微调即可）
TEMPLATE_CONFIDENCE = 0.65  # 模板匹配阈值（0.6-0.7最佳）
SEARCH_X_RANGE = 20  # 只在第一个按钮X±20像素内搜索（避免跨列）
SCROLL_STEP = 500  # 页面滚动步长
DOWNLOAD_TIMEOUT = 25  # 下载超时
PAGE_LOAD_DELAY = 4  # 翻页后加载时间

# 全局状态
is_running = True
is_paused = False
first_btn_pos = None  # 用户手动点击的第一个按钮坐标 (X,Y)
download_col_x = None  # 下载列固定X坐标


# ==================== 2. 图像增强（确保模板清晰）====================
def enhance_template():
    """增强下载按钮模板，返回灰度增强图"""
    if not os.path.exists(DOWNLOAD_ICON_PATH):
        print(f"❌ 未找到模板：{DOWNLOAD_ICON_PATH}")
        exit(1)

    # 读取→灰度→高对比度→锐化
    img = cv2.imread(DOWNLOAD_ICON_PATH)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    contrast = cv2.convertScaleAbs(gray, alpha=2.2, beta=35)  # 增强对比度
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharpened = cv2.filter2D(contrast, -1, kernel)

    # 保存增强模板（检查效果）
    cv2.imwrite("enhanced_template.png", sharpened)
    print(f"✅ 模板增强完成：enhanced_template.png（高对比度+锐化）")
    return sharpened, img.shape[:2]  # 返回模板+模板尺寸 (h,w)


# ==================== 3. 手动选择第一个按钮（核心精准定位）====================
def select_first_button():
    """让用户手动点击第一个下载按钮，返回坐标 (X,Y)"""
    global first_btn_pos, download_col_x
    print("\n" + "=" * 50)
    print("📌 请手动选择第一个下载按钮")
    print("👉 3秒后，将鼠标移动到第一个下载按钮上，按【鼠标左键】确认！")
    print("=" * 50)
    time.sleep(3)

    # 监听鼠标左键点击
    def on_click(x, y, button, pressed):
        if pressed and button == mouse.Button.left:
            global first_btn_pos, download_col_x
            first_btn_pos = (x, y)
            download_col_x = x  # 固定下载列X坐标
            print(f"✅ 已确认第一个按钮坐标：({x},{y})")
            return False  # 停止监听

    with mouse.Listener(on_click=on_click) as listener:
        listener.join()

    if not first_btn_pos:
        print("❌ 未选择按钮，脚本退出")
        exit(1)
    return first_btn_pos


# ==================== 4. 核心功能：识别同列所有按钮（支持滚动）====================
def find_all_buttons_in_column(template, template_size):
    """基于第一个按钮的X列，识别页面内所有下载按钮（支持滚动）"""
    template_h, template_w = template_size
    buttons = []
    processed_y = set()  # 记录已处理的Y坐标（避免重复）

    # 初始可视区Y范围
    current_top_y = 0
    current_bottom_y = SCREEN_HEIGHT

    while is_running:
        # 1. 截图当前可视区（只截下载列附近，减少干扰）
        search_x1 = max(0, download_col_x - SEARCH_X_RANGE)
        search_x2 = min(SCREEN_WIDTH, download_col_x + SEARCH_X_RANGE)
        try:
            screen = ImageGrab.grab(bbox=(search_x1, current_top_y, search_x2, current_bottom_y))
        except Exception as e:
            print(f"⚠️ 截图失败：{e}")
            time.sleep(1)
            continue

        # 2. 增强截图+模板匹配
        screen_gray = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2GRAY)
        # 去噪+对比度增强（减少页面干扰）
        screen_denoised = cv2.GaussianBlur(screen_gray, (3, 3), 0)
        screen_enhanced = cv2.convertScaleAbs(screen_denoised, alpha=1.8, beta=25)

        # 3. 匹配当前可视区的按钮
        result = cv2.matchTemplate(screen_enhanced, template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= TEMPLATE_CONFIDENCE)

        for pt in zip(*locations[::-1]):
            # 转换为屏幕绝对坐标
            btn_x = search_x1 + pt[0] + template_w // 2
            btn_y = current_top_y + pt[1] + template_h // 2

            # 去重：Y坐标差<15视为同一按钮
            y_key = round(btn_y / 15) * 15
            if y_key not in processed_y:
                processed_y.add(y_key)
                buttons.append((btn_x, btn_y))
                print(f"🔍 找到按钮：({int(btn_x)},{int(btn_y)})")

        # 4. 判断是否需要滚动页面（检查是否有未处理的区域）
        # 滚动条件：当前可视区底部 < 屏幕高度，且最后一个按钮接近底部
        if current_bottom_y < SCREEN_HEIGHT * 2:  # 限制最大滚动范围（避免无限滚动）
            last_btn_y = max([btn[1] for btn in buttons]) if buttons else 0
            if last_btn_y > current_bottom_y - 200:  # 最后一个按钮接近底部
                print(f"🔄 滚动页面（当前底部Y：{current_bottom_y}）")
                pyautogui.scroll(-SCROLL_STEP)  # 向下滚动
                time.sleep(1.5)  # 等待页面稳定
                current_top_y += SCROLL_STEP
                current_bottom_y += SCROLL_STEP
                continue

        # 5. 停止条件：无新按钮或滚动到最大范围
        break

    # 按Y坐标排序（从上到下）
    buttons.sort(key=lambda p: p[1])
    print(f"\n✅ 共找到 {len(buttons)} 个按钮（已去重）")
    return buttons


# ==================== 5. 下载执行（支持暂停+重试）====================
def init_file_count():
    """初始化文件计数（避免重复统计）"""
    valid_files = set()
    for f in os.listdir(DOWNLOAD_PATH):
        f_path = os.path.join(folder, f)
        if os.path.isfile(f_path) and os.path.getsize(f_path) >= 2048:
            valid_files.add((f, os.path.getsize(f_path)))
    return valid_files, len(valid_files)


def detect_new_file(initial_files):
    """检测新增下载文件"""
    current_files = set()
    for f in os.listdir(DOWNLOAD_PATH):
        f_path = os.path.join(DOWNLOAD_PATH, f)
        if os.path.isfile(f_path) and os.path.getsize(f_path) >= 2048:
            current_files.add((f, os.path.getsize(f_path)))
    new_files = current_files - initial_files
    if new_files:
        new_file = sorted(new_files, key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_PATH, x[0])))[-1]
        print(f"✅ 下载成功：{new_file[0]}（{new_file[1] / 1024:.1f}KB）")
        initial_files.add(new_file)
        return True
    return False


def download_single_button(btn_pos, btn_idx, initial_files):
    """下载单个按钮（支持暂停+重试）"""
    x, y = btn_pos
    retry = 0
    while retry < 2 and is_running:
        # 处理暂停
        while is_paused:
            time.sleep(0.5)
            if not is_running:
                return False

        try:
            # 模拟人类操作：随机偏移+平滑移动
            offset_x = random.randint(-3, 3)
            offset_y = random.randint(-3, 3)
            final_x = x + offset_x
            final_y = y + offset_y

            pyautogui.moveTo(final_x, final_y, duration=random.uniform(0.3, 0.6))
            time.sleep(random.uniform(0.2, 0.4))  # 停留确认
            pyautogui.click()
            print(f"\n【第{btn_idx + 1}个】点击坐标：({int(final_x)},{int(final_y)})")

            # 等待下载完成
            start_time = time.time()
            while time.time() - start_time < DOWNLOAD_TIMEOUT:
                if detect_new_file(initial_files):
                    time.sleep(1.5)  # 防反爬间隔
                    return True
                time.sleep(0.5)
            print(f"⚠️ 超时，重试第{retry + 1}次")
        except Exception as e:
            print(f"⚠️ 下载出错：{e}，重试第{retry + 1}次")

        retry += 1
        time.sleep(1)

    print(f"❌ 第{btn_idx + 1}个下载失败（已重试2次）")
    return False


# ==================== 6. 自动翻页（下载完当前页后执行）====================
def auto_turn_next_page():
    """自动点击下一页按钮（适配知网默认翻页按钮位置）"""
    print(f"\n" + "=" * 50)
    print(f"📄 当前页下载完成，准备翻到下一页")
    print("=" * 50)

    # 知网列表页下一页按钮通常在页面底部居中（可根据实际调整坐标）
    # 若坐标不准：手动点击下一页后，用pyautogui.position()查看坐标并修改
    next_page_pos = (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 80)  # 底部居中

    # 点击翻页
    pyautogui.moveTo(next_page_pos[0], next_page_pos[1], duration=0.5)
    time.sleep(0.3)
    pyautogui.click()
    print(f"✅ 已点击下一页按钮（坐标：{next_page_pos}）")

    # 等待页面加载
    print(f"⌛ 等待页面加载...（{PAGE_LOAD_DELAY}秒）")
    time.sleep(PAGE_LOAD_DELAY)

    # 重置全局状态，准备下一页
    global first_btn_pos
    first_btn_pos = None
    return True


# ==================== 7. 键盘控制（暂停/停止）====================
def on_key_press(key):
    global is_running, is_paused
    try:
        if key == keyboard.Key.esc:
            print("\n⚠️ 按ESC停止下载")
            is_running = False
            return False
        elif key == keyboard.Key.space:
            is_paused = not is_paused
            print(f"\n{'⏸️ 已暂停' if is_paused else '▶️ 继续下载'}")
    except:
        pass


# ==================== 8. 主流程（清晰易懂）====================
def main():
    global is_running

    print("=" * 70)
    print("📌 知网下载脚本（手动定位版）")
    print("✅ 核心流程：手动点第一个按钮→自动找其他→下载→自动翻页")
    print("⌨️  快捷键：ESC=停止 | 空格=暂停/继续")
    print("=" * 70)

    # 1. 初始化：增强模板+文件计数
    template, template_size = enhance_template()
    initial_files, initial_count = init_file_count()
    print(f"✅ 初始文件数：{initial_count}（{DOWNLOAD_PATH}）")

    # 2. 启动键盘监听
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()

    try:
        page_num = 1
        while is_running:
            print(f"\n" + "=" * 60)
            print(f"🚀 开始处理第{page_num}页")
            print("=" * 60)

            # 3. 手动选择第一个按钮
            select_first_button()

            # 4. 识别同列所有按钮（支持滚动）
            buttons = find_all_buttons_in_column(template, template_size)
            if len(buttons) == 0:
                print("❌ 未找到任何按钮，脚本退出")
                break

            # 5. 逐个下载
            success_count = 0
            for idx, btn in enumerate(buttons):
                if not is_running:
                    break
                if download_single_button(btn, idx, initial_files):
                    success_count += 1

            # 6. 当前页统计
            print(f"\n" + "=" * 50)
            print(f"📊 第{page_num}页统计：成功{success_count}/{len(buttons)}个")
            print("=" * 50)

            # 7. 自动翻页（用户可按ESC停止）
            if is_running:
                if not auto_turn_next_page():
                    print("❌ 翻页失败，脚本退出")
                    break
                page_num += 1

    finally:
        # 最终统计
        final_files = set()
        for f in os.listdir(DOWNLOAD_PATH):
            f_path = os.path.join(DOWNLOAD_PATH, f)
            if os.path.isfile(f_path) and os.path.getsize(f_path) >= 2048:
                final_files.add((f, os.path.getsize(f_path)))
        total_downloaded = len(final_files) - initial_count

        listener.stop()
        print(f"\n" + "=" * 50)
        print(f"📊 最终统计：")
        print(f"   处理页数：{page_num}页")
        print(f"   累计下载：{total_downloaded}个文件")
        print(f"   下载路径：{DOWNLOAD_PATH}")
        print("=" * 50)
        print("👋 脚本已退出")


if __name__ == "__main__":
    # 修复：处理文件夹变量名错误
    folder = DOWNLOAD_PATH  # 补充folder变量定义（之前init_file_count中用到）
    main()