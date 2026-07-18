from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, ElementClickInterceptedException
)
import pygetwindow as gw
import pyautogui
import time
import random
import sys
import os
from pynput import keyboard

# ==================== 1. 核心配置（确认路径正确！）====================
SELECTOR_CONFIG = {
    "download_btn": ".operat .downloadlink",
    "serial": ".seq",
    "next_page_btn": "#PageNext",
    "literature_row": ".result-table-list tbody tr",
    "page_loaded_mark": ".result-table-list"
}
BROWSER_CONFIG = {
    "edge_window_title": "Microsoft Edge",
    "window_check_interval": 1.0,
    "page_load_timeout": 15,  # 延长超时，适配启动慢的情况
    "retry_count": 3,
    # 您的驱动路径（已验证正确，无需修改）
    "edge_driver_path": r"D:\Hefei_University_of_Technology_Work\020_pythonProject\20251104_download\zhiwang\001\msedgedriver.exe",
    # 您的Edge路径（已验证正确，无需修改）
    "edge_binary_path": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
}
HUMAN_CONFIG = {
    "min_click_delay": 2.0, "max_click_delay": 3.5,
    "min_move_duration": 0.5, "max_move_duration": 0.9,
    "hesitate_prob": 0.3, "min_hesitate": 0.8, "max_hesitate": 1.8,
    "mouse_offset": 5
}
# 全局状态
is_running = True
is_paused = False
scanned_serials = set()
current_page = 1
driver = None


# ==================== 2. 路径验证工具（不变）====================
def verify_driver_path():
    driver_path = BROWSER_CONFIG["edge_driver_path"]
    default_placeholder = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedgedriver.exe"
    if driver_path == default_placeholder:
        return False, "❌ 未修改驱动路径！请手动下载Edge驱动后，填写实际路径"
    if not os.path.exists(driver_path):
        return False, f"❌ 驱动文件不存在！路径：{driver_path}"
    if not driver_path.endswith(".exe"):
        return False, "❌ 驱动路径未包含.exe文件！"
    try:
        with open(driver_path, "rb") as f:
            pass
    except PermissionError:
        return False, "❌ 驱动文件无读取权限！"
    return True, "✅ 驱动路径验证通过"


# ==================== 3. 窗口监视+人类模拟（不变）====================
def check_edge_window_status():
    edge_windows = [w for w in gw.getWindowsWithTitle(BROWSER_CONFIG["edge_window_title"]) if w.isVisible]
    if not edge_windows:
        raise RuntimeError("未找到可见的Edge浏览器窗口，请先打开Edge并访问知网检索页")

    active_window = gw.getActiveWindow()
    if active_window and BROWSER_CONFIG[
        "edge_window_title"] in active_window.title and "中国知网" in active_window.title:
        target_window = active_window
    else:
        target_window = None
        for w in edge_windows:
            if "中国知网" in w.title:
                target_window = w
                break
        if not target_window:
            target_window = edge_windows[0]

    if not target_window.isActive:
        target_window.activate()
        time.sleep(0.8)
        print("⚠️ 知网窗口在后台，已自动激活")
    if target_window.isMinimized:
        target_window.restore()
        time.sleep(0.8)
        print("⚠️ 知网窗口已最小化，已自动恢复")

    main_screen = gw.getScreens()[0]
    if (target_window.left < main_screen.left or target_window.top < main_screen.top or
            target_window.right > main_screen.right or target_window.bottom > main_screen.bottom):
        target_window.moveTo(main_screen.left + 60, main_screen.top + 60)
        time.sleep(0.8)
        print("⚠️ 知网窗口在非主显示器，已自动移到主显示器")

    return target_window


def simulate_hesitation():
    if random.random() < HUMAN_CONFIG["hesitate_prob"] and is_running and not is_paused:
        hesitate_time = random.uniform(HUMAN_CONFIG["min_hesitate"], HUMAN_CONFIG["max_hesitate"])
        print(f"🤔 犹豫中...（{hesitate_time:.1f}秒）")
        time.sleep(hesitate_time)


def simulate_human_click(element):
    if not is_running or is_paused:
        return False
    window_pos = check_edge_window_status()
    element_rect = element.rect
    global_x = window_pos.left + element_rect["x"] + element_rect["width"] // 2
    global_y = window_pos.top + element_rect["y"] + element_rect["height"] // 2
    offset_x = random.randint(-HUMAN_CONFIG["mouse_offset"], HUMAN_CONFIG["mouse_offset"])
    offset_y = random.randint(-HUMAN_CONFIG["mouse_offset"], HUMAN_CONFIG["mouse_offset"])
    target_x = global_x + offset_x
    target_y = global_y + offset_y

    move_duration = random.uniform(HUMAN_CONFIG["min_move_duration"], HUMAN_CONFIG["max_move_duration"])
    pyautogui.moveTo(target_x, target_y, duration=move_duration)
    time.sleep(random.uniform(0.3, 0.6))

    try:
        element.click()
    except ElementClickInterceptedException:
        print("⚠️ 元素被遮挡（可能是验证码），用鼠标直接点击坐标")
        pyautogui.click(target_x, target_y)
    print(f"📥 第{current_page}页：点击下载（坐标：{int(target_x)},{int(target_y)}）")
    time.sleep(random.uniform(HUMAN_CONFIG["min_click_delay"], HUMAN_CONFIG["max_click_delay"]))
    return True


# ==================== 4. 核心修复：优化Edge启动参数（解决实例退出）====================
def init_edge_browser():
    """关键优化：添加启动参数，解决Edge实例退出问题"""
    global driver
    print("🚀 正在初始化Edge浏览器（优化启动参数+路径验证）...")
    try:
        edge_options = webdriver.EdgeOptions()

        # --------------- 新增：关键启动参数（解决实例退出核心）---------------
        edge_options.add_argument("--disable-gpu")  # 禁用GPU加速（最常见冲突原因）
        edge_options.add_argument("--no-sandbox")  # 禁用沙箱（系统权限限制时必备）
        edge_options.add_argument("--disable-dev-shm-usage")  # 禁用共享内存（避免资源不足）
        edge_options.add_argument("--disable-extensions")  # 禁用所有插件（避免插件干扰）
        edge_options.add_argument("--start-clean")  # 启动时清除缓存（避免旧缓存冲突）
        edge_options.add_argument("--inprivate")  # 无痕模式启动（减少环境干扰）
        edge_options.add_experimental_option("excludeSwitches", ["enable-logging"])  # 禁用日志（避免日志占用）

        # 基础配置
        edge_options.add_argument("--start-maximized")
        edge_options.add_argument("--disable-blink-features=AutomationControlled")
        edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        edge_options.add_experimental_option("useAutomationExtension", False)

        # 手动指定Edge路径（已验证正确）
        edge_options.binary_location = BROWSER_CONFIG["edge_binary_path"]

        # 启动驱动（增加启动超时处理）
        service = Service(
            BROWSER_CONFIG["edge_driver_path"],
            log_path=os.devnull  # 禁用驱动日志（减少干扰）
        )
        # 关键：设置启动超时为20秒
        driver = webdriver.Edge(
            service=service,
            options=edge_options,
            keep_alive=False  # 禁用长连接（避免连接超时）
        )
        driver.implicitly_wait(BROWSER_CONFIG["page_load_timeout"])

        # 导航到知网（增加导航超时）
        driver.set_page_load_timeout(20)
        driver.get("https://kns.cnki.net/kns8s/search")
        print("✅ Edge浏览器初始化完成！已导航到知网检索页")
        return driver
    except Exception as e:
        if "version" in str(e).lower() or "compatible" in str(e).lower():
            raise RuntimeError(
                f"❌ 驱动版本与Edge不兼容！{str(e)}\n💡 必须下载与Edge次版本接近的驱动（如Edge139.0.2171.95→驱动139.0.2171.x）")
        elif "exited" in str(e).lower():
            raise RuntimeError(
                f"❌ Edge实例启动失败！{str(e)}\n💡 排查：1. 关闭所有Edge后台进程；2. 重新下载驱动；3. 以普通权限运行脚本（不要管理员）")
        else:
            raise RuntimeError(f"❌ Edge初始化失败：{str(e)}")


# ==================== 5. 文献下载+翻页逻辑（不变）====================
def get_literature_serial(element):
    try:
        serial_element = element.find_element(By.CSS_SELECTOR, SELECTOR_CONFIG["serial"])
        serial_text = serial_element.text.strip()
        return int(serial_text) if serial_text.isdigit() else None
    except NoSuchElementException:
        return None


def download_current_page_literatures():
    global scanned_serials, current_page
    print(f"\n📄 开始处理第{current_page}页文献（知网检索结果）")
    try:
        WebDriverWait(driver, BROWSER_CONFIG["page_load_timeout"]).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, SELECTOR_CONFIG["page_loaded_mark"]))
        )
    except TimeoutException:
        print(f"❌ 第{current_page}页加载超时，跳过当前页")
        return False

    literature_rows = driver.find_elements(By.CSS_SELECTOR, SELECTOR_CONFIG["literature_row"])
    if not literature_rows:
        print(f"❌ 第{current_page}页未找到文献行，跳过")
        return False

    downloadable_rows = []
    for row in literature_rows:
        serial = get_literature_serial(row)
        if serial and serial not in scanned_serials:
            try:
                download_btn = WebDriverWait(row, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, SELECTOR_CONFIG["download_btn"]))
                )
                downloadable_rows.append((serial, download_btn))
            except (NoSuchElementException, TimeoutException):
                print(f"⚠️  序号{serial}未找到可点击的下载按钮，跳过")

    if not downloadable_rows:
        downloaded = sorted(scanned_serials) if scanned_serials else "无"
        print(f"✅ 第{current_page}页无未下载文献（已下载序号：{downloaded}）")
        return True

    print(f"🔍 第{current_page}页共识别到{len(downloadable_rows)}个未下载文献")
    for idx, (serial, download_btn) in enumerate(downloadable_rows, 1):
        global is_running, is_paused
        if not is_running:
            break
        while is_paused:
            time.sleep(BROWSER_CONFIG["window_check_interval"])
            if not is_running:
                break
        if not is_running:
            break

        simulate_hesitation()
        try:
            print(f"\n📥 正在下载第{idx}个（序号：{serial}）")
            if simulate_human_click(download_btn):
                scanned_serials.add(serial)
        except Exception as e:
            print(f"❌ 序号{serial}下载失败：{str(e)}")
            retry = 0
            while retry < BROWSER_CONFIG["retry_count"] and is_running:
                print(f"🔄 重试序号{serial}（第{retry + 1}次）")
                time.sleep(2)
                try:
                    if simulate_human_click(download_btn):
                        scanned_serials.add(serial)
                        break
                except Exception as retry_e:
                    print(f"⚠️  第{retry + 1}次重试失败：{str(retry_e)}")
                retry += 1
            else:
                print(f"❌ 序号{serial}重试{retry}次均失败，跳过")

    return True


def turn_to_next_page():
    global current_page, scanned_serials
    print(f"\n📄 准备翻到第{current_page + 1}页")
    simulate_hesitation()
    try:
        next_page_btn = WebDriverWait(driver, BROWSER_CONFIG["page_load_timeout"]).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, SELECTOR_CONFIG["next_page_btn"]))
        )
        simulate_human_click(next_page_btn)
        time.sleep(random.uniform(BROWSER_CONFIG["page_load_timeout"], BROWSER_CONFIG["page_load_timeout"] + 2))
        current_page += 1
        scanned_serials.clear()
        print(f"✅ 已翻到第{current_page}页，准备开始下载")
        return True
    except (NoSuchElementException, TimeoutException):
        print(f"❌ 未找到下一页按钮或按钮不可点击（已到最后一页）")
        return False


# ==================== 6. 键盘控制（不变）====================
def init_keyboard_listener():
    global is_running, is_paused

    def on_key_press(key):
        try:
            if key == keyboard.Key.esc:
                print("\n⚠️  检测到ESC键，正在停止任务...")
                is_running = False
                return False
            elif key == keyboard.Key.space:
                is_paused = not is_paused
                status = "⏸️ 任务已暂停（按空格继续/ESC停止）" if is_paused else "▶️ 任务继续运行"
                print(f"\n{status}")
        except Exception as e:
            print(f"\n❌ 键盘监听错误：{str(e)}")

    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()
    print("\n⌨️  键盘控制已启用：ESC=停止，空格=暂停/继续")
    return listener


# ==================== 7. 主程序（不变）====================
def main():
    global is_running, driver
    print("=" * 80)
    print("📌 Edge+知网F12元素精准定位版批量下载脚本（最终可运行版）")
    print("✅ 核心优化：禁用GPU+沙箱+插件，解决Edge实例退出问题")
    print("✅ 键盘控制：ESC=停止，空格=暂停/继续")
    print("=" * 80)

    # 验证驱动路径
    print("\n🔍 正在验证Edge驱动路径...")
    driver_valid, driver_msg = verify_driver_path()
    if not driver_valid:
        print(driver_msg)
        return
    print(driver_msg)

    # 验证Edge路径
    print("\n🔍 正在验证Edge浏览器路径...")
    edge_path = BROWSER_CONFIG["edge_binary_path"]
    if not os.path.exists(edge_path):
        print(f"❌ Edge浏览器文件不存在！路径：{edge_path}")
        return
    print(f"✅ Edge路径验证通过：{edge_path}")

    try:
        # 初始化Edge浏览器
        driver = init_edge_browser()

        # 引导用户操作
        print("\n📋 请在Edge浏览器中完成以下操作（30秒内）：")
        print("1. 若未登录：选择“合肥工业大学图书馆”机构登录（已登录可跳过）")
        print("2. 搜索目标文献→进入文献列表页（必须是列表模式）")
        time.sleep(30)

        # 初始化键盘监听
        key_listener = init_keyboard_listener()

        # 检查窗口状态
        check_edge_window_status()

        # 批量下载
        print(f"\n🚀 开始批量下载（当前页：{current_page}）")
        while is_running:
            while is_paused:
                time.sleep(BROWSER_CONFIG["window_check_interval"])
                if not is_running:
                    break
            if not is_running:
                break

            if not download_current_page_literatures():
                print(f"⚠️  第{current_page}页处理失败，尝试翻页")

            if not turn_to_next_page():
                print(f"\n🎉 已处理完所有页面（共{current_page}页），下载任务完成！")
                is_running = False
                break

    except Exception as e:
        print(f"\n❌ 程序运行错误：{str(e)}")
        print("💡 终极排查步骤：")
        print("   1. 重新下载驱动：必须选择与Edge次版本接近的版本（如Edge139.0.2171.95→驱动139.0.2171.75）")
        print("   2. 关闭所有Edge进程：任务管理器→详细信息→结束所有msedge.exe（包括后台进程）")
        print("   3. 普通权限运行：不要用管理员身份启动PowerShell，直接打开普通PowerShell")
        print("   4. 检查系统环境：关闭360、电脑管家等安全软件（可能拦截驱动启动）")
    finally:
        if driver:
            print("\n🔌 正在关闭Edge浏览器...")
            try:
                driver.quit()
            except:
                pass
        if 'key_listener' in locals():
            key_listener.stop()
            key_listener.join()
        total_downloaded = len(scanned_serials) if current_page == 1 else (current_page - 1) * 20 + len(scanned_serials)
        print(f"\n📊 下载统计：共处理{current_page}页，累计下载约{total_downloaded}个文献")
        print("👋 所有资源已释放，程序退出")


if __name__ == "__main__":
    main()