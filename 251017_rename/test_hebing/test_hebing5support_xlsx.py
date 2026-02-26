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
EXCEL_PATH = r'D:\工作簿1.xlsx'  # 支持.xlsx文件
INPUT_DIR = r'D:\分类：效力位阶\002行政法规177=37+140篇\行政法规\doc'
OUTPUT_DIR = r'D:\txt1'

# 创建输出目录
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 读取 Excel 文件
try:
    df = pd.read_excel(EXCEL_PATH, dtype=str, engine='openpyxl')  # 这里改成了 openpyxl
    df['标题'] = df['标题'].astype(str).str.strip()
    df['公布日期'] = df['公布日期'].astype(str).str.strip()
    print("Excel 文件读取成功!")
except Exception as e:
    print(f"读取 Excel 文件失败: {e}")
    exit()

# ...（其他代码保持不变）tonghebing4