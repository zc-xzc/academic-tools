import pyautogui
import time
import random
from pynput import keyboard

# ==================== 配置参数（根据实际情况修改）====================
DOWNLOAD_COUNT_PER_PAGE = 50  # 每页面文件数量（默认50）
VERTICAL_DISTANCE = 65  # 两个下载按钮的垂直距离（像素，必须手动测量！）
MIN_CLICK_DELAY = 2  # 下载最小等待时间（秒）
MAX_CLICK_DELAY = 4  # 下载最大等待时间（秒）
MIN_SCROLL_STEP = 400  # 最小滚动距离（像素）
MAX_SCROLL_STEP = 600  # 最大滚动距离（像素）
MIN_SCROLL_DELAY = 2  # 滚动最小等待时间（秒）
MAX_SCROLL_DELAY = 4  # 滚动最大等待时间（秒）
HESITATE_PROB = 0.15  # 15%概率出现“犹豫”（0-1之间）
MIN_HESITATE = 1  # 犹豫最小时间（秒）
MAX_HESITATE = 3  # 犹豫最大时间（秒）
MOUSE_OFFSET_RANGE = 3  # 鼠标位置随机偏移（像素，模拟手动偏差）
# ====================================================================

# 全局状态变量
is_running = True  # 是否正在运行
is_paused = False  # 是否暂停
current_page = 1  # 当前页码
current_download = 1  # 当前下载序号（每页面内）


def on_key_press(key):
    """键盘监听回调：处理翻页、暂停、停止"""
    global is_running, is_paused, current_page, current_download
    try:
        # 按 ESC 键：紧急停止脚本
        if key == keyboard.Key.esc:
            print("\n⚠️  检测到 ESC 键，正在停止脚本...")
            is_running = False
            return False  # 停止监听

        # 按空格键：暂停/继续
        elif key == keyboard.Key.space:
            is_paused = not is_paused
            if is_paused:
                print("\n⏸️  脚本已暂停（按空格键继续，ESC键停止）")
            else:
                print("\n▶️  脚本继续运行")

        # 按 → 键：下一页
        elif key == keyboard.Key.right:
            if not is_paused:
                print(f"\n📄 准备切换到第 {current_page + 1} 页...")
                # 模拟人类翻页前的停顿
                time.sleep(random.uniform(0.8, 1.5))
                current_page += 1
                current_download = 1  # 重置当前页下载序号
                # 模拟自然翻页（优先键盘，不行再用坐标）
                pyautogui.press('right')
                # 翻页后等待页面加载（随机延迟，更真实）
                load_delay = random.uniform(1.8, 3.0)
                print(f"⌛ 等待页面加载...（{load_delay:.1f}秒）")
                time.sleep(load_delay)
            else:
                print("\n❌ 请先按空格键继续脚本，再进行翻页")

        # 按 ← 键：上一页
        elif key == keyboard.Key.left:
            if current_page > 1 and not is_paused:
                print(f"\n📄 准备切换到第 {current_page - 1} 页...")
                time.sleep(random.uniform(0.8, 1.5))
                current_page -= 1
                current_download = 1
                pyautogui.press('left')
                load_delay = random.uniform(1.8, 3.0)
                print(f"⌛ 等待页面加载...（{load_delay:.1f}秒）")
                time.sleep(load_delay)
            elif current_page == 1:
                print("\n❌ 已经是第1页，无法后退")
            else:
                print("\n❌ 请先按空格键继续脚本，再进行翻页")

    except Exception as e:
        print(f"\n❌ 键盘操作出错：{e}")


def simulate_hesitation():
    """模拟人类操作中的“犹豫”（随机触发）"""
    if random.random() < HESITATE_PROB:
        hesitate_time = random.uniform(MIN_HESITATE, MAX_HESITATE)
        print(f"🤔 犹豫中...（{hesitate_time:.1f}秒）")
        time.sleep(hesitate_time)


def auto_download():
    """自动下载单页内的所有文件（模拟人类操作）"""
    global current_download, is_running, is_paused
    print(f"\n🚀 开始下载第 {current_page} 页，共 {DOWNLOAD_COUNT_PER_PAGE} 个文件")
    print(f"📍 第1个下载按钮位置：{pyautogui.position()}（请确保鼠标已对准！）")
    input("⚠️  确认鼠标已放在第1个下载按钮上，按回车键开始...")

    # 记录初始位置（第1个下载按钮的坐标）
    start_x, start_y = pyautogui.position()
    # 屏幕可视区域高度（用于判断是否需要滚动）
    screen_height = pyautogui.size()[1]
    # 滚动阈值：当按钮位置超过屏幕70%高度时，触发滚动
    scroll_threshold = screen_height * 0.7

    for i in range(current_download, DOWNLOAD_COUNT_PER_PAGE + 1):
        if not is_running:
            break
        while is_paused:
            time.sleep(0.5)  # 暂停时循环等待

        try:
            # 1. 模拟犹豫（随机触发）
            simulate_hesitation()

            # 2. 计算当前下载按钮坐标（增加随机偏移，模拟手动偏差）
            offset_x = random.randint(-MOUSE_OFFSET_RANGE, MOUSE_OFFSET_RANGE)
            offset_y = random.randint(-MOUSE_OFFSET_RANGE, MOUSE_OFFSET_RANGE)
            current_y = start_y + (i - 1) * VERTICAL_DISTANCE + offset_y
            target_x = start_x + offset_x

            # 3. 平滑移动鼠标（人类移动速度：0.4-0.7秒）
            move_duration = random.uniform(0.4, 0.7)
            pyautogui.moveTo(target_x, current_y, duration=move_duration)
            print(f"\n📥 正在下载第 {current_page} 页 - 第 {i} 个文件（坐标：{target_x:.0f}, {current_y:.0f}）")

            # 4. 鼠标停留片刻（模拟确认位置，0.2-0.5秒）
            pause_before_click = random.uniform(0.2, 0.5)
            time.sleep(pause_before_click)

            # 5. 点击下载（模拟轻击，避免机械点击）
            pyautogui.click(clicks=1, interval=0.1, button='left')

            # 6. 等待下载触发（随机延迟，符合网络波动）
            download_delay = random.uniform(MIN_CLICK_DELAY, MAX_CLICK_DELAY)
            print(f"⌛ 等待下载响应...（{download_delay:.1f}秒）")
            time.sleep(download_delay)

            # 7. 动态判断是否需要滚动（模拟人类看到按钮快超出屏幕时滚动）
            if current_y > scroll_threshold:
                scroll_step = random.randint(MIN_SCROLL_STEP, MAX_SCROLL_STEP)
                scroll_delay = random.uniform(MIN_SCROLL_DELAY, MAX_SCROLL_DELAY)
                print(f"🔄 滚动页面...（距离：{scroll_step}像素，等待{scroll_delay:.1f}秒）")
                pyautogui.scroll(-scroll_step)  # 向下滚动
                time.sleep(scroll_delay)
                # 滚动后更新初始Y轴位置（避免后续坐标偏差）
                start_y -= scroll_step

            current_download = i  # 更新当前下载序号

        except Exception as e:
            print(f"\n❌ 第 {i} 个文件下载失败：{e}")
            # 人工介入：让用户手动处理，处理完按回车键继续
            input("⚠️  请手动下载该文件后，按回车键继续...")

    if is_running:
        print(f"\n✅ 第 {current_page} 页下载完成！")
        print("👉 按 → 键切换到下一页，按 ← 键返回上一页，按空格键暂停")


if __name__ == "__main__":
    # 显示使用说明
    print("=" * 60)
    print("📌 【人类模拟版】自动化下载脚本使用说明")
    print("1. 先将浏览器全屏，打开目标页面")
    print("2. 手动将鼠标移动到第1个下载按钮上")
    print("3. 脚本运行后，按回车键开始当前页下载")
    print("4. 快捷键控制：")
    print("   - 空格键：暂停/继续")
    print("   - → 键：下一页（当前页下载完成后使用）")
    print("   - ← 键：上一页")
    print("   - ESC 键：紧急停止脚本")
    print("5. 脚本特点：模拟人类犹豫、随机延迟、自然滚动")
    print("=" * 60)

    # 启动键盘监听（非阻塞）
    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()

    try:
        # 循环执行：下载当前页 → 等待翻页 → 下载下一页
        while is_running:
            if not is_paused and current_download <= DOWNLOAD_COUNT_PER_PAGE:
                auto_download()
            time.sleep(1)  # 等待翻页或暂停操作
    except KeyboardInterrupt:
        print("\n⚠️  用户手动停止脚本")
    finally:
        listener.stop()
        listener.join()
        print("\n👋 脚本已退出")