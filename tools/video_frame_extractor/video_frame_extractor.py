
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2, os, re, ctypes
from pathlib import Path
from threading import Thread

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm"}

def get_short_path(long_path):
    try:
        buf = ctypes.create_unicode_buffer(300)
        result = ctypes.windll.kernel32.GetShortPathNameW(long_path, buf, len(buf))
        if result: return buf.value
    except Exception: pass
    return long_path

def safe_imwrite(path, img, fmt="jpg", quality=92):
    try:
        ext = "." + fmt.lower()
        params = []
        if fmt.upper() in ("JPEG", "JPG"):
            params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        elif fmt.upper() == "PNG":
            png_level = int((100 - quality) / 100.0 * 9)
            params = [cv2.IMWRITE_PNG_COMPRESSION, png_level]
        elif fmt.upper() == "WEBP":
            params = [cv2.IMWRITE_WEBP_QUALITY, quality]
        ret, buf = cv2.imencode(ext, img, params)
        if not ret: return False
        with open(path, "wb") as f: f.write(buf.tobytes())
        return True
    except Exception: return False

def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', "_", name).rstrip(". ")


THEME = {"bg":"#1e1e2e","fg":"#cdd6f4","fg_dim":"#a6adc8","fg_bright":"#ffffff","accent":"#89b4fa",
         "accent2":"#a6e3a1","accent_warn":"#fab387","btn_bg":"#45475a","btn_active":"#585b70",
         "entry_bg":"#313244","entry_fg":"#cdd6f4","frame_bg":"#181825","progress_bg":"#313244","border":"#45475a"}

class VideoFrameExtractor:
    def __init__(self, root):
        self.root = root
        self.root.title("视频抽帧工具")
        self.root.geometry("680x760")
        self.root.resizable(True, True)
        self.root.minsize(650, 700)
        self.root.configure(bg=THEME["bg"])
        self.mode = tk.StringVar(value="single")
        self.video_path = tk.StringVar()
        self.folder_path = tk.StringVar()
        self.output_dir = tk.StringVar(value=str(Path.home() / "Desktop"))
        self.fps_value = tk.IntVar(value=1)
        self.add_prefix = tk.BooleanVar(value=True)
        self.start_time = tk.StringVar(value="0")
        self.end_time = tk.StringVar(value="")
        self.img_format = tk.StringVar(value="jpg")
        self.quality = tk.IntVar(value=92)
        self.scale_mode = tk.StringVar(value="100")
        self.custom_width = tk.StringVar(value="")
        self.status_text = tk.StringVar(value="请选择视频文件或拖入视频")
        self.progress_value = tk.DoubleVar(value=0)
        self.video_list_text = tk.StringVar(value="")
        self.running = False
        self.video_files = []
        self.setup_ui()

    def _lbl(self, p, t, s=11, b=False, **kw):
        kw.setdefault("fg", THEME["fg"])
        kw.setdefault("bg", THEME["bg"])
        return tk.Label(p, text=t, font=("Microsoft YaHei", s, "bold" if b else "normal"), **kw)
    def _dim(self, p, t, s=9, **kw):
        kw.setdefault("fg", THEME["fg_dim"])
        kw.setdefault("bg", THEME["bg"])
        return tk.Label(p, text=t, font=("Microsoft YaHei", s), **kw)
    def _btn(self, p, t, cmd, c=None, s=10, **kw):
        kw.setdefault("bg", c if c else THEME["btn_bg"])
        kw.setdefault("fg", THEME["fg_bright"])
        kw.setdefault("activebackground", THEME["btn_active"])
        kw.setdefault("activeforeground", THEME["fg_bright"])
        kw.setdefault("relief", tk.FLAT)
        kw.setdefault("cursor", "hand2")
        kw.setdefault("bd", 0)
        kw.setdefault("padx", 12)
        kw.setdefault("pady", 3)
        return tk.Button(p, text=t, command=cmd, font=("Microsoft YaHei", s), **kw)
    def _ent(self, p, tv, ro=True, **kw):
        kw.setdefault("bg", THEME["entry_bg"])
        kw.setdefault("fg", THEME["entry_fg"])
        kw.setdefault("readonlybackground", THEME["entry_bg"])
        kw.setdefault("relief", tk.FLAT)
        kw.setdefault("bd", 0)
        return tk.Entry(p, textvariable=tv, font=("Microsoft YaHei", 10),
                        state="readonly" if ro else tk.NORMAL, **kw)
    def _chk(self, p, t, v, cmd=None):
        return tk.Checkbutton(p, text=t, variable=v, font=("Microsoft YaHei", 9),
                              fg=THEME["fg"], bg=THEME["bg"], activeforeground=THEME["fg"],
                              activebackground=THEME["bg"], selectcolor=THEME["entry_bg"],
                              relief=tk.FLAT, bd=0, command=cmd)
    def _rad(self, p, t, v, val, cmd=None):
        return tk.Radiobutton(p, text=t, variable=v, value=val, font=("Microsoft YaHei", 10),
                              fg=THEME["fg"], bg=THEME["bg"], activeforeground=THEME["accent"],
                              activebackground=THEME["bg"], selectcolor=THEME["entry_bg"],
                              indicatoron=False, width=7, padx=8, pady=3, relief=tk.FLAT, bd=0, command=cmd)

    def setup_ui(self):
        self._lbl(self.root, "视频抽帧工具", 20, True, fg=THEME["accent"]).pack(pady=(20,3))
        self._dim(self.root, "提取视频帧为图片 · 支持拖入视频 · JPEG/PNG · 画质/缩放可调", 9).pack()
        mf = tk.Frame(self.root, bg=THEME["bg"]); mf.pack(pady=(15,5))
        self._rad(mf, "📁 单视频", self.mode, "single", self.on_mode_change).pack(side=tk.LEFT, padx=(0,4))
        self._rad(mf, "📂 文件夹批量", self.mode, "folder", self.on_mode_change).pack(side=tk.LEFT)
        self.main_frame = tk.Frame(self.root, bg=THEME["bg"])
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=5)
        canvas = tk.Canvas(self.main_frame, bg=THEME["bg"], highlightthickness=0)
        self.scroll_frame = tk.Frame(canvas, bg=THEME["bg"])
        self.scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0), window=self.scroll_frame, anchor="nw")
        self.single_frame = tk.Frame(self.scroll_frame, bg=THEME["bg"])
        self.folder_frame = tk.Frame(self.scroll_frame, bg=THEME["bg"])
        self._build_single_mode(); self._build_folder_mode()
        self.single_frame.pack(fill=tk.BOTH, expand=True)
        self._build_output_settings(self.scroll_frame)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        bottom = tk.Frame(self.root, bg=THEME["bg"]); bottom.pack(fill=tk.X, padx=40, pady=(5,5))
        style = ttk.Style(); style.theme_use("clam")
        style.configure("TProgressbar", troughcolor=THEME["progress_bg"], background=THEME["accent2"],
                        bordercolor=THEME["border"], lightcolor=THEME["accent2"], darkcolor=THEME["accent2"])
        self.progress = ttk.Progressbar(bottom, variable=self.progress_value, maximum=100, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(0,5))
        tk.Label(bottom, textvariable=self.status_text, font=("Microsoft YaHei", 9), fg=THEME["fg_dim"], bg=THEME["bg"]).pack(anchor="w")
        bf = tk.Frame(self.root, bg=THEME["bg"]); bf.pack(pady=(5,20))
        self.start_btn = self._btn(bf, "▶  开始抽帧", self.start_extraction, "#a6e3a1", 14)
        self.start_btn.pack(side=tk.LEFT, padx=(0,12))
        self._btn(bf, "📂 打开输出目录", self.open_output).pack(side=tk.LEFT)

    def _build_single_mode(self):
        r=0; self._lbl(self.single_frame,"视频文件",11,True).grid(row=r,column=0,sticky="w")
        r+=1; ff=tk.Frame(self.single_frame,bg=THEME["bg"])
        ff.grid(row=r,column=0,columnspan=2,sticky="ew",pady=(0,12))
        self._ent(ff,self.video_path).pack(side=tk.LEFT,fill=tk.X,expand=True,ipady=3)
        self._btn(ff,"浏览...",self.browse_video,THEME["accent"]).pack(side=tk.RIGHT,padx=(8,0))
        self._build_common_fields(self.single_frame,2)
        self._build_time_range_fields(self.single_frame,6)
        self.single_info=self._dim(self.single_frame,"",9,fg=THEME["accent_warn"])
        self.single_info.grid(row=9,column=0,columnspan=2,sticky="w",pady=(5,5))

    def _build_folder_mode(self):
        r=0; self._lbl(self.folder_frame,"视频文件夹",11,True).grid(row=r,column=0,sticky="w")
        r+=1; ff=tk.Frame(self.folder_frame,bg=THEME["bg"])
        ff.grid(row=r,column=0,columnspan=2,sticky="ew",pady=(0,12))
        self._ent(ff,self.folder_path).pack(side=tk.LEFT,fill=tk.X,expand=True,ipady=3)
        self._btn(ff,"浏览...",self.browse_folder,THEME["accent_warn"]).pack(side=tk.RIGHT,padx=(8,0))
        self._build_common_fields(self.folder_frame,2)
        self._build_time_range_fields(self.folder_frame,6)
        self.prefix_cb=self._chk(self.folder_frame,"文件名添加父文件夹前缀  (例: 2026070314capture_frame_00001_0.00s.jpg)",self.add_prefix)
        self.prefix_cb.grid(row=9,column=0,columnspan=2,sticky="w",pady=(5,3))
        tk.Label(self.folder_frame, textvariable=self.video_list_text, font=("Microsoft YaHei", 9),
                  fg=THEME["accent_warn"], bg=THEME["bg"], wraplength=560, justify=tk.LEFT).grid(
            row=10, column=0, columnspan=2, sticky="w", pady=(0, 5))

    def _build_common_fields(self, parent, start_row):
        r=start_row; self._lbl(parent,"输出目录",11,True).grid(row=r,column=0,sticky="w",pady=(0,3))
        r+=1; of=tk.Frame(parent,bg=THEME["bg"])
        of.grid(row=r,column=0,columnspan=2,sticky="ew",pady=(0,12))
        self._ent(of,self.output_dir).pack(side=tk.LEFT,fill=tk.X,expand=True,ipady=3)
        self._btn(of,"浏览...",self.browse_output,THEME["accent"]).pack(side=tk.RIGHT,padx=(8,0))
        r+=1; self._lbl(parent,"每秒抽取帧数",11,True).grid(row=r,column=0,sticky="w",pady=(0,3))
        r+=1; ff=tk.Frame(parent,bg=THEME["bg"])
        ff.grid(row=r,column=0,columnspan=2,sticky="ew",pady=(0,5))
        tk.Spinbox(ff,from_=1,to=60,textvariable=self.fps_value,font=("Microsoft YaHei",12),
                   width=8,justify=tk.CENTER,relief=tk.FLAT,bd=3,bg=THEME["entry_bg"],
                   fg=THEME["entry_fg"],buttonbackground=THEME["btn_bg"],
                   command=self.on_fps_change).pack(side=tk.LEFT)
        self._dim(ff,"帧/秒  (1-60)",10).pack(side=tk.LEFT,padx=(10,0))

    def _build_time_range_fields(self, parent, start_row):
        r=start_row
        self._lbl(parent,"⏱ 抽取时间范围（留空=全部）",11,True).grid(row=r,column=0,sticky="w",pady=(10,3))
        r+=1; tr_frame=tk.Frame(parent,bg=THEME["bg"])
        tr_frame.grid(row=r,column=0,columnspan=2,sticky="ew",pady=(0,5))
        self._dim(tr_frame,"从",10).pack(side=tk.LEFT)
        tk.Entry(tr_frame,textvariable=self.start_time,font=("Microsoft YaHei",10),
                 width=6,justify=tk.CENTER,bg=THEME["entry_bg"],fg=THEME["entry_fg"],
                 relief=tk.FLAT,bd=2,insertbackground=THEME["fg"]).pack(side=tk.LEFT,padx=(5,2))
        self._dim(tr_frame,"秒 到",10).pack(side=tk.LEFT)
        tk.Entry(tr_frame,textvariable=self.end_time,font=("Microsoft YaHei",10),
                 width=6,justify=tk.CENTER,bg=THEME["entry_bg"],fg=THEME["entry_fg"],
                 relief=tk.FLAT,bd=2,insertbackground=THEME["fg"]).pack(side=tk.LEFT,padx=(5,2))
        self._dim(tr_frame,"秒（留空=全部）",9).pack(side=tk.LEFT,padx=(2,0))

    def _build_output_settings(self, parent):
        sep=tk.Frame(parent,bg=THEME["border"],height=1); sep.pack(fill=tk.X,pady=(8,8))
        hdr=tk.Frame(parent,bg=THEME["bg"]); hdr.pack(fill=tk.X)
        self._lbl(hdr,"⚙ 输出设置",12,True,fg=THEME["accent"]).pack(side=tk.LEFT)
        st=tk.Frame(parent,bg=THEME["bg"]); st.pack(fill=tk.X,pady=(5,0))
        fmt_f=tk.Frame(st,bg=THEME["bg"]); fmt_f.pack(fill=tk.X,pady=(0,8))
        self._lbl(fmt_f,"图片格式",10).pack(side=tk.LEFT)
        for val,txt in [("jpg","JPEG"),("png","PNG")]:
            tk.Radiobutton(fmt_f,text=txt,variable=self.img_format,value=val,font=("Microsoft YaHei",9),
                           fg=THEME["fg"],bg=THEME["bg"],activeforeground=THEME["accent"],
                           activebackground=THEME["bg"],selectcolor=THEME["entry_bg"],
                           indicatoron=False,width=7,padx=6,pady=2,relief=tk.FLAT,bd=0).pack(side=tk.LEFT,padx=(10,0))
        qual_f=tk.Frame(st,bg=THEME["bg"]); qual_f.pack(fill=tk.X,pady=(0,8))
        self._lbl(qual_f,"画质",10).pack(side=tk.LEFT)
        self.scale_quality=tk.Scale(qual_f,from_=1,to=100,orient=tk.HORIZONTAL,variable=self.quality,
                                     length=160,bg=THEME["bg"],fg=THEME["fg"],troughcolor=THEME["entry_bg"],
                                     highlightthickness=0,activebackground=THEME["accent"],bd=0)
        self.scale_quality.pack(side=tk.LEFT,padx=(10,5))
        self.qual_label=self._dim(qual_f,"92",9); self.qual_label.pack(side=tk.LEFT)
        self.quality.trace_add("write",lambda*_:self.qual_label.config(text=str(self.quality.get())))
        sc_f=tk.Frame(st,bg=THEME["bg"]); sc_f.pack(fill=tk.X,pady=(0,0))
        self._lbl(sc_f,"缩放",10).pack(side=tk.LEFT)
        for val,txt in [("100","原尺寸"),("50","50%"),("25","25%"),("custom","自定义宽")]:
            tk.Radiobutton(sc_f,text=txt,variable=self.scale_mode,value=val,font=("Microsoft YaHei",9),
                           fg=THEME["fg"],bg=THEME["bg"],activeforeground=THEME["accent"],
                           activebackground=THEME["bg"],selectcolor=THEME["entry_bg"],
                           indicatoron=False,width=8,padx=4,pady=2,relief=tk.FLAT,bd=0).pack(side=tk.LEFT,padx=(8,0))
        self.custom_entry=tk.Entry(sc_f,textvariable=self.custom_width,font=("Microsoft YaHei",9),
                                    width=5,justify=tk.CENTER,bg=THEME["entry_bg"],fg=THEME["entry_fg"],
                                    relief=tk.FLAT,bd=2,insertbackground=THEME["fg"])
        self.custom_entry.pack(side=tk.LEFT,padx=(5,0))
        self._dim(sc_f,"px",9).pack(side=tk.LEFT,padx=(2,0))





    def on_mode_change(self):
        if self.mode.get()=="single":
            self.folder_frame.pack_forget(); self.single_frame.pack(fill=tk.BOTH,expand=True)
            self.video_list_text.set("")
            if self.video_path.get(): self.update_single_info()
        else:
            self.single_frame.pack_forget(); self.folder_frame.pack(fill=tk.BOTH,expand=True)
            self.on_fps_change()

    def browse_video(self):
        path=filedialog.askopenfilename(title="选择视频文件",filetypes=[
            ("视频文件","*.mp4 *.avi *.mov *.mkv *.flv *.wmv *.webm"),("所有文件","*.*")])
        if path: self.video_path.set(path); self.update_single_info()

    def browse_folder(self):
        path=filedialog.askdirectory(title="选择视频所在文件夹",
                                     initialdir=self.folder_path.get() or str(Path.home()))
        if path: self.folder_path.set(path); self.scan_videos()

    def browse_output(self):
        path=filedialog.askdirectory(title="选择输出目录",initialdir=self.output_dir.get())
        if path: self.output_dir.set(path)

    def on_fps_change(self):
        if self.mode.get()=="single" and self.video_path.get(): self.update_single_info()
        elif self.mode.get()=="folder" and self.folder_path.get(): self.scan_videos()

    def _parse_time_range(self, video_duration, video_fps):
        try: s=float(self.start_time.get()) if self.start_time.get().strip() else 0
        except ValueError: s=0
        s=max(0,min(s,video_duration))
        end_str=self.end_time.get().strip()
        if end_str:
            try: e=max(s,min(float(end_str),video_duration))
            except ValueError: e=video_duration
        else: e=video_duration
        return int(s*video_fps), int(e*video_fps)

    def _get_video_info(self, vp):
        short=get_short_path(vp); cap=cv2.VideoCapture(short)
        if cap.isOpened():
            total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); fps=cap.get(cv2.CAP_PROP_FPS)
            cap.release(); return total, fps
        cap.release(); return 0, 0

    def update_single_info(self):
        path=self.video_path.get()
        if path and os.path.exists(path):
            total,fps=self._get_video_info(path)
            if fps>0:
                dur=total/fps
                sf,ef=self._parse_time_range(dur,fps); seg_dur=(ef-sf)/fps
                est=int(seg_dur*self.fps_value.get())
                if sf>0 or ef<int(dur*fps):
                    self.single_info.config(text=f"全长:{dur:.1f}s | 区间:{sf/fps:.1f}s~{ef/fps:.1f}s | 区段:{seg_dur:.1f}s | 预计:~{est}张")
                else:
                    self.single_info.config(text=f"时长:{dur:.1f}s | 总帧:{total} | 预计:~{est}张")
            else: self.single_info.config(text="⚠ 无法读取视频")

    def scan_videos(self):
        folder=self.folder_path.get()
        if not folder or not os.path.isdir(folder): return
        self.video_files=[os.path.join(folder,f) for f in os.listdir(folder)
                          if Path(f).suffix.lower() in VIDEO_EXTENSIONS]
        total_est=0; bad=0
        for vf in self.video_files:
            total,fps=self._get_video_info(vf)
            if fps>0:
                dur=total/fps
                sf,ef=self._parse_time_range(dur,fps)
                total_est+=int(((ef-sf)/fps)*self.fps_value.get())
            else: bad+=1
        if self.video_files:
            msg=f"发现 {len(self.video_files)} 个视频 | 预计共抽取 ~{total_est} 张"
            if bad: msg+=f" | ⚠ {bad} 个无法读取"
            if self.add_prefix.get():
                parent_name=sanitize_filename(Path(folder).name)
                msg+=f"\n前缀: [{parent_name}]"
            self.video_list_text.set(msg)
        else: self.video_list_text.set("该文件夹内未找到视频文件")

    def _resize_frame(self, frame):
        mode=self.scale_mode.get(); h,w=frame.shape[:2]
        if mode=="100": return frame
        elif mode=="50": return cv2.resize(frame,(w//2,h//2),interpolation=cv2.INTER_AREA)
        elif mode=="25": return cv2.resize(frame,(w//4,h//4),interpolation=cv2.INTER_AREA)
        elif mode=="custom":
            try:
                cw=int(self.custom_width.get())
                if cw>0 and cw<w:
                    return cv2.resize(frame,(cw,int(h*cw/w)),interpolation=cv2.INTER_AREA)
            except ValueError: pass
        return frame

    def start_extraction(self):
        if self.running: return
        output_dir=self.output_dir.get()
        if not output_dir: messagebox.showwarning("提示","请选择输出目录"); return
        if self.mode.get()=="single":
            video_path=self.video_path.get()
            if not video_path: messagebox.showwarning("提示","请先选择视频文件"); return
            if not os.path.exists(video_path): messagebox.showerror("错误","视频文件不存在"); return
            targets=[video_path]
        else:
            if not self.video_files: messagebox.showwarning("提示","文件夹中未发现视频文件"); return
            targets=list(self.video_files)
        self.running=True; self.start_btn.config(state=tk.DISABLED,text="正在抽取...")
        self.progress_value.set(0); self.status_text.set("正在初始化...")
        Thread(target=self.do_extraction,args=(targets,output_dir),daemon=True).start()

    def do_extraction(self, video_paths, output_dir):
        extract_fps=self.fps_value.get()
        img_fmt=self.img_format.get(); img_quality=self.quality.get()
        total_saved=0; video_count=len(video_paths); skipped=0
        prefix=""
        if self.mode.get()=="folder" and self.add_prefix.get():
            prefix=sanitize_filename(Path(self.folder_path.get()).name)
        try:
            for vi,vp in enumerate(video_paths):
                short=get_short_path(vp); cap=cv2.VideoCapture(short)
                if not cap.isOpened():
                    cap.release()
                    skipped += 1
                    self.root.after(0, lambda n=Path(vp).stem: self.status_text.set(f"⚠ 跳过 '{n}'"))
                    continue
                    self.root.after(0,lambda n=Path(vp).stem:self.status_text.set(f"⚠ 跳过 '{n}'")); continue
                video_fps=cap.get(cv2.CAP_PROP_FPS); total_frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if video_fps <= 0 or total_frames <= 0:
                    cap.release()
                    skipped += 1
                    self.root.after(0, lambda n=Path(vp).stem: self.status_text.set(f"⚠ 跳过 '{n}' — 无法读取"))
                    continue
                actual_efps=min(extract_fps,int(video_fps)); frame_interval=max(1,int(video_fps/actual_efps))
                video_name=Path(vp).stem; safe_name=sanitize_filename(video_name)
                frames_dir=os.path.join(output_dir,f"{safe_name}_frames"); os.makedirs(frames_dir,exist_ok=True)
                video_duration=total_frames/video_fps
                start_frame,end_frame=self._parse_time_range(video_duration,video_fps)
                if start_frame>0:
                    cap.set(cv2.CAP_PROP_POS_FRAMES,start_frame)
                seg_frames=end_frame-start_frame
                self.root.after(0,lambda n=video_name,i=vi,t=video_count,s=start_frame/video_fps,e=end_frame/video_fps:
                    self.status_text.set(f"[{i+1}/{t}] 抽取 '{n}' ({s:.1f}s~{e:.1f}s) ..."))
                saved=0; failed=0; frame_idx=start_frame; last_pct=-1
                while frame_idx<=end_frame:
                    ret,frame=cap.read()
                    if not ret: break
                    if (frame_idx-start_frame)%frame_interval==0:
                        frame=self._resize_frame(frame)
                        timestamp=frame_idx/video_fps
                        fname=(f"{prefix}_{safe_name}_frame_{saved+1:05d}_{timestamp:.2f}s.{img_fmt}"
                               if prefix else f"frame_{saved+1:05d}_{timestamp:.2f}s.{img_fmt}")
                        sp=os.path.join(frames_dir,fname)
                        if safe_imwrite(sp,frame,img_fmt,img_quality): saved+=1
                        else: failed+=1
                    frame_idx+=1
                    if seg_frames>0:
                        pct=int(((frame_idx-start_frame)/seg_frames)*100)
                        if pct!=last_pct:
                            last_pct=pct; self.root.after(0,lambda p=pct:self.progress_value.set(p))
                            self.root.after(0,lambda c=saved,i=vi,t=video_count,n=video_name:
                                self.status_text.set(f"[{i+1}/{t}] '{n}' - 已抽取 {c} 张"))
                cap.release(); total_saved+=saved
                if failed: self.root.after(0,lambda f=failed,n=video_name:
                    self.status_text.set(f"⚠ '{n}' 有 {f} 张写入失败"))
            self.root.after(0,lambda:self.progress_value.set(100))
            msg=f"完成！共 {video_count} 个视频，抽取 {total_saved} 张"
            if skipped: msg+=f"，跳过 {skipped} 个"
            self.on_finished(msg)
        except Exception as e: self.on_finished(f"出错: {str(e)}")

    def on_finished(self, msg):
        self.running=False; self.start_btn.config(state=tk.NORMAL,text="▶  开始抽帧")
        self.status_text.set(msg)
        output_dir=self.output_dir.get()
        if output_dir and os.path.isdir(output_dir):
            if messagebox.askyesno("完成",f"{msg}\n\n是否打开输出目录？"): os.startfile(output_dir)

    def open_output(self):
        d=self.output_dir.get()
        if d and os.path.isdir(d): os.startfile(d)
        else: messagebox.showwarning("提示","输出目录不存在")

if __name__=="__main__":
    root=tk.Tk(); app=VideoFrameExtractor(root); root.mainloop()
