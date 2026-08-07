<!-- licensing-notice -->
> [!NOTE]
> This repository includes third-party material. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for attribution, license scope and lawful-use requirements.

# Academic Tools

个人学术科研与文件处理工具箱。包含政策文本分析、文件批量处理、PDF 重命名、视频抽帧等 Python 工具，以及一组 Claude 技能（Skills）。

## 目录结构总览

```
academic-tools/
├── classification/          # 政策文本分类与统计分析
├── file_utils/              # 文件批量处理（合并 / 重命名 / 文本处理）
├── pdf_utils/               # PDF 批量重命名
├── models/                  # 应用框架示例
├── tools/                   # 实用小工具（自动点击 / 文档分割 / 视频抽帧）
├── skills/                  # Claude 技能定义
├── README.md
├── LICENSE                 (MIT)
└── THIRD_PARTY_NOTICES.md
```

---

## 一、政策文本分析（classification/）

面向"数字政府 / 环境规制"等政策文本库的自动化分析工具。

### 1.1 政策要素提取 — `classification/element/scripts/`

对政策文件进行多维分类与要素提取：

| 文件 | 说明 |
|------|------|
| `element_extract_v1.py` | V1：按政府层级（国家/省/市/区县）等维度分类 |
| `element_extract_v2.py` | V2：改进版 |
| `element_extract_v3.py` | V3：最新版，含多维度分类标准配置 |

**依赖**：`pandas numpy matplotlib seaborn python-docx PyPDF2`

**用法**：修改脚本顶部 `INPUT_DIR` / `OUTPUT_DIR` 路径后运行：

```bash
python classification/element/scripts/element_extract_v1.py
```

### 1.2 政策描述性统计 — `classification/policy/policy_stats.py`

对政策文本做描述性统计分析，自动生成 Markdown 报告 + 图表：

- 时间分布（各年份政策数量）
- 省级 / 城市群区域分布
- 时空分布热力图
- 规制工具类型分布
- 环境要素分布

**依赖**：`pandas numpy matplotlib`

**用法**：修改 `MAIN_FOLDER` 为政策文本目录后运行：

```bash
python classification/policy/policy_stats.py
```

输出：`政策文本描述性统计分析报告.md` 及多张 PNG 图表。

---

## 二、文件批量处理（file_utils/）

### 2.1 文件合并 — `file_utils/merge/`

批量合并政策文件 / 目录列表的系列脚本（按迭代版本从 V2 到 V6）：

| 文件 | 说明 |
|------|------|
| `merge_basic.py` | 基础版：按 Excel 目录列表合并 txt 文件 |
| `merge_v2.py` ~ `merge_v6_*.py` | 迭代优化版，逐步加入模糊匹配、子目录递归、统计等能力 |
| `merge_xlsx.py` | 合并 Excel 文件 |

**依赖**：`pandas python-docx openpyxl`

**用法**：修改脚本中 `EXCEL_PATH` / `WORD_DIR` / `OUTPUT_DIR` 路径后运行：

```bash
python file_utils/merge/merge_v6_all.py
```

### 2.2 文档重命名 — `file_utils/rename_doc/`

批量重命名 Word / 文本文件（结合目录列表，支持追加年份等）：

| 文件 | 说明 |
|------|------|
| `rename_basic.py` | 基础重命名 |
| `rename_doc.py` | 按 Excel 目录列表重命名 doc 文件 |
| `rename_add_year.py` | 重命名并追加年份 |
| `rename_batch.py` | 批量版 |
| `rename_optimized.py` | 优化版 |

**依赖**：`pandas python-docx`

### 2.3 文本处理 — `file_utils/txt_process/`

- `txt_process.py` / `txt_process_v2.py`：批量处理 txt 文本（清理、格式统一、重命名）。

---

## 三、PDF 重命名（pdf_utils/）

| 文件 | 说明 |
|------|------|
| `pdf_rename.py` | PDF 按"期刊 + 完整标题"重命名（自动识别 + 手动干预） |
| `pdf_rename_batch.py` | 批量版，精准提取标题、过滤无效信息 |

**依赖**：`PyPDF2`

```bash
python pdf_utils/pdf_rename.py
```

---

## 四、实用小工具（tools/）

### 4.1 自动点击器 — `tools/auto_click/auto_click.py`

基于 `pyautogui` 的通用自动点击器：记录鼠标位置，每 2 秒自动点击一次。

```bash
pip install pyautogui
python tools/auto_click/auto_click.py
```

### 4.2 文档分割 — `tools/misc/split_doc.py`

带 GUI 的 TXT 文档分割工具（tkinter 界面，按条件拆分大文本）。

```bash
python tools/misc/split_doc.py
```

### 4.3 政策文本结构化 — `tools/misc/misc_script.py`

批量读取文本/表格类文件，提取地区、政策、技术投入、人才政策、模式做法等字段，并支持地区对比分析与建议生成。

**依赖**：`pandas python-docx`

### 4.4 视频抽帧工具 — `tools/video_frame_extractor/`

带 GUI 的视频帧提取工具，支持单视频 / 文件夹批量处理、时间范围截取、JPEG/PNG/WebP 输出、画质调节与分辨率缩放。

| 文件 | 版本 | 说明 |
|------|------|------|
| `video_frame_extractor.py` | **V3** | 最新版，含全部功能 |
| `video_frame_extractor_v1_full.py` | V1 | 原始版，仅全视频抽帧 |

**功能**：
- 单视频 / 文件夹批量模式切换
- 每秒抽取帧数（1-60）
- 时间范围截取（从 X 秒到 Y 秒，留空 = 全部）
- JPEG / PNG / WebP 输出格式可选
- 画质滑块（1-100）
- 分辨率缩放（原尺寸 / 50% / 25% / 自定义宽度）
- 文件夹批量模式自动添加父文件夹前缀
- 中文路径完整兼容（Windows 8.3 短路径）
- 深色主题、多线程后台处理、进度条实时显示

**依赖**：`opencv-python` + Python 3.12+（tkinter 内置）

```bash
pip install opencv-python
python tools/video_frame_extractor/video_frame_extractor.py
```

**输出**：每个视频生成独立文件夹 `{视频名}_frames/`，图片命名 `frame_00001_0.00s.jpg`。

---

## 五、应用框架示例（models/）

- `models/demo/model_demo.py`：一个 CLI 命令行应用框架示例（用户管理 / 数据操作 / 系统设置 / 信息展示模块）。

```bash
python models/demo/model_demo.py
```

---

## 六、Claude 技能（skills/）

个人使用的 Claude 技能集合：

### 学术科研类

| 技能 | 说明 |
|------|------|
| `academic-tools` | 本仓库工具的使用入口 |
| `nature-agent` | 文献检索 / 写作 / 润色 / 引文工作流 |
| `nature-academic-search` | 多源文献检索、引文验证、引用文件管理 |
| `nature-citation` | 引文格式管理（GB/T 7714、IEEE、APA 等） |
| `nature-paper2ppt` | 论文转中文 Nature 风格 PPT |
| `research-equipment-procurement` | 科研设备/硬件采购方法论（多厂商比价、背对背竞价、真实性验证、压价谈判、验收闭环） |
| `ecommerce-consumer-rights` | 电商购物维权方法论（发票纠纷、退款被拒、客服推诿、平台规则死循环，含维权路径与外部监管升级） |

### 个人生产力类

| 技能 | 说明 |
|------|------|
| `conversation-archive` | 对话归档与恢复 |
| `schedule` | 定时任务管理 |
| `qinggan-loop-planner` | 青甘大环线旅行规划 |
| `frontend-design` | 前端视觉设计指导 |
| `consolidate-memory` | 记忆整合 |
| `interpersonal-boundary-guide` | 人际边界思考指南 |
| `macos-cleanup` | macOS 软件缓存与残留清理（面向本机智能体） |

---

## 依赖汇总

核心依赖（一次性安装）：

```bash
pip install requests selenium pyautogui opencv-python pillow pynput pandas matplotlib openpyxl python-docx PyPDF2 seaborn
```

| 工具 | 额外依赖 |
|------|----------|
| 政策分析 | 中文字体（推荐 SimHei） |
| 视频抽帧 | opencv-python |
| PDF 重命名 | PyPDF2 |
| 文档合并 | pandas, python-docx, openpyxl |

---

## 说明

- 所有工具均为个人 / 学术用途。
- 本仓库包含第三方材料，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
- 许可证：MIT
