# 知网批量下载脚本（F12元素定位版 - 整合完整版）
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import random
import keyboard

# ==================== 配置参数（无需修改，F12数据固定）====================
# 元素CSS选择器（从F12提取，精准定位）
SERIAL_SELECTOR = "td.seq"  # 序号元素选择器
DOWNLOAD_BTN_SELECTOR = "td.operat a.downloadlink"  # 下载按钮选择器
LITERATURE_ROW_SELECTOR = "table.result-table-list tbody tr"  # 单条文献行选择器
NEXT_PAGE_SELECTOR = "a#Page_next_top"  # 下一页按钮选择器
PAGE_COUNT_SELECTOR = "span.countPageMark"  # 页码信息选择器（如"2/10"）
# 人类模拟参数（避免机械操作）
MIN_CLICK_DELAY = 1.2  # 点击下载后最小等待时间（秒）
MAX_CLICK_DELAY = 2.3  # 点击下载后最大等待时间（秒）
MIN_MOVE_DURATION = 0.3  # 鼠标移动最小时间（秒）
MAX_MOVE_DURATION = 0.6  # 鼠标移动最大时间（秒）
HESITATE_PROB = 0.18  # 18%概率触发犹豫停顿
MIN_HESITATE = 0.5  # 犹豫最小时间（秒）
MAX_HESITATE = 1.2  # 犹豫最大时间（秒）
# 页面控制参数
PAGE_ITEM_COUNT = 50  # 每页固定50条（知网默认）
LOAD_WAIT_TIME = 5  # 页面加载等待时间（秒）
DOWNLOAD_TRIGGER_WAIT = 2  # 点击下载后等待触发时间（秒）
# 全局状态变量
is_running = True
is_paused = False
scanned_serials = set()  # 已下载的序号（避免重复）
start_serial = None  # 起始下载序号
driver = None  # Selenium浏览器实例


# ==================== 工具函数（模拟人类操作+元素处理）====================
def simulate_hesitation():
    """模拟人类犹豫停顿（随机触发）"""
    if random.random() < HESITATE_PROB:
        hesitate_time = random.uniform(MIN_HESITATE, MAX_HESITATE)
        print(f"🤔 犹豫中...（{hesitate_time:.1f}秒）")
        time.sleep(hesitate_time)


def simulate_human_click(element):
    """模拟人类点击：随机移动速度+犹豫+点击"""
    # 随机移动到元素（避免瞬间移动）
    action = webdriver.ActionChains(driver)
    move_duration = random.uniform(MIN_MOVE_DURATION, MAX_MOVE_DURATION)
    action.move_to_element_with_offset(element, 5, 5)  # 偏移5px，模拟真实点击偏差
    action.perform()
    time.sleep(move_duration)

    # 随机犹豫后点击
    simulate_hesitation()
    element.click()
    print(f"✅ 点击下载：序号{element.get_attribute('data-serial')}")

    # 等待下载触发（确保文件开始下载）
    time.sleep(random.uniform(MIN_CLICK_DELAY, MAX_CLICK_DELAY))


def get_current_page_info():
    """获取当前页信息：当前页码、起始序号、结束序号"""
    # 1. 获取页码信息（如"2/10" → 当前页2）
    page_mark = WebDriverWait(driver, LOAD_WAIT_TIME).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, PAGE_COUNT_SELECTOR))
    )
    current_page = int(page_mark.text.split("/")[0])

    # 2. 获取当前页所有序号，计算起始和结束序号
    serial_elements = driver.find_elements(By.CSS_SELECTOR, SERIAL_SELECTOR)
    if not serial_elements:
        raise NoSuchElementException("未找到序号元素，请确认页面是文献结果页（列表模式）")

    # 提取序号文本并转换为整数（过滤无效文本）
    serials = []
    for el in serial_elements:
        serial_text = el.text.strip()
        if serial_text.isdigit():
            serials.append(int(serial_text))

    if not serials:
        raise ValueError("当前页未识别到有效序号，请检查页面是否加载完成")

    page_start = min(serials)
    page_end = max(serials)

    return {
        "current_page": current_page,
        "page_start": page_start,
        "page_end": page_end,
        "serials": serials
    }


def filter_downloadable_literatures(current_page_info):
    """过滤当前页需要下载的文献：基于起始序号+未处理"""
    # 获取当前页所有文献行
    literature_rows = driver.find_elements(By.CSS_SELECTOR, LITERATURE_ROW_SELECTOR)
    if not literature_rows:
        return []

    downloadable = []
    for row in literature_rows:
        # 提取当前行序号
        try:
            serial_el = row.find_element(By.CSS_SELECTOR, SERIAL_SELECTOR)
            serial_text = serial_el.text.strip()
            if not serial_text.isdigit():
                continue
            serial = int(serial_text)
        except NoSuchElementException:
            continue  # 无序号元素，跳过

        # 过滤条件：>=起始序号 + 未处理过
        if serial >= start_serial and serial not in scanned_serials:
            # 提取当前行下载按钮（确保可点击）
            try:
                download_btn = WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, DOWNLOAD_BTN_SELECTOR))
                )
                # 给下载按钮绑定序号属性，方便日志输出
                download_btn.set_attribute("data-serial", str(serial))
                downloadable.append((serial, download_btn))
            except (NoSuchElementException, TimeoutException):
                print(f"⚠️  序号{serial}未找到可点击的下载按钮，跳过")
                continue

    # 按序号排序（确保从上到下下载）
    downloadable.sort(key=lambda x: x[0])
    return downloadable


# ==================== 键盘控制函数（暂停/继续/停止）====================
def on_key_press(key):
    """键盘事件监听：空格键暂停/继续，ESC键停止"""
    global is_running, is_paused
    try:
        if hasattr(key, 'name') and key.name == "esc":
            print("\n⚠️  检测到ESC键，正在停止下载任务...")
            is_running = False
        elif hasattr(key, 'name') and key.name == "space":
            is_paused = not is_paused
            if is_paused:
                print("\n⏸️  脚本已暂停（按空格键继续，ESC键停止）")
            else:
                print("\n▶️  脚本继续运行")
    except Exception as e:
        print(f"\n❌ 键盘事件处理错误：{e}")


# ==================== 翻页函数 ====================
def click_next_page():
    """点击下一页按钮，返回是否翻页成功"""
    try:
        next_btn = WebDriverWait(driver, LOAD_WAIT_TIME).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, NEXT_PAGE_SELECTOR))
        )
        next_btn.click()
        print(f"🔄 已点击下一页，等待页面加载...")
        time.sleep(LOAD_WAIT_TIME)  # 等待新页面加载完成
        return True
    except (NoSuchElementException, TimeoutException):
        print("❌ 未找到下一页按钮或按钮不可点击（可能已到最后一页）")
        return False


# ==================== 核心下载逻辑 ====================
def auto_download():
    global driver, start_serial, is_running, is_paused, scanned_serials

    print("=" * 75)
    print("📌 知网批量下载脚本（F12元素定位整合版）")
    print("✅ 核心特性：HTML元素精准定位、序号范围自动计算、人类模拟操作")
    print("⌨️  快捷键控制：空格键=暂停/继续 | ESC键=紧急停止")
    print("📝 注意事项：确保已安装Chrome浏览器，且有知网下载权限（机构/会员登录）")
    print("=" * 75)

    try:
        # 1. 初始化Chrome浏览器（自动安装对应版本驱动）
        print("\n🚀 正在初始化Chrome浏览器...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service)
        driver.maximize_window()  # 最大化窗口（避免元素被遮挡）
        print("✅ Chrome浏览器已启动！")

        # 2. 引导用户登录知网并导航到目标页面
        print("\n📋 请在浏览器中完成以下操作：")
        print("1. 访问知网官网（https://www.cnki.net/）")
        print("2. 登录你的账号（机构登录/个人会员，确保有下载权限）")
        print("3. 搜索目标主题（如'环境规制'），进入文献结果页")
        print("4. 切换到【列表模式】（确保能看到序号和下载按钮）")
        input("\n✅ 完成以上操作后，按回车键开始下载任务...")

        # 3. 输入起始下载序号
        while True:
            start_input = input("\n请输入起始下载序号（如1、75，需在当前页序号范围内）：")
            if start_input.isdigit():
                start_serial = int(start_input)
                print(f"✅ 已选定起始序号：{start_serial}")
                break
            else:
                print("❌ 输入无效！请输入数字序号（如75）")

        # 4. 启动键盘监听（非阻塞）
        keyboard.on_press(on_key_press)
        print("\n📥 开始执行下载任务...（按空格键暂停，ESC键停止）")
        download_count = 0

        # 5. 循环下载（当前页→翻页→下一页）
        while is_running:
            # 处理暂停状态
            while is_paused:
                time.sleep(0.5)
                if not is_running:
                    break
            if not is_running:
                break

            # 获取当前页信息
            try:
                current_page_info = get_current_page_info()
                print(
                    f"\n📄 当前状态：第{current_page_info['current_page']}页 | 序号范围：{current_page_info['page_start']}~{current_page_info['page_end']}")
            except Exception as e:
                print(f"\n❌ 获取当前页信息失败：{e}")
                choice = input("是否尝试翻页？（y/n）：")
                if choice.lower() == "y":
                    click_next_page()
                else:
                    break
                continue

            # 过滤当前页可下载文献
            downloadable = filter_downloadable_literatures(current_page_info)
            if not downloadable:
                print(f"\n✅ 当前页无需要下载的文献（已处理到序号：{max(scanned_serials) if scanned_serials else 0}）")
                choice = input("是否切换到下一页？（y/n）：")
                if choice.lower() == "y":
                    if not click_next_page():
                        print("⚠️  翻页失败，任务终止")
                        break
                else:
                    break
                continue

            # 批量下载当前页文献
            print(f"🔍 当前页可下载文献：{len(downloadable)}个 | 序号：{[x[0] for x in downloadable]}")
            for serial, download_btn in downloadable:
                if not is_running:
                    break
                while is_paused:
                    time.sleep(0.5)
                    if not is_running:
                        break

                # 执行下载操作
                try:
                    print(f"\n📥 正在处理第{download_count + 1}个文件 | 序号：{serial}")
                    simulate_human_click(download_btn)
                    # 标记为已处理，避免重复下载
                    scanned_serials.add(serial)
                    download_count += 1
                except Exception as e:
                    print(f"❌ 序号{serial}下载失败：{e}")
                    # 失败处理选项
                    choice = input("请选择操作：1=重试 2=跳过 3=手动处理后继续（输入数字）：")
                    if choice == "1":
                        print(f"🔄 正在重试序号{serial}...")
                        simulate_human_click(download_btn)
                        scanned_serials.add(serial)
                        download_count += 1
                    elif choice == "2":
                        print(f"➡️  跳过序号{serial}，继续下一个")
                    elif choice == "3":
                        input(f"✅ 手动下载序号{serial}完成后，按回车键继续...")
                        scanned_serials.add(serial)
                        download_count += 1
                    else:
                        print(f"❌ 输入无效，自动跳过序号{serial}")

        # 6. 任务结束统计
        print("\n" + "=" * 50)
        print(f"📊 下载任务统计：")
        print(f"   - 累计下载成功：{download_count}个文件")
        print(f"   - 已处理序号范围：{sorted(scanned_serials) if scanned_serials else '无'}")
        print(f"   - 任务状态：{'正常结束' if is_running else '用户手动停止'}")
        print("=" * 50)

    except Exception as e:
        print(f"\n❌ 脚本运行出错：{e}")
        print("💡 错误排查建议：")
        print("   1. 确保Chrome浏览器已安装且版本最新")
        print("   2. 检查网络是否正常，知网账号是否登录")
        print("   3. 确认当前页面是文献列表页（非详情页）")
    finally:
        # 清理资源：关闭键盘监听和浏览器
        keyboard.unhook_all()
        if driver:
            print("\n🔌 正在关闭浏览器...")
            driver.quit()
        print("\n👋 脚本已完全退出")


# ==================== 启动入口 ====================
if __name__ == "__main__":
    auto_download()