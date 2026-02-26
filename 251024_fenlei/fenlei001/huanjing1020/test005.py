import os
import re
import shutil
import pandas as pd
from datetime import datetime
from docx import Document
import PyPDF2
from collections import defaultdict

# -------------------------- 核心配置（分类标准与关键词） --------------------------
# 1. 主分类：政府层级（国家→省→市，严格区分）
LEVELS = {
    '国家层面': [
        '国家', '国务院', '中央', '全国', '人大', '部委',  # 行政主体
        '宏观导向', '顶层设计', '国家战略', '全国性'  # 层级特征
    ],
    '省层面': [
        '省', '自治区', '直辖市',  # 省级行政单位（如"山东省" "北京市"）
        '省人民政府', '自治区政府', '直辖市政府',  # 省级政府
        '省级规划', '省内'  # 省级特征
    ],
    '市层面': [
        '市', '自治州',  # 市级行政单位（如"上海市" "深圳市"）
        '市人民政府', '市政府', '市级',  # 市级政府
        '市内', '市级规划'  # 市级特征
    ]
}

# 2. 辅分类：文件类型（细化分类）
DOC_TYPES = {
    '法律与行政法规': ['法', '条例', '行政法规', '人大颁布', '主席令', '国务院令'],
    '政策性文件与规划': ['规划', '战略', '政策', '中长期目标', '发展纲要', '行动计划（宏观）'],
    '部门规章与标准文件': ['规章', '标准', '规范', '规定', '执行细则', '技术要求', '排放标准'],
    '地方政府文件': ['地方政府令', '地方性政策', '省市实施办法', '区域细则'],
    '执法与通报文件': ['执法', '通报', '检查结果', '处罚决定', '监管报告', '督查通报'],
    '行动方案': ['行动方案', '实施方案', '专项行动', '攻坚计划', '具体措施']
}

# 3. 核心主题关键词（确保文件与主题相关）
CORE_KEYWORDS = [
    '污染防治', '排放标准', '生态保护', '碳达峰', '碳中和', '双碳',
    '绿色转型', '环境治理', '执法检查', '惩处机制', '激励补贴'
]

# 4. 时间范围（2015年1月1日至今）
START_DATE = datetime(2015, 1, 1)
CURRENT_DATE = datetime.now()


# -------------------------- 工具函数：文件读取与内容解析 --------------------------
def read_file_content(file_path):
    """读取txt/docx/pdf文件内容（支持多编码）"""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == '.txt':
            return read_txt(file_path)
        elif ext == '.docx':
            return read_docx(file_path)
        elif ext == '.pdf':
            return read_pdf(file_path)
        else:
            print(f"不支持的文件类型：{ext}（{file_path}）")
            return ""
    except Exception as e:
        print(f"读取文件失败 {file_path}：{str(e)}")
        return ""

def read_txt(file_path):
    """尝试多种编码读取txt文件"""
    encodings = ['utf-8', 'gbk', 'gb2312', 'ansi']
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    return ""

def read_docx(file_path):
    """读取docx文件文本内容"""
    doc = Document(file_path)
    return ' '.join([para.text for para in doc.paragraphs])

def read_pdf(file_path):
    """读取pdf文件文本内容"""
    text = ""
    with open(file_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + " "
    return text


# -------------------------- 核心逻辑：分类与筛选 --------------------------
def is_relevant(text):
    """判断文件是否与核心主题相关（匹配至少1个核心关键词）"""
    text_lower = text.lower()
    for kw in CORE_KEYWORDS:
        if kw.lower() in text_lower:
            return True
    return False

def extract_date(text, file_name):
    """提取文件日期（优先文本内日期，再文件名，格式支持YYYY-MM-DD/YYYY年MM月DD日）"""
    # 日期正则（支持多种格式）
    date_patterns = [
        r'\b20\d{2}[/-]\d{1,2}[/-]\d{1,2}\b',  # YYYY-MM-DD / YYYY/MM/DD
        r'\b20\d{2}年\d{1,2}月\d{1,2}日\b'     # YYYY年MM月DD日
    ]
    # 从文本提取
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            return parse_date(match.group())
    # 从文件名提取
    for pattern in date_patterns:
        match = re.search(pattern, file_name)
        if match:
            return parse_date(match.group())
    return None

def parse_date(date_str):
    """解析日期字符串为datetime对象"""
    try:
        if '-' in date_str or '/' in date_str:
            return datetime.strptime(date_str.replace('/', '-'), '%Y-%m-%d')
        elif '年' in date_str:
            return datetime.strptime(date_str, '%Y年%m月%d日')
    except:
        return None
    return None

def classify_level(text):
    """主分类：判断政府层级（国家/省/市，优先级：国家→省→市）"""
    text_lower = text.lower()
    # 先匹配国家层面
    for kw in LEVELS['国家层面']:
        if kw.lower() in text_lower:
            return ['国家层面']
    # 再匹配省层面
    for kw in LEVELS['省层面']:
        if kw.lower() in text_lower:
            return ['省层面']
    # 最后匹配市层面
    for kw in LEVELS['市层面']:
        if kw.lower() in text_lower:
            return ['市层面']
    # 未匹配
    return ['未明确层级']

def classify_doc_type(text):
    """辅分类：判断文件类型（支持多类型匹配）"""
    matched = []
    text_lower = text.lower()
    for doc_type, keywords in DOC_TYPES.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                matched.append(doc_type)
                break  # 每个类型只匹配一次
    return matched if matched else ['未明确类型']


# -------------------------- 主处理函数：文件分析与结果生成 --------------------------
def process_file(file_path):
    """处理单个文件，返回完整分类信息"""
    file_name = os.path.basename(file_path)
    text = read_file_content(file_path)
    if not text:
        return None

    # 核心信息提取
    relevant = is_relevant(text)
    date = extract_date(text, file_name)
    in_time_range = "是" if (date and START_DATE <= date <= CURRENT_DATE) else "否"
    level = classify_level(text)
    doc_types = classify_doc_type(text)

    return {
        '文件名': file_name,
        '文件路径': file_path,
        '提取日期': date.strftime('%Y-%m-%d') if date else '未提取到',
        '是否在时间范围（2015至今）': in_time_range,
        '是否与主题相关': '是' if relevant else '否',
        '政府层级': ';'.join(level),
        '文件类型': ';'.join(doc_types)
    }

def batch_process(input_dir):
    """批量处理目录下所有文件"""
    results = []
    for root, _, files in os.walk(input_dir):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in ['.txt', '.docx', '.pdf']:  # 仅处理目标格式
                file_path = os.path.join(root, file)
                info = process_file(file_path)
                if info:
                    results.append(info)
    return results


# -------------------------- 结果输出：表格、报告与文件整理 --------------------------
def generate_info_table(results, output_dir):
    """生成包含所有关键信息的Excel表格"""
    df = pd.DataFrame(results)
    # 调整列顺序（按重要性排序）
    cols = [
        '文件名', '文件路径', '提取日期', '是否在时间范围（2015至今）',
        '是否与主题相关', '政府层级', '文件类型'
    ]
    df = df[cols]
    table_path = os.path.join(output_dir, '政策文件分类信息表.xlsx')
    df.to_excel(table_path, index=False, engine='openpyxl')
    print(f"分类信息表已保存至：{table_path}")
    return df

def generate_summary_report(df, output_dir):
    """生成分类总结报告（统计数量与分布）"""
    summary = []
    total = len(df)
    # 时间范围筛选结果
    in_time = df[df['是否在时间范围（2015至今）'] == '是']
    out_time = df[df['是否在时间范围（2015至今）'] == '否']
    # 主题相关结果
    relevant = in_time[in_time['是否与主题相关'] == '是']  # 仅统计时间范围内的相关文件

    # 总体统计
    summary.append("===== 政策文件分类总结报告 =====")
    summary.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    summary.append(f"总文件数：{total} 份")
    summary.append(f"2015年至今的文件数：{len(in_time)} 份（占比 {round(len(in_time)/total*100, 2)}%）")
    summary.append(f"时间范围外的文件数：{len(out_time)} 份（单独存放）")
    summary.append(f"时间范围内且与主题相关的文件数：{len(relevant)} 份（核心分析对象）\n")

    # 政府层级分布（仅核心文件）
    level_counts = defaultdict(int)
    for level in relevant['政府层级']:
        level_counts[level] += 1
    summary.append("----- 政府层级分布（核心文件） -----")
    for level, cnt in sorted(level_counts.items(), key=lambda x: -x[1]):
        summary.append(f"- {level}：{cnt} 份（占核心文件 {round(cnt/len(relevant)*100, 2)}%）")

    # 文件类型分布（仅核心文件）
    type_counts = defaultdict(int)
    for types in relevant['文件类型']:
        for t in types.split(';'):
            type_counts[t] += 1
    summary.append("\n----- 文件类型分布（核心文件） -----")
    for t, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
        summary.append(f"- {t}：{cnt} 份（占核心文件 {round(cnt/len(relevant)*100, 2)}%）")

    # 保存报告
    report_path = os.path.join(output_dir, '分类总结报告.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(summary))
    print(f"总结报告已保存至：{report_path}")

def organize_files(df, output_root):
    """按「政府层级/文件类型」整理文件（严格分层）"""
    os.makedirs(output_root, exist_ok=True)

    # 1. 时间范围外的文件→单独文件夹
    out_time_dir = os.path.join(output_root, '0_时间范围外（2015年前）')
    os.makedirs(out_time_dir, exist_ok=True)

    # 2. 时间范围内但不相关的文件→单独文件夹
    irrelevant_dir = os.path.join(output_root, '1_时间范围内但不相关')
    os.makedirs(irrelevant_dir, exist_ok=True)

    # 3. 核心文件（时间范围内且相关）→ 政府层级/文件类型
    core_root = os.path.join(output_root, '2_核心文件（时间范围内且相关）')
    os.makedirs(core_root, exist_ok=True)

    # 遍历文件进行整理
    for _, row in df.iterrows():
        src = row['文件路径']
        fname = row['文件名']
        in_time = row['是否在时间范围（2015至今）'] == '是'
        relevant = row['是否与主题相关'] == '是'

        if not in_time:
            # 时间范围外
            dest = os.path.join(out_time_dir, fname)
        elif in_time and not relevant:
            # 时间内但不相关
            dest = os.path.join(irrelevant_dir, fname)
        else:
            # 核心文件：层级/类型
            level = row['政府层级'].split(';')[0]  # 取第一个层级
            doc_type = row['文件类型'].split(';')[0]  # 取第一个类型
            dest_dir = os.path.join(core_root, level, doc_type)
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, fname)

        # 处理重名文件
        counter = 1
        while os.path.exists(dest):
            name, ext = os.path.splitext(fname)
            dest = os.path.join(os.path.dirname(dest), f"{name}_{counter}{ext}")
            counter += 1

        shutil.copy2(src, dest)
        print(f"已整理：{fname} → {os.path.dirname(dest)}")


# -------------------------- 主程序入口 --------------------------
def main():
    print("===== 政策文件层级-类型分类系统 =====")
    input_dir = input("请输入待处理文件的根目录：").strip()
    if not os.path.isdir(input_dir):
        print(f"错误：{input_dir} 不是有效目录！")
        return

    # 1. 批量处理文件
    print("\n开始分析文件内容并分类...")
    results = batch_process(input_dir)
    if not results:
        print("未找到可处理的文件（支持txt/docx/pdf）！")
        return
    print(f"文件分析完成，共处理 {len(results)} 份文件")

    # 2. 生成信息表格
    df = generate_info_table(results, input_dir)

    # 3. 生成总结报告
    generate_summary_report(df, input_dir)

    # 4. 整理文件
    if input("\n是否按分类结果整理文件？(y/n)：").strip().lower() == 'y':
        output_root = input("请输入整理后文件的根目录：").strip()
        print("开始整理文件...")
        organize_files(df, output_root)
        print(f"文件整理完成，保存至：{output_root}")

if __name__ == "__main__":
    main()