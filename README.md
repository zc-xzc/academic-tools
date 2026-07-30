<!-- licensing-notice -->
> [!NOTE]
> This repository includes third-party material. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for attribution, license scope and lawful-use requirements.

# Academic Tools

A collection of Python automation and analysis tools for academic research.

## Tools

| Directory | Description |
|-----------|-------------|
| cnki_downloader/ | CNKI (中国知网) paper batch downloader with image recognition |
| classification/ | Policy text statistical analysis & environmental regulation classifier |
| file_utils/ | Batch file rename, merge, split, and text processing |
| pdf_utils/ | PDF batch renaming tools |
| tools/ | Auto-clicker and miscellaneous utilities |
| models/ | Application framework demo template |

## Requirements

`ash
pip install requests selenium pyautogui opencv-python pillow pynput pandas matplotlib openpyxl
`

Additional requirements:
- **CNKI Downloader**: Edge WebDriver (download separately)
- **Policy Analysis**: Chinese font support (SimHei recommended)

## Notes

- The CNKI downloader uses screen recognition to automate paper downloads
- All tools are for personal/academic use only
