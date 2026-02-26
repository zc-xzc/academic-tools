import os
import re
import shutil
from datetime import datetime
from docx import Document
import PyPDF2

# -------------------------- 核心配置：强化环境规制相关关键词 --------------------------
# 1. 层级分类（保持原有框架，新增环境规制主体相关关键词）
LEVELS = {
    '国家层面': ['宏观导向', '顶层设计', '国家', '国务院', '中央', '全国', '法律', '行政法规'],
    '省市层面': ['地方', '省', '市', '自治区', '直辖市', '区域', '地方政府', '地方性法规'],
    '部门/专项层面': ['部门', '大气', '水', '土壤', '碳排放', '污染源', '专项', '行业标准', '监管细则']
}

# 2. 环境规制核心关键词（基于提供的内涵和关键词扩展）
KEYWORDS = {
    # 法律基础
    '环境法律': ['环境法', '空气法', '土壤法', '水法', '能源法', '环保法', '清洁空气法', '清洁水法'],
    # 规制工具（命令控制型）
    '命令控制型规制': ['排放标准', '强制监管', '法律法规', '监管手段', '工业污染管控'],
    # 规制工具（市场激励型）
    '市场激励型规制': ['污染税', '环境税', '能源税', '排污交易', '排污权交易', '碳税', '碳交易', '绿色金融',
                       '生态补偿'],
    # 规制目标与行为
    '规制目标与行为': ['污染防治', '节能', '减排', '排污', '废物管理', '资源利用', '环境治理'],
    # 多元协同与创新
    '多元协同与创新': ['环境信息披露', '非政府组织', '公众监督', '行业自律', '绿色供应链', '数字技术', '区块链',
                       '全生命周期管理']
}

# 3. 文件类型（强化环境规制相关文件类型识别）
DOC_TYPES = {
    '法律与行政法规': ['法律', '法规', '条例', '行政法', '人大', '环境法', '清洁空气法', '清洁水法'],
    '政策性文件与规划': ['政策', '规划', '战略', '中长期目标', '可持续发展', '绿色发展'],
    '部门规章与标准文件': ['规章', '标准', '规范', '规定', '执行细则', '排放标准', '行业标准'],
    '地方政府文件': ['地方政府', '地方性', '省市', '人民政府', '区域治理'],
    '执法与通报文件': ['执法', '通报', '检查结果', '处罚决定', '监管报告', '排污检查']
}

# 4. 区域（保持原有城市群）
REGIONS = {
    '京津冀': ['北京', '天津', '河北', '京津冀', '雄安'],
    '长三角': ['上海', '江苏', '浙江', '安徽', '长三角', '沪苏浙皖'],
    '珠三角': ['广东', '广州', '深圳', '珠三角', '粤港澳', '大湾区']
}

# 时间范围（2015年至今，与环境规制多元协同阶段匹配）
START_YEAR = 2015
CURRENT_YEAR = datetime.now().year


# -------------------------- 核心功能：文件读取与内容解析 --------------------------
def read_file_content(file_path):
    """读取不同类型文件的内容（支持txt、docx、pdf）"""
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
    """读取txt文件（尝试多种编码）"""
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
    """读取pdf文件文本内容"""
    text = ""
    with open(file_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + " "
    return text


# -------------------------- 核心功能：分类与检索逻辑 --------------------------
def extract_year(text, file_name):
    """提取文件年份（优先文件名，再文本内容）"""
    # 从文件名提取年份
    year_match = re.search(r'\b(20\d{2})\b', file_name)
    if year_match:
        year = int(year_match.group(1))
        if START_YEAR <= year <= CURRENT_YEAR:
            return year
    # 从文本提取年份
    year_match = re.search(r'\b(20\d{2})\b', text)
    if year_match:
        year = int(year_match.group(1))
        if START_YEAR <= year <= CURRENT_YEAR:
            return year
    return None


def classify_by_keywords(text, keyword_dict):
    """根据关键词字典匹配内容，返回匹配的类别"""
    matched = []
    text_lower = text.lower()  # 小写处理，避免大小写影响
    for category, keywords in keyword_dict.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                matched.append(category)
                break  # 每个类别只匹配一次
    return matched if matched else ['未匹配']


def analyze_environmental_regulation(text):
    """专项分析：判断文件是否涉及环境规制的三个阶段特征"""
    stages = []
    # 1. 命令控制阶段（20世纪60-70年代，法律法规+政府主导）
    if re.search(r'命令控制|政府主导|强制监管|清洁空气法|清洁水法', text, re.IGNORECASE):
        stages.append('命令控制阶段')
    # 2. 工具扩展阶段（1980-1990年代，市场工具+非正式规制）
    if re.search(r'污染税|排污权交易|非正式规制|市场激励', text, re.IGNORECASE):
        stages.append('工具扩展阶段')
    # 3. 多元协同阶段（21世纪后，多元主体+数字技术+可持续发展）
    if re.search(r'多元协同|公众监督|非政府组织|绿色金融|区块链|可持续发展', text, re.IGNORECASE):
        stages.append('多元协同阶段')
    return stages if stages else ['未明确阶段']


# -------------------------- 主流程：文件处理与结果输出 --------------------------
def process_document(file_path):
    """处理单个文件，返回完整分类结果"""
    file_name = os.path.basename(file_path)
    text = read_file_content(file_path)
    if not text:
        return None

    # 核心分类结果
    return {
        '文件名': file_name,
        '路径': file_path,
        '年份': extract_year(text, file_name) or '未明确',
        '层级': classify_by_keywords(text, LEVELS),
        '区域': classify_by_keywords(text, REGIONS),
        '文件类型': classify_by_keywords(text, DOC_TYPES),
        '环境规制关键词': classify_by_keywords(text, KEYWORDS),
        '规制阶段': analyze_environmental_regulation(text)
    }


def batch_process(input_dir):
    """批量处理目录下的文件"""
    results = []
    for root, _, files in os.walk(input_dir):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in ['.txt', '.docx', '.pdf']:  # 支持的文件类型
                file_path = os.path.join(root, file)
                result = process_document(file_path)
                if result:
                    results.append(result)
    return results


def save_report(results, output_dir):
    """保存检索报告（突出环境规制相关信息）"""
    report_path = os.path.join(output_dir, '环境规制文件检索报告.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"环境规制文件检索报告（生成时间：{datetime.now().strftime('%Y-%m-%d')}）\n")
        f.write(f"共检索到 {len(results)} 个相关文件\n\n")

        for i, res in enumerate(results, 1):
            f.write(f"文件 {i}：{res['文件名']}\n")
            f.write(f"路径：{res['路径']}\n")
            f.write(f"年份：{res['年份']}\n")
            f.write(f"层级：{', '.join(res['层级'])}\n")
            f.write(f"区域：{', '.join(res['区域'])}\n")
            f.write(f"文件类型：{', '.join(res['文件类型'])}\n")
            f.write(f"匹配的环境规制关键词：{', '.join(res['环境规制关键词'])}\n")
            f.write(f"所属规制阶段：{', '.join(res['规制阶段'])}\n")
            f.write("-" * 100 + "\n")
    print(f"检索报告已保存至：{report_path}")


def main():
    print("===== 环境规制相关文件检索工具 =====")
    input_dir = input("请输入文件所在目录：").strip()
    if not os.path.isdir(input_dir):
        print(f"错误：{input_dir} 不是有效目录")
        return

    # 批量处理文件
    print("开始检索环境规制相关文件...")
    results = batch_process(input_dir)
    print(f"检索完成，共找到 {len(results)} 个相关文件")

    # 保存报告
    save_report(results, input_dir)

    # 可选：按规制阶段/区域整理文件
    if input("是否按分类整理文件？(y/n)：").strip().lower() == 'y':
        output_root = input("请输入整理后的根目录：").strip()
        for res in results:
            # 构建路径：根目录/年份/规制阶段/区域/文件类型
            stage = res['规制阶段'][0] if res['规制阶段'] else '未分类'
            region = res['区域'][0] if res['区域'] else '未分类'
            file_type = res['文件类型'][0] if res['文件类型'] else '未分类'
            year = str(res['年份']) if res['年份'] != '未明确' else '年份未明确'

            target_dir = os.path.join(output_root, year, stage, region, file_type)
            os.makedirs(target_dir, exist_ok=True)

            # 复制文件（处理重名）
            src = res['路径']
            dest = os.path.join(target_dir, res['文件名'])
            counter = 1
            while os.path.exists(dest):
                name, ext = os.path.splitext(res['文件名'])
                dest = os.path.join(target_dir, f"{name}_{counter}{ext}")
                counter += 1
            shutil.copy2(src, dest)
        print(f"文件已整理至：{output_root}")


if __name__ == "__main__":
    main()