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

# ==================== 核心配置（精准匹配专用） ====================
TARGET_BUTTONS = 10  # 固定10个按钮
DOWNLOAD_PATH = r"D:\Downloads"
CONFIDENCE = 0.35  # 精准匹配置信度（平衡精准度和成功率）
BUTTON_DUPLICATE_DISTANCE = 40  # 按钮间距阈值（适配知网常见间距）
EDGE_THRESHOLD = 100  # 边缘检测阈值（突出按钮轮廓）
TEMP_SCREENSHOT = "temp_screenshot.png"
WINDOW_TITLE = "框选下载按钮区域"
FILE_MIN_SIZE = 2048
DOWNLOAD_TIMEOUT = 30

# 时间设置（稳定优先，避免操作过快）
MOVE_DURATION = (0.4, 0.7)  # 鼠标移动时间（确保精准到位）
CLICK_DELAY = (0.6, 0.9)  # 点击前停留时间
DOWNLOAD_INTERVAL = (1.2, 1.8)  # 下载间隔

# 全局状态
is_running = True
is_paused = False
selected_region = None
downloaded_count = 0
screen_size = pyautogui.size()  # 屏幕实际尺寸


# ==================== 精准匹配工具函数 ====================
def get_system_scaling():
    """获取系统缩放，用于坐标校准"""
    try:
        user32 = ctypes.windll.user32
        dpi = user32.GetDpiForSystem()
        return dpi / 96.0
    except:
        return 1.0


def init_download_path():
    Path(DOWNLOAD_PATH).mkdir(exist_ok=True)
    print(f"✅ 下载路径：{DOWNLOAD_PATH}")


def load_and_process_template():
    """加载按钮模板并预处理（边缘检测+灰度化），提升匹配精度"""
    template_path = "download_icon.png"
    if not os.path.exists(template_path):
        print(f"❌ 未找到 {template_path}！")
        print("请按以下要求截图：")
        print("1. 只截下载按钮本身（25-30像素）")
        print("2. 确保按钮清晰，无模糊、无多余背景")
        print("3. 保存到脚本文件夹，命名为download_icon.png")
        exit(1)

    # 读取模板→灰度化→边缘检测（突出按钮轮廓，匹配更精准）
    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    if template is None:
        print("❌ 按钮截图无效，请重新截图")
        exit(1)

    # 边缘检测（关键优化：减少背景干扰，突出按钮形状）
    template_edge = cv2.Canny(template, EDGE_THRESHOLD // 2, EDGE_THRESHOLD)
    template_h, template_w = template_edge.shape[:2]

    # 校验模板尺寸（避免过小/过大导致匹配偏差）
    if not (20 <= template_w <= 40 and 20 <= template_h <= 40):
        print(f"⚠️ 按钮模板尺寸异常（{template_w}x{template_h}像素）")
        print("建议截图25-30像素的清晰按钮")
        input("👉 按回车继续（或重新截图后重试）...")

    print(f"✅ 加载模板成功（尺寸：{template_w}x{template_h}像素，已做边缘检测）")
    return template_edge, (template_w, template_h)


# ==================== 截图+框选（精准坐标映射） ====================
def take_precise_screenshot():
    """精准截图，确保与屏幕坐标一致"""
    print(f"\n📸 正在截图（请确保知网页面最大化，无遮挡，显示10个按钮）")
    time.sleep(1.2)  # 给用户切换窗口的时间
    try:
        # 截图整个屏幕，确保坐标完整
        screen = ImageGrab.grab(bbox=(0, 0, screen_size[0], screen_size[1]))
        screen.save(TEMP_SCREENSHOT)

        # 验证截图有效性
        if not os.path.exists(TEMP_SCREENSHOT) or os.path.getsize(TEMP_SCREENSHOT) < 10240:
            print("❌ 截图失败（可能被系统拦截）")
            return False

        print(f"✅ 截图成功（屏幕尺寸：{screen_size[0]}x{screen_size[1]}像素）")
        return True
    except Exception as e:
        print(f"❌ 截图失败：{str(e)}")
        return False


def select_precise_region():
    """框选区域，确保坐标精准映射"""
    global selected_region
    ref_point = []
    cropping = False

    # 读取截图（与屏幕尺寸一致）
    img = cv2.imread(TEMP_SCREENSHOT)
    if img is None:
        print("❌ 无法读取截图")
        return False

    img_copy = img.copy()
    img_h, img_w = img.shape[:2]

    # 绘制精准框选提示
    prompt = "按住左键框选10个按钮所在竖列 → 松开后按ESC关闭"
    cv2.putText(img_copy, prompt, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    cv2.putText(img_copy, "要求：刚好包含10个按钮，左右不留多余空白", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                (255, 0, 0), 2)

    def click_event(event, x, y, flags, param):
        nonlocal ref_point, cropping
        if event == cv2.EVENT_LBUTTONDOWN:
            ref_point = [(x, y)]
            cropping = True
        elif event == cv2.EVENT_LBUTTONUP:
            ref_point.append((x, y))
            cropping = False
            # 绘制框选矩形（粗线，方便确认）
            cv2.rectangle(img_copy, ref_point[0], ref_point[1], (0, 255, 0), 4)
            cv2.imshow(WINDOW_TITLE, img_copy)
        elif event == cv2.EVENT_MOUSEMOVE and cropping:
            # 实时预览框选区域
            temp_img = img_copy.copy()
            cv2.rectangle(temp_img, ref_point[0], (x, y), (0, 255, 0), 3)
            cv2.imshow(WINDOW_TITLE, temp_img)

    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_TITLE, img_w // 2, img_h // 2)  # 缩放窗口，方便操作
    cv2.imshow(WINDOW_TITLE, img_copy)
    cv2.setMouseCallback(WINDOW_TITLE, click_event)

    # 等待ESC关闭
    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break

    cv2.destroyAllWindows()

    # 处理框选区域（确保坐标正确，无颠倒）
    if len(ref_point) == 2:
        x1 = min(ref_point[0][0], ref_point[1][0])
        y1 = min(ref_point[0][1], ref_point[1][1])
        x2 = max(ref_point[0][0], ref_point[1][0])
        y2 = max(ref_point[0][1], ref_point[1][1])

        # 校验框选区域合理性（避免过宽/过窄）
        box_w = x2 - x1
        box_h = y2 - y1
        if box_w < 20 or box_w > 50:
            print(f"⚠️ 框选宽度异常（{box_w}像素），建议宽度25-40像素")
            return False

        selected_region = (x1, y1, x2, y2)
        print(f"✅ 框选区域：({x1},{y1})→({x2},{y2})（尺寸：{box_w}x{box_h}像素）")
        return True
    else:
        print("❌ 未完成有效框选")
        return False


# ==================== 核心：精准匹配10个按钮 ====================
def find_precise_10_buttons(template, template_size):
    """精准匹配按钮：边缘检测+精确坐标计算+严格去重"""
    template_edge, (template_w, template_h) = template, template_size
    x1, y1, x2, y2 = selected_region

    # 读取截图→截取ROI→预处理（与模板一致：灰度化+边缘检测）
    img = cv2.imread(TEMP_SCREENSHOT)
    roi = img[y1:y2, x1:x2]  # 截取框选区域
    roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    roi_edge = cv2.Canny(roi_gray, EDGE_THRESHOLD // 2, EDGE_THRESHOLD)  # 与模板预处理一致

    # 精准匹配（使用边缘检测后的图像，抗干扰能力强）
    result = cv2.matchTemplate(roi_edge, template_edge, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= CONFIDENCE)

    buttons = []
    for pt in zip(*locations[::-1]):
        # 精确计算按钮中心坐标（关键：模板中心=左上角+模板宽高/2）
        center_x = x1 + pt[0] + template_w // 2
        center_y = y1 + pt[1] + template_h // 2

        # 坐标边界校验（避免超出屏幕）
        center_x = max(20, min(screen_size[0] - 20, center_x))
        center_y = max(20, min(screen_size[1] - 20, center_y))

        # 严格去重：距离小于40像素视为同一按钮（适配知网按钮间距）
        duplicate = False
        for (bx, by) in buttons:
            if abs(center_x - bx) < BUTTON_DUPLICATE_DISTANCE and abs(center_y - by) < BUTTON_DUPLICATE_DISTANCE:
                duplicate = True
                break
        if not duplicate:
            buttons.append((center_x, center_y))
            print(f"🔍 匹配到按钮：({center_x:.0f},{center_y:.0f})")

    # 按Y坐标排序（从上到下，符合阅读习惯）
    buttons.sort(key=lambda x: x[1])

    # 确保取前10个
    if len(buttons) >= TARGET_BUTTONS:
        selected_buttons = buttons[:TARGET_BUTTONS]
        print(f"\n✅ 成功匹配到{len(buttons)}个按钮，选择前10个（从上到下）")
        for i, (x, y) in enumerate(selected_buttons, 1):
            print(f"  按钮{i}：({x},{y})")
        return selected_buttons
    else:
        print(f"\n❌ 框选区域内只找到{len(buttons)}个按钮（需要10个）")
        print("可能原因：")
        print("1. 框选区域未包含所有10个按钮")
        print("2. 按钮模板与实际按钮差异过大（重新截图）")
        print("3. 按钮被遮挡或页面未完全加载")
        return None


# ==================== 精准下载函数 ====================
def precise_move_and_click(x, y):
    """精准移动到按钮并点击（确保命中）"""
    try:
        # 精准移动（使用easeInOutQuad缓动，模拟人工操作）
        pyautogui.FAILSAFE = False
        duration = random.uniform(*MOVE_DURATION)
        pyautogui.moveTo(x, y, duration=duration, tween=pyautogui.easeInOutQuad)
        print(f"📍 移动到 ({x},{y})（耗时{duration:.2f}秒）")

        # 点击前停留，确保稳定
        time.sleep(random.uniform(*CLICK_DELAY))

        # 单击（知网下载按钮默认单击有效）
        pyautogui.click()
        print("👆 已精准点击按钮")
        return True
    except Exception as e:
        print(f"❌ 操作失败：{str(e)}")
        return False


def download_single_button(btn_idx, x, y):
    """下载单个按钮（精准版）"""
    print(f"\n📥 下载第{btn_idx + 1}/{TARGET_BUTTONS}个按钮（坐标：{x},{y}）")

    # 精准移动并点击
    if not precise_move_and_click(x, y):
        return False

    # 等待文件下载完成
    start_time = time.time()
    initial_files = set(os.listdir(DOWNLOAD_PATH))

    while time.time() - start_time < DOWNLOAD_TIMEOUT:
        current_files = set(os.listdir(DOWNLOAD_PATH))
        new_files = current_files - initial_files

        # 过滤临时文件和小文件
        valid_new_files = []
        for f in new_files:
            f_path = os.path.join(DOWNLOAD_PATH, f)
            if os.path.isfile(f_path) and not f.endswith(('.crdownload', '.part', '.tmp')):
                file_size = os.path.getsize(f_path)
                if file_size >= FILE_MIN_SIZE:
                    valid_new_files.append((f, file_size))

        if valid_new_files:
            # 取最新的有效文件
            valid_new_files.sort(key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_PATH, x[0])))
            new_file, file_size = valid_new_files[-1]
            print(f"✅ 下载成功：{new_file}（{file_size / 1024:.1f}KB）")

            # 下载间隔
            time.sleep(random.uniform(*DOWNLOAD_INTERVAL))
            return True

        time.sleep(1.2)  # 每隔1.2秒检查一次

    print(f"❌ 下载超时（{DOWNLOAD_TIMEOUT}秒）")
    return False


# ==================== 键盘控制（保持简单） ====================
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
    except:
        pass


# ==================== 主程序（精准+简单流程） ====================
def main():
    global is_running, downloaded_count
    system_scaling = get_system_scaling()
    print("=" * 65)
    print("📌 知网10按钮精准下载器（定位优化版）")
    print("✅ 核心优势：边缘检测匹配+精准坐标计算+稳定操作")
    print("✅ 快捷键：ESC=停止 | 空格=暂停/继续")
    print(f"✅ 系统信息：屏幕尺寸{screen_size[0]}x{screen_size[1]}像素，缩放{system_scaling:.2f}x")
    print("=" * 65)

    # 管理员提示（必须，否则鼠标控制失效）
    print("\n⚠️  请确保已以管理员身份运行脚本！")
    input("👉 确认后按回车开始...")

    # 初始化
    init_download_path()
    template, template_size = load_and_process_template()

    # 截图+框选（确保精准）
    while is_running:
        if take_precise_screenshot() and select_precise_region():
            break
        print("🔄 重新尝试截图框选...")
        time.sleep(2)

    # 匹配10个按钮（精准匹配）
    buttons = None
    while is_running and not buttons:
        buttons = find_precise_10_buttons(template, template_size)
        if not buttons:
            input("👉 按回车重新框选...")
            while is_running:
                if take_precise_screenshot() and select_precise_region():
                    break

    # 开始下载
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()
    print(f"\n🚀 开始下载10个文件（精准模式）...")

    try:
        for idx, (x, y) in enumerate(buttons):
            if not is_running:
                break
            while is_paused:
                time.sleep(0.5)
            if download_single_button(idx, x, y):
                downloaded_count += 1
        print(f"\n🎉 下载任务结束！共下载{downloaded_count}/{TARGET_BUTTONS}个文件")
    finally:
        listener.stop()
        listener.join()
        # 清理临时截图
        if os.path.exists(TEMP_SCREENSHOT):
            os.remove(TEMP_SCREENSHOT)
        print(f"\n📁 下载路径：{DOWNLOAD_PATH}")
        print("👋 脚本退出")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ 用户手动停止")
        if os.path.exists(TEMP_SCREENSHOT):
            os.remove(TEMP_SCREENSHOT)
        print(f"📊 已下载：{downloaded_count}/{TARGET_BUTTONS}个文件")