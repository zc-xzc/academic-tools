import os
import re
import shutil
import pandas as pd
from datetime import datetime
from docx import Document
import PyPDF2
from collections import defaultdict

# -------------------------- 多维度分类关键词库（核心优化点） --------------------------
# 1. 政府层级（主分类，优先级：国家→省→市）
LEVELS = {
    '国家层面': ['国家', '国务院', '中央', '全国', '人大', '部委', '宏观导向', '顶层设计'],
    '省层面': ['省', '自治区', '直辖市', '省人民政府', '省级', '省内'],
    '市层面': ['市', '自治州', '市人民政府', '市级', '市内']
}

# 2. 文件类型（辅分类1）
DOC_TYPES = {
    '法律': ['法', '人大颁布', '主席令'],
    '行政法规': ['条例', '行政法规', '国务院令'],
    '规划': ['规划', '战略', '纲要', '中长期目标'],
    '标准': ['标准', '规范', '技术要求', '排放标准'],
    '地方政府文件': ['地方政府令', '实施办法', '区域细则'],
    '执法通报': ['执法', '通报', '处罚决定', '督查结果'],
    '行动方案': ['行动方案', '实施方案', '攻坚计划']
}

# 3. 环境要素（辅分类2，新增核心维度）
ENVIRONMENTAL_FACTORS = {
    '大气': ['大气', '空气', 'PM2.5', '雾霾', '扬尘', '挥发性有机物'],
    '水': ['水', '水质', '河流', '湖泊', '黑臭水体', '污水处理'],
    '土壤': ['土壤', '土地', '重金属', '土壤修复', '耕地污染'],
    '碳排放': ['碳', '碳中和', '碳达峰', '双碳', '低碳', '碳交易'],
    '污染源': ['污染源', '排污', '污染物', '污染源普查', '工业污染'],
    '生态保护': ['生态', '生态红线', '自然保护区', '生物多样性', '生态修复']
}

# 4. 政策工具类型（辅分类3，新增核心维度）
POLICY_TOOLS = {
    '命令控制型': ['强制', '必须', '禁止', '处罚', '关停', '限期整改', '强制执行'],
    '市场激励型': ['补贴', '奖励', '税收优惠', '碳交易', '排污权交易', '绿色金融'],
    '自愿参与型': ['自愿', '倡议', '承诺', '认证', '企业自律', '行业公约'],
    '多元协同型': ['公众监督', 'NGO', '社会组织', '跨区域合作', '政企联动']
}

# 5. 区域标识（辅分类4，支持多城市群比较）
REGIONS = {
    '京津冀': ['北京', '天津', '河北', '京津冀', '雄安'],
    '长三角': ['上海', '江苏', '浙江', '安徽', '长三角', '沪苏浙皖'],
    '珠三角': ['广东', '广州', '深圳', '珠三角', '粤港澳', '大湾区'],
    '全国性': ['全国', '无特定区域', '各地区']  # 无明确区域指向的国家层面文件
}

# 核心主题关键词（确保文件相关性）
CORE_KEYWORDS = ['污染防治', '排放标准', '生态保护', '碳达峰', '碳中和', '绿色转型',
                 '环境治理', '执法检查', '惩处机制', '激励补贴']

# 时间范围（2015-2025）
START_YEAR = 2015
CURRENT_YEAR = 2025


# -------------------------- 文件读取与基础解析 --------------------------
def read_file_content(file_path):
    """读取txt/docx/pdf内容，兼容多编码"""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == '.txt':
            return read_txt(file_path)
        elif ext == '.docx':
            return read_docx(file_path)
        elif ext == '.pdf':
            return read_pdf(file_path)
        return ""
    except Exception as e:
        print(f"读取失败 {file_path}：{e}")
        return ""

def read_txt(file_path):
    for encoding in ['utf-8', 'gbk', 'gb2312']:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    return ""

def read_docx(file_path):
    return ' '.join([para.text for para in Document(file_path).paragraphs])

def read_pdf(file_path):
    text = ""
    with open(file_path, 'rb') as f:
        for page in PyPDF2.PdfReader(f).pages:
            if page.extract_text():
                text += page.extract_text() + " "
    return text


# -------------------------- 多维度分类核心逻辑 --------------------------
def is_relevant(text):
    """判断是否与核心主题相关（至少匹配1个核心关键词）"""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in CORE_KEYWORDS)

def extract_year(text, file_name):
    """提取文件年份（优先文本，再文件名）"""
    year_match = re.search(r'\b20[1-2]\d\b', text) or re.search(r'\b20[1-2]\d\b', file_name)
    return int(year_match.group()) if (year_match and START_YEAR <= int(year_match.group()) <= CURRENT_YEAR) else None

def classify_by_dimension(text, dimension_dict):
    """按指定维度分类（支持多标签）"""
    matched = []
    text_lower = text.lower()
    for category, keywords in dimension_dict.items():
        if any(kw.lower() in text_lower for kw in keywords):
            matched.append(category)
    return matched if matched else ['未明确']

def get_region(text, file_name):
    """区域标识（优先文件中明确提到的区域，无则标记为全国性）"""
    text_lower = (text + " " + file_name).lower()
    for region, keywords in REGIONS.items():
        if any(kw.lower() in text_lower for kw in keywords):
            return [region]
    return ['全国性']  # 默认全国性（尤其是国家层面文件）


# -------------------------- 单文件全维度分析 --------------------------
def analyze_file(file_path):
    """输出包含5维分类的完整信息字典"""
    file_name = os.path.basename(file_path)
    text = read_file_content(file_path)
    if not text:
        return None

    # 核心信息提取
    year = extract_year(text, file_name)
    relevant = is_relevant(text)
    level = classify_by_dimension(text, LEVELS)
    doc_type = classify_by_dimension(text, DOC_TYPES)
    env_factor = classify_by_dimension(text, ENVIRONMENTAL_FACTORS)
    policy_tool = classify_by_dimension(text, POLICY_TOOLS)
    region = get_region(text, file_name)

    return {
        '文件名': file_name,
        '文件路径': file_path,
        '年份': year if year else '未明确',
        '是否相关': '是' if relevant else '否',
        '政府层级': ';'.join(level),
        '文件类型': ';'.join(doc_type),
        '环境要素': ';'.join(env_factor),
        '政策工具类型': ';'.join(policy_tool),
        '所属区域': ';'.join(region)
    }


# -------------------------- 批量处理与结果输出 --------------------------
def batch_analyze(input_dir):
    """批量处理目录下所有文件，返回全维度信息列表"""
    results = []
    for root, _, files in os.walk(input_dir):
        for file in files:
            if os.path.splitext(file)[1].lower() in ['.txt', '.docx', '.pdf']:
                info = analyze_file(os.path.join(root, file))
                if info:
                    results.append(info)
    return results

def generate_analysis_table(results, output_dir):
    """生成多维度分析Excel表（支持数据透视分析）"""
    df = pd.DataFrame(results)
    # 列顺序按分析优先级排列
    cols = [
        '文件名', '文件路径', '年份', '是否相关',
        '政府层级', '所属区域', '环境要素',
        '文件类型', '政策工具类型'
    ]
    df = df[cols]
    table_path = os.path.join(output_dir, '政策文件多维度分析表.xlsx')
    df.to_excel(table_path, index=False, engine='openpyxl')
    print(f"多维度分析表已保存至：{table_path}")
    return df

def generate_detailed_summary(df, output_dir):
    """生成多维度统计报告（支持跨维度分析）"""
    summary = []
    total = len(df)
    relevant = df[df['是否相关'] == '是']
    relevant_count = len(relevant)

    # 总体统计
    summary.append("===== 政策文件多维度分类总结报告 =====")
    summary.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d')}")
    summary.append(f"总文件数：{total} 份 | 相关文件数：{relevant_count} 份\n")

    # 1. 政府层级×区域交叉统计
    summary.append("----- 政府层级×区域分布 -----")
    level_region = pd.crosstab(relevant['政府层级'], relevant['所属区域'])
    summary.append(level_region.to_string())

    # 2. 环境要素×政策工具交叉统计
    summary.append("\n----- 环境要素×政策工具分布 -----")
    # 处理多标签（按首个标签统计）
    relevant['环境要素_首'] = relevant['环境要素'].apply(lambda x: x.split(';')[0])
    relevant['政策工具_首'] = relevant['政策工具类型'].apply(lambda x: x.split(';')[0])
    factor_tool = pd.crosstab(relevant['环境要素_首'], relevant['政策工具_首'])
    summary.append(factor_tool.to_string())

    # 3. 区域×文件类型统计（前3类）
    summary.append("\n----- 区域×文件类型Top3 -----")
    for region in ['京津冀', '长三角', '珠三角']:
        region_data = relevant[relevant['所属区域'].str.contains(region)]
        type_counts = region_data['文件类型'].str.split(';', expand=True).stack().value_counts()
        summary.append(f"\n{region} Top3文件类型：")
        summary.append(type_counts.head(3).to_string())

    # 保存报告
    report_path = os.path.join(output_dir, '多维度分类总结报告.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(summary))
    print(f"详细总结报告已保存至：{report_path}")

def organize_files_by_dimension(df, output_root):
    """按「层级/区域/环境要素」三级目录整理文件（支持快速定位）"""
    os.makedirs(output_root, exist_ok=True)

    # 1. 不相关文件
    irrelevant_dir = os.path.join(output_root, '0_不相关文件')
    os.makedirs(irrelevant_dir, exist_ok=True)

    # 2. 相关文件（按层级/区域/环境要素）
    relevant_root = os.path.join(output_root, '1_相关文件')
    os.makedirs(relevant_root, exist_ok=True)

    for _, row in df.iterrows():
        src = row['文件路径']
        fname = row['文件名']
        if row['是否相关'] == '否':
            dest = os.path.join(irrelevant_dir, fname)
        else:
            # 取首个标签作为目录（多标签文件仅存一份到首个目录）
            level = row['政府层级'].split(';')[0]
            region = row['所属区域'].split(';')[0]
            env_factor = row['环境要素'].split(';')[0]
            dest_dir = os.path.join(relevant_root, level, region, env_factor)
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, fname)

        # 处理重名
        counter = 1
        while os.path.exists(dest):
            name, ext = os.path.splitext(fname)
            dest = os.path.join(os.path.dirname(dest), f"{name}_{counter}{ext}")
            counter += 1
        shutil.copy2(src, dest)


# -------------------------- 主程序 --------------------------
def main():
    print("===== 政策文件多维度精准分类系统 =====")
    input_dir = input("请输入待处理文件目录：").strip()
    if not os.path.isdir(input_dir):
        print("无效目录！")
        return

    # 1. 批量分析
    print("开始多维度分类分析...")
    results = batch_analyze(input_dir)
    if not results:
        print("未找到有效文件！")
        return
    print(f"分析完成，共处理 {len(results)} 份文件")

    # 2. 生成分析表格（核心输出，用于后续数据分析）
    df = generate_analysis_table(results, input_dir)

    # 3. 生成详细总结报告
    generate_detailed_summary(df, input_dir)

    # 4. 按维度整理文件
    if input("\n是否按多维度整理文件？(y/n)：").strip().lower() == 'y':
        output_root = input("请输入整理目录：").strip()
        organize_files_by_dimension(df, output_root)
        print(f"文件整理完成，路径：{output_root}")

if __name__ == "__main__":
    main()


# 依赖安装命令：pip install python-docx PyPDF2 pandas openpyxl