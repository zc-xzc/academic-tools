import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
import os
import re
import ctypes
from pathlib import Path
from threading import Thread


VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm"}


def get_short_path(long_path):
    """将含中文的路径转为 Windows 8.3 短路径，绕过 OpenCV 的 Unicode 问题。"""
    try:
        buf = ctypes.create_unicode_buffer(300)
        result = ctypes.windll.kernel32.GetShortPathNameW(long_path, buf, len(buf))
        if result:
            return buf.value
    except Exception:
        pass
    return long_path


def safe_imwrite(path, img, quality=92):
    """用 Python 原生 IO 写图片，彻底避免 cv2.imwrite 的 Unicode 路径问题。"""
    try:
        ret, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ret:
            return False
        with open(path, "wb") as f:
            f.write(buf.tobytes())
        return True
    except Exception:
        return False


def sanitize_filename(name):
    """保留中文，只移除文件系统不允许的字符。"""
    return re.sub(r'[<>:"/\\|?*]', "_", name).rstrip(". ")


class VideoFrameExtractor:
    def __init__(self, root):
        self.root = root
        self.root.title("视频抽帧工具")
        self.root.geometry("650x580")
        self.root.resizable(False, False)

        self.mode = tk.StringVar(value="single")
        self.video_path = tk.StringVar()
        self.folder_path = tk.StringVar()
        self.output_dir = tk.StringVar(value=str(Path.home() / "Desktop"))
        self.fps_value = tk.IntVar(value=1)
        self.add_prefix = tk.BooleanVar(value=True)
        self.status_text = tk.StringVar(value="请选择视频文件或文件夹")
        self.progress_value = tk.DoubleVar(value=0)
        self.video_list_text = tk.StringVar(value="")
        self.running = False
        self.video_files = []

        self.setup_ui()

    def setup_ui(self):
        title = tk.Label(
            self.root, text="视频抽帧工具",
            font=("Microsoft YaHei", 18, "bold"), fg="#2c3e50"
        )
        title.pack(pady=(20, 5))

        tk.Label(
            self.root, text="提取视频中的帧保存为图片",
            font=("Microsoft YaHei", 10), fg="#7f8c8d"
        ).pack()

        # 模式切换
        mode_frame = tk.Frame(self.root)
        mode_frame.pack(pady=(15, 0))
        tk.Radiobutton(
            mode_frame, text="单视频", variable=self.mode, value="single",
            font=("Microsoft YaHei", 11), command=self.on_mode_change,
            indicatoron=False, width=10, padx=10, pady=4,
            selectcolor="#3498db", fg="#2c3e50"
        ).pack(side=tk.LEFT, padx=(0, 5))
        tk.Radiobutton(
            mode_frame, text="文件夹批量", variable=self.mode, value="folder",
            font=("Microsoft YaHei", 11), command=self.on_mode_change,
            indicatoron=False, width=10, padx=10, pady=4,
            selectcolor="#e67e22", fg="#2c3e50"
        ).pack(side=tk.LEFT)

        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=10)

        self.single_frame = tk.Frame(self.main_frame)
        self.folder_frame = tk.Frame(self.main_frame)

        self._build_single_mode()
        self._build_folder_mode()

        self.single_frame.pack(fill=tk.BOTH, expand=True)

        # 进度 & 状态
        bottom = tk.Frame(self.root)
        bottom.pack(fill=tk.X, padx=40, pady=(0, 5))
        self.progress = ttk.Progressbar(
            bottom, variable=self.progress_value, maximum=100, mode="determinate"
        )
        self.progress.pack(fill=tk.X, pady=(0, 5))
        tk.Label(
            bottom, textvariable=self.status_text,
            font=("Microsoft YaHei", 9), fg="#2c3e50"
        ).pack(anchor="w")

        # 按钮
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=(5, 20))
        self.start_btn = tk.Button(
            btn_frame, text="开始抽帧", command=self.start_extraction,
            font=("Microsoft YaHei", 13, "bold"), width=15, height=2,
            bg="#27ae60", fg="white", activebackground="#219a52",
            relief=tk.FLAT, cursor="hand2"
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 15))
        tk.Button(
            btn_frame, text="打开输出目录", command=self.open_output,
            font=("Microsoft YaHei", 11), width=12, height=2,
            bg="#95a5a6", fg="white", activebackground="#7f8c8d",
            relief=tk.FLAT, cursor="hand2"
        ).pack(side=tk.LEFT)

    def _build_single_mode(self):
        row = 0
        tk.Label(self.single_frame, text="视频文件", font=("Microsoft YaHei", 11)).grid(
            row=row, column=0, sticky="w"
        )
        row += 1
        ff = tk.Frame(self.single_frame)
        ff.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 15))
        tk.Entry(
            ff, textvariable=self.video_path, font=("Microsoft YaHei", 10),
            state="readonly", relief=tk.SUNKEN
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        tk.Button(
            ff, text="浏览...", command=self.browse_video,
            font=("Microsoft YaHei", 10), width=8, bg="#3498db", fg="white",
            activebackground="#2980b9", relief=tk.FLAT, cursor="hand2"
        ).pack(side=tk.RIGHT, padx=(8, 0))

        self._build_common_fields(self.single_frame, start_row=2)
        self.single_info = tk.Label(
            self.single_frame, text="", font=("Microsoft YaHei", 9), fg="#e67e22"
        )
        self.single_info.grid(row=7, column=0, columnspan=2, sticky="w", pady=(0, 10))

    def _build_folder_mode(self):
        row = 0
        tk.Label(self.folder_frame, text="视频文件夹", font=("Microsoft YaHei", 11)).grid(
            row=row, column=0, sticky="w"
        )
        row += 1
        ff = tk.Frame(self.folder_frame)
        ff.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 15))
        tk.Entry(
            ff, textvariable=self.folder_path, font=("Microsoft YaHei", 10),
            state="readonly", relief=tk.SUNKEN
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        tk.Button(
            ff, text="浏览...", command=self.browse_folder,
            font=("Microsoft YaHei", 10), width=8, bg="#e67e22", fg="white",
            activebackground="#d35400", relief=tk.FLAT, cursor="hand2"
        ).pack(side=tk.RIGHT, padx=(8, 0))

        self._build_common_fields(self.folder_frame, start_row=2)

        # 文件夹专属选项：添加父文件夹前缀
        self.prefix_cb = tk.Checkbutton(
            self.folder_frame,
            text="图片文件名自动添加父文件夹前缀  (例: 2026070314capture_frame_00001_0.00s.jpg)",
            variable=self.add_prefix,
            font=("Microsoft YaHei", 9), fg="#2c3e50",
            activeforeground="#2c3e50",
            selectcolor=self.folder_frame.cget("bg") if hasattr(self.folder_frame, 'cget') else "#f0f0f0"
        )
        self.prefix_cb.grid(row=7, column=0, columnspan=2, sticky="w", pady=(5, 5))

        tk.Label(
            self.folder_frame, textvariable=self.video_list_text,
            font=("Microsoft YaHei", 9), fg="#e67e22", justify=tk.LEFT
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(0, 10))

    def _build_common_fields(self, parent, start_row):
        r = start_row
        tk.Label(parent, text="输出目录", font=("Microsoft YaHei", 11)).grid(
            row=r, column=0, sticky="w", pady=(0, 5)
        )
        r += 1
        of = tk.Frame(parent)
        of.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(0, 15))
        tk.Entry(
            of, textvariable=self.output_dir, font=("Microsoft YaHei", 10),
            state="readonly", relief=tk.SUNKEN
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        tk.Button(
            of, text="浏览...", command=self.browse_output,
            font=("Microsoft YaHei", 10), width=8, bg="#3498db", fg="white",
            activebackground="#2980b9", relief=tk.FLAT, cursor="hand2"
        ).pack(side=tk.RIGHT, padx=(8, 0))

        r += 1
        tk.Label(parent, text="每秒抽取帧数", font=("Microsoft YaHei", 11)).grid(
            row=r, column=0, sticky="w", pady=(0, 5)
        )
        r += 1
        ff = tk.Frame(parent)
        ff.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        tk.Spinbox(
            ff, from_=1, to=60, textvariable=self.fps_value,
            font=("Microsoft YaHei", 12), width=8, justify=tk.CENTER,
            relief=tk.SUNKEN, command=self.on_fps_change
        ).pack(side=tk.LEFT)
        tk.Label(
            ff, text="帧/秒  (1-60)", font=("Microsoft YaHei", 10), fg="#7f8c8d"
        ).pack(side=tk.LEFT, padx=(10, 0))

    def on_mode_change(self):
        if self.mode.get() == "single":
            self.folder_frame.pack_forget()
            self.single_frame.pack(fill=tk.BOTH, expand=True)
            self.video_list_text.set("")
            if self.video_path.get():
                self.update_single_info()
        else:
            self.single_frame.pack_forget()
            self.folder_frame.pack(fill=tk.BOTH, expand=True)
            self.on_fps_change()

    def browse_video(self):
        path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[
                ("视频文件", "*.mp4 *.avi *.mov *.mkv *.flv *.wmv *.webm"),
                ("所有文件", "*.*")
            ]
        )
        if path:
            self.video_path.set(path)
            self.update_single_info()

    def browse_folder(self):
        path = filedialog.askdirectory(
            title="选择视频所在文件夹",
            initialdir=self.folder_path.get() or str(Path.home())
        )
        if path:
            self.folder_path.set(path)
            self.scan_videos()

    def browse_output(self):
        path = filedialog.askdirectory(
            title="选择输出目录", initialdir=self.output_dir.get()
        )
        if path:
            self.output_dir.set(path)

    def on_fps_change(self):
        if self.mode.get() == "single" and self.video_path.get():
            self.update_single_info()
        elif self.mode.get() == "folder" and self.folder_path.get():
            self.scan_videos()

    def _get_video_info(self, vp):
        """用短路径打开视频，避免 Unicode 问题。"""
        short = get_short_path(vp)
        cap = cv2.VideoCapture(short)
        if cap.isOpened():
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            cap.release()
            return total, fps
        cap.release()
        return 0, 0

    def update_single_info(self):
        path = self.video_path.get()
        if path and os.path.exists(path):
            total, fps = self._get_video_info(path)
            if fps > 0:
                dur = total / fps
                est = int(dur * self.fps_value.get())
                self.single_info.config(
                    text=f"时长: {dur:.1f}s | 总帧: {total} | 预计: ~{est} 张"
                )
            else:
                self.single_info.config(text="⚠ 无法读取视频，可能是编码不兼容")

    def scan_videos(self):
        folder = self.folder_path.get()
        if not folder or not os.path.isdir(folder):
            return
        self.video_files = [
            os.path.join(folder, f) for f in os.listdir(folder)
            if Path(f).suffix.lower() in VIDEO_EXTENSIONS
        ]
        total_est = 0
        bad = 0
        for vf in self.video_files:
            total, fps = self._get_video_info(vf)
            if fps > 0:
                total_est += int((total / fps) * self.fps_value.get())
            else:
                bad += 1

        if self.video_files:
            msg = f"发现 {len(self.video_files)} 个视频 | 预计共抽取 ~{total_est} 张"
            if bad:
                msg += f" | ⚠ {bad} 个无法读取"
            if self.add_prefix.get():
                parent_name = sanitize_filename(Path(folder).name)
                msg += f"\n前缀: [{parent_name}]"
            self.video_list_text.set(msg)
        else:
            self.video_list_text.set("该文件夹内未找到视频文件")

    def start_extraction(self):
        if self.running:
            return
        output_dir = self.output_dir.get()
        if not output_dir:
            messagebox.showwarning("提示", "请选择输出目录")
            return

        if self.mode.get() == "single":
            video_path = self.video_path.get()
            if not video_path:
                messagebox.showwarning("提示", "请先选择视频文件")
                return
            if not os.path.exists(video_path):
                messagebox.showerror("错误", "视频文件不存在")
                return
            targets = [video_path]
        else:
            if not self.video_files:
                messagebox.showwarning("提示", "文件夹中未发现视频文件")
                return
            targets = list(self.video_files)

        self.running = True
        self.start_btn.config(state=tk.DISABLED, text="正在抽取...")
        self.progress_value.set(0)
        self.status_text.set("正在初始化...")
        Thread(
            target=self.do_extraction, args=(targets, output_dir), daemon=True
        ).start()

    def do_extraction(self, video_paths, output_dir):
        extract_fps = self.fps_value.get()
        total_saved = 0
        video_count = len(video_paths)
        skipped = 0

        # 文件夹模式的前缀
        prefix = ""
        if self.mode.get() == "folder" and self.add_prefix.get():
            folder_path = self.folder_path.get()
            prefix = sanitize_filename(Path(folder_path).name)

        try:
            for vi, vp in enumerate(video_paths):
                short = get_short_path(vp)
                cap = cv2.VideoCapture(short)
                if not cap.isOpened():
                    cap.release()
                    skipped += 1
                    video_name = Path(vp).stem
                    self.root.after(0, lambda n=video_name: self.status_text.set(
                        f"⚠ 跳过 '{n}' — 无法打开视频"
                    ))
                    continue

                video_fps = cap.get(cv2.CAP_PROP_FPS)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if video_fps <= 0 or total_frames <= 0:
                    cap.release()
                    skipped += 1
                    video_name = Path(vp).stem
                    self.root.after(0, lambda n=video_name: self.status_text.set(
                        f"⚠ 跳过 '{n}' — 无法读取视频信息"
                    ))
                    continue

                actual_extract_fps = min(extract_fps, int(video_fps))
                frame_interval = max(1, int(video_fps / actual_extract_fps))

                video_name = Path(vp).stem
                safe_name = sanitize_filename(video_name)
                frames_dir = os.path.join(output_dir, f"{safe_name}_frames")
                os.makedirs(frames_dir, exist_ok=True)

                self.root.after(
                    0,
                    lambda n=video_name, i=vi, t=video_count: self.status_text.set(
                        f"[{i + 1}/{t}] 正在抽取 '{n}' ..."
                    )
                )

                saved = 0
                failed = 0
                frame_idx = 0
                last_pct = -1

                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break

                    if frame_idx % frame_interval == 0:
                        timestamp = frame_idx / video_fps
                        # 构建文件名：可选前缀
                        if prefix:
                            fname = f"{prefix}_{safe_name}_frame_{saved + 1:05d}_{timestamp:.2f}s.jpg"
                        else:
                            fname = f"frame_{saved + 1:05d}_{timestamp:.2f}s.jpg"
                        sp = os.path.join(frames_dir, fname)
                        if safe_imwrite(sp, frame):
                            saved += 1
                        else:
                            failed += 1

                    frame_idx += 1

                    pct = int((frame_idx / total_frames) * 100)
                    if pct != last_pct:
                        last_pct = pct
                        self.root.after(0, lambda p=pct: self.progress_value.set(p))
                        self.root.after(
                            0,
                            lambda c=saved, i=vi, t=video_count, n=video_name: self.status_text.set(
                                f"[{i + 1}/{t}] '{n}' - 已抽取 {c} 张"
                            )
                        )

                cap.release()
                total_saved += saved
                if failed:
                    self.root.after(
                        0,
                        lambda f=failed, n=video_name: self.status_text.set(
                            f"⚠ '{n}' 有 {f} 张写入失败"
                        )
                    )

            self.root.after(0, lambda: self.progress_value.set(100))
            msg = f"完成！共 {video_count} 个视频，抽取 {total_saved} 张"
            if skipped:
                msg += f"，跳过 {skipped} 个"
            self.on_finished(msg)

        except Exception as e:
            self.on_finished(f"出错: {str(e)}")

    def on_finished(self, msg):
        self.running = False
        self.start_btn.config(state=tk.NORMAL, text="开始抽帧")
        self.status_text.set(msg)
        output_dir = self.output_dir.get()
        if output_dir and os.path.isdir(output_dir):
            result = messagebox.askyesno(
                "完成", f"{msg}\n\n是否打开输出目录？"
            )
            if result:
                os.startfile(output_dir)

    def open_output(self):
        d = self.output_dir.get()
        if d and os.path.isdir(d):
            os.startfile(d)
        else:
            messagebox.showwarning("提示", "输出目录不存在")


if __name__ == "__main__":
    root = tk.Tk()
    app = VideoFrameExtractor(root)
    root.mainloop()
