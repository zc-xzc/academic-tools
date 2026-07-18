# button_preprocess.py（单独运行，生成优化后图标）
import cv2
import numpy as np

def optimize_download_icon(raw_icon_path="D:\Hefei_University_of_Technology_Work/020_pythonProject/20251104_download\zhiwang/001\download_icon.png", save_path="D:\Hefei_University_of_Technology_Work/020_pythonProject/20251104_download\zhiwang/001\optimized_download_icon.png"):
    # 1. 读取原始图标（灰度化）
    raw_icon = cv2.imread(raw_icon_path, cv2.IMREAD_GRAYSCALE)
    if raw_icon is None:
        print(f"❌ 未找到原始图标：{raw_icon_path}")
        return False

    # 2. 阈值处理：去除白色/浅灰背景（适配你的按钮背景）
    # 阈值220：只保留比浅灰更深的按钮区域，背景变为纯黑
    _, thresh_icon = cv2.threshold(raw_icon, 220, 255, cv2.THRESH_BINARY_INV)

    # 3. 边缘检测：突出按钮轮廓（核心优化，减少页面干扰）
    # 适配25-30像素小图标，边缘更清晰
    optimized_icon = cv2.Canny(thresh_icon, 70, 130)

    # 4. 保存优化后图标
    cv2.imwrite(save_path, optimized_icon)
    print(f"✅ 按钮优化完成！")
    print(f"   原始图标：{raw_icon.shape[1]}x{raw_icon.shape[0]}像素")
    print(f"   优化后图标：{optimized_icon.shape[1]}x{optimized_icon.shape[0]}像素")
    print(f"   保存路径：{save_path}")
    return True

# 运行预处理
if __name__ == "__main__":
    optimize_download_icon()