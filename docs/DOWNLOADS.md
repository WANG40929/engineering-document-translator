# 下载版本说明 / Download Editions

## 中文

GitHub Releases 提供两个 Windows 压缩包，主程序功能和版本号完全相同：

| 版本 | 包含内容 | 适合谁 | 下载后怎么用 |
|---|---|---|---|
| 完整版 `Full-with-BabelDOC` | 主程序、BabelDOC 智能排版引擎、布局模型和字体 | 需要翻译报告、说明书、论文等连续正文 PDF 的用户 | 解压完整文件夹，运行 `DocumentTranslator.exe`；不要只把 EXE 单独移走 |
| 轻量版 `Lite-no-BabelDOC` | 主程序，不含 BabelDOC | 主要翻译 Word、Excel、CSV、工程图纸和短标签 PDF，或希望自己安装引擎的用户 | 解压后直接运行 `DocumentTranslator.exe` |

轻量版仍然可以翻译 PDF，但使用“原位保版”引擎。选择“自动”时，如果没有找到 BabelDOC，软件会安全回退到原位保版。完整版约 1 GB（解压后），体积主要来自本地布局模型和多语言字体；它们不是 DeepSeek 模型，也不会消耗 DeepSeek Token。

### 轻量版自行安装 BabelDOC

1. 安装 64 位 Python 3.10–3.12。
2. 打开 PowerShell，依次运行：

```powershell
py -3.12 -m venv "$env:LOCALAPPDATA\DocumentTranslator\babeldoc-env"
& "$env:LOCALAPPDATA\DocumentTranslator\babeldoc-env\Scripts\python.exe" -m pip install --upgrade pip
& "$env:LOCALAPPDATA\DocumentTranslator\babeldoc-env\Scripts\python.exe" -m pip install BabelDOC==0.6.4
& "$env:LOCALAPPDATA\DocumentTranslator\babeldoc-env\Scripts\babeldoc.exe" --warmup
```

3. 打开软件的“设置 → 高级”。
4. 在“高质量引擎”中选择：

```text
%LOCALAPPDATA%\DocumentTranslator\babeldoc-env\Scripts\babeldoc.exe
```

5. PDF 模式选择“自动选择”或“智能排版”。

如果电脑上的 Python 命令不是 `py -3.12`，可以将第一行改为 `python -m venv ...`。首次 `--warmup` 会下载模型和字体，需要联网并占用约 1 GB 磁盘空间。

## English

GitHub Releases provides two Windows archives with the same application features and version:

| Edition | Included | Recommended for | Usage |
|---|---|---|---|
| Full `Full-with-BabelDOC` | Application, BabelDOC smart-layout engine, layout models, and fonts | Reports, manuals, papers, and prose-heavy PDFs | Extract the entire folder and run `DocumentTranslator.exe`; do not move only the EXE |
| Lite `Lite-no-BabelDOC` | Application without BabelDOC | Word, Excel, CSV, drawings, short-label PDFs, or custom engine installations | Extract and run `DocumentTranslator.exe` |

The Lite edition still translates PDFs using strict in-place placement. Automatic mode safely falls back to that engine when BabelDOC is unavailable. The Full edition uses roughly 1 GB after extraction, mostly for local layout models and multilingual fonts. These are not DeepSeek models and do not consume DeepSeek tokens.

### Install BabelDOC for the Lite edition

1. Install 64-bit Python 3.10–3.12.
2. Run these commands in PowerShell:

```powershell
py -3.12 -m venv "$env:LOCALAPPDATA\DocumentTranslator\babeldoc-env"
& "$env:LOCALAPPDATA\DocumentTranslator\babeldoc-env\Scripts\python.exe" -m pip install --upgrade pip
& "$env:LOCALAPPDATA\DocumentTranslator\babeldoc-env\Scripts\python.exe" -m pip install BabelDOC==0.6.4
& "$env:LOCALAPPDATA\DocumentTranslator\babeldoc-env\Scripts\babeldoc.exe" --warmup
```

3. Open **Settings → Advanced → High-quality engine** and select `%LOCALAPPDATA%\DocumentTranslator\babeldoc-env\Scripts\babeldoc.exe`.
4. Select **Automatic** or **Smart layout** as the PDF mode.

If `py -3.12` is unavailable, replace it with `python`. The first `--warmup` requires internet access and downloads roughly 1 GB of local resources.
