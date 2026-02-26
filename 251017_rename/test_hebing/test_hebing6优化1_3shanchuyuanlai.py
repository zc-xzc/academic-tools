import os
import pandas as pd
from difflib import SequenceMatcher
import re
from docx import Document
import shutil

def clean_filename(filename):
    """清理文件名，去除特殊字符并统一格式"""
    filename = re.sub(r'\.\.\.$', '', filename).strip()
    filename = re.sub(r'\(.*?\)', '', filename).strip()
    filename = re.sub(r'[+*%￥#@!~`^&()_=\[\]{};:,.<>?/\\|]', ' ', filename)
    filename = ' '.join(filename.split()).strip()
    return filename

def clean_title(title):
    """清理标题，去除特殊字符并统一格式"""
    title = re.sub(r'[+*%￥#@!~`^&()_=\[\]{};:,.<>?/\\|]', ' ', title)
    title = ' '.join(title.split()).strip()
    return title

def similarity(a, b):
    """计算两个字符串的相似度"""
    return SequenceMatcher(None, a, b).ratio()

def incremental_match(df, cleaned_filename, max_initial_length=20, max_incremental_length=100):
    """逐步匹配文件名与表格标题"""
    matched = None
    current_length = max_initial_length
    while current_length <= max_incremental_length:
        truncated_filename = cleaned_filename[:current_length]
        matched = df[df['标题_截断'] == truncated_filename]
        if not matched.empty:
            return matched
        current_length += 5
    return matched

def extract_title_from_docx(file_path):
    """从docx文件中提取标题"""
    try:
        doc = Document(file_path)
        for para in doc.paragraphs[:5]:
            if para.text.strip():
                return clean_title(para.text.strip())
        return None
    except:
        return None

def extract_title_from_txt(file_path):
    """从txt文件中提取标题"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read(200)
            lines = content.split('\n')
            for line in lines:
                cleaned_line = clean_title(line.strip())
                if cleaned_line:
                    return cleaned_line
        return None
    except:
        return None

def process_directory(root_dir):
    """处理目录中的表格和文档文件"""
    # 查找表格文件
    table_path = None
    for filename in os.listdir(root_dir):
        if filename.endswith(('.xls', '.xlsx')):
            table_path = os.path.join(root_dir, filename)
            break

    if not table_path:
        print(f"目录中没有找到表格文件: {root_dir}")
        return

    try:
        # 根据文件扩展名选择合适的引擎
        if table_path.endswith('.xls'):
            df = pd.read_excel(table_path, dtype=str, engine='xlrd')
        else:
            df = pd.read_excel(table_path, dtype=str, engine='openpyxl')
        df['标题'] = df['标题'].astype(str).str.strip()
        df['公布日期'] = df['公布日期'].astype(str).str.strip()
        df['标题_清理'] = df['标题'].apply(clean_title)
        df['标题_截断'] = df['标题'].apply(lambda x: clean_title(x)[:20])
    except Exception as e:
        print(f"读取表格失败: {e}")
        return

    # 创建processed文件夹存放生成的文件
    processed_dir = os.path.join(root_dir, 'processed')
    os.makedirs(processed_dir, exist_ok=True)

    # 遍历目录中的文档文件
    for filename in os.listdir(root_dir):
        file_path = os.path.join(root_dir, filename)
        if not os.path.isfile(file_path):
            continue

        file_ext = os.path.splitext(filename)[1].lower()
        if file_ext not in ['.doc', '.docx', '.txt']:
            continue

        # 清理文件名
        cleaned_filename = clean_filename(filename)
        initial_truncated_filename = cleaned_filename[:20]

        # 尝试匹配
        matched_exact = df[df['标题_清理'] == cleaned_filename]
        if not matched_exact.empty:
            seq = matched_exact.iloc[0]['序号']
            agency = matched_exact.iloc[0]['制定机关']
            year = matched_exact.iloc[0]['公布日期'].split('.')[0]
            print(f"精确匹配成功: {filename} -> {seq}_{agency}_{year}")
        else:
            matched_truncated = df[df['标题_截断'] == initial_truncated_filename]
            if not matched_truncated.empty:
                seq = matched_truncated.iloc[0]['序号']
                agency = matched_truncated.iloc[0]['制定机关']
                year = matched_truncated.iloc[0]['公布日期'].split('.')[0]
                print(f"截断匹配成功: {filename} -> {seq}_{agency}_{year}")
            else:
                matched_incremental = incremental_match(df, cleaned_filename)
                if matched_incremental is not None and not matched_incremental.empty:
                    seq = matched_incremental.iloc[0]['序号']
                    agency = matched_incremental.iloc[0]['制定机关']
                    year = matched_incremental.iloc[0]['公布日期'].split('.')[0]
                    print(f"逐步匹配成功: {filename} -> {seq}_{agency}_{year}")
                else:
                    max_ratio = 0
                    matched_fuzzy = None
                    for _, row in df.iterrows():
                        title = row['标题_清理']
                        current_ratio = similarity(cleaned_filename, title)
                        if current_ratio > max_ratio:
                            max_ratio = current_ratio
                            matched_fuzzy = row

                    if matched_fuzzy is not None and max_ratio > 0.6:
                        seq = matched_fuzzy['序号']
                        agency = matched_fuzzy['制定机关']
                        year = matched_fuzzy['公布日期'].split('.')[0]
                        print(f"模糊匹配成功: {filename} (相似度: {max_ratio:.2f}) -> {seq}_{agency}_{year}")
                    else:
                        extracted_title = None
                        if file_ext == '.docx':
                            extracted_title = extract_title_from_docx(file_path)
                        elif file_ext == '.txt':
                            extracted_title = extract_title_from_txt(file_path)

                        if extracted_title:
                            matched_content = df[df['标题_清理'] == extracted_title]
                            if not matched_content.empty:
                                seq = matched_content.iloc[0]['序号']
                                agency = matched_content.iloc[0]['制定机关']
                                year = matched_content.iloc[0]['公布日期'].split('.')[0]
                                print(f"从内容匹配成功: {filename} -> {seq}_{agency}_{year}")
                            else:
                                print(f"⚠️ 提取标题但未匹配到: {filename}, 提取的标题: {extracted_title}")
                                continue
                        else:
                            print(f"⚠️ 未匹配到: {filename}")
                            continue

        # 生成新文件名
        new_name = f"{seq}_{agency}_{year}{file_ext}"
        output_path = os.path.join(processed_dir, new_name)

        # 复制文件到processed文件夹
        try:
            shutil.copy(file_path, output_path)
            print(f"文件已复制: {output_path}")
        except Exception as e:
            print(f"复制