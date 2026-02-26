import os
import re
import shutil
import pandas as pd
from datetime import datetime
from docx import Document
import PyPDF2
from collections import defaultdict

# -------------------------- 优化后的分类标准配置 --------------------------
# 1. 政府层级（拆分省市层面为省/市单独分类，明确优先级）
LEVELS = {
    '国家层面': ['宏观导向', '顶层设计', '国家', '国务院', '中央', '全国', '人大', '部委'],
    '省层面': ['省', '自治区', '直辖市', '省级政府', '省内', '省级规划'],
    '市层面': ['市', '自治州', '市级政府', '市内', '市级规划'],
    '部门/专项层面': ['部门', '大气', '水', '土壤', '碳排放', '污染源', '专项']
}

# 2. 新增核心维度：环境要素（与政策主题强相关）
ENVIRONMENTAL_FACTORS = {
    '大气': ['大气', '空气', 'PM2.5', '雾霾', '扬尘', '挥发性有机物(VOCs)'],
    '水': ['水', '水质', '河流', '湖泊', '黑臭水体', '污水处理', '水源地'],
    '土壤': ['土壤', '土地', '重金属', '耕地污染', '土壤修复', '农用地'],
    '碳排放': ['碳达峰', '碳中和', '双碳', '低碳', '碳交易', '温室气体'],
    '生态保护': ['生态', '生态红线', '自然保护区', '生物多样性', '生态修复']
}

# 3. 新增核心维度：政策工具类型（反映执行方式）
POLICY_TOOLS = {
    '命令控制型': ['强制', '禁止', '处罚', '关停', '限期整改', '标准限值'],
    '市场激励型': ['补贴', '税收优惠', '碳交易', '排污权交易', '绿色金融'],
    '自愿参与型': ['倡议', '承诺', '认证', '企业自律', '行业公约']
}

# 4. 关键词库（区分核心主题词与特征词）
CORE_THEMES = [  # 用于判断文件相关性（至少匹配1个）
    '污染防治', '排放标准', '生态保护', '碳达峰', '碳中和',
    '环境治理', '绿色转型', '执法检查'
]
KEYWORDS = {  # 特征关键词（细化标签）
    '污染防治': ['污染防治', '污染治理', '防治污染', '综合治理'],
    '排放标准': ['排放标准', '排放限值', '排放要求', '技术标准'],
    '生态保护': ['生态保护', '生态建设', '生态修复', '生态环境'],
    '碳达峰碳中和': ['碳达峰', '碳中和', '双碳', '碳目标'],
    '绿色转型': ['绿色转型', '绿色发展', '低碳转型', '绿色升级'],
    '环境治理': ['环境治理', '环境管理', '治理体系'],
    '执法检查': ['执法检查', '监督检查', '执法监督', '检查执法'],
    '惩处机制': ['惩处机制', '处罚措施', '问责机制', '惩戒机制'],
    '激励补贴': ['激励补贴', '奖励政策', '补贴措施', '优惠政策']
}

# 5. 文件类型（细化分类，避免交叉）
DOC_TYPES = {
    '法律与行政法规': ['法', '条例', '行政法规', '人大颁布', '主席令', '国务院令'],
    '政策性文件与规划': ['政策', '规划', '战略', '中长期目标', '发展纲要'],
    '标准与技术规范': ['标准', '规范', '技术要求', '排放限值', '技术导则'],
    '地方政府文件': ['地方政府令', '地方性实施办法', '省市细则'],
    '执法与通报文件': ['执法', '通报', '处罚决定', '督查结果'],
    '行动方案': ['行动方案', '实施方案', '攻坚计划', '专项行动']
}

# 6. 区域（保留核心区域，后续可扩展）
REGIONS = {
    '京津冀': ['北京', '天津', '河北', '京津冀', '雄安'],
    '长三角': ['上海', '江苏', '浙江', '安徽', '长三角', '沪苏浙皖'],
    '珠三角': ['广东', '广州', '深圳', '珠三角', '粤港澳', '大湾区']
}

# 7. 时间范围（细化到日期）
START_DATE = datetime(2015, 1, 1)
CURRENT_DATE = datetime.now()


# -------------------------- 文件读取与解析函数 --------------------------
def read_file_content(file_path):
    """根据文件类型读取内容（支持txt/docx/pdf）"""
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


# -------------------------- 核心分类与提取函数 --------------------------
def is_relevant(text):
    """判断文件是否与核心主题相关（至少匹配1个核心主题词）"""
    text_lower = text.lower()
    for theme in CORE_THEMES:
        if theme.lower() in text_lower:
            return True
    return False


def extract_date(text, file_name):
    """提取文件日期（支持YYYY-MM-DD/YYYY年MM月DD日，精确到日）"""
    date_patterns = [
        r'\b20\d{2}[/-]\d{1,2}[/-]\d{1,2}\b',  # 数字日期格式
        r'\b20\d{2}年\d{1,2}月\d{1,2}日\b'  # 中文日期格式
    ]
    # 优先从文本提取，再从文件名提取
    for pattern in date_patterns:
        match = re.search(pattern, text) or re.search(pattern, file_name)
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


def classify_content(text, classification_dict, is_priority=False):
    """
    按分类字典对文本进行分类
    is_priority=True时启用优先级（匹配到高优先级类别后停止）
    """
    result = []
    text_lower = text.lower()
    for category, keywords in classification_dict.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                result.append(category)
                if is_priority:  # 层级分类需要优先级
                    return result
                break  # 非优先级分类保留所有匹配
    return result if result else [f'未分类-{list(classification_dict.keys())[0].split("/")[0]}']


# -------------------------- 文档处理主函数 --------------------------
def process_document(file_path):
    """处理单个文档并返回完整分类结果"""
    file_name = os.path.basename(file_path)
    text = read_file_content(file_path)
    if not text:
        return None

    # 核心信息提取
    date = extract_date(text, file_name)
    in_time_range = "是" if (date and START_DATE <= date <= CURRENT_DATE) else "否"
    relevant = is_relevant(text)

    # 分类（政府层级启用优先级）
    levels = classify_content(text, LEVELS, is_priority=True)
    env_factors = classify_content(text, ENVIRONMENTAL_FACTORS)
    policy_tools = classify_content(text, POLICY_TOOLS)
    keywords = classify_content(text, KEYWORDS)
    doc_types = classify_content(text, DOC_TYPES)
    regions = classify_content(text, REGIONS)

    return {
        'file_name': file_name,
        'file_path': file_path,
        'date': date.strftime('%Y-%m-%d') if date else '未提取到',
        'in_time_range': in_time_range,
        'is_relevant': '是' if relevant else '否',
        'levels': levels,
        'env_factors': env_factors,
        'policy_tools': policy_tools,
        'keywords': keywords,
        'doc_types': doc_types,
        'regions': regions
    }


def process_directory(input_dir):
    """批量处理目录下的所有文档"""
    results = []
    for root, _, files in os.walk(input_dir):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in ['.txt', '.docx', '.pdf']:  # 支持主流文本格式
                file_path = os.path.join(root, file)
                result = process_document(file_path)
                if result:
                    results.append(result)
    return results


# -------------------------- 结果输出与分析函数 --------------------------
def save_classification_report(results, report_path):
    """保存详细分类报告"""
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"环境政策文档分类报告 - 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(
            f"共处理 {len(results)} 个文档 | 相关文档: {sum(1 for r in results if r['is_relevant'] == '是')} 个\n\n")

        for i, result in enumerate(results, 1):
            f.write(f"文档 {i}: {result['file_name']}\n")
            f.write(f"路径: {result['file_path']}\n")
            f.write(f"日期: {result['date']} | 时间范围内: {result['in_time_range']} | 相关: {result['is_relevant']}\n")
            f.write(f"层级: {', '.join(result['levels'])}\n")
            f.write(f"环境要素: {', '.join(result['env_factors'])}\n")
            f.write(f"政策工具: {', '.join(result['policy_tools'])}\n")
            f.write(f"地区: {', '.join(result['regions'])}\n")
            f.write(f"文档类型: {', '.join(result['doc_types'])}\n")
            f.write(f"关键词: {', '.join(result['keywords'])}\n")
            f.write("-" * 100 + "\n")


def generate_multidimensional_report(results, output_dir):
    """生成多维度统计报告（支持交叉分析，用于发现文献不足）"""
    df = pd.DataFrame(results)
    relevant_df = df[df['is_relevant'] == '是']
    report = []

    # 1. 总体统计
    report.append("===== 多维度分类统计报告 =====")
    report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d')}")
    report.append(f"总文档数: {len(df)} | 相关文档数: {len(relevant_df)}\n")

    # 2. 环境要素×政策工具交叉分析（核心维度）
    report.append("----- 环境要素×政策工具分布 -----")
    relevant_df['env_first'] = relevant_df['env_factors'].apply(lambda x: x[0])
    relevant_df['tool_first'] = relevant_df['policy_tools'].apply(lambda x: x[0])
    factor_tool_cross = pd.crosstab(relevant_df['env_first'], relevant_df['tool_first'])
    report.append(factor_tool_cross.to_string())

    # 3. 政府层级×区域分布
    report.append("\n----- 政府层级×区域分布 -----")
    level_region_cross = pd.crosstab(
        relevant_df['levels'].apply(lambda x: x[0]),
        relevant_df['regions'].apply(lambda x: x[0])
    )
    report.append(level_region_cross.to_string())

    # 4. 文献不足分析提示
    report.append("\n===== 潜在文献不足分析 =====")
    # 4.1 环境要素覆盖不足
    factor_counts = relevant_df['env_first'].value_counts()
    undercovered_factors = [f for f, cnt in factor_counts.items() if cnt < len(relevant_df) * 0.1]  # 占比低于10%
    if undercovered_factors:
        report.append(f"环境要素覆盖不足（占比<10%）: {', '.join(undercovered_factors)}")
    # 4.2 政策工具类型单一
    tool_counts = relevant_df['tool_first'].value_counts()
    if len(tool_counts) < 3:
        missing_tools = [t for t in POLICY_TOOLS.keys() if t not in tool_counts.index]
        report.append(f"政策工具类型不完整，缺少: {', '.join(missing_tools)}")
    # 4.3 区域覆盖不全
    region_counts = relevant_df['regions'].apply(lambda x: x[0]).value_counts()
    missing_regions = [r for r in REGIONS.keys() if r not in region_counts.index]
    if missing_regions:
        report.append(f"区域覆盖不足，缺少: {', '.join(missing_regions)}")

    # 保存报告
    report_path = os.path.join(output_dir, "多维度统计分析报告.txt")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    return report_path


def organize_files(results, output_dir):
    """根据分类结果整理文件（按时间→层级→环境要素）"""
    for result in results:
        if result['is_relevant'] != '是':
            continue  # 只整理相关文件
        # 构建分类路径
        year = result['date'].split('-')[0] if '-' in result['date'] else '年份未知'
        level = result['levels'][0]
        env_factor = result['env_factors'][0]
        target_path = os.path.join(output_dir, year, level, env_factor)

        # 创建目录并复制文件（处理重名）
        os.makedirs(target_path, exist_ok=True)
        src_path = result['file_path']
        dest_path = os.path.join(target_path, result['file_name'])
        counter = 1
        while os.path.exists(dest_path):
            name, ext = os.path.splitext(result['file_name'])
            dest_path = os.path.join(target_path, f"{name}_{counter}{ext}")
            counter += 1
        shutil.copy2(src_path, dest_path)
        print(f"已整理: {result['file_name']} -> {target_path}")


# -------------------------- 主函数 --------------------------
def main():
    print("===== 优化版环境政策文档分类工具 =====")
    input_dir = input("请输入要处理的文档目录: ").strip()
    if not os.path.isdir(input_dir):
        print(f"错误: {input_dir} 不是有效的目录")
        return

    # 处理文档
    print("\n开始处理文档...")
    results = process_directory(input_dir)
    print(f"处理完成，共处理 {len(results)} 个文档")

    # 保存基础分类报告
    basic_report = os.path.join(input_dir, "分类详情报告.txt")
    save_classification_report(results, basic_report)
    print(f"分类详情报告已保存至: {basic_report}")

    # 生成多维度统计报告（含文献不足分析）
    stats_report = generate_multidimensional_report(results, input_dir)
    print(f"多维度统计分析报告已保存至: {stats_report}")

    # 可选：整理文件
    if input("\n是否按分类整理相关文件? (y/n): ").strip().lower() == 'y':
        output_dir = input("请输入目标整理目录: ").strip()
        os.makedirs(output_dir, exist_ok=True)
        print("开始整理文件...")
        organize_files(results, output_dir)
        print("文件整理完成")


if __name__ == "__main__":
    main()