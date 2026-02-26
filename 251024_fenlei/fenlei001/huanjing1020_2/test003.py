import os
import re
import shutil
import random
import pandas as pd
from datetime import datetime
from docx import Document
import PyPDF2
from collections import defaultdict

# -------------------------- 分类标准配置（新增环境要素和政策工具维度） --------------------------
LEVELS = {
    '国家层面': ['宏观导向', '顶层设计', '国家', '国务院', '中央', '全国'],
    '省市层面': ['地方', '省', '市', '自治区', '直辖市', '区域'],
    '部门/专项层面': ['部门', '大气', '水', '土壤', '碳排放', '污染源', '专项']
}

KEYWORDS = {
    '污染防治': ['污染防治', '污染治理', '防治污染'],
    '排放标准': ['排放标准', '排放限值', '排放要求'],
    '生态保护': ['生态保护', '生态建设', '生态修复', '生态环境'],
    '碳达峰碳中和': ['碳达峰', '碳中和', '双碳', '碳目标'],
    '绿色转型': ['绿色转型', '绿色发展', '低碳转型', '绿色升级'],
    '环境治理': ['环境治理', '环境管理', '治理体系'],
    '执法检查': ['执法检查', '监督检查', '执法监督', '检查执法'],
    '惩处机制': ['惩处机制', '处罚措施', '问责机制', '惩戒机制'],
    '激励补贴': ['激励补贴', '奖励政策', '补贴措施', '优惠政策']
}

DOC_TYPES = {
    '法律与行政法规': ['法律', '法规', '条例', '行政法', '人大'],
    '政策性文件与规划': ['政策', '规划', '战略', '中长期目标', '计划', '纲要'],
    '部门规章与标准文件': ['规章', '标准', '规范', '规定', '执行细则'],
    '地方政府文件': ['地方政府', '地方性', '省市', '人民政府'],
    '执法与通报文件': ['执法', '通报', '检查结果', '处罚决定', '通告']
}

REGIONS = {
    '京津冀': ['北京', '天津', '河北', '京津冀', '雄安'],
    '长三角': ['上海', '江苏', '浙江', '安徽', '长三角', '沪苏浙皖'],
    '珠三角': ['广东', '广州', '深圳', '珠三角', '粤港澳', '大湾区'],
    '东北地区': ['辽宁', '吉林', '黑龙江', '东北'],
    '中西部': ['山西', '河南', '湖北', '湖南', '重庆', '四川', '陕西', '甘肃', '中西部']
}

# 新增：环境要素维度
ENVIRONMENTAL_FACTORS = {
    '大气': ['大气', '空气', 'PM2.5', '雾霾', '扬尘', '挥发性有机物'],
    '水': ['水', '水质', '河流', '湖泊', '黑臭水体', '污水处理'],
    '土壤': ['土壤', '土地', '重金属', '土壤修复', '耕地污染'],
    '碳排放': ['碳', '碳中和', '碳达峰', '双碳', '低碳', '碳交易'],
    '污染源': ['污染源', '排污', '污染物', '污染源普查', '工业污染'],
    '生态保护': ['生态', '生态红线', '自然保护区', '生物多样性', '生态修复']
}

# 新增：政策工具类型维度
POLICY_TOOLS = {
    '命令控制型': ['强制', '必须', '禁止', '处罚', '关停', '限期整改', '强制执行'],
    '市场激励型': ['补贴', '奖励', '税收优惠', '碳交易', '排污权交易', '绿色金融'],
    '自愿参与型': ['自愿', '倡议', '承诺', '认证', '企业自律', '行业公约'],
    '多元协同型': ['公众监督', 'NGO', '社会组织', '跨区域合作', '政企联动']
}

# 时间范围设置
START_YEAR = 2015
CURRENT_YEAR = datetime.now().year


# -------------------------- 文件读取函数 --------------------------
def read_file_content(file_path):
    """根据文件类型读取内容"""
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
        print(f"读取文件出错 {file_path}: {str(e)}")
        return ""


def read_txt(file_path):
    """读取txt文件（多编码尝试）"""
    encodings = ['utf-8', 'gbk', 'gb2312', 'ansi']
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    return ""


def read_docx(file_path):
    """读取docx文件"""
    doc = Document(file_path)
    return ' '.join([para.text for para in doc.paragraphs])


def read_pdf(file_path):
    """读取pdf文件"""
    text = ""
    with open(file_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + " "
    return text


# -------------------------- 信息提取与分类函数 --------------------------
def extract_year(text, file_name):
    """从文本或文件名中提取年份"""
    # 先从文件名提取
    year_match = re.search(r'\b(20\d{2})\b', file_name)
    if year_match:
        year = int(year_match.group(1))
        if START_YEAR <= year <= CURRENT_YEAR:
            return year

    # 再从文本中提取
    year_match = re.search(r'\b(20\d{2})\b', text)
    if year_match:
        year = int(year_match.group(1))
        if START_YEAR <= year <= CURRENT_YEAR:
            return year

    return None


def classify_content(text, classification_dict):
    """根据分类字典对文本进行分类（支持多标签）"""
    result = []
    text_lower = text.lower()
    for category, keywords in classification_dict.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                result.append(category)
                break  # 每个类别只匹配一次
    return result


def process_document(file_path):
    """处理单个文档并返回分类结果（新增环境要素和政策工具）"""
    file_name = os.path.basename(file_path)
    text = read_file_content(file_path)

    if not text:
        return None

    # 提取信息（新增环境要素和政策工具分类）
    year = extract_year(text, file_name)
    levels = classify_content(text, LEVELS)
    keywords = classify_content(text, KEYWORDS)
    doc_types = classify_content(text, DOC_TYPES)
    regions = classify_content(text, REGIONS)
    env_factors = classify_content(text, ENVIRONMENTAL_FACTORS)  # 新增
    policy_tools = classify_content(text, POLICY_TOOLS)  # 新增

    # 处理未分类的情况
    if not levels:
        levels = ['未分类-层级']
    if not regions:
        regions = ['未分类-地区']
    if not doc_types:
        doc_types = ['未分类-类型']
    if not keywords:
        keywords = ['未匹配关键词']
    if not env_factors:
        env_factors = ['未明确-环境要素']  # 新增
    if not policy_tools:
        policy_tools = ['未明确-政策工具']  # 新增

    return {
        'file_name': file_name,
        'file_path': file_path,
        'year': year if year else '未确定年份',
        'levels': levels,
        'keywords': keywords,
        'doc_types': doc_types,
        'regions': regions,
        'env_factors': env_factors,  # 新增
        'policy_tools': policy_tools  # 新增
    }


def process_directory(input_dir):
    """处理目录下的所有文档"""
    results = []
    for root, _, files in os.walk(input_dir):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in ['.txt', '.docx', '.pdf']:  # 移除对.doc的支持（docx更通用）
                file_path = os.path.join(root, file)
                result = process_document(file_path)
                if result:
                    results.append(result)
    return results


# -------------------------- 准确性验证机制 --------------------------
def generate_detailed_summary(results, output_dir):
    """生成交叉分析报告（验证分类合理性）"""
    df = pd.DataFrame(results)
    # 处理多标签（取第一个标签用于交叉分析）
    df['level_first'] = df['levels'].apply(lambda x: x[0])
    df['region_first'] = df['regions'].apply(lambda x: x[0])
    df['env_first'] = df['env_factors'].apply(lambda x: x[0])
    df['tool_first'] = df['policy_tools'].apply(lambda x: x[0])
    df['doc_type_first'] = df['doc_types'].apply(lambda x: x[0])

    summary = []
    total = len(df)
    summary.append("===== 分类交叉验证报告 =====")
    summary.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    summary.append(f"总文件数：{total} 份\n")

    # 1. 环境要素 × 政策工具交叉统计（核心验证）
    summary.append("----- 环境要素 × 政策工具分布 -----")
    env_tool_cross = pd.crosstab(df['env_first'], df['tool_first'])
    summary.append(env_tool_cross.to_string())
    summary.append("\n注：若某组合占比异常（如<5%），需检查分类逻辑或文献数量\n")

    # 2. 政府层级 × 区域交叉统计
    summary.append("----- 政府层级 × 区域分布 -----")
    level_region_cross = pd.crosstab(df['level_first'], df['region_first'])
    summary.append(level_region_cross.to_string())

    # 3. 文件类型 × 政策工具交叉统计
    summary.append("\n----- 文件类型 × 政策工具分布 -----")
    type_tool_cross = pd.crosstab(df['doc_type_first'], df['tool_first'])
    summary.append(type_tool_cross.to_string())

    # 保存报告
    report_path = os.path.join(output_dir, "分类交叉验证报告.txt")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(summary))
    print(f"分类交叉验证报告已保存至: {report_path}")
    return df


def generate_sampling_verification(results, output_dir, sample_ratio=0.1):
    """生成人工抽样验证报告（随机抽取10%-20%文件）"""
    sample_size = max(1, int(len(results) * sample_ratio))
    samples = random.sample(results, sample_size)

    verification = []
    verification.append("===== 人工抽样验证表 =====")
    verification.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d')}")
    verification.append(f"总样本量：{len(results)} 份 | 抽样数量：{sample_size} 份（{sample_ratio*100}%）")
    verification.append("请对比机器分类与人工分类结果，填写准确率\n")

    for i, sample in enumerate(samples, 1):
        verification.append(f"样本 {i}: {sample['file_name']}")
        verification.append(f"路径: {sample['file_path']}")
        verification.append(f"机器分类 - 环境要素: {', '.join(sample['env_factors'])}")
        verification.append(f"机器分类 - 政策工具: {', '.join(sample['policy_tools'])}")
        verification.append(f"机器分类 - 层级: {', '.join(sample['levels'])}")
        verification.append("人工分类 - 环境要素: _______________")
        verification.append("人工分类 - 政策工具: _______________")
        verification.append("人工分类 - 层级: _______________")
        verification.append("是否一致（是/否）: _______________")
        verification.append("-" * 80 + "\n")

    # 计算准确率公式
    verification.append("\n准确率计算：（一致样本数 / 总抽样数）× 100% （目标≥80%）")

    # 保存验证表
    verify_path = os.path.join(output_dir, "人工抽样验证表.txt")
    with open(verify_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(verification))
    print(f"人工抽样验证表已保存至: {verify_path}")


# -------------------------- 文献检索不足分析 --------------------------
def generate_insufficiency_analysis(df, output_dir):
    """生成文献检索不足分析报告"""
    analysis = []
    analysis.append("===== 文献检索不足分析报告 =====")
    analysis.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    total = len(df)
    if total == 0:
        analysis.append("无有效文献数据，无法进行分析")
        report_path = os.path.join(output_dir, "文献检索不足分析报告.txt")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(analysis))
        print(f"文献检索不足分析报告已保存至: {report_path}")
        return

    # 1. 分类维度覆盖不足分析
    analysis.append("----- 1. 分类维度覆盖不足 -----")

    # 1.1 环境要素失衡分析
    env_counts = df['env_first'].value_counts()
    analysis.append("\n环境要素分布：")
    for env, cnt in env_counts.items():
        ratio = cnt / total * 100
        analysis.append(f"- {env}: {cnt} 份（{ratio:.2f}%）")
        if ratio < 5 and env != '未明确-环境要素':  # 占比过低（<5%）
            analysis.append(f"  ⚠️ 警告：{env}相关文献占比过低，建议补充检索")

    # 1.2 政策工具单一分析
    tool_counts = df['tool_first'].value_counts()
    analysis.append("\n政策工具分布：")
    for tool, cnt in tool_counts.items():
        ratio = cnt / total * 100
        analysis.append(f"- {tool}: {cnt} 份（{ratio:.2f}%）")
        if ratio < 5 and tool != '未明确-政策工具':
            analysis.append(f"  ⚠️ 警告：{tool}相关文献占比过低，可能缺少该类型政策")

    # 1.3 区域覆盖不全分析
    region_counts = df['region_first'].value_counts()
    analysis.append("\n区域分布：")
    for region, cnt in region_counts.items():
        ratio = cnt / total * 100
        analysis.append(f"- {region}: {cnt} 份（{ratio:.2f}%）")
        if ratio < 3 and region not in ['未分类-地区', '全国性']:
            analysis.append(f"  ⚠️ 警告：{region}区域文献覆盖不足，建议补充")

    # 2. 时间分布不均分析
    analysis.append("\n----- 2. 时间分布不均 -----")
    year_counts = df[df['year'] != '未确定年份']['year'].value_counts().sort_index()
    analysis.append("年份分布：")
    for year in range(START_YEAR, CURRENT_YEAR + 1):
        cnt = year_counts.get(year, 0)
        ratio = cnt / total * 100 if total > 0 else 0
        analysis.append(f"- {year}年: {cnt} 份（{ratio:.2f}%）")
        if cnt == 0:
            analysis.append(f"  ⚠️ 警告：{year}年无文献，可能存在检索遗漏")

    # 3. 文件类型缺失分析
    analysis.append("\n----- 3. 文件类型缺失 -----")
    doc_type_counts = df['doc_type_first'].value_counts()
    analysis.append("文件类型分布：")
    for doc_type, cnt in doc_type_counts.items():
        ratio = cnt / total * 100
        analysis.append(f"- {doc_type}: {cnt} 份（{ratio:.2f}%）")
        if ratio < 5 and doc_type != '未分类-类型':
            analysis.append(f"  ⚠️ 警告：{doc_type}类文献不足，建议补充检索")

    # 4. 主题相关性不足分析
    analysis.append("\n----- 4. 主题相关性不足 -----")
    unmatch_keywords = df[df['keywords'].apply(lambda x: '未匹配关键词' in x)]
    unmatch_ratio = len(unmatch_keywords) / total * 100 if total > 0 else 0
    analysis.append(f"未匹配关键词的文献数：{len(unmatch_keywords)} 份（{unmatch_ratio:.2f}%）")
    if unmatch_ratio > 20:
        analysis.append("  ⚠️ 警告：未匹配关键词文献占比过高，建议补充核心关键词（如无废城市、清洁生产等）")

    # 保存分析报告
    report_path = os.path.join(output_dir, "文献检索不足分析报告.txt")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(analysis))
    print(f"文献检索不足分析报告已保存至: {report_path}")


# -------------------------- 原有功能：分类报告与文件整理 --------------------------
def save_classification_report(results, report_path):
    """保存基础分类报告"""
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"文档分类报告 - 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"共处理 {len(results)} 个文档\n\n")

        for i, result in enumerate(results, 1):
            f.write(f"文档 {i}: {result['file_name']}\n")
            f.write(f"路径: {result['file_path']}\n")
            f.write(f"年份: {result['year']}\n")
            f.write(f"层级: {', '.join(result['levels'])}\n")
            f.write(f"地区: {', '.join(result['regions'])}\n")
            f.write(f"文档类型: {', '.join(result['doc_types'])}\n")
            f.write(f"环境要素: {', '.join(result['env_factors'])}\n")  # 新增
            f.write(f"政策工具: {', '.join(result['policy_tools'])}\n")  # 新增
            f.write(f"关键词: {', '.join(result['keywords'])}\n")
            f.write("-" * 80 + "\n")


def organize_files(results, output_dir):
    """根据分类结果组织文件（新增环境要素维度）"""
    for result in results:
        # 创建分类路径（新增环境要素层级）
        year_dir = str(result['year'])
        level_dir = result['levels'][0]
        region_dir = result['regions'][0]
        env_dir = result['env_factors'][0]  # 新增
        type_dir = result['doc_types'][0]

        # 构建目标路径
        target_path = os.path.join(
            output_dir,
            year_dir,
            level_dir,
            region_dir,
            env_dir,  # 新增
            type_dir
        )

        # 创建目录
        os.makedirs(target_path, exist_ok=True)

        # 复制文件（处理重名）
        src_path = result['file_path']
        dest_path = os.path.join(target_path, result['file_name'])
        counter = 1
        while os.path.exists(dest_path):
            name, ext = os.path.splitext(result['file_name'])
            dest_path = os.path.join(target_path, f"{name}_{counter}{ext}")
            counter += 1

        shutil.copy2(src_path, dest_path)
        print(f"已复制: {result['file_name']} -> {target_path}")


# -------------------------- 主函数 --------------------------
def main():
    print("===== 环境政策文档分类工具（优化版） =====")
    input_dir = input("请输入要处理的文档目录: ").strip()

    if not os.path.isdir(input_dir):
        print(f"错误: {input_dir} 不是有效的目录")
        return

    # 处理文档
    print("\n开始处理文档...")
    results = process_directory(input_dir)
    print(f"处理完成，共处理 {len(results)} 个文档")

    # 生成基础分类报告
    report_path = os.path.join(input_dir, "分类报告.txt")
    save_classification_report(results, report_path)
    print(f"基础分类报告已保存至: {report_path}")

    # 生成交叉验证报告（准确性验证1）
    df = generate_detailed_summary(results, input_dir)

    # 生成人工抽样验证表（准确性验证2）
    sample_ratio = float(input("\n请输入人工抽样比例（如0.1表示10%）: ").strip() or 0.1)
    generate_sampling_verification(results, input_dir, sample_ratio)

    # 生成文献检索不足分析报告
    generate_insufficiency_analysis(df, input_dir)

    # 组织文件
    organize = input("\n是否要按分类结果整理文件? (y/n): ").strip().lower()
    if organize == 'y':
        output_dir = input("请输入目标整理目录: ").strip()
        os.makedirs(output_dir, exist_ok=True)
        print("开始整理文件...")
        organize_files(results, output_dir)
        print("文件整理完成")


if __name__ == "__main__":
    main()