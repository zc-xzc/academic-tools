import os
import pandas as pd
from difflib import SequenceMatcher
import re
from docx import Document
import pyttsx3
import time
import random

def speak(text):
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()

# 配置路径
EXCEL_PATH = r'D:\工作簿1.xls'
INPUT_DIR = r'D:\分类：效力位阶\002行政法规177=37+140篇\行政法规\txt'
OUTPUT_DIR = r'D:\txt1'

# 创建输出目录
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 读取 Excel 文件
try:
    df = pd.read_excel(EXCEL_PATH, dtype=str, engine='xlrd')
    df['标题'] = df['标题'].astype(str).str.strip()
    df['公布日期'] = df['公布日期'].astype(str).str.strip()
    print("Excel 文件读取成功!")
except Exception as e:
    print(f"读取 Excel 文件失败: {e}")
    exit()

# 辅助函数：清理文件名中的特殊符号
def clean_filename(filename):
    filename = re.sub(r'\.\.\.$', '', filename).strip()  # 去除结尾的 ...
    filename = re.sub(r'\(.*?\)', '', filename).strip()  # 去除括号及内容
    filename = re.sub(r'[+*%￥#@!~`^&()_=\[\]{};:,.<>?/\\|]', ' ', filename)
    filename = ' '.join(filename.split()).strip()
    return filename

# 辅助函数：清理标题中的特殊符号
def clean_title(title):
    title = re.sub(r'[+*%￥#@!~`^&()_=\[\]{};:,.<>?/\\|]', ' ', title)
    title = ' '.join(title.split()).strip()
    return title

# 辅助函数：计算两个字符串的相似度
def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

# 辅助函数：逐步增加截取长度进行匹配
def incremental_match(df, cleaned_filename, max_initial_length=20, max_incremental_length=100):
    matched = None
    current_length = max_initial_length
    while current_length <= max_incremental_length:
        truncated_filename = cleaned_filename[:current_length]
        matched = df[df['标题_截断'] == truncated_filename]
        if not matched.empty:
            return matched
        current_length += 5  # 每次增加5个字符继续匹配
    return matched

# 辅助函数：从 DOCX 文件中提取标题
def extract_title_from_docx(file_path):
    try:
        doc = Document(file_path)
        for para in doc.paragraphs[:5]:
            if para.text.strip():
                return clean_title(para.text.strip())
        return None
    except Exception as e:
        print(f"提取 DOCX 标题失败: {e}")
        return None

# 辅助函数：从 TXT 文件中提取标题
def extract_title_from_txt(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read(200)  # 读取前200个字符
            lines = content.split('\n')
            for line in lines:
                cleaned_line = clean_title(line.strip())
                if cleaned_line:
                    return cleaned_line
        return None
    except Exception as e:
        print(f"提取 TXT 标题失败: {e}")
        return None

# 辅助函数：截取文件名以避免路径过长
def truncate_new_filename(new_name, max_length=150):
    base_name, ext = os.path.splitext(new_name)
    if len(new_name) > max_length:
        return base_name[:max_length - len(ext)] + ext
    return new_name

# 辅助函数：生成唯一标识符
def generate_unique_id(length=6):
    return ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=length))

# 预处理表格标题
df['标题_清理'] = df['标题'].apply(clean_title)
df['标题_截断'] = df['标题'].apply(lambda x: clean_title(x)[:20])

# 遍历输入目录中的所有文件
for filename in os.listdir(INPUT_DIR):
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in ['.doc', '.docx', '.txt']:
        print(f"跳过非目标文件：{filename}")
        continue

    file_path = os.path.join(INPUT_DIR, filename)

    if not os.path.exists(file_path):
        print(f"文件不存在：{file_path}")
        continue

    cleaned_filename = clean_filename(filename)
    initial_truncated_filename = cleaned_filename[:20]

    matched_exact = df[df['标题_清理'] == cleaned_filename]
    if not matched_exact.empty:
        seq = matched_exact.iloc[0]['序号']
        agency = matched_exact.iloc[0]['制定机关']
        year = matched_exact.iloc[0]['公布日期'].split('.')[0]
        print(f"精确匹配成功：{filename} -> 序号：{seq}, 制定机关：{agency}, 年份：{year}")
    else:
        matched_truncated = df[df['标题_截断'] == initial_truncated_filename]
        if not matched_truncated.empty:
            seq = matched_truncated.iloc[0]['序号']
            agency = matched_truncated.iloc[0]['制定机关']
            year = matched_truncated.iloc[0]['公布日期'].split('.')[0]
            print(f"截断匹配成功：{filename} -> 序号：{seq}, 制定机关：{agency}, 年份：{year}")
        else:
            matched_incremental = incremental_match(df, cleaned_filename)
            if matched_incremental is not None and not matched_incremental.empty:
                seq = matched_incremental.iloc[0]['序号']
                agency = matched_incremental.iloc[0]['制定机关']
                year = matched_incremental.iloc[0]['公布日期'].split('.')[0]
                print(f"逐步匹配成功：{filename} -> 序号：{seq}, 制定机关：{agency}, 年份：{year}")
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
                    print(f"模糊匹配成功：{filename} (相似度: {max_ratio:.2f}) -> 序号：{seq}, 制定机关：{agency}, 年份：{year}")
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
                            print(f"从文档内容匹配成功：{filename} -> 序号：{seq}, 制定机关：{agency}, 年份：{year}")
                        else:
                            print(f"⚠️ 从文档内容提取标题但未匹配到：{filename}，提取的标题：{extracted_title}")
                            speak(f"从文档内容提取标题但未匹配到：{filename}，提取的标题：{extracted_title}")
                            continue
                    else:
                        print(f"⚠️ 未匹配到：{filename}")
                        speak(f"未匹配到：{filename}")
                        continue

    # 生成新文件名，保留原始文件名和扩展名
    new_name = f"{seq}_{agency}_{year}_{filename}"
    new_name = truncate_new_filename(new_name)  # 截断新文件名以避免路径过长

    # 添加唯一标识符避免文件名冲突
    if os.path.exists(os.path.join(OUTPUT_DIR, new_name)):
        unique_id = generate_unique_id()
        base_name, ext = os.path.splitext(new_name)
        new_name = f"{base_name}_{unique_id}{ext}"

    output_path = os.path.join(OUTPUT_DIR, new_name)

    try:
        os.rename(file_path, output_path)
        print(f"文件已重命名：{output_path}")
    except Exception as e:
        print(f"重命名文件失败：{filename} -> {e}")
        speak(f"重命名文件失败：{filename} -> {e}")

print("所有文件处理完成！")