# 下载版本说明 / Download Editions

## 中文

v1.5.0 提供三种 Windows 交付方式。三者使用相同的主程序、API 供应商支持和翻译质量设置。

| 版本 | 包含内容 | 推荐用途 | 使用方式 |
|---|---|---|---|
| **Windows Setup Full** | 主程序、BabelDOC 智能 PDF 引擎、布局模型和字体 | 推荐大多数用户，特别是报告、说明书和连续正文 PDF | 运行安装程序，按向导完成安装 |
| **Portable Full** | 与安装完整版相同，但不写入系统安装目录 | 需要完整功能但不希望安装 | 解压完整文件夹，运行 `DocumentTranslator.exe` |
| **Portable Lite** | 主程序，不含 BabelDOC | Word、Excel、CSV、图纸、短标签 PDF，或自行管理 BabelDOC 的用户 | 解压完整文件夹，运行 `DocumentTranslator.exe` |

Setup Full 的安装向导提供简体中文、英语、俄语、西班牙语、法语和德语，并在每次启动时按 Windows 界面语言自动选择。

### 选择建议

- 不确定选哪个：选择 **Windows Setup Full**。它默认内置智能 PDF 引擎。
- 不能或不想安装软件：选择 **Portable Full**。
- 更在意下载体积，且主要处理 Word、Excel、CSV 或工程图纸：选择 **Portable Lite**。

Lite 版仍可使用“原位保版”方式翻译 PDF。自动模式找不到 BabelDOC 时会安全回退，不影响 Word、Excel、CSV 等其他格式。

所有安装包、压缩包和内部目录均使用英文、数字等 ASCII 安全名称，避免乱码。发布包内提供：

- `ReadMe.html`：双击后在浏览器中阅读；
- `ReadMe.txt`：可用记事本直接打开；
- `Legal`：许可证与第三方组件说明。

用户不需要安装 Markdown 阅读器。

### 为 Portable Lite 自行安装 BabelDOC

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

如果 `py -3.12` 不可用，可将第一条命令改为 `python -m venv ...`。首次 `--warmup` 需要联网下载布局模型和字体。它们属于引擎资源，不计入软件的 100 MB 译文缓存。

---

## English

Version 1.5.0 provides three Windows delivery options. All three use the same application, API-provider support, and translation-quality settings.

| Edition | Included | Recommended for | Usage |
|---|---|---|---|
| **Windows Setup Full** | Application, BabelDOC smart PDF engine, layout models, and fonts | Recommended for most users, especially reports, manuals, and prose-heavy PDFs | Run the installer and follow the setup wizard |
| **Portable Full** | The same full feature set without system installation | Complete features on a portable or restricted computer | Extract the complete folder and run `DocumentTranslator.exe` |
| **Portable Lite** | Application without BabelDOC | Word, Excel, CSV, drawings, short-label PDFs, or separately managed BabelDOC installations | Extract the complete folder and run `DocumentTranslator.exe` |

The Setup Full wizard offers Simplified Chinese, English, Russian, Spanish, French, and German, and detects the Windows UI language on every launch.

### Which edition should I choose?

- If unsure, choose **Windows Setup Full**. The smart PDF engine is included by default.
- If installation is not allowed or preferred, choose **Portable Full**.
- If download size matters and you mainly process Word, Excel, CSV, or engineering drawings, choose **Portable Lite**.

Portable Lite still translates PDFs with strict in-place placement. Automatic mode safely falls back when BabelDOC is unavailable, and other document formats are unaffected.

Installer, archive, and internal directory names use ASCII characters to prevent garbled filenames. Every package includes:

- `ReadMe.html`, which opens in a web browser;
- `ReadMe.txt`, which opens in Notepad;
- `Legal`, containing license and third-party notices.

No Markdown reader is required.

### Install BabelDOC for Portable Lite

1. Install 64-bit Python 3.10–3.12.
2. Run these commands in PowerShell:

```powershell
py -3.12 -m venv "$env:LOCALAPPDATA\DocumentTranslator\babeldoc-env"
& "$env:LOCALAPPDATA\DocumentTranslator\babeldoc-env\Scripts\python.exe" -m pip install --upgrade pip
& "$env:LOCALAPPDATA\DocumentTranslator\babeldoc-env\Scripts\python.exe" -m pip install BabelDOC==0.6.4
& "$env:LOCALAPPDATA\DocumentTranslator\babeldoc-env\Scripts\babeldoc.exe" --warmup
```

3. Open **Settings → Advanced**.
4. Select this file under **High-quality engine**:

```text
%LOCALAPPDATA%\DocumentTranslator\babeldoc-env\Scripts\babeldoc.exe
```

5. Select **Automatic** or **Smart layout** as the PDF mode.

If `py -3.12` is unavailable, replace the first command with `python -m venv ...`. The first `--warmup` requires internet access to download layout models and fonts. These engine resources are separate from the application's 100 MB translation cache.
