import os
import pandas as pd
from difflib import SequenceMatcher
import re
from docx import Document
import shutil

def clean_filename(filename):
    filename = re.sub(r'\.\.\.$', '', filename).strip()
    filename = re.sub(r'\(.*?\)', '', filename).strip()
    filename = re.sub(r'[+*%￥#@!~`^&()_=\[\]{};:,.<>?/\\|]', ' ', filename)
    filename = ' '.join(filename.split()).strip()
    return filename

def clean_title(title):
    title = re.sub(r'[+*%￥#@!~`^&()_=\[\]{};:,.<>?/\\|]', ' ', title)
    title = ' '.join(title.split()).strip()
    return title

def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

def incremental_match(df, cleaned_filename, max_initial_length=20, max_incremental_length=100):
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
    try:
        doc = Document(file_path)
        for para in doc.paragraphs[:5]:
            if para.text.strip():
                return clean_title(para.text.strip())
        return None
    except:
        return None

def extract_title_from_txt(file_path):
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

def process_directory(directory):
    # 查找目录中的表格文件
    table_path = None
    for filename in os.listdir(directory):
        if filename.endswith(('.xls', '.xlsx')):
            table_path = os.path.join(directory, filename)
            break

    if not table_path:
        print(f"目录没有表格文件，跳过: {directory}")
        return

    try:
        df = pd.read_excel(table_path, dtype=str, engine='xlrd')
        df['标题'] = df['标题'].astype(str).str.strip()
        df['公布日期'] = df['公布日期'].astype(str).str.strip()
        df['标题_清理'] = df['标题'].apply(clean_title)
        df['标题_截断'] = df['标题'].apply(lambda x: clean_title(x)[:20])
    except Exception as e:
        print(f"读取表格失败: {e}")
        return

    processed_dir = os.path.join(directory, 'processed')
    os.makedirs(processed_dir, exist_ok=True)

    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if not os.path.isfile(file_path):
            continue

        file_ext = os.path.splitext(filename)[1].lower()
        if file_ext not in ['.doc', '.docx', '.txt']:
            continue

        cleaned_filename = clean_filename(filename)
        initial_truncated_filename = cleaned_filename[:20]

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

        new_name = f"{seq}_{agency}_{year}_{filename}"
        output_path = os.path.join(processed_dir, new_name)

        try:
            shutil.move(file_path, output_path)
            print(f"文件已移动: {output_path}")
        except Exception as e:
            print(f"移动文件失败: {e}")

def find_valid_directories(root_dir):
    valid_dirs = []
    for dirpath, _, filenames in os.walk(root_dir):
        has_table = any(f.endswith(('.xls', '.xlsx')) for f in filenames)
        has_docs = any(f.endswith(('.doc', '.docx', '.txt')) for f in filenames)
        if has_table and has_docs:
            valid_dirs.append(dirpath)
    return valid_dirs

if __name__ == "__main__":
    root_dir = r"D:\Desktop\合工大项目\A001_2509-2605全年重点项目环境规制\C004_政策索引\北大法宝\A001_环境规制\分类：效力位阶 - 副本"  # 在这里输入您的根目录路径
    valid_dirs = find_valid_directories(root_dir)

    if not valid_dirs:
        print("未找到符合条件的目录")
    else:
        print(f"找到以下目录需要处理:")
        for d in valid_dirs:
            print(f"  - {d}")
            process_directory(d)

    print("\n所有处理完成！")