import os
import re
import shutil
import pandas as pd
from datetime import datetime
from docx import Document
import PyPDF2
from collections import defaultdict

# -------------------------- 多维度分类关键词库（整合优化版） --------------------------
# 1. 政府层级（主分类，优先级：国家→省→市）
LEVELS = {
    '国家层面': ['国家', '国务院', '中央', '全国', '人大', '部委', '宏观导向', '顶层设计', '国家战略'],
    '省层面': ['省', '自治区', '直辖市', '省人民政府', '省级', '省内', '省级规划'],
    '市层面': ['市', '自治州', '市人民政府', '市级', '市内', '市级规划']
}

# 2. 文件类型（辅分类1）
DOC_TYPES = {
    '法律': ['法', '人大颁布', '主席令'],
    '行政法规': ['条例', '行政法规', '国务院令'],
    '规划': ['规划', '战略', '纲要', '中长期目标', '发展纲要'],
    '标准': ['标准', '规范', '技术要求', '排放标准', '排放限值'],
    '地方政府文件': ['地方政府令', '实施办法', '区域细则', '地方性政策'],
    '执法通报': ['执法', '通报', '处罚决定', '督查结果', '检查结果'],
    '行动方案': ['行动方案', '实施方案', '攻坚计划', '专项行动']
}

# 3. 环境要素（辅分类2，核心新增维度）
ENVIRONMENTAL_FACTORS = {
    '大气': ['大气', '空气', 'PM2.5', '雾霾', '扬尘', '挥发性有机物'],
    '水': ['水', '水质', '河流', '湖泊', '黑臭水体', '污水处理'],
    '土壤': ['土壤', '土地', '重金属', '土壤修复', '耕地污染'],
    '碳排放': ['碳', '碳中和', '碳达峰', '双碳', '低碳', '碳交易'],
    '污染源': ['污染源', '排污', '污染物', '污染源普查', '工业污染'],
    '生态保护': ['生态', '生态红线', '自然保护区', '生物多样性', '生态修复']
}

# 4. 政策工具类型（辅分类3，核心新增维度）
POLICY_TOOLS = {
    '命令控制型': ['强制', '必须', '禁止', '处罚', '关停', '限期整改', '强制执行'],
    '市场激励型': ['补贴', '奖励', '税收优惠', '碳交易', '排污权交易', '绿色金融'],
    '自愿参与型': ['自愿', '倡议', '承诺', '认证', '企业自律', '行业公约'],
    '多元协同型': ['公众监督', 'NGO', '社会组织', '跨区域合作', '政企联动']
}

# 5. 区域标识（辅分类4，支持多城市群）
REGIONS = {
    '京津冀': ['北京', '天津', '河北', '京津冀', '雄安'],
    '长三角': ['上海', '江苏', '浙江', '安徽', '长三角', '沪苏浙皖'],
    '珠三角': ['广东', '广州', '深圳', '珠三角', '粤港澳', '大湾区'],
    '全国性': ['全国', '无特定区域', '各地区']
}

# 核心主题关键词（用于相关性判断）
CORE_KEYWORDS = ['污染防治', '排放标准', '生态保护', '碳达峰', '碳中和', '绿色转型',
                 '环境治理', '执法检查', '惩处机制', '激励补贴', '双碳', '低碳转型']

# 时间范围配置（2015-2025）
START_YEAR = 2015
END_YEAR = 2025
START_DATE = datetime(2015, 1, 1)
END_DATE = datetime(2025, 12, 31)


# -------------------------- 文件读取与内容解析（增强版） --------------------------
def read_file_content(file_path):
    """读取txt/docx/pdf内容，支持多编码和错误处理"""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == '.txt':
            return read_txt(file_path)
        elif ext == '.docx':
            return read_docx(file_path)
        elif ext == '.pdf':
            return read_pdf(file_path)
        else:
            print(f"不支持的文件类型: {ext}（{file_path}）")
            return ""
    except Exception as e:
        print(f"读取失败 {file_path}：{str(e)}")
        return ""


def read_txt(file_path):
    """尝试多种编码读取txt，提高兼容性"""
    encodings = ['utf-8', 'gbk', 'gb2312', 'ansi']
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    print(f"无法解析编码：{file_path}")
    return ""


def read_docx(file_path):
    """读取docx文件文本内容"""
    doc = Document(file_path)
    return ' '.join([para.text for para in doc.paragraphs])


def read_pdf(file_path):
    """读取pdf文件文本内容（支持多页）"""
    text = ""
    with open(file_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + " "
    return text


# -------------------------- 核心信息提取与分类（整合优化） --------------------------
def is_relevant(text):
    """判断文件是否与核心主题相关（至少匹配1个核心关键词）"""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in CORE_KEYWORDS)


def extract_date(text, file_name):
    """提取文件日期（支持多种格式，优先文本后文件名）"""
    date_patterns = [
        r'\b20\d{2}[/-]\d{1,2}[/-]\d{1,2}\b',  # YYYY-MM-DD / YYYY/MM/DD
        r'\b20\d{2}年\d{1,2}月\d{1,2}日\b'  # YYYY年MM月DD日
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


def extract_year(date_obj):
    """从日期对象提取年份（兼容None值）"""
    if isinstance(date_obj, datetime):
        return date_obj.year if (START_YEAR <= date_obj.year <= END_YEAR) else None
    return None


def classify_by_dimension(text, dimension_dict, priority=False):
    """按维度分类（支持优先级模式和多标签）"""
    matched = []
    text_lower = text.lower()
    for category, keywords in dimension_dict.items():
        if any(kw.lower() in text_lower for kw in keywords):
            matched.append(category)
            if priority:  # 优先级模式：匹配到第一个即返回
                return matched
    return matched if matched else ['未明确']


def get_region(text, file_name):
    """区域分类（优先文件内容，补充文件名）"""
    combined_text = (text + " " + file_name).lower()
    for region, keywords in REGIONS.items():
        if any(kw.lower() in combined_text for kw in keywords):
            return [region]
    return ['全国性']  # 默认为全国性


# -------------------------- 单文件分析与批量处理 --------------------------
def analyze_file(file_path):
    """全维度分析单个文件，返回结构化信息"""
    file_name = os.path.basename(file_path)
    text = read_file_content(file_path)
    if not text:
        return None

    # 核心信息提取
    date = extract_date(text, file_name)
    year = extract_year(date)
    in_time_range = "是" if (date and START_DATE <= date <= END_DATE) else "否"
    relevant = is_relevant(text)

    # 多维度分类
    level = classify_by_dimension(text, LEVELS, priority=True)  # 政府层级有优先级
    doc_type = classify_by_dimension(text, DOC_TYPES)
    env_factor = classify_by_dimension(text, ENVIRONMENTAL_FACTORS)
    policy_tool = classify_by_dimension(text, POLICY_TOOLS)
    region = get_region(text, file_name)

    return {
        '文件名': file_name,
        '文件路径': file_path,
        '提取日期': date.strftime('%Y-%m-%d') if date else '未提取到',
        '是否在时间范围': in_time_range,
        '年份': year if year else '未明确',
        '是否相关': '是' if relevant else '否',
        '政府层级': ';'.join(level),
        '文件类型': ';'.join(doc_type),
        '环境要素': ';'.join(env_factor),
        '政策工具类型': ';'.join(policy_tool),
        '所属区域': ';'.join(region)
    }


def batch_analyze(input_dir):
    """批量处理目录下所有文件，返回分析结果列表"""
    results = []
    for root, _, files in os.walk(input_dir):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in ['.txt', '.docx', '.pdf']:
                file_path = os.path.join(root, file)
                info = analyze_file(file_path)
                if info:
                    results.append(info)
    return results


# -------------------------- 结果输出：表格与报告 --------------------------
def generate_analysis_table(results, output_dir):
    """生成多维度分析Excel表（支持数据透视）"""
    df = pd.DataFrame(results)
    # 按分析优先级排序列
    cols = [
        '文件名', '文件路径', '提取日期', '年份', '是否在时间范围', '是否相关',
        '政府层级', '所属区域', '环境要素', '文件类型', '政策工具类型'
    ]
    df = df[cols] if all(col in df.columns for col in cols) else df
    table_path = os.path.join(output_dir, '政策文件多维度分析表.xlsx')
    df.to_excel(table_path, index=False, engine='openpyxl')
    print(f"多维度分析表已保存至：{table_path}")
    return df


def generate_summary_report(df, output_dir):
    """生成多维度统计报告（含交叉分析）"""
    summary = []
    total = len(df)
    relevant = df[(df['是否相关'] == '是') & (df['是否在时间范围'] == '是')]
    relevant_count = len(relevant)

    # 总体统计
    summary.append("===== 环境政策文件多维度分析报告 =====")
    summary.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    summary.append(f"总文件数：{total} 份")
    summary.append(f"时间范围内且相关文件数：{relevant_count} 份（核心分析对象）\n")

    # 1. 政府层级分布
    level_counts = defaultdict(int)
    for levels in relevant['政府层级']:
        for level in levels.split(';'):
            level_counts[level] += 1
    summary.append("----- 政府层级分布 -----")
    for level, cnt in sorted(level_counts.items(), key=lambda x: -x[1]):
        summary.append(f"- {level}：{cnt} 份（占比 {round(cnt / relevant_count * 100, 2)}%）")

    # 2. 环境要素×政策工具交叉统计
    summary.append("\n----- 环境要素×政策工具分布 -----")
    relevant['环境要素_首'] = relevant['环境要素'].apply(lambda x: x.split(';')[0])
    relevant['政策工具_首'] = relevant['政策工具类型'].apply(lambda x: x.split(';')[0])
    factor_tool = pd.crosstab(relevant['环境要素_首'], relevant['政策工具_首'])
    summary.append(factor_tool.to_string())

    # 3. 区域×文件类型Top3
    summary.append("\n----- 重点区域文件类型Top3 -----")
    for region in ['京津冀', '长三角', '珠三角']:
        region_data = relevant[relevant['所属区域'].str.contains(region)]
        if not region_data.empty:
            type_counts = region_data['文件类型'].str.split(';', expand=True).stack().value_counts()
            summary.append(f"\n{region}：")
            summary.append(type_counts.head(3).to_string())

    # 保存报告
    report_path = os.path.join(output_dir, '多维度分析报告.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(summary))
    print(f"分析报告已保存至：{report_path}")


# -------------------------- 文件整理功能（完善版） --------------------------
def organize_files_by_category(df, output_root):
    """按多维度分类整理文件（支持相关/不相关分离）"""
    os.makedirs(output_root, exist_ok=True)

    # 1. 不相关文件处理
    irrelevant = df[df['是否相关'] == '否']
    if not irrelevant.empty:
        irrelevant_dir = os.path.join(output_root, '不相关文件')
        os.makedirs(irrelevant_dir, exist_ok=True)
        for _, row in irrelevant.iterrows():
            copy_file(row['文件路径'], row['文件名'], irrelevant_dir)

    # 2. 相关文件按层级/区域/环境要素整理
    relevant = df[(df['是否相关'] == '是') & (df['是否在时间范围'] == '是')]
    if not relevant.empty:
        for _, row in relevant.iterrows():
            # 构建三级目录
            level = row['政府层级'].split(';')[0]
            region = row['所属区域'].split(';')[0]
            env_factor = row['环境要素'].split(';')[0]
            target_dir = os.path.join(output_root, '相关文件', level, region, env_factor)
            os.makedirs(target_dir, exist_ok=True)
            copy_file(row['文件路径'], row['文件名'], target_dir)

    print(f"文件已整理至：{output_root}")


def copy_file(src_path, file_name, target_dir):
    """复制文件并处理重名问题"""
    dest_path = os.path.join(target_dir, file_name)
    counter = 1
    # 处理重名
    while os.path.exists(dest_path):
        name, ext = os.path.splitext(file_name)
        dest_path = os.path.join(target_dir, f"{name}_{counter}{ext}")
        counter += 1
    shutil.copy2(src_path, dest_path)


# -------------------------- 主函数入口 --------------------------
def main():
    print("===== 环境政策文件多维度分析工具 =====")
    input_dir = input("请输入文件所在目录：").strip()
    if not os.path.isdir(input_dir):
        print(f"错误：{input_dir} 不是有效目录")
        return

    # 批量分析文件
    print("开始分析文件...")
    results = batch_analyze(input_dir)
    if not results:
        print("未找到可分析的文件（支持txt/docx/pdf）")
        return
    print(f"分析完成，共处理 {len(results)} 个文件")

    # 生成表格和报告
    output_dir = input("请输入结果保存目录：").strip()
    os.makedirs(output_dir, exist_ok=True)
    df = generate_analysis_table(results, output_dir)
    generate_summary_report(df, output_dir)

    # 可选：整理文件
    if input("是否按分类整理文件？(y/n)：").strip().lower() == 'y':
        organize_root = input("请输入整理后根目录：").strip()
        organize_files_by_category(df, organize_root)

    print("所有操作完成！")


if __name__ == "__main__":
    main()