import os
import pandas as pd

# 配置路径
EXCEL_PATH = r'D:\Desktop\合工大项目\A001_2509-2605全年重点项目环境规制\C004_政策索引\北大法宝\A001_环境规制\分类：效力位阶 - 副本\001法律64篇\【北大法宝】目录列表.xls'
WORD_DIR = r'D:\Desktop\合工大项目\A001_2509-2605全年重点项目环境规制\C004_政策索引\北大法宝\A001_环境规制\分类：效力位阶 - 副本\001法律64篇\word'
OUTPUT_DIR = r'D:\Desktop\合工大项目\A001_2509-2605全年重点项目环境规制\C004_政策索引\北大法宝\A001_环境规制\分类：效力位阶 - 副本\001法律64篇\word1'

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

# 遍历 Word 文件
for filename in os.listdir(WORD_DIR):
    if not filename.endswith('.doc'):  # 只处理 .doc 文件
        print(f"跳过非 .doc 文件：{filename}")
        continue

    file_path = os.path.join(WORD_DIR, filename)

    # 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"文件不存在：{file_path}")
        continue

    # 去除文件名中最后一个括号及其内容
    last_open_bracket = filename.rfind('(')
    if last_open_bracket != -1:
        processed_filename = filename[:last_open_bracket].strip()
    else:
        processed_filename = filename

    # 去除文件名中的省略号（如果存在）
    processed_filename = processed_filename.replace('...', '').strip()

    # 尝试精确匹配
    matched_exact = df[df['标题'] == processed_filename]

    if not matched_exact.empty:
        seq = matched_exact.iloc[0]['序号']
        agency = matched_exact.iloc[0]['制定机关']
        year = matched_exact.iloc[0]['公布日期'].split('.')[0]  # 提取年份
        print(f"✅ 精确匹配成功：{filename} -> 序号：{seq}, 制定机关：{agency}, 年份：{year}")
    else:
        # 尝试模糊匹配
        max_ratio = 0
        matched_fuzzy = None
        for _, row in df.iterrows():
            title = row['标题']
            if processed_filename in title or title in processed_filename:
                matched_fuzzy = row
                break

        if matched_fuzzy is not None:
            seq = matched_fuzzy['序号']
            agency = matched_fuzzy['制定机关']
            year = matched_fuzzy['公布日期'].split('.')[0]  # 提取年份
            print(f"✅ 模糊匹配成功：{filename} -> 序号：{seq}, 制定机关：{agency}, 年份：{year}")
        else:
            print(f"⚠️ 未匹配到：{filename}")
            continue

    # 生成新文件名
    new_name = f"{seq}_{agency}_{year}.doc"
    output_path = os.path.join(OUTPUT_DIR, new_name)

    # 重命名文件
    try:
        os.rename(file_path, output_path)
        print(f"文件已重命名：{output_path}")
    except Exception as e:
        print(f"重命名文件失败：{filename} -> {e}")

print("所有文件处理完成！")