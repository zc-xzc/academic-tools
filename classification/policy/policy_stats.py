# ====================== 1. 环境准备与配置 ======================
import os
import re
import warnings
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from collections import Counter

# 忽略无关警告
warnings.filterwarnings('ignore')
# 设置中文字体（解决图表中文乱码）
plt.rcParams['font.sans-serif'] = ['SimHei']  # 黑体
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
# 设置图表样式
plt.style.use('ggplot')
plt.rcParams['figure.figsize'] = (12, 8)

# ====================== 2. 核心参数配置（请根据你的实际路径修改） ======================
MAIN_FOLDER = r"D:\Hefei_University_of_Technology_Work\A001_2509-2605全年重点项目环境规制\C100_政策索引\中国环境报文本数据（2013.08-2024.11）"  # 替换为你的主文件夹路径（如：D:/政策文本）
REPORT_SAVE_PATH = "政策文本描述性统计分析报告.md"  # 报告保存路径

# 定义关键分类词典（可根据你的政策文本内容调整/补充）
## 2.1 规制工具类型（通用分类，可自定义）
REGULATORY_TOOLS = {
    "命令控制型": ["禁止", "责令", "限期", "处罚", "审批", "许可", "标准", "强制"],
    "经济激励型": ["补贴", "税收", "收费", "基金", "价格", "信贷", "奖励"],
    "自愿型": ["倡议", "公示", "承诺", "自愿", "协商", "引导"]
}
## 2.2 环境要素（通用分类，可自定义）
ENVIRONMENT_FACTORS = {
    "大气环境": ["大气", "雾霾", "PM2.5", "扬尘", "废气", "二氧化硫"],
    "水环境": ["水", "河流", "湖泊", "污水", "废水", "饮用水", "地下水"],
    "土壤环境": ["土壤", "耕地", "重金属", "农用地", "建设用地"],
    "固废/危废": ["固废", "垃圾", "危险废物", "废弃物", "渣土"],
    "生态保护": ["生态", "森林", "湿地", "生物多样性", "自然保护区"]
}
## 2.3 城市群映射（可根据你的文本补充）
URBAN_AGGLOMERATIONS = {
    "京津冀": ["北京", "天津", "河北"],
    "长三角": ["上海", "江苏", "浙江", "安徽"],
    "珠三角": ["广东（珠三角）", "广州", "深圳", "佛山", "东莞"],
    "成渝": ["重庆", "四川"],
    "长江中游": ["湖北", "湖南", "江西"]
}


# ====================== 3. 文本数据读取与基础信息提取 ======================
def extract_basic_info(file_path, file_name):
    """
    从单个政策文本中提取基础信息：年份、月份、区域、规制工具、环境要素
    """
    # 3.1 从文件名提取时间（如20130830.txt → 2013年8月）
    time_pattern = re.compile(r"(\d{4})(\d{2})(\d{2})")
    time_match = time_pattern.search(file_name)
    year, month = None, None
    if time_match:
        year = int(time_match.group(1))
        month = int(time_match.group(2))

    # 3.2 读取文本内容（编码适配常见格式：utf-8/gbk）
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except:
        with open(file_path, 'r', encoding='gbk') as f:
            content = f.read()
    content = content.lower()  # 统一小写，避免大小写匹配问题

    # 3.3 提取区域（优先匹配文本中出现的省级行政区，可扩展地级市）
    provinces = [
        "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
        "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
        "湖北", "湖南", "广东", "广西", "海南", "重庆", "四川", "贵州",
        "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆"
    ]
    province = None
    for p in provinces:
        if p in content:
            province = p
            break  # 取第一个匹配的省级行政区（可根据需求调整为多区域）

    # 3.4 提取规制工具类型（匹配关键词，取出现频次最高的类型）
    tool_type = None
    tool_count = {}
    for tool, keywords in REGULATORY_TOOLS.items():
        count = sum([content.count(key) for key in keywords])
        tool_count[tool] = count
    if tool_count:
        tool_type = max(tool_count, key=tool_count.get)

    # 3.5 提取环境要素（匹配关键词，取出现频次最高的类型）
    env_factor = None
    env_count = {}
    for factor, keywords in ENVIRONMENT_FACTORS.items():
        count = sum([content.count(key) for key in keywords])
        env_count[factor] = count
    if env_count:
        env_factor = max(env_count, key=env_count.get)

    # 3.6 匹配城市群
    urban_agglomeration = None
    if province:
        for agg, provs in URBAN_AGGLOMERATIONS.items():
            if province in provs:
                urban_agglomeration = agg
                break

    return {
        "文件名": file_name,
        "文件路径": file_path,
        "年份": year,
        "月份": month,
        "省级区域": province,
        "城市群": urban_agglomeration,
        "规制工具类型": tool_type,
        "环境要素": env_factor
    }


# 遍历所有子文件夹，读取所有txt文件并提取信息
def read_all_policy_files(main_folder):
    """遍历主文件夹下所有子文件夹，读取txt政策文件"""
    policy_data = []
    # 遍历主文件夹→子文件夹→文件
    for root, dirs, files in os.walk(main_folder):
        for file in files:
            if file.endswith(".txt"):  # 仅处理txt文件
                file_path = os.path.join(root, file)
                try:
                    info = extract_basic_info(file_path, file)
                    policy_data.append(info)
                    print(f"成功读取：{file_path}")
                except Exception as e:
                    print(f"读取失败：{file_path}，错误：{str(e)}")
    # 转换为DataFrame，方便后续分析
    df = pd.DataFrame(policy_data)
    # 处理缺失值（填充为"未知"）
    df = df.fillna("未知")
    return df


# 执行数据读取
print("开始读取政策文本文件...")
df_policy = read_all_policy_files(MAIN_FOLDER)
print(f"文件读取完成！共读取 {len(df_policy)} 份政策文本")


# ====================== 4. 描述性统计分析（文字+图表） ======================
def generate_analysis_report(df):
    """生成完整的描述性统计分析报告（文字+图表）"""
    report_content = []
    report_content.append("# 政策文本描述性统计分析报告\n")

    # 4.1 时间分布分析
    report_content.append("## 一、政策文本时间分布分析\n")
    # 统计各年数量
    year_counts = df[df["年份"] != "未知"]["年份"].value_counts().sort_index()
    # 文字概述
    if len(year_counts) > 0:
        max_year = year_counts.idxmax()
        min_year = year_counts.idxmin()
        total_years = len(year_counts)
        year_desc = f"""
本次分析的政策文本时间跨度为{min_year}-{max_year}年（共{total_years}年），各年份政策文本数量分布如下：
- 数量最多的年份为{max_year}年，共{year_counts[max_year]}份；
- 数量最少的年份为{min_year}年，共{year_counts[min_year]}份；
- 整体来看，{'政策文本数量呈逐年上升趋势' if year_counts.iloc[-1] > year_counts.iloc[0] else '政策文本数量呈波动变化趋势'}。
        """
    else:
        year_desc = "未提取到有效年份信息，无法分析时间分布。"
    report_content.append(year_desc)

    # 绘制时间分布柱状图
    if len(year_counts) > 0:
        plt.figure()
        year_counts.plot(kind="bar", color="#1f77b4", alpha=0.8)
        plt.title("政策文本各年份数量分布", fontsize=14)
        plt.xlabel("年份", fontsize=12)
        plt.ylabel("文本数量", fontsize=12)
        plt.xticks(rotation=45)
        plt.tight_layout()
        time_fig_path = "时间分布.png"
        plt.savefig(time_fig_path, dpi=300)
        report_content.append(f"\n![政策文本各年份数量分布]({time_fig_path})\n")

    # 4.2 区域分布分析
    report_content.append("## 二、政策文本区域分布分析\n")
    # 1) 省级分布
    province_counts = df[df["省级区域"] != "未知"]["省级区域"].value_counts().head(10)
    # 2) 城市群分布
    agg_counts = df[df["城市群"] != "未知"]["城市群"].value_counts()

    # 文字概述
    province_desc = ""
    if len(province_counts) > 0:
        top_province = province_counts.index[0]
        province_desc = f"""
### （1）省级区域分布
本次分析的政策文本覆盖{len(df[df['省级区域'] != '未知']['省级区域'].unique())}个省级行政区，数量排名前10的省份如下：
- 数量最多的省份为{top_province}，共{province_counts[top_province]}份；
- 前10省份合计占全部有效区域文本的{round(province_counts.sum() / len(df[df['省级区域'] != '未知']) * 100, 2)}%，反映出政策文本在区域分布上的不均衡性。

### （2）城市群分布
本次分析的政策文本涉及{len(agg_counts)}个城市群，具体分布：
"""
        for agg, count in agg_counts.items():
            province_desc += f"- {agg}城市群：{count}份（占比{round(count / len(df[df['城市群'] != '未知']) * 100, 2)}%）；\n"
    else:
        province_desc = "未提取到有效省级区域信息，无法分析区域分布。"
    report_content.append(province_desc)

    # 绘制区域分布图表
    if len(province_counts) > 0:
        # 省级前10柱状图
        plt.figure()
        province_counts.plot(kind="bar", color="#ff7f0e", alpha=0.8)
        plt.title("政策文本省级区域分布（前10）", fontsize=14)
        plt.xlabel("省份", fontsize=12)
        plt.ylabel("文本数量", fontsize=12)
        plt.xticks(rotation=45)
        plt.tight_layout()
        province_fig_path = "省级区域分布.png"
        plt.savefig(province_fig_path, dpi=300)
        report_content.append(f"\n![政策文本省级区域分布（前10）]({province_fig_path})\n")

        # 城市群饼图
        if len(agg_counts) > 0:
            plt.figure()
            plt.pie(agg_counts.values, labels=agg_counts.index, autopct='%1.1f%%', startangle=90)
            plt.title("政策文本城市群分布", fontsize=14)
            plt.tight_layout()
            agg_fig_path = "城市群分布.png"
            plt.savefig(agg_fig_path, dpi=300)
            report_content.append(f"\n![政策文本城市群分布]({agg_fig_path})\n")

    # 4.3 时空分布分析
    report_content.append("## 三、政策文本时空分布分析\n")
    # 筛选有效年份和区域的数据
    df_time_space = df[(df["年份"] != "未知") & (df["省级区域"] != "未知")]
    if len(df_time_space) > 0:
        # 构建年度-区域交叉表
        cross_table = pd.crosstab(df_time_space["年份"], df_time_space["省级区域"])
        # 文字概述
        time_space_desc = f"""
本次分析共筛选出{len(df_time_space)}份含有效年份和区域的政策文本，时空分布特征如下：
- 核心热点区域：{cross_table.sum(axis=0).idxmax()}在各年份均有较多政策文本分布（累计{cross_table.sum(axis=0).max()}份）；
- 核心热点年份：{cross_table.sum(axis=1).idxmax()}年政策文本覆盖{cross_table.loc[cross_table.sum(axis=1).idxmax()].count()}个省级行政区，覆盖范围最广；
- 整体特征：政策文本的区域覆盖度随年份{'上升' if cross_table.count(axis=1).iloc[-1] > cross_table.count(axis=1).iloc[0] else '下降'}，反映政策聚焦范围的{'扩大' if cross_table.count(axis=1).iloc[-1] > cross_table.count(axis=1).iloc[0] else '收缩'}。
        """
        report_content.append(time_space_desc)

        # 绘制时空分布热力图
        plt.figure(figsize=(15, 10))
        # 只显示前15个省份（避免图表过密）
        top_provinces = cross_table.sum(axis=0).nlargest(15).index
        cross_table_top = cross_table[top_provinces]
        plt.imshow(cross_table_top, cmap="YlOrRd", aspect="auto")
        plt.colorbar(label="文本数量")
        plt.title("政策文本时空分布热力图（年份×省级区域）", fontsize=14)
        plt.xlabel("省级区域", fontsize=12)
        plt.ylabel("年份", fontsize=12)
        plt.xticks(range(len(cross_table_top.columns)), cross_table_top.columns, rotation=45)
        plt.yticks(range(len(cross_table_top.index)), cross_table_top.index)
        plt.tight_layout()
        time_space_fig_path = "时空分布热力图.png"
        plt.savefig(time_space_fig_path, dpi=300)
        report_content.append(f"\n![政策文本时空分布热力图]({time_space_fig_path})\n")
    else:
        report_content.append("未提取到有效年份和区域的组合信息，无法分析时空分布。\n")

    # 4.4 规制工具类型分布分析
    report_content.append("## 四、政策文本规制工具类型分布分析\n")
    tool_counts = df[df["规制工具类型"] != "未知"]["规制工具类型"].value_counts()
    # 文字概述
    if len(tool_counts) > 0:
        tool_desc = f"""
本次分析共识别出{len(tool_counts)}类规制工具类型，分布特征如下：
- 主导规制工具：{tool_counts.index[0]}占比最高（{round(tool_counts.iloc[0] / tool_counts.sum() * 100, 2)}%，共{tool_counts.iloc[0]}份），反映当前政策以{'行政命令为主' if tool_counts.index[0] == '命令控制型' else '经济激励为主' if tool_counts.index[0] == '经济激励型' else '自愿引导为主'}；
- 次要规制工具：{tool_counts.index[1]}占{round(tool_counts.iloc[1] / tool_counts.sum() * 100, 2)}%，{tool_counts.index[2]}占{round(tool_counts.iloc[2] / tool_counts.sum() * 100, 2)}%，工具类型分布{'相对均衡' if max(tool_counts) / min(tool_counts) < 2 else '高度集中'}。
        """
        report_content.append(tool_desc)

        # 绘制规制工具饼图
        plt.figure()
        plt.pie(tool_counts.values, labels=tool_counts.index, autopct='%1.1f%%', startangle=90,
                colors=["#2ca02c", "#d62728", "#9467bd"])
        plt.title("政策文本规制工具类型分布", fontsize=14)
        plt.tight_layout()
        tool_fig_path = "规制工具类型分布.png"
        plt.savefig(tool_fig_path, dpi=300)
        report_content.append(f"\n![政策文本规制工具类型分布]({tool_fig_path})\n")
    else:
        report_content.append("未提取到有效规制工具类型信息，无法分析。\n")

    # 4.5 环境要素分布分析
    report_content.append("## 五、政策文本环境要素分布分析\n")
    env_counts = df[df["环境要素"] != "未知"]["环境要素"].value_counts()
    # 文字概述
    if len(env_counts) > 0:
        env_desc = f"""
本次分析共识别出{len(env_counts)}类环境要素，分布特征如下：
- 核心关注要素：{env_counts.index[0]}占比最高（{round(env_counts.iloc[0] / env_counts.sum() * 100, 2)}%，共{env_counts.iloc[0]}份），反映政策聚焦于{env_counts.index[0]}相关治理；
- 要素覆盖度：前3类环境要素（{env_counts.index[0]}、{env_counts.index[1]}、{env_counts.index[2]}）合计占{round(env_counts.iloc[:3].sum() / env_counts.sum() * 100, 2)}%，政策关注要素{'相对集中' if env_counts.iloc[:3].sum() / env_counts.sum() > 0.8 else '较为分散'}。
        """
        report_content.append(env_desc)

        # 绘制环境要素柱状图
        plt.figure()
        env_counts.plot(kind="bar", color="#8c564b", alpha=0.8)
        plt.title("政策文本环境要素分布", fontsize=14)
        plt.xlabel("环境要素类型", fontsize=12)
        plt.ylabel("文本数量", fontsize=12)
        plt.xticks(rotation=45)
        plt.tight_layout()
        env_fig_path = "环境要素分布.png"
        plt.savefig(env_fig_path, dpi=300)
        report_content.append(f"\n![政策文本环境要素分布]({env_fig_path})\n")
    else:
        report_content.append("未提取到有效环境要素信息，无法分析。\n")

    # 4.6 整体总结
    report_content.append("## 六、整体总结\n")
    total_texts = len(df)
    valid_year = len(df[df["年份"] != "未知"])
    valid_region = len(df[df["省级区域"] != "未知"])
    valid_tool = len(df[df["规制工具类型"] != "未知"])
    valid_env = len(df[df["环境要素"] != "未知"])

    summary = f"""
本次共分析{total_texts}份政策文本，核心结论如下：
1. 时间特征：{valid_year}份文本含有效年份信息，时间跨度为{df[df['年份'] != '未知']['年份'].min() if valid_year > 0 else '无'}-{df[df['年份'] != '未知']['年份'].max() if valid_year > 0 else '无'}年，{'政策数量呈逐年上升趋势' if valid_year > 0 and df[df['年份'] != '未知']['年份'].value_counts().sort_index().iloc[-1] > df[df['年份'] != '未知']['年份'].value_counts().sort_index().iloc[0] else '政策数量无明显时间趋势'}；
2. 区域特征：{valid_region}份文本含有效区域信息，主要集中在{df[df['省级区域'] != '未知']['省级区域'].value_counts().index[0] if valid_region > 0 else '无'}等省份/{df[df['城市群'] != '未知']['城市群'].value_counts().index[0] if len(df[df['城市群'] != '未知']) > 0 else '无'}城市群；
3. 工具特征：{valid_tool}份文本可识别规制工具类型，以{df[df['规制工具类型'] != '未知']['规制工具类型'].value_counts().index[0] if valid_tool > 0 else '无'}为主导；
4. 要素特征：{valid_env}份文本可识别环境要素，聚焦于{df[df['环境要素'] != '未知']['环境要素'].value_counts().index[0] if valid_env > 0 else '无'}治理。
    """
    report_content.append(summary)

    # 将报告内容写入文件
    with open(REPORT_SAVE_PATH, 'w', encoding='utf-8') as f:
        f.write("\n".join(report_content))
    print(f"分析报告已生成！保存路径：{os.path.abspath(REPORT_SAVE_PATH)}")


# 执行报告生成
generate_analysis_report(df_policy)