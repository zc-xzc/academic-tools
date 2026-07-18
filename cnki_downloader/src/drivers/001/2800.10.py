import os
import cv2
import numpy as np
import pyautogui
import time
import random
import keyboard  # 确保安装的是 python-keyboard 库
from PIL import ImageGrab
from pathlib import Path

# 配置参数
DOWNLOAD_PATH = "downloads"  # 下载文件保存路径
TEMPLATE_PATH = "download_icon.png"  # 下载图标模板路径（确保此文件在运行目录）
CONFIDENCE = 0.7  # 匹配置信度
OFFSET_TOLERANCE = 5  # 点击偏移公差（像素）
DOWNLOAD_TIMEOUT = 10  # 单个文件下载超时（秒）
PAGE_TURN_DELAY = 2  # 翻页后等待时间（秒）
SCREENSHOT_DELAY = 1  # 截图后等待时间（秒）

# 全局变量
is_running = True
is_paused = False
downloaded_total = 0
download_region = None  # 下载按钮区域 (x1, y1, x2, y2)
scaling_factor = 1.0  # 屏幕缩放因子


def get_scaling_factor():
    """获取屏幕缩放比例"""
    import ctypes
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    physical_size = (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    logical_size = pyautogui.size()
    return round(logical_size[0] / physical_size[0], 2)


def capture_screen(region=None):
    """截取屏幕图像，可选区域（x1,y1,x2,y2）"""
    if region:
        x1, y1, x2, y2 = region
        screen = ImageGrab.grab(bbox=(x1, y1, x2, y2))
    else:
        screen = ImageGrab.grab()
    return cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)


def select_download_region():
    """让用户手动框选下载按钮所在的列"""
    global download_region
    screen_img = capture_screen()
    img_h, img_w = screen_img.shape[:2]
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
            cv2.rectangle(screen_img, ref_point[0], ref_point[1], (0, 255, 0), 2)
            cv2.imshow("框选下载按钮所在列（宽度约30像素）", screen_img)
        elif event == cv2.EVENT_MOUSEMOVE and cropping:
            temp_img = screen_img.copy()
            cv2.rectangle(temp_img, ref_point[0], (x, y), (0, 255, 0), 2)
            cv2.imshow("框选下载按钮所在列（宽度约30像素）", temp_img)

    cv2.namedWindow("框选下载按钮所在列（宽度约30像素）", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("框选下载按钮所在列（宽度约30像素）", img_w // 2, img_h // 2)
    cv2.imshow("框选下载按钮所在列（宽度约30像素）", screen_img)
    cv2.setMouseCallback("框选下载按钮所在列（宽度约30像素）", click_event)

    print("请框选包含所有下载按钮的列（宽度约30像素），完成后按任意键继续")
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    if len(ref_point) == 2:
        x1, y1 = ref_point[0]
        x2, y2 = ref_point[1]
        # 确保区域坐标正确（左上角和右下角）
        download_region = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        print(f"已选择下载区域：{download_region}")
        return True
    else:
        print("框选失败，请重新运行程序")
        return False


def find_download_buttons(template, screen_img):
    """在指定区域识别下载按钮，返回中心坐标列表"""
    if not download_region:
        return []

    x1, y1, x2, y2 = download_region
    roi = screen_img[y1:y2, x1:x2]  # 提取感兴趣区域（用户框选的列）

    # 预处理图像以提高识别率
    gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

    # 多尺度匹配以适应不同大小
    buttons = []
    template_h, template_w = gray_template.shape[:2]

    # 尝试不同缩放比例（解决图标大小可能的细微差异）
    for scale in [0.9, 1.0, 1.1]:
        scaled_template = cv2.resize(gray_template,
                                     (int(template_w * scale), int(template_h * scale)))
        s_h, s_w = scaled_template.shape[:2]

        if s_h > gray_roi.shape[0] or s_w > gray_roi.shape[1]:
            continue

        result = cv2.matchTemplate(gray_roi, scaled_template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= CONFIDENCE)  # 筛选置信度以上的匹配

        # 计算按钮中心坐标（转换为全局坐标）
        for pt in zip(*locations[::-1]):
            center_x = x1 + pt[0] + s_w // 2  # 区域内x坐标 + 区域起始x
            center_y = y1 + pt[1] + s_h // 2  # 区域内y坐标 + 区域起始y
            buttons.append((round(center_x), round(center_y)))

    # 去重并按Y坐标排序（确保从上到下识别）
    if not buttons:
        return []

    # 按Y坐标排序（从上到下）
    buttons.sort(key=lambda x: x[1])

    # 去重处理（避免同一按钮被多次识别，考虑图标高度的1/2作为阈值）
    unique_buttons = [buttons[0]]
    for btn in buttons[1:]:
        last_btn = unique_buttons[-1]
        if btn[1] - last_btn[1] > template_h // 2:  # 超过半个图标高度视为新按钮
            unique_buttons.append(btn)

    return unique_buttons


def download_buttons(buttons, template):
    """下载指定的按钮，返回成功数量"""
    global downloaded_total
    success_count = 0
    template_h = template.shape[0]  # 图标高度（用于误差补偿参考）

    # 记录初始文件数量（用于检测新下载的文件）
    initial_files = set(os.listdir(DOWNLOAD_PATH))

    for i, (x, y) in enumerate(buttons):
        if not is_running:
            break
        while is_paused:
            time.sleep(0.5)  # 暂停时等待

        print(f"\n下载第{i + 1}个按钮（坐标：{x},{y}）")
        success = False

        # 尝试不同偏移量点击（解决定位误差累积问题）
        for dy in range(-OFFSET_TOLERANCE, OFFSET_TOLERANCE + 1, 2):
            try_y = y + dy  # 补偿y方向误差
            pyautogui.moveTo(x, try_y, duration=random.uniform(0.1, 0.3))  # 模拟人工移动
            pyautogui.click()
            time.sleep(1)  # 等待点击响应

            # 检查是否有新文件开始下载（临时文件）
            current_files = set(os.listdir(DOWNLOAD_PATH))
            new_files = [f for f in current_files - initial_files
                         if f.endswith(('.crdownload', '.part', '.tmp'))]  # 浏览器临时文件后缀

            if new_files:
                # 等待下载完成（临时文件消失）
                start_time = time.time()
                while time.time() - start_time < DOWNLOAD_TIMEOUT:
                    completed_files = [f for f in os.listdir(DOWNLOAD_PATH)
                                       if f not in initial_files and
                                       not f.endswith(('.crdownload', '.part', '.tmp'))]
                    if completed_files:
                        print(f"✅ 下载成功（偏移补偿：{dy}px）")
                        success = True
                        success_count += 1
                        downloaded_total += 1
                        initial_files.add(completed_files[0])  # 记录已完成文件
                        break
                    time.sleep(0.5)
                if success:
                    break  # 成功后退出偏移尝试

        if not success:
            print(f"❌ 下载失败")

        # 随机延迟，避免被网站检测为自动化工具
        time.sleep(random.uniform(0.5, 1.0))

    return success_count


def turn_page():
    """使用右键翻页（适配知网页面）"""
    print("\n尝试翻页...")
    # 点击页面中间位置激活窗口（确保翻页操作生效）
    screen_width, screen_height = pyautogui.size()
    pyautogui.click(screen_width // 2, screen_height // 2)
    time.sleep(0.5)

    # 按右键翻页（知网支持右键翻页）
    pyautogui.press('right')
    time.sleep(PAGE_TURN_DELAY)  # 等待页面加载
    return True


def setup_hotkeys():
    """设置快捷键（替换Listener的实现方式）"""
    global is_running, is_paused

    # ESC键停止
    keyboard.add_hotkey('esc', lambda: setattr(globals(), 'is_running', False))

    # 空格键暂停/继续
    def toggle_pause():
        global is_paused
        is_paused = not is_paused
        print(f"\n{'⏸️ 已暂停' if is_paused else '▶️ 继续下载'}")

    keyboard.add_hotkey('space', toggle_pause)


def main():
    global scaling_factor
    print("=" * 80)
    print("📌 知网批量下载器")
    print("✅ 功能：自动识别下载按钮，批量下载多页内容")
    print("✅ 快捷键：ESC=停止 | 空格=暂停/继续")
    print("=" * 80)

    # 初始化屏幕缩放比例
    scaling_factor = get_scaling_factor()
    print(f"屏幕缩放比例：{scaling_factor:.2f}x")

    # 创建下载目录
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
    print(f"下载路径：{os.path.abspath(DOWNLOAD_PATH)}")

    # 检查模板文件（下载图标）
    if not os.path.exists(TEMPLATE_PATH):
        print(f"❌ 未找到下载图标模板：{TEMPLATE_PATH}，请将图标文件放在运行目录")
        return

    template = cv2.imread(TEMPLATE_PATH)
    if template is None:
        print(f"❌ 无法加载模板图片：{TEMPLATE_PATH}")
        return

    # 让用户框选下载按钮所在列（第一页手动框选，后续自动复用）
    if not select_download_region():
        return

    # 设置快捷键（替换原来的Listener）
    setup_hotkeys()

    page_num = 1
    try:
        while is_running:
            print(f"\n{'=' * 60}")
            print(f"📄 开始处理第{page_num}页")

            # 截取当前页面
            print("截取页面图像...")
            screen_img = capture_screen()
            time.sleep(SCREENSHOT_DELAY)

            # 识别下载按钮
            buttons = find_download_buttons(template, screen_img)
            print(f"识别到{len(buttons)}个下载按钮")

            # 验证当前页按钮数量（预期10个）
            if len(buttons) != 10:
                print(f"⚠️ 警告：本页识别到{len(buttons)}个按钮，预期10个")
                if input("是否继续？(y/n)").lower() != 'y':
                    break

            # 执行下载
            success_count = download_buttons(buttons, template)
            print(f"第{page_num}页下载完成：成功{success_count}/{len(buttons)}个")

            # 验证下载成功数量
            if success_count != 10:
                print(f"⚠️ 警告：本页成功下载{success_count}个，预期10个")
                if input("是否继续翻页？(y/n)").lower() != 'y':
                    break

            # 翻页（右键）
            if not turn_page():
                print("❌ 翻页失败，任务结束")
                break

            page_num += 1

    finally:
        print("\n" + "=" * 70)
        print(f"🎉 下载任务结束，共下载{downloaded_total}个文件")
        print(f"📁 文件保存路径：{os.path.abspath(DOWNLOAD_PATH)}")
        print("=" * 70)


if __name__ == "__main__":
    main()