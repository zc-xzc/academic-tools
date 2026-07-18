import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os


class TxtSplitter:
    def __init__(self, root):
        self.root = root
        self.root.title("TXT文档分割工具")
        self.root.geometry("500x300")
        self.root.resizable(False, False)

        # 设置中文字体
        self.style = ttk.Style()
        self.style.configure("TLabel", font=("SimHei", 10))
        self.style.configure("TButton", font=("SimHei", 10))
        self.style.configure("TRadiobutton", font=("SimHei", 10))

        # 选择的文件路径
        self.file_path = ""

        # 创建界面元素
        self.create_widgets()

    def create_widgets(self):
        # 文件选择区域
        file_frame = ttk.Frame(self.root, padding="10")
        file_frame.pack(fill=tk.X)

        ttk.Label(file_frame, text="选择TXT文件:").pack(side=tk.LEFT, padx=5)
        self.file_entry = ttk.Entry(file_frame)
        self.file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        browse_btn = ttk.Button(file_frame, text="浏览", command=self.browse_file)
        browse_btn.pack(side=tk.LEFT, padx=5)

        # 分割方式选择
        split_frame = ttk.Frame(self.root, padding="10")
        split_frame.pack(fill=tk.X)

        self.split_var = tk.StringVar(value="words")
        ttk.Radiobutton(split_frame, text="按每份字数分割", variable=self.split_var, value="words").pack(side=tk.LEFT,
                                                                                                         padx=10)
        ttk.Radiobutton(split_frame, text="按指定份数分割", variable=self.split_var, value="parts").pack(side=tk.LEFT,
                                                                                                         padx=10)

        # 数量输入区域
        num_frame = ttk.Frame(self.root, padding="10")
        num_frame.pack(fill=tk.X)

        self.num_label = ttk.Label(num_frame, text="每份字数:")
        self.num_label.pack(side=tk.LEFT, padx=5)

        self.num_entry = ttk.Entry(num_frame, width=10)
        self.num_entry.pack(side=tk.LEFT, padx=5)
        self.num_entry.insert(0, "1000")  # 默认值

        # 绑定分割方式变化事件
        self.split_var.trace_add("write", self.update_label)

        # 操作按钮区域
        btn_frame = ttk.Frame(self.root, padding="10")
        btn_frame.pack(fill=tk.X)

        split_btn = ttk.Button(btn_frame, text="开始分割", command=self.split_file)
        split_btn.pack(pady=10)

        # 状态显示区域
        self.status_var = tk.StringVar(value="请选择文件并设置分割参数")
        status_label = ttk.Label(self.root, textvariable=self.status_var, foreground="blue")
        status_label.pack(pady=10)

    def update_label(self, *args):
        """根据分割方式更新标签文本"""
        if self.split_var.get() == "words":
            self.num_label.config(text="每份字数:")
            self.num_entry.delete(0, tk.END)
            self.num_entry.insert(0, "1000")
        else:
            self.num_label.config(text="分割份数:")
            self.num_entry.delete(0, tk.END)
            self.num_entry.insert(0, "5")

    def browse_file(self):
        """浏览并选择TXT文件"""
        file_path = filedialog.askopenfilename(
            title="选择TXT文件",
            filetypes=[("TXT文件", "*.txt"), ("所有文件", "*.*")]
        )
        if file_path:
            self.file_path = file_path
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, file_path)
            self.status_var.set(f"已选择文件: {os.path.basename(file_path)}")

    def split_file(self):
        """分割文件的主函数"""
        if not self.file_path:
            messagebox.showerror("错误", "请先选择TXT文件")
            return

        try:
            num = int(self.num_entry.get())
            if num <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字")
            return

        try:
            # 读取文件内容
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            total_length = len(content)
            if total_length == 0:
                messagebox.showinfo("提示", "文件内容为空，无需分割")
                return

            # 创建保存分割文件的目录
            dir_name = os.path.splitext(os.path.basename(self.file_path))[0] + "_split"
            dir_path = os.path.join(os.path.dirname(self.file_path), dir_name)
            os.makedirs(dir_path, exist_ok=True)

            # 按字数分割
            if self.split_var.get() == "words":
                if num >= total_length:
                    messagebox.showinfo("提示", "分割字数大于等于文件总字数，无需分割")
                    return

                parts = []
                for i in range(0, total_length, num):
                    parts.append(content[i:i + num])

                self.save_parts(parts, dir_path)
                self.status_var.set(f"分割完成，共生成 {len(parts)} 个文件，保存在 {dir_path}")
                messagebox.showinfo("成功", f"分割完成，共生成 {len(parts)} 个文件\n保存路径: {dir_path}")

            # 按份数分割
            else:
                if num >= total_length:
                    num = total_length  # 防止份数多于字数

                part_size = total_length // num
                parts = []

                for i in range(num):
                    start = i * part_size
                    # 最后一部分取到末尾
                    end = (i + 1) * part_size if i < num - 1 else total_length
                    parts.append(content[start:end])

                self.save_parts(parts, dir_path)
                self.status_var.set(f"分割完成，共生成 {num} 个文件，保存在 {dir_path}")
                messagebox.showinfo("成功", f"分割完成，共生成 {num} 个文件\n保存路径: {dir_path}")

        except Exception as e:
            messagebox.showerror("错误", f"分割失败: {str(e)}")
            self.status_var.set(f"分割失败: {str(e)}")

    def save_parts(self, parts, dir_path):
        """保存分割后的文件"""
        base_name = os.path.splitext(os.path.basename(self.file_path))[0]

        for i, part in enumerate(parts):
            file_name = f"{base_name}_part{i + 1}.txt"
            file_path = os.path.join(dir_path, file_name)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(part)


if __name__ == "__main__":
    root = tk.Tk()
    app = TxtSplitter(root)
    root.mainloop()