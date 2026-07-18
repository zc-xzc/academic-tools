import time
import sys

class FullApplication:
    def __init__(self):
        # 初始化数据存储
        self.user_data = []  # 用户数据列表
        self.system_config = {
            "theme": "light",
            "notifications": True,
            "version": "1.0.0"
        }
        self.current_user = None  # 当前登录用户

    def print_separator(self):
        """打印分隔线，优化界面展示"""
        print("\n" + "="*40 + "\n")

    def main_menu(self):
        """主菜单模块：作为所有功能的入口"""
        while True:
            self.print_separator()
            print("===== 主功能菜单 =====")
            print("1. 用户管理模块")
            print("2. 数据操作模块")
            print("3. 系统设置模块")
            print("4. 信息展示模块")
            print("5. 退出程序")
            choice = input("请选择功能模块(1-5)：")

            if choice == "1":
                self.user_management()
            elif choice == "2":
                self.data_operation()
            elif choice == "3":
                self.system_settings()
            elif choice == "4":
                self.info_display()
            elif choice == "5":
                print("正在退出程序...感谢使用")
                time.sleep(1)
                sys.exit()
            else:
                print("输入错误，请重新选择！")
                time.sleep(1)

    def user_management(self):
        """用户管理模块：登录、注册、注销功能"""
        while True:
            self.print_separator()
            print("===== 用户管理模块 =====")
            print(f"当前登录用户：{self.current_user if self.current_user else '未登录'}")
            print("1. 用户注册")
            print("2. 用户登录")
            print("3. 用户注销")
            print("4. 返回主菜单")
            choice = input("请选择操作(1-4)：")

            if choice == "1":
                self.user_register()
            elif choice == "2":
                self.user_login()
            elif choice == "3":
                self.user_logout()
            elif choice == "4":
                print("返回主菜单...")
                time.sleep(0.5)
                break
            else:
                print("输入错误，请重新选择！")
                time.sleep(1)

    def user_register(self):
        """用户注册功能"""
        print("\n----- 用户注册 -----")
        username = input("请输入用户名：").strip()
        # 检查用户名是否已存在
        if any(user["username"] == username for user in self.user_data):
            print("用户名已存在！")
            time.sleep(1)
            return
        password = input("请输入密码：").strip()
        if len(password) < 6:
            print("密码长度不能少于6位！")
            time.sleep(1)
            return
        # 保存用户数据
        self.user_data.append({
            "username": username,
            "password": password,
            "register_time": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        print(f"用户 {username} 注册成功！")
        time.sleep(1)

    def user_login(self):
        """用户登录功能"""
        if self.current_user:
            print(f"您已登录：{self.current_user}，无需重复登录")
            time.sleep(1)
            return
        print("\n----- 用户登录 -----")
        username = input("请输入用户名：").strip()
        password = input("请输入密码：").strip()
        # 验证用户信息
        for user in self.user_data:
            if user["username"] == username and user["password"] == password:
                self.current_user = username
                print(f"登录成功！欢迎回来，{username}")
                time.sleep(1)
                return
        print("用户名或密码错误！")
        time.sleep(1)

    def user_logout(self):
        """用户注销功能"""
        if not self.current_user:
            print("您尚未登录，无需注销")
            time.sleep(1)
            return
        print(f"用户 {self.current_user} 已注销")
        self.current_user = None
        time.sleep(1)

    def data_operation(self):
        """数据操作模块：增删改查功能"""
        # 验证登录状态
        if not self.current_user:
            print("请先登录才能操作数据！")
            time.sleep(1)
            return

        while True:
            self.print_separator()
            print("===== 数据操作模块 =====")
            print(f"当前操作用户：{self.current_user}")
            print("1. 添加数据")
            print("2. 查看所有数据")
            print("3. 修改数据")
            print("4. 删除数据")
            print("5. 返回主菜单")
            choice = input("请选择操作(1-5)：")

            if choice == "1":
                self.add_data()
            elif choice == "2":
                self.view_all_data()
            elif choice == "3":
                self.modify_data()
            elif choice == "4":
                self.delete_data()
            elif choice == "5":
                print("返回主菜单...")
                time.sleep(0.5)
                break
            else:
                print("输入错误，请重新选择！")
                time.sleep(1)

    def add_data(self):
        """添加数据功能"""
        print("\n----- 添加数据 -----")
        data_name = input("请输入数据名称：").strip()
        data_content = input("请输入数据内容：").strip()
        # 为当前用户添加数据（关联用户）
        for user in self.user_data:
            if user["username"] == self.current_user:
                # 初始化用户数据列表（如果不存在）
                if "data" not in user:
                    user["data"] = []
                user["data"].append({
                    "id": len(user["data"]) + 1,
                    "name": data_name,
                    "content": data_content,
                    "create_time": time.strftime("%Y-%m-%d %H:%M:%S")
                })
                print(f"数据 '{data_name}' 添加成功！")
                time.sleep(1)
                return

    def view_all_data(self):
        """查看所有数据功能"""
        print("\n----- 所有数据 -----")
        for user in self.user_data:
            if user["username"] == self.current_user:
                if "data" not in user or not user["data"]:
                    print("暂无数据，请先添加")
                    time.sleep(1)
                    return
                # 展示数据列表
                for item in user["data"]:
                    print(f"ID: {item['id']} | 名称: {item['name']} | 创建时间: {item['create_time']}")
                    print(f"内容: {item['content']}\n")
                time.sleep(2)
                return

    def modify_data(self):
        """修改数据功能"""
        print("\n----- 修改数据 -----")
        for user in self.user_data:
            if user["username"] == self.current_user:
                if "data" not in user or not user["data"]:
                    print("暂无数据，无法修改")
                    time.sleep(1)
                    return
                try:
                    data_id = int(input("请输入要修改的数据ID："))
                    # 查找对应ID的数据
                    for item in user["data"]:
                        if item["id"] == data_id:
                            new_name = input("请输入新名称（不修改按回车）：").strip()
                            new_content = input("请输入新内容（不修改按回车）：").strip()
                            if new_name:
                                item["name"] = new_name
                            if new_content:
                                item["content"] = new_content
                            item["update_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                            print("数据修改成功！")
                            time.sleep(1)
                            return
                    print("未找到对应ID的数据")
                except ValueError:
                    print("ID必须是数字！")
                time.sleep(1)
                return

    def delete_data(self):
        """删除数据功能"""
        print("\n----- 删除数据 -----")
        for user in self.user_data:
            if user["username"] == self.current_user:
                if "data" not in user or not user["data"]:
                    print("暂无数据，无法删除")
                    time.sleep(1)
                    return
                try:
                    data_id = int(input("请输入要删除的数据ID："))
                    # 查找并删除对应ID的数据
                    for i, item in enumerate(user["data"]):
                        if item["id"] == data_id:
                            del user["data"][i]
                            # 重新编号ID（保持连续性）
                            for j in range(i, len(user["data"])):
                                user["data"][j]["id"] = j + 1
                            print("数据删除成功！")
                            time.sleep(1)
                            return
                    print("未找到对应ID的数据")
                except ValueError:
                    print("ID必须是数字！")
                time.sleep(1)
                return

    def system_settings(self):
        """系统设置模块：配置修改功能"""
        while True:
            self.print_separator()
            print("===== 系统设置模块 =====")
            print(f"1. 主题设置（当前：{self.system_config['theme']}）")
            print(f"2. 通知设置（当前：{'开启' if self.system_config['notifications'] else '关闭'}）")
            print("3. 查看系统信息")
            print("4. 返回主菜单")
            choice = input("请选择操作(1-4)：")

            if choice == "1":
                new_theme = input("请输入主题（light/dark）：").strip().lower()
                if new_theme in ["light", "dark"]:
                    self.system_config["theme"] = new_theme
                    print(f"主题已设置为：{new_theme}")
                else:
                    print("主题只能是light或dark！")
                time.sleep(1)
            elif choice == "2":
                self.system_config["notifications"] = not self.system_config["notifications"]
                print(f"通知已{'开启' if self.system_config['notifications'] else '关闭'}")
                time.sleep(1)
            elif choice == "3":
                print("\n----- 系统信息 -----")
                print(f"版本号：{self.system_config['version']}")
                print(f"当前时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"注册用户数：{len(self.user_data)}")
                print(f"当前登录用户：{self.current_user if self.current_user else '未登录'}")
                time.sleep(2)
            elif choice == "4":
                print("返回主菜单...")
                time.sleep(0.5)
                break
            else:
                print("输入错误，请重新选择！")
                time.sleep(1)

    def info_display(self):
        """信息展示模块：数据统计与帮助"""
        while True:
            self.print_separator()
            print("===== 信息展示模块 =====")
            print("1. 数据统计")
            print("2. 使用帮助")
            print("3. 返回主菜单")
            choice = input("请选择操作(1-3)：")

            if choice == "1":
                self.data_statistics()
            elif choice == "2":
                self.show_help()
            elif choice == "3":
                print("返回主菜单...")
                time.sleep(0.5)
                break
            else:
                print("输入错误，请重新选择！")
                time.sleep(1)

    def data_statistics(self):
        """数据统计功能"""
        print("\n----- 数据统计 -----")
        total_users = len(self.user_data)
        total_data = 0
        for user in self.user_data:
            if "data" in user:
                total_data += len(user["data"])
        print(f"注册用户总数：{total_users}")
        print(f"所有用户数据总数：{total_data}")
        if self.current_user:
            for user in self.user_data:
                if user["username"] == self.current_user:
                    user_data_count = len(user["data"]) if "data" in user else 0
                    print(f"当前用户数据数量：{user_data_count}")
                    break
        time.sleep(2)

    def show_help(self):
        """使用帮助功能"""
        print("\n----- 使用帮助 -----")
        print("1. 首先需在【用户管理模块】完成注册和登录")
        print("2. 登录后可在【数据操作模块】进行数据的增删改查")
        print("3. 【系统设置模块】可修改主题和通知状态")
        print("4. 【信息展示模块】可查看数据统计和帮助信息")
        print("5. 所有模块均可通过菜单返回上级或主菜单")1
        input("按回车键返回...")

if __name__ == "__main__":
    # 初始化并启动应用
    app = FullApplication()
    print("欢迎使用完整功能应用系统！")
    app.main_menu()