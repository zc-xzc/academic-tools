import os
import pandas as pd
from difflib import SequenceMatcher
import re


# 配置路径
EXCEL_PATH = r'D:\Desktop\合工大项目\A001_2509-2605全年重点项目环境规制\C004_政策索引\北大法宝\A001_环境规制\分类：效力位阶 - 副本\004部门规章(12976)\D2部门规范性文件(3445)\【北大法宝】目录列表.xls'
WORD_DIR = r'D:\Desktop\合工大项目\A001_2509-2605全年重点项目环境规制\C004_政策索引\北大法宝\A001_环境规制\分类：效力位阶 - 副本\004部门规章(12976)\D2部门规范性文件(3445)\doc'
OUTPUT_DIR = r'D:\Desktop\合工大项目\A001_2509-2605全年重点项目环境规制\C004_政策索引\北大法宝\A001_环境规制\分类：效力位阶 - 副本\004部门规章(12976)\D2部门规范性文件(3445)\doc1'

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

# 辅助函数：处理全角和半角字符
def normalize_text(text):
    # 全角转半角
    text = text.translate(str.maketrans({chr(0xFF01 + i): chr(0x21 + i) for i in range(94)}))
    return text

# 辅助函数：清理文件名中的特殊符号
def clean_filename(filename):
    # 去除文件名中的省略号和括号内容
    filename = re.sub(r'\.\.\.$', '', filename).strip()  # 去除结尾的 ...
    filename = re.sub(r'\(.*?\)', '', filename).strip()  # 去除括号及内容
    # 替换特殊符号为空格
    filename = re.sub(r'[+*%￥#@!~`^&()_=\[\]{};:,.<>?/\\|]', ' ', filename)
    # 去除多余的空格
    filename = ' '.join(filename.split()).strip()
    # 处理全角和半角字符
    filename = normalize_text(filename)
    return filename

# 辅助函数：清理标题中的特殊符号
def clean_title(title):
    # 替换特殊符号为下划线
    title = re.sub(r'[+*%￥#@!~`^&()_=\[\]{};:,.<>?/\\|]', '_', title)
    # 去除多余的下划线
    title = '_'.join(title.split('_')).strip()
    # 处理全角和半角字符
    title = normalize_text(title)
    return title

# 辅助函数：计算两个字符串的相似度
def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

# 辅助函数：截取文件名的前 50 个字符（处理 Word 截断问题）
def truncate_filename(filename, max_length=50):
    if len(filename) > max_length:
        return filename[:max_length]
    return filename

# 预处理表格标题
df['标题_清理'] = df['标题'].apply(clean_title)
df['标题_截断'] = df['标题'].apply(lambda x: truncate_filename(clean_title(x)))

# 遍历 Word 文件
for filename in os.listdir(WORD_DIR):
    if not filename.endswith(('.doc', '.docx')):  # 只处理 .doc 和 .docx 文件
        print(f"跳过非 Word 文件：{filename}")
        continue

    file_path = os.path.join(WORD_DIR, filename)

    # 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"文件不存在：{file_path}")
        continue

    # 清理文件名
    cleaned_filename = clean_filename(filename)
    truncated_filename = truncate_filename(cleaned_filename)

    # 尝试精确匹配
    matched_exact = df[df['标题_清理'] == cleaned_filename]

    if not matched_exact.empty:
        seq = matched_exact.iloc[0]['序号']
        agency = matched_exact.iloc[0]['制定机关']
        year = matched_exact.iloc[0]['公布日期'].split('.')[0]  # 提取年份
        print(f"✅ 精确匹配成功：{filename} -> 序号：{seq}, 制定机关：{agency}, 年份：{year}")
    else:
        # 尝试截断后的精确匹配
        matched_truncated = df[df['标题_截断'] == truncated_filename]

        if not matched_truncated.empty:
            seq = matched_truncated.iloc[0]['序号']
            agency = matched_truncated.iloc[0]['制定机关']
            year = matched_truncated.iloc[0]['公布日期'].split('.')[0]  # 提取年份
            print(f"✅ 截断匹配成功：{filename} -> 序号：{seq}, 制定机关：{agency}, 年份：{year}")
        else:
            # 尝试模糊匹配
            max_ratio = 0
            matched_fuzzy = None
            for _, row in df.iterrows():
                title = row['标题_清理']
                ratio = similarity(cleaned_filename, title)
                if ratio > max_ratio:
                    max_ratio = ratio
                    matched_fuzzy = row

            if matched_fuzzy is not None and max_ratio > 0.6:  # 调整相似度阈值为 0.6
                seq = matched_fuzzy['序号']
                agency = matched_fuzzy['制定机关']
                year = matched_fuzzy['公布日期'].split('.')[0]  # 提取年份
                print(f"✅ 模糊匹配成功：{filename} (相似度: {max_ratio:.2f}) -> 序号：{seq}, 制定机关：{agency}, 年份：{year}")
            else:
                print(f"⚠️ 未匹配到：{filename}")
                continue

    # 生成新文件名，保留原始文件名
    new_name = f"{seq}_{agency}_{year}_{filename}"
    output_path = os.path.join(OUTPUT_DIR, new_name)

    # 重命名文件
    try:
        os.rename(file_path, output_path)
        print(f"文件已重命名：{output_path}")
    except Exception as e:
        print(f"重命名文件失败：{filename} -> {e}")

print("所有文件处理完成！")