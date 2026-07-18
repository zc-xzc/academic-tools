import pyautogui
import time
import random
import os  # 新增os模块导入
import cv2
import numpy as np
from pynput import keyboard, mouse
from PIL import ImageGrab

# ==================== 配置参数（根据实际情况修改）====================
ICON_PATH = "download_icon.png"  # 下载图标截图路径（必须准备！）
CLOSE_POPUP_PATH = "close_popup.png"  # 下载成功弹窗关闭按钮截图（无则设为None）
VERIFY_ICON_PATH = "verify_icon.png"  # 验证场景特征图（无则设为None）
CONFIDENCE = 0.8  # 图像识别置信度（0-1，越高越精准）
SCAN_REGION = None  # 扫描区域（None=全屏，格式：(x1,y1,x2,y2)）
MIN_CLICK_DELAY = 1.5  # 点击后最小等待时间（秒）
MAX_CLICK_DELAY = 3.0  # 点击后最大等待时间（秒）
MIN_SCROLL_STEP = 300  # 最小滚动距离（像素）
MAX_SCROLL_STEP = 500  # 最大滚动距离（像素）
SCROLL_DELAY = 1.5  # 滚动后等待页面加载时间（秒）
HESITATE_PROB = 0.1  # 10%概率犹豫（模拟人类）
MIN_HESITATE = 0.3  # 犹豫最小时间（秒）
MAX_HESITATE = 1.0  # 犹豫最大时间（秒）
MOUSE_OFFSET_RANGE = 2  # 鼠标点击随机偏移（像素）
# ====================================================================

# 全局状态变量
is_running = True  # 是否运行
is_paused = False  # 是否暂停
is_verifying = False  # 是否处于验证状态
current_download_idx = 1  # 当前下载序号
start_icon_pos = None  # 起始下载按钮位置（用户选定或自动识别）
scanned_positions = set()  # 已扫描过的按钮位置（避免重复点击）


def load_image(path):
    """加载图像（用于图像识别）"""
    if not path or not os.path.exists(path):
        return None
    img = cv2.imread(path)
    if img is None:
        print(f"⚠️  无法加载图像：{path}")
    return img


# 预加载识别图像
DOWNLOAD_ICON = load_image(ICON_PATH)
CLOSE_POPUP_ICON = load_image(CLOSE_POPUP_PATH)
VERIFY_ICON = load_image(VERIFY_ICON_PATH)


def find_image_on_screen(target_img, confidence=CONFIDENCE, region=SCAN_REGION):
    """在屏幕上查找目标图像，返回中心点坐标列表（[(x,y), ...]或None）"""
    if target_img is None:
        return None
    # 截取屏幕图像
    screen = ImageGrab.grab(bbox=region)
    screen_np = np.array(screen)
    screen_bgr = cv2.cvtColor(screen_np, cv2.COLOR_RGB2BGR)

    # 模板匹配
    result = cv2.matchTemplate(screen_bgr, target_img, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= confidence)

    # 提取所有匹配位置的中心点（去重，避免同一按钮被多次识别）
    positions = []
    h, w = target_img.shape[:2]
    for pt in zip(*locations[::-1]):
        center_x = pt[0] + w // 2
        center_y = pt[1] + h // 2
        # 去重：距离已存位置小于20像素则视为同一按钮
        if not any(abs(center_x - x) < 20 and abs(center_y - y) < 20 for (x, y) in positions):
            positions.append((center_x, center_y))

    # 按Y轴排序（从上到下），再按X轴排序（从左到右）
    positions.sort(key=lambda p: (p[1], p[0]))
    return positions if positions else None


def is_verification_detected():
    """检测是否出现验证场景"""
    if VERIFY_ICON is None:
        return False
    verify_pos = find_image_on_screen(VERIFY_ICON, confidence=0.7)
    return len(verify_pos) > 0 if verify_pos else False


def close_download_popup():
    """关闭下载成功弹窗（如果存在）"""
    if CLOSE_POPUP_ICON is None:
        return
    popup_pos = find_image_on_screen(CLOSE_POPUP_ICON, confidence=0.75)
    if popup_pos:
        print("🔍 发现下载成功弹窗，正在关闭...")
        x, y = popup_pos[0]
        pyautogui.moveTo(x, y, duration=random.uniform(0.3, 0.5))
        time.sleep(random.uniform(0.2, 0.4))
        pyautogui.click()
        time.sleep(random.uniform(0.5, 0.8))


def simulate_hesitation():
    """模拟人类犹豫动作"""
    if random.random() < HESITATE_PROB:
        hesitate_time = random.uniform(MIN_HESITATE, MAX_HESITATE)
        print(f"🤔 犹豫中...（{hesitate_time:.1f}秒）")
        time.sleep(hesitate_time)


def select_start_position():
    """让用户手动选择起始下载按钮（按鼠标左键确认）"""
    global start_icon_pos
    print("\n📍 请在3秒内将鼠标移动到【起始下载按钮】上，按鼠标左键确认！")
    time.sleep(3)

    # 监听鼠标左键点击
    def on_click(x, y, button, pressed):
        global start_icon_pos
        if pressed and button == mouse.Button.left:
            start_icon_pos = (x, y)
            print(f"✅ 已选定起始位置：({x}, {y})")
            return False  # 停止监听

    with mouse.Listener(on_click=on_click) as listener:
        listener.join()

    return start_icon_pos is not None


def on_key_press(key):
    """键盘监听：处理暂停、继续、翻页、停止"""
    global is_running, is_paused, is_verifying, current_download_idx, scanned_positions
    try:
        # ESC键：紧急停止
        if key == keyboard.Key.esc:
            print("\n⚠️  检测到ESC键，正在停止脚本...")
            is_running = False
            return False

        # 空格键：暂停/继续
        elif key == keyboard.Key.space:
            is_paused = not is_paused
            if is_paused:
                print("\n⏸️  脚本已暂停（按空格键继续，ESC键停止）")
            else:
                print("\n▶️  脚本继续运行")
                is_verifying = False  # 继续时重置验证状态

        # →键：下一页
        elif key == keyboard.Key.right:
            if not is_paused and not is_verifying:
                print(f"\n📄 准备切换到下一页...")
                simulate_hesitation()
                # 模拟翻页操作（可替换为翻页按钮坐标点击）
                pyautogui.press('right')
                load_delay = random.uniform(1.8, 3.2)
                print(f"⌛ 等待页面加载...（{load_delay:.1f}秒）")
                time.sleep(load_delay)
                # 重置当前页状态
                current_download_idx = 1
                scanned_positions.clear()
                print(f"✅ 已切换到新页面，准备开始下载（序号重置为1）")
            else:
                print("\n❌ 请先处理验证/暂停状态，再进行翻页")

        # ←键：上一页
        elif key == keyboard.Key.left:
            if not is_paused and not is_verifying:
                print(f"\n📄 准备返回上一页...")
                simulate_hesitation()
                pyautogui.press('left')
                load_delay = random.uniform(1.8, 3.2)
                print(f"⌛ 等待页面加载...（{load_delay:.1f}秒）")
                time.sleep(load_delay)
                current_download_idx = 1
                scanned_positions.clear()
            else:
                print("\n❌ 请先处理验证/暂停状态，再返回上一页")

    except Exception as e:
        print(f"\n❌ 键盘操作出错：{e}")


def auto_download():
    """自动下载主逻辑（图像识别+动态顺序+验证处理）"""
    global current_download_idx, is_running, is_paused, is_verifying, scanned_positions
    print("\n🚀 开始当前页面下载任务")

    # 步骤1：选择起始位置（自动识别或用户手动选择）
    while True:
        choice = input("\n请选择起始方式：1=自动识别第一个下载按钮 2=手动选择起始按钮（输入数字）：")
        if choice == "1":
            print("🔍 正在自动识别页面上的下载按钮...")
            all_icons = find_image_on_screen(DOWNLOAD_ICON)
            if not all_icons:
                print("❌ 未识别到任何下载按钮，请检查截图是否准确或页面是否加载完成")
                retry = input("是否重试？（y/n）：")
                if retry.lower() != "y":
                    return
            else:
                global start_icon_pos
                start_icon_pos = all_icons[0]
                print(f"✅ 自动识别到第一个下载按钮：{start_icon_pos}")
                break
        elif choice == "2":
            if select_start_position():
                break
            else:
                print("❌ 未选择起始位置，请重新操作")
        else:
            print("❌ 输入无效，请输入1或2")

    # 步骤2：开始按顺序下载
    while is_running and not is_paused:
        # 检测验证场景
        if is_verification_detected():
            print("\n⚠️  检测到验证页面/弹窗！")
            is_verifying = True
            input("👉 请手动完成验证后，按回车键继续下载...")
            is_verifying = False
            print("▶️  验证完成，继续下载")
            time.sleep(1)

        # 查找当前页面所有未扫描的下载按钮
        all_icons = find_image_on_screen(DOWNLOAD_ICON)
        if not all_icons:
            print("\n🔍 未找到更多下载按钮，当前页面下载完成！")
            break

        # 过滤已扫描的按钮（避免重复点击）
        available_icons = [pos for pos in all_icons if pos not in scanned_positions]
        if not available_icons:
            print("\n✅ 当前页面所有下载按钮已处理完毕！")
            break

        # 找到当前应下载的按钮（从起始位置往后排序）
        # 若起始位置在列表中，从起始位置开始；否则从第一个开始
        if start_icon_pos in all_icons:
            start_idx = all_icons.index(start_icon_pos)
            # 从起始位置往后取未扫描的按钮
            target_icons = [pos for pos in all_icons[start_idx:] if pos not in scanned_positions]
        else:
            target_icons = available_icons

        if not target_icons:
            print("\n✅ 起始位置之后无更多未下载按钮！")
            break

        # 取第一个目标按钮
        target_x, target_y = target_icons[0]
        scanned_positions.add((target_x, target_y))

        try:
            # 模拟人类操作流程
            simulate_hesitation()

            # 1. 平滑移动鼠标（带随机偏移）
            offset_x = random.randint(-MOUSE_OFFSET_RANGE, MOUSE_OFFSET_RANGE)
            offset_y = random.randint(-MOUSE_OFFSET_RANGE, MOUSE_OFFSET_RANGE)
            move_x = target_x + offset_x
            move_y = target_y + offset_y
            move_duration = random.uniform(0.4, 0.7)
            pyautogui.moveTo(move_x, move_y, duration=move_duration)
            print(f"\n📥 正在下载第 {current_download_idx} 个文件（坐标：{move_x:.0f}, {move_y:.0f}）")

            # 2. 确认位置（停留片刻）
            time.sleep(random.uniform(0.2, 0.5))

            # 3. 点击下载
            pyautogui.click(clicks=1, interval=0.1)

            # 4. 等待下载响应（随机延迟）
            download_delay = random.uniform(MIN_CLICK_DELAY, MAX_CLICK_DELAY)
            print(f"⌛ 等待下载完成...（{download_delay:.1f}秒）")
            time.sleep(download_delay)

            # 5. 关闭下载成功弹窗（如果有）
            close_download_popup()

            # 6. 检测是否需要滚动页面（当目标按钮接近屏幕底部时）
            screen_height = pyautogui.size()[1]
            if move_y > screen_height * 0.8:
                scroll_step = random.randint(MIN_SCROLL_STEP, MAX_SCROLL_STEP)
                print(f"🔄 页面滚动中...（距离：{scroll_step}像素）")
                pyautogui.scroll(-scroll_step)
                time.sleep(SCROLL_DELAY)

            # 7. 更新序号
            current_download_idx += 1

        except Exception as e:
            print(f"\n❌ 第 {current_download_idx} 个文件下载失败：{e}")
            scanned_positions.remove((target_x, target_y))  # 移除失败的位置，允许重试
            choice = input("👉 请选择：1=重试 2=跳过 3=手动处理后继续（输入数字）：")
            if choice == "1":
                print("🔄 正在重试...")
                time.sleep(1)
            elif choice == "2":
                print("➡️  跳过该文件，继续下一个")
                current_download_idx += 1
                time.sleep(0.5)
            elif choice == "3":
                input("✅ 手动处理完成后，按回车键继续...")
                current_download_idx += 1
            else:
                print("❌ 输入无效，跳过该文件")
                current_download_idx += 1
                time.sleep(0.5)


if __name__ == "__main__":
    # 检查必要文件
    if not os.path.exists(ICON_PATH):
        print(f"❌ 未找到下载图标截图：{ICON_PATH}")
        print("👉 请截取下载图标的清晰截图，命名为download_icon.png，放在脚本同一文件夹")
        exit(1)

    # 显示使用说明
    print("=" * 70)
    print("📌 【智能图像识别版】自动化下载脚本")
    print("核心功能：图像识别下载按钮、适配间距变化、验证自动切人工、自定义起始位置")
    print("快捷键控制：")
    print("   - 空格键：暂停/继续")
    print("   - → 键：切换到下一页（当前页完成后）")
    print("   - ← 键：返回上一页")
    print("   - ESC 键：紧急停止脚本")
    print("注意事项：")
    print("   1. 确保download_icon.png截图清晰，与页面图标一致")
    print("   2. 浏览器保持全屏，避免遮挡下载按钮")
    print("   3. 遇到验证时手动处理，完成后按回车继续")
    print("=" * 70)

    # 启动键盘监听（非阻塞）
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()

    try:
        # 循环执行：下载当前页 → 等待翻页 → 下载下一页
        while is_running:
            if not is_paused and not is_verifying:
                auto_download()
                # 当前页下载完成后，提示翻页
                print("\n📌 当前页面下载任务结束")
                print("👉 按 → 键切换到下一页，按 ← 键返回上一页，按ESC键退出")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n⚠️  用户手动停止脚本")
    finally:
        listener.stop()
        listener.join()
        print("\n👋 脚本已退出")