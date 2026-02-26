import os
import re
import shutil
import pandas as pd
from datetime import datetime
from docx import Document
import PyPDF2
from collections import defaultdict

# -------------------------- 配置参数（主题相关标准与分类维度） --------------------------
# 1. 环境规制主题核心关键词（用于判断相关性）
THEME_KEYWORDS = [
    # 法律基础
    '环境法', '空气法', '土壤法', '水法', '能源法', '环保法', '清洁空气法', '清洁水法',
    # 规制工具
    '污染税', '环境税', '能源税', '排污权交易', '碳税', '碳交易', '绿色金融', '生态补偿',
    # 规制行为与目标
    '污染防治', '节能', '减排', '排污', '废物管理', '资源利用', '环境治理', '排放标准',
    # 多元协同与阶段特征
    '环境规制', '命令控制', '市场激励', '非正式规制', '多元协同', '公众监督', '非政府组织',
    '环境信息披露', '绿色供应链', '区块链', '可持续发展'
]

# 2. 分类维度（保持严格对应）
LEVELS = {
    '国家层面': ['宏观导向', '顶层设计', '国家', '国务院', '中央', '全国', '法律', '行政法规'],
    '省市层面': ['地方', '省', '市', '自治区', '直辖市', '区域', '地方政府', '地方性法规'],
    '部门/专项层面': ['部门', '大气', '水', '土壤', '碳排放', '污染源', '专项', '行业标准']
}

REGIONS = {
    '京津冀': ['北京', '天津', '河北', '京津冀', '雄安'],
    '长三角': ['上海', '江苏', '浙江', '安徽', '长三角', '沪苏浙皖'],
    '珠三角': ['广东', '广州', '深圳', '珠三角', '粤港澳', '大湾区']
}

DOC_TYPES = {
    '法律与行政法规': ['法律', '法规', '条例', '行政法', '人大'],
    '政策性文件与规划': ['政策', '规划', '战略', '中长期目标', '可持续发展'],
    '部门规章与标准文件': ['规章', '标准', '规范', '规定', '执行细则', '排放标准'],
    '地方政府文件': ['地方政府', '地方性', '省市', '人民政府'],
    '执法与通报文件': ['执法', '通报', '检查结果', '处罚决定', '监管报告']
}

REGULATION_STAGES = {
    '命令控制阶段': ['命令控制', '政府主导', '强制监管', '清洁空气法', '清洁水法'],
    '工具扩展阶段': ['污染税', '排污权交易', '市场激励', '非正式规制'],
    '多元协同阶段': ['多元协同', '公众监督', '非政府组织', '绿色金融', '区块链', '可持续发展']
}

# 时间范围
START_YEAR = 2015
CURRENT_YEAR = datetime.now().year


# -------------------------- 核心工具函数（文件读取与解析） --------------------------
def read_file_content(file_path):
    """读取txt/docx/pdf文件内容"""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == '.txt':
            return read_txt(file_path)
        elif ext == '.docx':
            return read_docx(file_path)
        elif ext == '.pdf':
            return read_pdf(file_path)
        else:
            print(f"不支持的文件类型: {ext} - {file_path}")
            return ""
    except Exception as e:
        print(f"读取文件失败 {file_path}: {str(e)}")
        return ""


def read_txt(file_path):
    """尝试多种编码读取txt"""
    encodings = ['utf-8', 'gbk', 'gb2312', 'ansi']
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    return ""


def read_docx(file_path):
    """读取docx文本"""
    doc = Document(file_path)
    return ' '.join([para.text for para in doc.paragraphs])


def read_pdf(file_path):
    """读取pdf文本"""
    text = ""
    with open(file_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + " "
    return text


# -------------------------- 核心逻辑函数（相关性判断与分类） --------------------------
def is_relevant(text):
    """判断文档是否与环境规制主题相关（匹配至少1个核心关键词）"""
    text_lower = text.lower()
    for kw in THEME_KEYWORDS:
        if kw.lower() in text_lower:
            return True
    return False


def extract_year(text, file_name):
    """提取年份（2015-当前）"""
    year_match = re.search(r'\b(20\d{2})\b', file_name) or re.search(r'\b(20\d{2})\b', text)
    if year_match:
        year = int(year_match.group(1))
        return year if START_YEAR <= year <= CURRENT_YEAR else None
    return None


def classify(text, category_dict):
    """按分类字典匹配，返回所有匹配的类别（严格对应）"""
    matched = []
    text_lower = text.lower()
    for category, keywords in category_dict.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                matched.append(category)
                break  # 每个类别只匹配一次
    return matched if matched else ['未分类']


# -------------------------- 主处理函数（单文件处理与批量处理） --------------------------
def process_single_file(file_path):
    """处理单个文件，返回完整信息字典"""
    file_name = os.path.basename(file_path)
    text = read_file_content(file_path)
    if not text:
        return None

    # 核心信息提取
    relevant = is_relevant(text)
    year = extract_year(text, file_name)
    levels = classify(text, LEVELS)
    regions = classify(text, REGIONS)
    doc_types = classify(text, DOC_TYPES)
    stages = classify(text, REGULATION_STAGES)

    return {
        '文件名': file_name,
        '文件路径': file_path,
        '年份': year if year else '未明确',
        '层级': ';'.join(levels),  # 用分号分隔多类别
        '区域': ';'.join(regions),
        '文件类型': ';'.join(doc_types),
        '规制阶段': ';'.join(stages),
        '是否相关': '是' if relevant else '否'
    }


def batch_process(input_dir):
    """批量处理目录下所有文档"""
    results = []
    for root, _, files in os.walk(input_dir):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in ['.txt', '.docx', '.pdf']:  # 仅处理目标格式
                file_path = os.path.join(root, file)
                file_info = process_single_file(file_path)
                if file_info:
                    results.append(file_info)
    return results


# -------------------------- 结果输出函数（表格、总结、文件整理） --------------------------
def generate_table(results, output_dir):
    """生成Excel表格记录关键信息"""
    df = pd.DataFrame(results)
    # 调整列顺序
    cols = ['文件名', '文件路径', '年份', '是否相关', '层级', '区域', '文件类型', '规制阶段']
    df = df[cols]
    table_path = os.path.join(output_dir, '文档分类信息表.xlsx')
    df.to_excel(table_path, index=False, engine='openpyxl')
    print(f"分类信息表格已保存至：{table_path}")
    return df


def generate_summary(df, output_dir):
    """生成系统性总结报告"""
    summary = []
    total = len(df)
    relevant = df[df['是否相关'] == '是']
    irrelevant = df[df['是否相关'] == '否']
    relevant_count = len(relevant)
    irrelevant_count = len(irrelevant)

    # 总体统计
    summary.append("===== 文档分类总结报告 =====")
    summary.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    summary.append(f"总文档数：{total} 份")
    summary.append(f"相关文档数：{relevant_count} 份（占比 {round(relevant_count / total * 100, 2)}%）")
    summary.append(f"不相关文档数：{irrelevant_count} 份（占比 {round(irrelevant_count / total * 100, 2)}%）\n")

    # 相关文档细分统计
    summary.append("----- 相关文档细分统计 -----")

    # 1. 层级分布
    level_counts = defaultdict(int)
    for levels in relevant['层级']:
        for level in levels.split(';'):
            level_counts[level] += 1
    summary.append("\n层级分布：")
    for level, cnt in sorted(level_counts.items(), key=lambda x: -x[1]):
        summary.append(f"- {level}：{cnt} 份（占相关文档 {round(cnt / relevant_count * 100, 2)}%）")

    # 2. 区域分布
    region_counts = defaultdict(int)
    for regions in relevant['区域']:
        for region in regions.split(';'):
            region_counts[region] += 1
    summary.append("\n区域分布：")
    for region, cnt in sorted(region_counts.items(), key=lambda x: -x[1]):
        summary.append(f"- {region}：{cnt} 份（占相关文档 {round(cnt / relevant_count * 100, 2)}%）")

    # 3. 文件类型分布
    type_counts = defaultdict(int)
    for types in relevant['文件类型']:
        for t in types.split(';'):
            type_counts[t] += 1
    summary.append("\n文件类型分布：")
    for t, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
        summary.append(f"- {t}：{cnt} 份（占相关文档 {round(cnt / relevant_count * 100, 2)}%）")

    # 4. 规制阶段分布
    stage_counts = defaultdict(int)
    for stages in relevant['规制阶段']:
        for stage in stages.split(';'):
            stage_counts[stage] += 1
    summary.append("\n规制阶段分布：")
    for stage, cnt in sorted(stage_counts.items(), key=lambda x: -x[1]):
        summary.append(f"- {stage}：{cnt} 份（占相关文档 {round(cnt / relevant_count * 100, 2)}%）")

    # 保存总结报告
    summary_path = os.path.join(output_dir, '分类总结报告.txt')
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(summary))
    print(f"总结报告已保存至：{summary_path}")


def organize_files(df, output_root):
    """按分类整理文件（严格对应文件夹）"""
    # 创建根目录
    os.makedirs(output_root, exist_ok=True)

    # 1. 不相关文件单独存放
    irrelevant_dir = os.path.join(output_root, '0_不相关文档')
    os.makedirs(irrelevant_dir, exist_ok=True)

    # 2. 相关文件按层级→区域→文件类型存放
    relevant_root = os.path.join(output_root, '1_相关文档')
    os.makedirs(relevant_root, exist_ok=True)

    # 遍历所有文件进行整理
    for _, row in df.iterrows():
        src_path = row['文件路径']
        file_name = row['文件名']
        relevant = row['是否相关']

        if relevant == '否':
            # 不相关文件→单独文件夹
            dest_path = os.path.join(irrelevant_dir, file_name)
        else:
            # 相关文件→层级/区域/文件类型
            level = row['层级'].split(';')[0]  # 取第一个匹配的层级
            region = row['区域'].split(';')[0]  # 取第一个匹配的区域
            doc_type = row['文件类型'].split(';')[0]  # 取第一个匹配的类型
            dest_dir = os.path.join(relevant_root, level, region, doc_type)
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, file_name)

        # 处理文件名重复
        counter = 1
        while os.path.exists(dest_path):
            name, ext = os.path.splitext(file_name)
            dest_path = os.path.join(os.path.dirname(dest_path), f"{name}_{counter}{ext}")
            counter += 1

        shutil.copy2(src_path, dest_path)
        print(f"已整理：{file_name} → {os.path.dirname(dest_path)}")


# -------------------------- 主程序入口 --------------------------
def main():
    print("===== 环境规制文档分类系统 =====")
    input_dir = input("请输入待处理文档的根目录：").strip()
    if not os.path.isdir(input_dir):
        print(f"错误：{input_dir} 不是有效目录！")
        return

    # 1. 批量处理文档
    print("\n开始处理文档...")
    results = batch_process(input_dir)
    if not results:
        print("未找到可处理的文档（支持txt/docx/pdf）！")
        return
    print(f"文档处理完成，共处理 {len(results)} 份文档")

    # 2. 生成Excel表格
    df = generate_table(results, input_dir)

    # 3. 生成总结报告
    generate_summary(df, input_dir)

    # 4. 整理文件
    if input("\n是否按分类整理文件？(y/n)：").strip().lower() == 'y':
        output_root = input("请输入整理后文件的根目录：").strip()
        print("开始整理文件...")
        organize_files(df, output_root)
        print(f"文件整理完成，保存至：{output_root}")


if __name__ == "__main__":
    main()