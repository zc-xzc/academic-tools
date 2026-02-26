import os
import re
import shutil
from datetime import datetime
from docx import Document
import PyPDF2

# 分类标准配置
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
    '珠三角': ['广东', '广州', '深圳', '珠三角', '粤港澳', '大湾区']
}

# 时间范围设置
START_YEAR = 2015
CURRENT_YEAR = datetime.now().year


def read_file_content(file_path):
    """根据文件类型读取内容"""
    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == '.txt':
            return read_txt(file_path)
        elif ext in ['.doc', '.docx']:
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
    """读取txt文件"""
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
    full_text = []
    for para in doc.paragraphs:
        full_text.append(para.text)
    return ' '.join(full_text)


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
    """根据分类字典对文本进行分类"""
    result = []
    text_lower = text.lower()
    for category, keywords in classification_dict.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                result.append(category)
                break  # 每个类别只匹配一次
    return result


def process_document(file_path):
    """处理单个文档并返回分类结果"""
    file_name = os.path.basename(file_path)
    text = read_file_content(file_path)

    if not text:
        return None

    # 提取信息
    year = extract_year(text, file_name)
    levels = classify_content(text, LEVELS)
    keywords = classify_content(text, KEYWORDS)
    doc_types = classify_content(text, DOC_TYPES)
    regions = classify_content(text, REGIONS)

    # 处理未分类的情况
    if not levels:
        levels = ['未分类-层级']
    if not regions:
        regions = ['未分类-地区']
    if not doc_types:
        doc_types = ['未分类-类型']
    if not keywords:
        keywords = ['未匹配关键词']

    return {
        'file_name': file_name,
        'file_path': file_path,
        'year': year if year else '未确定年份',
        'levels': levels,
        'keywords': keywords,
        'doc_types': doc_types,
        'regions': regions
    }


def process_directory(input_dir):
    """处理目录下的所有文档"""
    results = []
    for root, _, files in os.walk(input_dir):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in ['.txt', '.doc', '.docx', '.pdf']:
                file_path = os.path.join(root, file)
                result = process_document(file_path)
                if result:
                    results.append(result)
    return results


def save_classification_report(results, report_path):
    """保存分类报告"""
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
            f.write(f"关键词: {', '.join(result['keywords'])}\n")
            f.write("-" * 80 + "\n")


def organize_files(results, output_dir):
    """根据分类结果组织文件"""
    for result in results:
        # 创建分类路径
        year_dir = str(result['year'])
        level_dir = result['levels'][0]  # 取第一个匹配的层级
        region_dir = result['regions'][0]  # 取第一个匹配的地区
        type_dir = result['doc_types'][0]  # 取第一个匹配的类型

        # 构建目标路径
        target_path = os.path.join(
            output_dir,
            year_dir,
            level_dir,
            region_dir,
            type_dir
        )

        # 创建目录
        os.makedirs(target_path, exist_ok=True)

        # 复制文件
        src_path = result['file_path']
        dest_path = os.path.join(target_path, result['file_name'])

        # 处理文件名重复的情况
        counter = 1
        while os.path.exists(dest_path):
            name, ext = os.path.splitext(result['file_name'])
            dest_path = os.path.join(target_path, f"{name}_{counter}{ext}")
            counter += 1

        shutil.copy2(src_path, dest_path)
        print(f"已复制: {result['file_name']} -> {target_path}")


def main():
    print("===== 环境政策文档分类工具 =====")
    input_dir = input("请输入要处理的文档目录: ").strip()

    if not os.path.isdir(input_dir):
        print(f"错误: {input_dir} 不是有效的目录")
        return

    # 处理文档
    print("\n开始处理文档...")
    results = process_directory(input_dir)
    print(f"处理完成，共处理 {len(results)} 个文档")

    # 保存报告
    report_path = os.path.join(input_dir, "分类报告.txt")
    save_classification_report(results, report_path)
    print(f"分类报告已保存至: {report_path}")

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