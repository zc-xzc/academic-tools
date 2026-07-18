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

    # 使用文件名（去除后缀）作为关键词
    keyword = os.path.splitext(filename)[0]  # 提取文件名（无后缀）
    matched = None
    max_ratio = 0

    # 模糊匹配文件名和标题
    for _, row in df.iterrows():
        title = row['标题']
        # 计算相似度（简单的包含关系，可以根据需要调整匹配逻辑）
        if keyword in title or title in keyword:
            matched = row
            break

    if matched is None:
        print(f"⚠️ 未匹配到：{filename}")
        continue

    seq = matched['序号']
    print(f"✅ 匹配成功：{filename} -> 序号：{seq}")

    # 生成新文件名
    new_name = f"【{seq}】{filename}"
    output_path = os.path.join(OUTPUT_DIR, new_name)

    # 重命名文件
    try:
        os.rename(file_path, output_path)
        print(f"文件已重命名：{output_path}")
    except Exception as e:
        print(f"重命名文件失败：{filename} -> {e}")

print("所有文件处理完成！")