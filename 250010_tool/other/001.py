import os
import re
import pandas as pd
from docx import Document
from collections import defaultdict

try:
    import textract  # 处理.doc文件（可选）
except ImportError:
    textract = None


# ------------------------------
# 1. 基础工具函数：文件读取与文本解析（优化提取精度）
# ------------------------------
def read_text_file(file_path):
    """读取文本类文件（TXT/DOCX/DOC）内容"""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == '.txt':
            for encoding in ['utf-8', 'gbk', 'gb2312']:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        return f.read()
                except UnicodeDecodeError:
                    continue
            raise Exception("无法识别编码")

        elif ext == '.docx':
            doc = Document(file_path)
            return '\n'.join([p.text.strip() for p in doc.paragraphs if p.text.strip()])

        elif ext == '.doc':
            if not textract:
                raise ImportError("需安装textract库处理.doc文件（pip install textract）")
            return textract.process(file_path).decode('utf-8', errors='ignore').strip()

        else:
            raise ValueError(f"不支持的文本格式：{ext}")

    except Exception as e:
        print(f"[读取失败] {file_path}：{str(e)}")
        return None


def read_table_file(file_path):
    """读取表格类文件（CSV/Excel）"""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == '.csv':
            return pd.read_csv(file_path, encoding_errors='replace')
        elif ext in ('.xlsx', '.xls'):
            return pd.read_excel(file_path)
        else:
            raise ValueError(f"不支持的表格格式：{ext}")
    except Exception as e:
        print(f"[读取失败] {file_path}：{str(e)}")
        return None


def standardize_region_name(region):
    """标准化地区名称（如“辽宁”→“辽宁省”，“贵州”→“贵州省”）"""
    province_map = {
        '北京': '北京市', '上海': '上海市', '天津': '天津市', '重庆': '重庆市',
        '安徽': '安徽省', '广东': '广东省', '江苏': '江苏省', '浙江': '浙江省',
        '山东': '山东省', '四川': '四川省', '湖北': '湖北省', '湖南': '湖南省',
        '福建': '福建省', '河南': '河南省', '河北': '河北省', '陕西': '陕西省',
        '江西': '江西省', '山西': '山西省', '黑龙江': '黑龙江省', '吉林': '吉林省',
        '辽宁': '辽宁省', '云南': '云南省', '贵州': '贵州省', '甘肃': '甘肃省',
        '青海': '青海省', '海南': '海南省', '广西': '广西壮族自治区', '内蒙古': '内蒙古自治区',
        '宁夏': '宁夏回族自治区', '新疆': '新疆维吾尔自治区', '西藏': '西藏自治区'
    }
    return province_map.get(region, region)  # 非省份名保持原样


def parse_text_to_structured(text, file_name):
    """优化：提升政策、技术投入提取精度，标准化地区名"""
    if not text:
        return pd.DataFrame()

    # 提取地区（匹配省级/市级行政区）
    region_pattern = re.compile(
        r'((?:北京|上海|天津|重庆|安徽|广东|江苏|浙江|山东|四川|湖北|湖南|福建|'
        r'河南|河北|陕西|江西|山西|黑龙江|吉林|辽宁|云南|贵州|甘肃|青海|海南|'
        r'广西|内蒙古|宁夏|新疆|西藏)(?:省|市|自治区)?|'
        r'(?:成都|深圳|广州|杭州|南京|武汉|西安|青岛|厦门|苏州|合肥|郑州|济南)[市]?)'
    )
    regions = list(set(region_pattern.findall(text)))
    regions = [standardize_region_name(r) for r in regions if len(r) >= 2]  # 标准化+过滤

    data = []
    for region in regions:
        # 提取地区相关描述（扩大上下文匹配范围）
        desc_match = re.search(
            fr'{re.escape(region)}[:：]?(.*?)(?={region_pattern.pattern}|$|\\n{3,})',
            text,
            re.DOTALL | re.IGNORECASE
        )
        desc = desc_match.group(1).strip() if desc_match else f"来自{file_name}的描述"

        # 优化1：提取政策（匹配“规划”“政策”“通知”等关键词）
        policy_pattern = re.compile(
            r'(发布|出台|印发).*?(规划|政策|通知|方案|意见)|'
            r'[数字政府|数字化转型].*?(规划|政策|通知)',
            re.DOTALL | re.IGNORECASE
        )
        policy_match = policy_pattern.search(desc)
        policy = policy_match.group(0).strip()[:150] if policy_match else "未明确政策"

        # 优化2：提取技术投入（匹配“投入”“投资”“预算”，支持“亿”“万”单位）
        tech_pattern = re.compile(
            r'(投入|投资|预算).*?(\d+\.?\d*)\s*(亿|万|亿元|万元)',
            re.DOTALL | re.IGNORECASE
        )
        tech_match = tech_pattern.search(desc)
        if tech_match:
            value = float(tech_match.group(2))
            unit = tech_match.group(3)
            # 统一单位为“亿元”（万元→亿元）
            tech_input = value if '亿' in unit else value / 10000
        else:
            tech_input = None

        # 优化3：提取人才政策（匹配“人才”“培养”“引进”）
        talent_pattern = re.compile(
            r'(人才).*?(培养|引进|计划|政策|激励)|'
            r'(培养|引进).*?(数字|政务).*?人才',
            re.DOTALL | re.IGNORECASE
        )
        talent_match = talent_pattern.search(desc)
        talent = talent_match.group(0).strip()[:150] if talent_match else "未明确人才措施"

        # 提取模式做法
        model_pattern = re.compile(
            r'(模式|做法|机制).*?(智慧|数据|一网通办|协同|治理)',
            re.DOTALL | re.IGNORECASE
        )
        model_match = model_pattern.search(desc)
        model = model_match.group(0).strip()[:200] if model_match else desc[:200]

        data.append({
            '地区': region,
            '数字化成果描述': desc[:300],
            '政策支持': policy,
            '技术投入(亿元)': tech_input,
            '人才政策': talent,
            '模式做法': model,
            '来源': file_name
        })

    return pd.DataFrame(data)


# ------------------------------
# 2. 核心功能：批量处理与数据整合（去重优化）
# ------------------------------
def batch_process_directory(dir_path):
    """批量处理目录下所有文件，返回整合后的结构化数据"""
    if not os.path.isdir(dir_path):
        print(f"错误：目录不存在 - {dir_path}")
        return None

    text_exts = ('.txt', '.docx', '.doc')
    table_exts = ('.csv', '.xlsx', '.xls')
    all_data = []

    for root, _, files in os.walk(dir_path):
        for file in files:
            file_path = os.path.join(root, file)
            file_ext = os.path.splitext(file)[1].lower()
            file_name = os.path.basename(file_path)

            if file_ext in text_exts:
                text = read_text_file(file_path)
                if text:
                    df = parse_text_to_structured(text, file_name)
                    if not df.empty:
                        all_data.append(df)

            elif file_ext in table_exts:
                df = read_table_file(file_path)
                if df is not None and not df.empty:
                    required_cols = ['地区', '数字化成果描述', '政策支持', '技术投入(亿元)', '人才政策', '模式做法']
                    for col in required_cols:
                        if col not in df.columns:
                            df[col] = "未提及" if col != '技术投入(亿元)' else None
                    # 表格数据也标准化地区名
                    df['地区'] = df['地区'].apply(
                        lambda x: standardize_region_name(str(x).strip()) if pd.notna(x) else x)
                    df['来源'] = file_name
                    all_data.append(df[required_cols + ['来源']])

    if not all_data:
        print("未获取到有效数据，请检查文件内容")
        return None
    # 合并去重（按地区名去重，保留信息更完整的行）
    combined_df = pd.concat(all_data, ignore_index=True)
    # 按地区分组，保留“数字化成果描述”最长的行（信息更完整）
    combined_df['desc_length'] = combined_df['数字化成果描述'].apply(lambda x: len(str(x)))
    combined_df = combined_df.sort_values('desc_length', ascending=False).drop_duplicates('地区', keep='first').drop(
        'desc_length', axis=1)
    print(f"数据整合完成，共覆盖 {len(combined_df)} 个地区\n")
    return combined_df


# ------------------------------
# 3. 分析功能：筛选、总结与对比（修复None切片错误）
# ------------------------------
def filter_advanced_regions(data):
    """筛选数字化建设成果突出的地区"""
    advanced_keywords = [
        "全国领先", "领先水平", "标杆", "示范", "样板",
        "成效显著", "效果明显", "成果突出", "大幅提升", "显著改善",
        "创新试点", "试点城市", "示范城市", "改革试点", "先行先试",
        "行政效能提升", "办事效率提高", "政务服务优化", "审批提速",
        "数字化转型成功", "数字政府典范", "智慧政务标杆",
        "全国前列", "排名前列", "优秀案例", "典型经验", "经验推广"
    ]
    pattern = re.compile('|'.join(advanced_keywords), re.IGNORECASE)
    mask = data['数字化成果描述'].apply(
        lambda x: bool(pattern.search(str(x))) if pd.notna(x) else False
    )
    return data[mask].copy()


def summarize_advanced_practices(advanced_regions):
    """总结先进地区的核心模式与做法"""
    practices = {}
    for _, row in advanced_regions.iterrows():
        region = row['地区']
        # 过滤无效做法（仅保留有实际内容的）
        key_practices = re.split(r'[;；。]', str(row['模式做法']))
        key_practices = [p.strip() for p in key_practices if p.strip() and len(p) > 10 and '未明确' not in p]
        # 补充默认做法（若提取为空）
        if not key_practices:
            key_practices = [f"推进{row['数字化成果描述'].split('，')[0]}"[:50]]

        practices[region] = {
            '核心模式': key_practices[:3],
            '政策亮点': row['政策支持'] if row['政策支持'] != "未明确政策" else "推进数字化转型专项规划",
            '技术特点': f"投入{row['技术投入(亿元)']:.1f}亿元" if row['技术投入(亿元)'] is not None else "重点建设智慧政务平台"
        }
    return practices


def compare_anhui(data, advanced_regions):
    """对比安徽与先进地区的差距"""
    # 匹配“安徽省”（避免匹配“合肥市”）
    anhui_mask = data['地区'].str.strip() == '安徽省'
    anhui_data = data[anhui_mask]
    if anhui_data.empty:
        # 若未找到“安徽省”，尝试匹配包含“安徽”的省级描述
        anhui_mask = data['地区'].str.contains('安徽', na=False) & ~data['地区'].str.contains('市', na=False)
        anhui_data = data[anhui_mask]
        if anhui_data.empty:
            return "未找到安徽省省级数据，请确保文件包含'安徽省'相关描述"

    anhui = anhui_data.iloc[0].to_dict()
    comparison = {
        '政策支持': {
            '安徽': anhui['政策支持'] if anhui['政策支持'] != "未明确政策" else "待完善专项政策",
            '先进地区': [r['政策支持'] for _, r in advanced_regions.iterrows()]
        },
        '技术投入': {
            '安徽': anhui['技术投入(亿元)'],
            '先进地区': [r['技术投入(亿元)'] for _, r in advanced_regions.iterrows()],
            '先进平均': None
        },
        '人才建设': {
            '安徽': anhui['人才政策'] if anhui['人才政策'] != "未明确人才措施" else "待强化人才体系",
            '先进地区': [r['人才政策'] for _, r in advanced_regions.iterrows()]
        }
    }

    # 计算技术投入平均值（排除None）
    valid_tech = [t for t in comparison['技术投入']['先进地区'] if t is not None]
    comparison['技术投入']['先进平均'] = round(sum(valid_tech) / len(valid_tech), 2) if valid_tech else "数据不足"
    return comparison


def propose_recommendations(comparison):
    """基于对比提出安徽可借鉴的具体建议"""
    if isinstance(comparison, str):
        return []

    recommendations = []
    advanced_policies = [p for p in comparison['政策支持']['先进地区'] if "未明确" not in p and p.strip()]
    advanced_talents = [t for t in comparison['人才建设']['先进地区'] if "未明确" not in t and t.strip()]
    anhui_tech = comparison['技术投入']['安徽']
    advanced_tech_avg = comparison['技术投入']['先进平均']

    # 1. 政策支持建议
    if advanced_policies:
        if "待完善" in comparison['政策支持']['安徽']:
            recommendations.append(
                f"政策层面：参考浙江省“发布数字政府建设‘十四五’规划”、江苏省“推进政务服务模式重构”等做法，"
                "尽快出台安徽省数字政府转型专项规划，明确2025-2030年阶段目标（如政务服务“一网通办”覆盖率100%），"
                "建立跨部门协同机制（如成立省级数字政府建设领导小组）。"
            )
        else:
            recommendations.append(
                f"政策优化：借鉴{advanced_policies[0].split('，')[0]}的经验，"
                "增加政策落地监督机制（如每季度发布转型成效报告），针对基层政务数字化增设专项扶持资金。"
            )

    # 2. 技术投入建议
    if isinstance(anhui_tech, (int, float)) and isinstance(advanced_tech_avg, (int, float)):
        gap = advanced_tech_avg - anhui_tech
        if gap > 0:
            recommendations.append(
                f"技术投入：安徽当前投入（{anhui_tech:.1f}亿元）较先进地区平均（{advanced_tech_avg:.1f}亿元）低{gap:.1f}亿元，"
                "建议重点投向三大领域：一是政务云平台升级（支撑全省数据共享），二是智能审批系统研发（减少人工环节），"
                "三是基层政务终端更新（覆盖市县乡村）；同时探索“政府+企业”共建模式（如与本地科技企业合作开发平台）。"
            )
        elif gap <= 0:
            recommendations.append(
                f"技术优化：安徽技术投入（{anhui_tech:.1f}亿元）已达先进水平，建议聚焦投入效率提升，"
                "建立技术投入绩效评估机制（如每亿元投入对应行政效能提升指标），避免重复建设。"
            )

    # 3. 人才建设建议
    if advanced_talents:
        if "待强化" in comparison['人才建设']['安徽']:
            recommendations.append(
                f"人才战略：借鉴贵州省“强化人才引进培育，构建数字人才培养新体系”、山东省“推进数字人才专项计划”等模式，"
                "实施三大举措：一是与中科大、合工大等高校共建“数字政府人才培养基地”，定向输送专业人才；"
                "二是推出“江淮数字人才计划”，引进长三角地区高层次专家；三是开展基层人员轮训（每年覆盖1万名政务人员）。"
            )
        else:
            recommendations.append(
                f"人才优化：参考{advanced_talents[0].split('，')[0]}的做法，"
                "完善人才激励机制（如数字政府项目分红、职称评定倾斜），建立跨区域人才交流平台（如与上海、浙江互派干部学习）。"
            )

    return recommendations if recommendations else [
        "安徽数字政府建设已处于先进水平，建议聚焦长三角协同（如数据跨省共享）打造特色标杆。"]


# ------------------------------
# 4. 主函数：流程控制与结果输出（修复None切片错误）
# ------------------------------
def main():
    # 你的文件目录路径（已确认正确）
    dir_path = r"D:\Hefei_University_of_Technology_Work\A020_250901数字政府规划\B03_各省市数字政府建设总体规划"

    # 1. 批量处理文件
    combined_data = batch_process_directory(dir_path)
    if combined_data is None:
        return

    # 2. 筛选先进地区
    advanced_regions = filter_advanced_regions(combined_data)
    if advanced_regions.empty:
        print("\n未筛选出先进地区，可调整filter_advanced_regions函数中的关键词")
        print("\n部分地区描述示例：")
        for _, row in combined_data.head(5).iterrows():
            print(f"{row['地区']}：{row['数字化成果描述'][:100]}...")
        return
    print("=" * 60)
    print("数字化建设成果突出的地区：")
    print(advanced_regions['地区'].tolist())
    print("=" * 60 + "\n")

    # 3. 总结先进模式与做法
    advanced_practices = summarize_advanced_practices(advanced_regions)
    print("先进地区核心模式与做法总结：")
    for region, info in advanced_practices.items():
        print(f"\n【{region}】")
        print("核心模式：")
        for i, mode in enumerate(info['核心模式'], 1):
            print(f"  {i}. {mode}")
        print(f"政策亮点：{info['政策亮点'][:120]}")
        print(f"技术特点：{info['技术特点']}")
    print("\n" + "=" * 60 + "\n")

    # 4. 对比安徽与先进地区（修复：处理None值，避免切片错误）
    comparison = compare_anhui(combined_data, advanced_regions)
    if isinstance(comparison, str):
        print(comparison)
        return
    print("安徽与先进地区对比分析：")
    for 维度, details in comparison.items():
        print(f"\n【{维度}】")
        # 处理安徽数据
        anhui_val = details['安徽']
        if anhui_val is None:
            print(f"安徽现状：数据缺失")
        else:
            print(f"安徽现状：{anhui_val}")
        # 处理先进地区数据（None替换为“数据缺失”）
        advanced_vals = [d if d is not None else "数据缺失" for d in details['先进地区'][:2]]
        # 对字符串类型数据切片，非字符串直接显示
        advanced_vals = [d[:50] + "..." if isinstance(d, str) and len(d) > 50 else d for d in advanced_vals]
        print(f"先进地区典型：{advanced_vals}")
        # 显示技术投入平均值
        if '先进平均' in details:
            print(f"先进地区平均水平：{details['先进平均']}")
    print("\n" + "=" * 60 + "\n")

    # 5. 提出可借鉴建议
    recommendations = propose_recommendations(comparison)
    print("安徽可借鉴的先进经验建议：")
    for i, rec in enumerate(recommendations, 1):
        print(f"\n{i}. {rec}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()