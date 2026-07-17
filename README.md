<p align="center">
  <img src="translator_app/assets/app_icon.png" width="104" alt="Engineering Document Translator icon">
</p>

<h1 align="center">工程文档智能翻译器</h1>
<h3 align="center">Engineering Document Translator</h3>

<p align="center">
  保留版式、保护工程编号，批量翻译 PDF、Word 和 Excel。<br>
  Translate engineering PDFs, Word files, and spreadsheets while preserving layout and technical identifiers.
</p>

<p align="center">
  <a href="https://github.com/WANG40929/engineering-document-translator/releases/latest"><img alt="Release" src="https://img.shields.io/github/v/release/WANG40929/engineering-document-translator?style=flat-square&color=F47A3C"></a>
  <img alt="Platform" src="https://img.shields.io/badge/platform-Windows-23262B?style=flat-square">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="DeepSeek" src="https://img.shields.io/badge/DeepSeek-V4-4D6BFE?style=flat-square">
  <a href="LICENSE.txt"><img alt="License" src="https://img.shields.io/badge/license-AGPL--3.0-23262B?style=flat-square"></a>
</p>

<p align="center">
  <strong><a href="https://github.com/WANG40929/engineering-document-translator/releases/latest">下载 Windows 正式版 / Download for Windows</a></strong>
  · <a href="#中文">中文</a>
  · <a href="#english">English</a>
  · <a href="CHANGELOG.md">更新日志 / Changelog</a>
</p>

![应用界面 / Application screenshot](docs/app-screenshot.png)

---

<a id="中文"></a>

## 中文

### 为什么做这个项目？

普通翻译工具往往只关心文字，却容易破坏工程文档的表格、图纸、页眉页脚和技术编号。本项目专门面向工程手册、图纸、装箱单、设备清单等文件：只处理已有文字层，尽量保留原文件结构，并在发送API请求前保护图号、KKS、标准号、尺寸和单位。

### 三步开始使用

1. 从 [Releases](https://github.com/WANG40929/engineering-document-translator/releases/latest) 下载最新版 Windows EXE。
2. 启动软件，填写自己的 DeepSeek API Key，并选择目标语言。
3. 拖入文件或文件夹，点击“开始翻译”。源文件不会被覆盖，译文会自动添加语言后缀。

> 默认模型是 `deepseek-v4-flash`，适合快速、低成本的批量翻译；复杂内容可切换到 `deepseek-v4-pro`。

### 支持的文件

| 格式 | 处理方式 | 保留内容 |
|---|---|---|
| PDF | 仅翻译已有文字层，不执行 OCR | 图片、矢量线条、页面尺寸和页数 |
| DOCX | 按完整段落翻译正文、表格、页眉和页脚 | 段落、表格和主要字符样式 |
| XLSX / XLSM | 只翻译字符串单元格 | 公式、数值、样式和工作表结构 |
| CSV / TSV | 按原编码和分隔符读写 | 行列结构和分隔符 |
| DOC | 通过本机 Microsoft Word 转换并回存 | 原 `.doc` 格式；需要安装 Word |

### 核心功能

- **保留版式：** 不把文档粗暴转换成纯文本。
- **技术编号保护：** 图号、物料号、KKS、标准号、尺寸、单位、网址等使用占位符保护。
- **文件队列：** 支持多文件、文件夹和拖放；已完成文件不会自动重复处理。
- **翻译质量检查：** 可自动复核疑似未翻译的物料名称和普通技术词。
- **术语表：** 支持 CSV、TSV、TXT、XLSX；选择后会记住路径，并在后续文件中继续使用。
- **纯目标语言：** 可选地把双语字段合并成单一目标语言，默认不勾选。
- **缓存与成本控制：** 相同文字跨文件复用；缓存上限 100 MB，超限后自动删除最旧记录并压缩至约 90 MB。
- **密钥安全：** API Key 使用 Windows DPAPI 加密，只能由当前 Windows 用户读取，不会写入项目或报告。

### 术语表格式

前两列分别填写“源术语”和“目标术语”：

```csv
lube oil,润滑油
bearing pedestal,轴承座
```

当前版本使用的是**人工确认的术语表**。自动抽取并审核术语库仍在规划中，缓存不能替代术语库。

### 从源码运行

需要 Python 3.10 或更高版本：

```powershell
git clone https://github.com/WANG40929/engineering-document-translator.git
cd engineering-document-translator
python -m pip install -r requirements.txt
python -m translator_app
```

命令行示例：

```powershell
$env:DEEPSEEK_API_KEY="你的密钥"
python -m translator_app.cli "D:\docs" --target zh --output-dir "D:\translated"
```

### 已知限制

- 扫描图片、PDF转曲文字和没有文字层的页面不会翻译。
- 很密集的 PDF 图签或过长译文可能需要缩小字体。
- DOCX 文本框、SmartArt 和嵌入对象中的文字暂未处理。
- 旧版 `.doc` 依赖 Microsoft Word。
- 建议先用少量代表性文件验证术语和版式，再处理大型项目文件。

### 下一步计划

- [ ] 可审核、可复用的自动术语库
- [ ] 可选 OCR 模块（保持默认不处理扫描页）
- [ ] 更直观的翻译质量报告
- [ ] Windows 安装包与自动更新提示

如果这个项目对你有帮助，欢迎点一个 **Star**，或通过 [Issues](https://github.com/WANG40929/engineering-document-translator/issues) 提交样本文档类型、问题和建议。

---

<a id="english"></a>

## English

### Why this project?

General-purpose translators focus on text and may damage tables, drawings, headers, footers, and technical identifiers. This application is built for engineering manuals, drawings, packing lists, and equipment schedules. It translates existing text layers only, preserves the document structure where practical, and protects drawing numbers, KKS identifiers, standards, dimensions, and units before sending text to the API.

### Get started in three steps

1. Download the latest Windows EXE from [Releases](https://github.com/WANG40929/engineering-document-translator/releases/latest).
2. Start the application, enter your own DeepSeek API key, and select a target language.
3. Drop files or folders into the window and click **Start Translation**. Source files are never overwritten; translated files receive a language suffix.

> `deepseek-v4-flash` is the default model for fast, cost-effective batch translation. Select `deepseek-v4-pro` for more demanding content.

### Supported files

| Format | Processing | Preserved content |
|---|---|---|
| PDF | Translates existing text layers only; no OCR | Images, vector drawings, page sizes, and page count |
| DOCX | Translates body text, tables, headers, and footers with paragraph context | Paragraphs, tables, and primary character styles |
| XLSX / XLSM | Translates string cells only | Formulas, values, styles, and workbook structure |
| CSV / TSV | Reads and writes using the detected encoding and delimiter | Rows, columns, and delimiters |
| DOC | Converts and saves through local Microsoft Word | Legacy `.doc` format; Word is required |

### Key features

- **Layout preservation:** Documents are not flattened into plain text.
- **Technical-token protection:** Drawing numbers, material IDs, KKS tags, standards, dimensions, units, and URLs are protected with placeholders.
- **Batch queue:** Supports files, folders, and drag-and-drop. Completed files are not processed again automatically.
- **Translation review:** Can retry likely untranslated material names and ordinary technical terms.
- **Glossaries:** Supports CSV, TSV, TXT, and XLSX. The selected path is remembered and reused for later files.
- **Target-only mode:** Optionally merges bilingual fields into the target language only. It is off by default.
- **Cache and cost control:** Reuses identical text across files. The cache is capped at 100 MB and compacted to about 90 MB after removing the oldest entries.
- **API-key security:** The key is encrypted with Windows DPAPI for the current user and is never written to the repository or reports.

### Glossary format

Use the first two columns for the source and target terms:

```csv
lube oil,润滑油
bearing pedestal,轴承座
```

The current version uses **human-approved glossary files**. Automatic terminology extraction and review are planned; the translation cache is not a terminology database.

### Run from source

Python 3.10 or later is required:

```powershell
git clone https://github.com/WANG40929/engineering-document-translator.git
cd engineering-document-translator
python -m pip install -r requirements.txt
python -m translator_app
```

CLI example:

```powershell
$env:DEEPSEEK_API_KEY="your-key"
python -m translator_app.cli "D:\docs" --target zh --output-dir "D:\translated"
```

### Known limitations

- Scanned images, outlined PDF text, and pages without a text layer are not translated.
- Dense PDF title blocks or long translations may require smaller font sizes.
- Text inside DOCX text boxes, SmartArt, and embedded objects is not currently processed.
- Legacy `.doc` support requires Microsoft Word.
- Validate terminology and layout with a representative sample before processing a large project.

### Roadmap

- [ ] Reviewable and reusable automatic terminology library
- [ ] Optional OCR module while keeping scanned pages untouched by default
- [ ] Clearer translation quality reports
- [ ] Windows installer and update notifications

If this project is useful, please consider giving it a **Star**. File-format examples, bug reports, and feature ideas are welcome in [Issues](https://github.com/WANG40929/engineering-document-translator/issues).

---

## License / 许可

AGPL-3.0-or-later. PyMuPDF is available under the AGPL or a commercial license. Closed-source commercial distribution requires an appropriate commercial license or a replacement PDF engine. See [LICENSE.txt](LICENSE.txt) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

本项目采用 AGPL-3.0-or-later。PyMuPDF 使用 AGPL / 商业双重许可；闭源商业分发需要购买相应商业许可或更换 PDF 引擎。
