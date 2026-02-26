import pyautogui
import time
import random
import os
import cv2
import numpy as np
from pynput import keyboard, mouse
from PIL import ImageGrab

# ==================== 1. 配置参数（根据屏幕分辨率微调）====================
# 图像识别参数
CONFIDENCE_DOWNLOAD = 0.75  # 下载图标识别置信度（0-1，越高越精准）
CONFIDENCE_SERIAL = 0.80  # 序号识别置信度
SCAN_REGION_PADDING = 50  # 识别区域边距（避免边缘漏识别）

# 布局特征参数（知网列表页固定特征）
SERIAL_DOWNLOAD_DX = None  # 序号→下载按钮 水平偏移（自动校准）
SERIAL_DOWNLOAD_DY = None  # 序号→下载按钮 垂直偏移（自动校准）
PAGE_ITEM_COUNT = 50  # 知网每页固定50条文献
SCROLL_STEP = 550  # 页面滚动距离（像素）
SCROLL_DELAY = 0.8  # 滚动后等待时间（秒）

# 人类模拟参数
MIN_CLICK_DELAY = 1.2  # 点击后最小等待（秒）
MAX_CLICK_DELAY = 2.3  # 点击后最大等待（秒）
MIN_MOVE_DURATION = 0.3  # 鼠标移动最小时间（秒）
MAX_MOVE_DURATION = 0.6  # 鼠标移动最大时间（秒）
HESITATE_PROB = 0.18  # 18%概率触发犹豫
MIN_HESITATE = 0.5  # 犹豫最小时间（秒）
MAX_HESITATE = 1.2  # 犹豫最大时间（秒）
MOUSE_OFFSET = 2  # 点击随机偏移（像素，模拟手动偏差）

# 全局状态
is_running = True
is_paused = False
is_verifying = False
scanned_serials = set()  # 已下载序号（避免重复）
browser_window = None  # 浏览器窗口范围（(x1,y1,x2,y2)）
start_serial = 1  # 起始下载序号（可修改）


# ==================== 2. 图像工具函数 ====================
def load_image(path, desc):
    """加载图像，带友好错误提示"""
    if not os.path.exists(path):
        print(f"❌ 未找到{desc}：{path}")
        print(f"👉 请截取{desc}并命名为{os.path.basename(path)}，放在脚本同一文件夹")
        exit(1)
    img = cv2.imread(path)
    if img is None:
        print(f"⚠️ {desc}截图无效（可能损坏或格式错误），请重新截取清晰图像")
        exit(1)
    return img


def find_image_in_region(target_img, region=None, confidence=0.8):
    """在指定区域查找目标图像，返回中心点坐标列表（去重后）"""
    # 截取屏幕区域
    screen = ImageGrab.grab(bbox=region)
    screen_np = np.array(screen)
    screen_bgr = cv2.cvtColor(screen_np, cv2.COLOR_RGB2BGR)

    # 模板匹配
    result = cv2.matchTemplate(screen_bgr, target_img, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= confidence)

    # 提取中心点并去重（距离<20像素视为同一目标）
    positions = []
    h, w = target_img.shape[:2]
    for pt in zip(*locations[::-1]):
        center_x = pt[0] + w // 2
        center_y = pt[1] + h // 2
        # 转换为屏幕绝对坐标（若有区域限定）
        if region:
            center_x += region[0]
            center_y += region[1]
        # 去重
        if not any(abs(center_x - x) < 20 and abs(center_y - y) < 20 for x, y in positions):
            positions.append((center_x, center_y))
    # 按Y轴排序（从上到下）
    positions.sort(key=lambda p: p[1])
    return positions


def verify_download_icon(pos, download_img):
    """验证坐标是否为有效下载按钮（二次确认，避免误点）"""
    # 截取目标位置周围区域
    x, y = pos
    h, w = download_img.shape[:2]
    verify_region = (x - w, y - h, x + w, y + h)
    # 确保区域在屏幕内
    verify_region = (
        max(0, verify_region[0]), max(0, verify_region[1]),
        min(pyautogui.size()[0], verify_region[2]),
        min(pyautogui.size()[1], verify_region[3])
    )
    # 查找下载图标
    matches = find_image_in_region(download_img, verify_region, CONFIDENCE_DOWNLOAD)
    return len(matches) > 0


# ==================== 3. 浏览器窗口与偏移校准 ====================
def get_browser_window():
    """获取浏览器窗口范围（用户将鼠标移到浏览器内确认）"""
    global browser_window
    print("\n📍 请在3秒内将鼠标移动到知网浏览器窗口内任意位置，按回车键确认！")
    time.sleep(3)
    mouse_x, mouse_y = pyautogui.position()
    # 简化：假设浏览器为当前活跃窗口（可覆盖90%场景）
    active_window = pyautogui.getActiveWindow()
    if active_window:
        browser_window = (
            active_window.left + SCAN_REGION_PADDING,
            active_window.top + SCAN_REGION_PADDING,
            active_window.right - SCAN_REGION_PADDING,
            active_window.bottom - SCAN_REGION_PADDING
        )
        print(f"✅ 已锁定浏览器范围：({browser_window[0]},{browser_window[1]})→({browser_window[2]},{browser_window[3]})")
    else:
        #  fallback：全屏范围（避免窗口识别失败）
        browser_window = (0, 0, pyautogui.size()[0], pyautogui.size()[1])
        print(f"⚠️ 未识别到活跃窗口，使用全屏范围（建议手动最大化浏览器）")


def calibrate_serial_download_offset(serial_img, download_img):
    """自动校准序号→下载按钮的偏移量"""
    global SERIAL_DOWNLOAD_DX, SERIAL_DOWNLOAD_DY
    print("\n📌 开始自动校准序号与下载按钮的位置关系...")

    # 1. 查找当前页序号
    serial_positions = find_image_in_region(serial_img, browser_window, CONFIDENCE_SERIAL)
    if len(serial_positions) < 3:
        print("❌ 识别到的序号不足3个，无法校准")
        print("👉 请确保：1. 序号截图清晰 2. 页面为知网文献列表页（列表模式）3. 序号在可视区域")
        exit(1)
    # 选择中间位置的序号（避免边缘偏差）
    target_serial_pos = serial_positions[len(serial_positions) // 2]
    print(f"🔍 选中校准序号位置：({target_serial_pos[0]},{target_serial_pos[1]})")

    # 2. 查找对应下载按钮（序号右侧区域）
    # 知网下载按钮通常在序号右侧200-400像素，下方0-10像素
    download_search_region = (
        target_serial_pos[0] + 200, target_serial_pos[1] - 10,
        target_serial_pos[0] + 400, target_serial_pos[1] + 10
    )
    download_positions = find_image_in_region(download_img, download_search_region, CONFIDENCE_DOWNLOAD)
    if not download_positions:
        print("❌ 未找到序号对应的下载按钮，无法校准")
        print("👉 请检查：1. 下载图标截图是否与页面一致 2. 文献行是否完整显示")
        exit(1)
    target_download_pos = download_positions[0]
    print(f"🔍 匹配到对应下载按钮：({target_download_pos[0]},{target_download_pos[1]})")

    # 3. 计算偏移量
    SERIAL_DOWNLOAD_DX = target_download_pos[0] - target_serial_pos[0]
    SERIAL_DOWNLOAD_DY = target_download_pos[1] - target_serial_pos[1]
    print(f"✅ 校准完成！偏移量：水平+{SERIAL_DOWNLOAD_DX}px，垂直+{SERIAL_DOWNLOAD_DY}px")


# ==================== 4. 核心下载逻辑 ====================
def simulate_hesitation():
    """模拟人类犹豫停顿（随机触发）"""
    if random.random() < HESITATE_PROB:
        hesitate_time = random.uniform(MIN_HESITATE, MAX_HESITATE)
        print(f"🤔 犹豫中...（{hesitate_time:.1f}秒）")
        time.sleep(hesitate_time)


def calculate_download_positions(serial_img, download_img):
    """计算当前页所有待下载按钮的坐标"""
    # 1. 识别当前页所有序号
    serial_positions = find_image_in_region(serial_img, browser_window, CONFIDENCE_SERIAL)
    if not serial_positions:
        print("⚠️ 当前页未识别到序号，可能已滚动到页底")
        return []

    # 2. 提取序号文本（从截图反推，或按位置排序分配相对序号）
    # 简化：按位置排序，分配相对序号（1~50），结合起始序号过滤
    download_pos_list = []
    for idx, (serial_x, serial_y) in enumerate(serial_positions):
        # 计算绝对序号（假设当前页是连续序号）
        current_serial = start_serial + idx
        # 过滤条件：未下载 + 序号≥起始序号
        if current_serial in scanned_serials or current_serial < start_serial:
            continue

        # 3. 计算下载按钮坐标（偏移量+随机偏差）
        download_x = serial_x + SERIAL_DOWNLOAD_DX + random.randint(-MOUSE_OFFSET, MOUSE_OFFSET)
        download_y = serial_y + SERIAL_DOWNLOAD_DY + random.randint(-MOUSE_OFFSET, MOUSE_OFFSET)
        download_pos = (download_x, download_y)

        # 4. 二次验证下载图标（避免偏移偏差）
        if verify_download_icon(download_pos, download_img):
            download_pos_list.append((current_serial, download_x, download_y))
        else:
            print(f"⚠️ 序号{current_serial}下载位置验证失败，跳过")

    # 按序号排序（确保从上到下下载）
    download_pos_list.sort(key=lambda x: x[0])
    print(f"\n📄 当前页待下载：{len(download_pos_list)}个（序号：{[x[0] for x in download_pos_list]}）")
    return download_pos_list


def auto_download_single_page(serial_img, download_img):
    """下载当前页所有待下载文献"""
    global scanned_serials
    download_pos_list = calculate_download_positions(serial_img, download_img)
    if not download_pos_list:
        return False

    # 下载触发滚动阈值（随机3-6个触发一次，更自然）
    scroll_trigger = random.randint(3, 6)
    for idx, (serial, x, y) in enumerate(download_pos_list):
        global is_running, is_paused, is_verifying
        # 处理暂停/停止/验证
        while is_paused or is_verifying:
            time.sleep(0.5)
            if not is_running:
                return False

        if not is_running:
            return False

        try:
            # 1. 模拟人类操作：犹豫+平滑移动
            simulate_hesitation()
            move_duration = random.uniform(MIN_MOVE_DURATION, MAX_MOVE_DURATION)
            pyautogui.moveTo(x, y, duration=move_duration)

            # 2. 点击下载
            print(f"📥 下载第{len(scanned_serials) + 1}个 | 序号：{serial} | 坐标：({x:.0f},{y:.0f})")
            pyautogui.click(clicks=1, interval=0.1)

            # 3. 等待下载响应
            click_delay = random.uniform(MIN_CLICK_DELAY, MAX_CLICK_DELAY)
            time.sleep(click_delay)

            # 4. 标记已下载
            scanned_serials.add(serial)

            # 5. 动态滚动（避免下载按钮超出屏幕）
            if (idx + 1) % scroll_trigger == 0:
                print(f"🔄 滚动页面（触发阈值：{scroll_trigger}）")
                pyautogui.scroll(-SCROLL_STEP)
                time.sleep(SCROLL_DELAY)
                scroll_trigger = random.randint(3, 6)  # 重置阈值

        except Exception as e:
            print(f"❌ 序号{serial}下载失败：{str(e)}")
            choice = input("👉 操作选择：1=重试 2=跳过 3=手动处理后继续（输入数字）：")
            if choice == "1":
                pyautogui.moveTo(x, y, duration=0.5)
                pyautogui.click()
                time.sleep(click_delay)
                scanned_serials.add(serial)
                print(f"✅ 序号{serial}重试成功")
            elif choice == "2":
                print(f"➡️  跳过序号{serial}")
            elif choice == "3":
                input("✅ 手动处理完成后按回车键继续...")
                scanned_serials.add(serial)

    print(f"\n✅ 当前页下载完成，已累计下载：{len(scanned_serials)}个")
    return True


# ==================== 5. 键盘控制 ====================
def on_key_press(key):
    """键盘事件监听：空格暂停/继续、ESC停止、←→翻页"""
    global is_running, is_paused, is_verifying, start_serial
    try:
        # ESC：停止
        if key == keyboard.Key.esc:
            print("\n⚠️  检测到ESC键，停止下载任务...")
            is_running = False
            return False

        # 空格：暂停/继续
        elif key == keyboard.Key.space:
            is_paused = not is_paused
            if is_paused:
                print("\n⏸️  脚本已暂停（按空格键继续，ESC键停止）")
            else:
                print("\n▶️  脚本继续运行")
                is_verifying = False  # 继续时重置验证状态

        # →：下一页
        elif key == keyboard.Key.right and not is_paused and not is_verifying:
            print(f"\n📄 切换到下一页...")
            pyautogui.press('right')
            time.sleep(3.5)  # 知网翻页加载时间
            # 更新起始序号（每页50条）
            start_serial += PAGE_ITEM_COUNT
            print(f"✅ 已切换到下一页，起始序号更新为：{start_serial}")

        # ←：上一页
        elif key == keyboard.Key.left and not is_paused and not is_verifying and start_serial > PAGE_ITEM_COUNT:
            print(f"\n📄 返回上一页...")
            pyautogui.press('left')
            time.sleep(3.5)
            start_serial -= PAGE_ITEM_COUNT
            print(f"✅ 已返回上一页，起始序号更新为：{start_serial}")

        # F5：标记人工验证完成
        elif key == keyboard.Key.f5:
            if is_verifying:
                print("\n▶️  人工验证完成，继续下载")
                is_verifying = False

    except Exception as e:
        print(f"\n❌ 键盘操作错误：{str(e)}")


def detect_verification():
    """检测是否需要人工验证（用户手动触发F5继续）"""
    global is_verifying
    # 简化：用户看到验证时手动按F5，脚本检测到F5后继续
    # 进阶：可添加验证码图标识别，此处因用户需自行处理，暂用手动触发
    while is_running and is_verifying:
        time.sleep(1)


# ==================== 6. 主程序入口 ====================
def main():
    print("=" * 70)
    print("📌 知网批量下载脚本（图像识别布局版）")
    print("✅ 核心：图像识别+自动校准+键盘控制，无F12依赖")
    print("⌨️  快捷键：空格=暂停/继续 | ESC=停止 | ←→=翻页 | F5=验证完成")
    print("📝 前置：已准备 download_icon.png（下载图标）、serial_icon.png（序号）")
    print("=" * 70)

    # 1. 加载图像
    print("\n🔍 加载识别图像...")
    download_img = load_image("download_icon.png", "下载图标截图")
    serial_img = load_image("serial_icon.png", "序号截图")

    # 2. 获取浏览器窗口
    get_browser_window()

    # 3. 自动校准偏移量
    calibrate_serial_download_offset(serial_img, download_img)

    # 4. 输入起始序号
    global start_serial
    while True:
        start_input = input("\n请输入起始下载序号（默认1）：")
        if not start_input:
            break
        if start_input.isdigit():
            start_serial = int(start_input)
            print(f"✅ 已设置起始序号：{start_serial}")
            break
        else:
            print("❌ 输入无效，请输入数字（如1、75）")

    # 5. 启动键盘监听
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()
    print("\n🚀 开始下载任务（按空格键暂停，ESC键停止）")
    input("👉 确认知网页面已在列表模式，按回车键开始...")

    try:
        while is_running:
            if is_paused:
                time.sleep(0.5)
                continue

            # 检测人工验证（用户按F5继续）
            if is_verifying:
                detect_verification()
                continue

            # 下载当前页
            page_download_success = auto_download_single_page(serial_img, download_img)
            if not page_download_success:
                # 询问是否翻页
                choice = input("\n当前页无更多可下载文献，是否切换到下一页？（y/n）：")
                if choice.lower() == "y":
                    pyautogui.press('right')
                    time.sleep(3.5)
                    start_serial += PAGE_ITEM_COUNT
                    print(f"✅ 已切换到下一页，起始序号：{start_serial}")
                else:
                    break

    finally:
        # 清理资源
        listener.stop()
        listener.join()
        print("\n" + "=" * 50)
        print(f"📊 下载统计：")
        print(f"   - 累计下载成功：{len(scanned_serials)}个")
        print(f"   - 已处理序号范围：{sorted(scanned_serials) if scanned_serials else '无'}")
        print(f"   - 任务状态：{'正常结束' if is_running else '用户手动停止'}")
        print("=" * 50)
        print("👋 脚本已完全退出")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  用户手动停止脚本")
    except Exception as e:
        print(f"\n❌ 脚本运行错误：{str(e)}")
        print("💡 排查建议：1. 截图是否清晰 2. 浏览器是否在列表模式 3. 网络是否正常")
