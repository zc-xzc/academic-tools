# -*- coding: utf-8 -*-
"""
PDF期刊+完整文献标题重命名工具（错误修复版）
修复核心：精准提取Article后的多行标题，过滤无效信息，避免重复期刊名/引用格式误判
"""

import PyPDF2
import os
import re
from typing import List


class PDFJournalTitleRenamer:
    def __init__(self):
        self.journal_keywords = {
            "Technological Forecasting & Social Change": ["technological forecasting & social change", "techfore",
                                                          "elsevier.com/locate/techfore"],
            "AgEcon Search": ["agecon search", "resources for the future", "discussion paper",
                              "agricultural & applied economics"],
            "International Environmental Agreements": ["int environ agreements", "s10784-024-09645-x",
                                                       "environmental rule of law"],
            "Environmental Science and Pollution Research": ["environmental science and pollution research",
                                                             "s11356-021-17460-z", "pollution research"],
            "Scholars Journal of Arts, Humanities and Social Sciences": ["sch j arts humanit soc sci", "sjahss",
                                                                         "environmental regulations and environmental performance"],
            "Sustainability": ["sustainability", "mdpi.com/journal/sustainability", "green eco-efficiency",
                               "sustainability-12-", "sustainability-14-"],
            "Journal of Environmental Economics and Management": ["s0095069625001081",
                                                                  "environmental economics and management"],
            "The Impact of Environmental Regulation on Employment": ["environmental regulation on employment",
                                                                     "employment scale", "employment structure"],
            "Unknown Journal (Default)": [""]
        }
        # 新增：无效信息排除关键词列表
        self.exclude_keywords = [
            "citation", "doi", "https://doi.org", "received", "accepted", "published",
            "author", "authors", "affiliation", "correspondence", "email", "tel:",
            "copyright", "licensee", "creative commons", "publisher’s note", "institutional review board",
            "informed consent", "data availability", "conflicts of interest", "funding"
        ]
        # 新增：标题核心主题词汇（用于校验有效性）
        self.topic_keywords = [
            "environmental regulation", "eco-efficiency", "corporate governance", "pollution",
            "energy saving", "green growth", "sustainable development", "environmental governance",
            "industrial pollution", "carbon emission", "environmental performance"
        ]

    def extract_header_text(self, pdf_path: str) -> List[str]:
        """提取文档开头核心文本：优先Article后的前10行，过滤无效信息"""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                header_lines = []
                max_pages = min(3, len(pdf_reader.pages))
                article_found = False  # 标记是否找到Article标识
                for page_num in range(max_pages):
                    page = pdf_reader.pages[page_num]
                    page_text = page.extract_text() or ""
                    lines = [line.strip() for line in page_text.split('\n') if line.strip()]

                    for line in lines:
                        line_lower = line.lower()
                        # 找到Article标识后开始提取
                        if not article_found and "article" in line_lower and len(line) < 20:
                            article_found = True
                            continue
                        # 提取Article后的前10行，且过滤无效关键词
                        if article_found and len(header_lines) < 10:
                            # 过滤包含无效关键词的行
                            if not any(keyword in line_lower for keyword in self.exclude_keywords):
                                header_lines.append(line)
                        elif len(header_lines) >= 10:
                            break
                    if len(header_lines) >= 10:
                        break
                return header_lines
        except PyPDF2.errors.PdfReadError:
            print(f"⚠️ 警告：{os.path.basename(pdf_path)} 已加密或损坏，需解密后处理")
            return []
        except Exception as e:
            print(f"⚠️ 读取{os.path.basename(pdf_path)}失败：{str(e)}")
            return []

    def merge_full_title(self, header_lines: List[str]) -> str:
        """合并多行标题，确保完整且有效"""
        if not header_lines:
            return "Unknown_Title"

        full_title = ""
        topic_count = 0  # 统计包含的主题词汇数
        for line in header_lines:
            line_lower = line.lower()
            # 若行中包含主题词汇，纳入标题
            for topic in self.topic_keywords:
                if topic in line_lower:
                    topic_count += 1
            # 合并连续的标题行（避免跨行断裂）
            if topic_count > 0 or (full_title and len(line) > 15 and not any(
                    keyword in line_lower for keyword in self.exclude_keywords)):
                full_title += line + " "
            # 标题长度足够且主题词汇≥1，停止合并（避免混入作者行）
            if len(full_title) > 50 and topic_count >= 1:
                break

        # 清理标题，去除多余空格
        full_title = full_title.strip().replace('  ', ' ')
        # 有效性校验：若标题无效，重新提取开头最长连续行
        if len(full_title) < 20 or topic_count == 0:
            # 备选方案：提取开头最长的连续3行文本
            candidate = ' '.join(header_lines[:3]).strip().replace('  ', ' ')
            full_title = candidate if len(candidate) > 20 else "Unknown_Title"

        # 限制标题长度（避免文件名溢出）
        return full_title[:180] if len(full_title) > 180 else full_title

    def identify_journal(self, header_lines: List[str]) -> str:
        """识别期刊名称（避免重复提取）"""
        header_text = ' '.join(header_lines).lower()
        matched_journals = []
        for journal_name, keywords in self.journal_keywords.items():
            if journal_name == "Unknown Journal (Default)":
                continue
            match_count = 0
            for keyword in keywords:
                if keyword.lower() in header_text:
                    match_count += 2
            if match_count > 0:
                matched_journals.append((journal_name, match_count))
        if matched_journals:
            return sorted(matched_journals, key=lambda x: x[1], reverse=True)[0][0]
        return "Unknown Journal (Default)"

    def clean_filename(self, text: str) -> str:
        """清理文件名非法字符"""
        illegal_chars = r'[\\/:*?"<>|]'
        return re.sub(illegal_chars, '_', text).replace('__', '_').strip('_')

    def get_unique_filename(self, directory: str, journal_name: str, title: str) -> str:
        """生成唯一文件名：时间戳_期刊名称_完整标题_序号.pdf"""
        import time
        timestamp = time.strftime("%Y%m%d_%H%M%S_", time.localtime())
        clean_journal = self.clean_filename(journal_name)
        clean_title = self.clean_filename(title)
        base_name = f"{timestamp}{clean_journal}_{clean_title}"
        full_path = os.path.join(directory, f"{base_name}.pdf")

        counter = 1
        while os.path.exists(full_path):
            new_name = f"{base_name}_{counter}"
            full_path = os.path.join(directory, f"{new_name}.pdf")
            counter += 1
        return os.path.basename(full_path)

    def rename_single_pdf(self, pdf_path: str, custom_suffix: str = "") -> bool:
        """重命名单个PDF（修复标题提取错误）"""
        if not os.path.exists(pdf_path) or not pdf_path.lower().endswith('.pdf'):
            print(f"❌ 无效文件：{os.path.basename(pdf_path)}")
            return False

        # 提取核心文本+合并完整标题+识别期刊
        header_lines = self.extract_header_text(pdf_path)
        journal_name = self.identify_journal(header_lines)
        paper_title = self.merge_full_title(header_lines)

        # 生成最终文件名
        directory = os.path.dirname(pdf_path)
        new_filename = self.get_unique_filename(directory, journal_name, paper_title)
        if custom_suffix:
            new_filename = new_filename.replace('.pdf', f"_{custom_suffix}.pdf")
        new_path = os.path.join(directory, new_filename)

        # 执行重命名
        try:
            os.rename(pdf_path, new_path)
            print(f"✅ 成功重命名：{os.path.basename(pdf_path)} -> {new_filename}")
            return True
        except Exception as e:
            print(f"❌ 重命名失败：{os.path.basename(pdf_path)} -> 错误：{str(e)}")
            return False

    def batch_rename_pdfs(self, directory: str, recursive: bool = False) -> None:
        """批量重命名文件夹中的PDF"""
        if not os.path.isdir(directory):
            print(f"❌ 目录不存在：{directory}")
            return

        success_count = 0
        fail_count = 0
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.lower().endswith('.pdf'):
                    pdf_path = os.path.join(root, file)
                    if self.rename_single_pdf(pdf_path):
                        success_count += 1
                    else:
                        fail_count += 1
            if not recursive:
                break

        print(f"\n📊 批量处理完成！")
        print(f"📈 成功：{success_count} 个文件（已修复标题提取错误）")
        print(f"📉 失败：{fail_count} 个文件（加密/损坏/无法识别）")


def user_interaction():
    """用户交互逻辑"""
    print("=" * 60)
    print("📄 PDF期刊+完整标题重命名工具（错误修复版）")
    print("✅ 修复核心：精准提取多行标题，过滤无效信息")
    print("✅ 文件名格式：时间戳_期刊名称_完整文献标题_序号.pdf")
    print("=" * 60)
    print("请选择处理方式：")
    print("1 - 处理单个PDF文件（优先修复错误文件）")
    print("2 - 批量处理文件夹中的所有PDF文件")
    print("=" * 60)

    while True:
        choice = input("输入选项（1/2）：").strip()
        if choice in ["1", "2"]:
            break
        print("❌ 输入无效，请输入1或2！")

    if choice == "1":
        pdf_path = input("请输入错误PDF的完整路径（例：C:/docs/错误文件.pdf）：").strip()
        custom_suffix = input("是否添加自定义后缀（无需则回车）：").strip()
        renamer = PDFJournalTitleRenamer()
        renamer.rename_single_pdf(pdf_path, custom_suffix)
    elif choice == "2":
        dir_path = input("请输入文件夹完整路径（例：C:/docs/papers）：").strip()
        recursive = input("是否递归处理子文件夹（y/n，默认n）：").strip().lower() == "y"
        renamer = PDFJournalTitleRenamer()
        renamer.batch_rename_pdfs(dir_path, recursive)

    print("\n🎉 操作结束！已修复标题提取错误，文件名包含完整文献标题～")


if __name__ == "__main__":
    user_interaction()