<p align="center">
  <img src="translator_app/assets/app_icon.png" width="104" alt="Document Translator icon">
</p>

<h1 align="center">文档智能翻译器</h1>
<h3 align="center">Document Translator</h3>

<p align="center">
  保留版式、保护技术编号，批量翻译 PDF、Word、Excel 和 CSV 等文档。<br>
  Translate PDFs, Word files, spreadsheets, and CSV files while preserving layout and technical identifiers.
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

### 下载哪个版本？

| 版本 | 是否包含智能 PDF 引擎 | 推荐用途 |
|---|---|---|
| **完整版 / Full** | 包含 BabelDOC、布局模型和字体，解压后约 1 GB | 报告、说明书、论文等连续正文 PDF；下载后直接使用智能排版 |
| **轻量版 / Lite** | 不包含 BabelDOC，体积较小 | Word、Excel、CSV、工程图纸和短标签 PDF；也可自行安装引擎 |

两个版本的主程序功能完全相同。轻量版找不到 BabelDOC 时会自动使用“原位保版”，不会影响其他格式。详细区别和自行安装方法见 [下载版本说明 / Download Editions](docs/DOWNLOADS.md)。完整版必须解压整个文件夹运行，不要只移动其中的 EXE。

### 三步开始使用

1. 从 [Releases](https://github.com/WANG40929/engineering-document-translator/releases/latest) 下载最新版 Windows EXE。
2. 启动软件，在“设置”中填写自己的 DeepSeek API Key，并选择目标语言。
3. 拖入文件或文件夹，点击“开始翻译”。源文件不会被覆盖，译文会自动添加语言后缀。

> 默认模型是 `deepseek-v4-flash`，适合快速、低成本的批量翻译；复杂内容可切换到 `deepseek-v4-pro`。

### 支持的文件

| 格式 | 处理方式 | 保留内容 |
|---|---|---|
| PDF | 自动选择“智能排版”或“原位保版”；可生成纯译文或中外文对照 PDF | 图片、矢量线条、页面尺寸和页数 |
| DOCX | 按完整段落翻译正文、表格、页眉和页脚 | 段落、表格和主要字符样式 |
| XLSX / XLSM | 只翻译字符串单元格 | 公式、数值、样式和工作表结构 |
| CSV / TSV | 按原编码和分隔符读写 | 行列结构和分隔符 |
| DOC | 通过本机 Microsoft Word 转换并回存 | 原 `.doc` 格式；需要安装 Word |

### 核心功能

- **保留版式：** 不把文档粗暴转换成纯文本。
- **双 PDF 引擎：** 报告和说明书可使用 BabelDOC 重建段落与排版；工程图纸和短标签继续使用精确原位替换。
- **PDF 输出形式：** 可选择纯译文、中外文对照，或同时生成两种 PDF。
- **技术编号保护：** 图号、物料号、KKS、标准号、尺寸、单位、网址等使用占位符保护。
- **文件队列：** 支持多文件、文件夹和拖放；已完成文件不会自动重复处理。
- **长文档容错：** 接口漏掉部分段落时只补译缺失内容，必要时自动拆小批次，不让单次不完整返回报废整份文件。
- **真实进度：** 按文字段落计算进度，显示当前页、已用时间和动态预计剩余时间；失败时停在实际位置。
- **任务控制：** 翻译运行时可请求停止；停止按钮在空闲状态自动隐藏。
- **翻译质量检查：** 可自动复核疑似未翻译的物料名称和普通技术词。
- **术语表：** 支持 CSV、TSV、TXT、XLSX；选择后会记住路径，并在后续文件中继续使用。
- **纯目标语言：** 可选地把双语字段合并成单一目标语言，默认不勾选。
- **缓存与成本控制：** 相同文字跨文件复用；缓存上限 100 MB，超限后自动删除最旧记录并压缩至约 90 MB。
- **密钥安全：** API Key 使用 Windows DPAPI 加密，只能由当前 Windows 用户读取，不会写入项目或报告。

### 高质量 PDF 引擎

“智能排版”使用可选的 [BabelDOC](https://github.com/funstory-ai/BabelDOC) 后端。它适合报告、手册和连续正文；“原位保版”适合图纸、图签、设备标签和短文本。自动模式会根据文档内容选择，找不到 BabelDOC 时安全回退到原位保版。

安装 BabelDOC 后，在“设置 → 高级 → 高质量引擎”中选择 `babeldoc.exe`。源码环境可使用：

```powershell
python -m venv .babeldoc-env
uv pip install --python .babeldoc-env\Scripts\python.exe BabelDOC==0.6.4
.babeldoc-env\Scripts\babeldoc.exe --warmup
```

BabelDOC 的程序、布局模型和字体目前约占 1 GB，属于可选程序资源，不计入 100 MB 译文缓存，也不会被缓存清理误删。API Key 通过任务专用临时配置传给本地后端，任务结束立即删除，并从错误信息中脱敏。

### 术语表格式

前两列分别填写“源术语”和“目标术语”：

```csv
lube oil,润滑油
bearing pedestal,轴承座
```

人工确认的术语表会跨文件持续复用。智能 PDF 模式还会调用 BabelDOC 的文档内自动术语提取；可审核、可永久积累的自动术语库仍在规划中，缓存不能替代术语库。

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
- 智能 PDF 模式需要单独安装 BabelDOC；其首次模型准备时间和磁盘占用高于原位保版模式。
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
2. Start the application, enter your own DeepSeek API key under **Settings**, and select a target language.
3. Drop files or folders into the window and click **Start Translation**. Source files are never overwritten; translated files receive a language suffix.

> `deepseek-v4-flash` is the default model for fast, cost-effective batch translation. Select `deepseek-v4-pro` for more demanding content.

### Supported files

| Format | Processing | Preserved content |
|---|---|---|
| PDF | Automatically selects smart reflow or strict in-place replacement; supports mono and bilingual output | Images, vector drawings, page sizes, and page count |
| DOCX | Translates body text, tables, headers, and footers with paragraph context | Paragraphs, tables, and primary character styles |
| XLSX / XLSM | Translates string cells only | Formulas, values, styles, and workbook structure |
| CSV / TSV | Reads and writes using the detected encoding and delimiter | Rows, columns, and delimiters |
| DOC | Converts and saves through local Microsoft Word | Legacy `.doc` format; Word is required |

### Key features

- **Layout preservation:** Documents are not flattened into plain text.
- **Dual PDF engines:** BabelDOC rebuilds paragraphs for reports and manuals, while strict in-place replacement remains available for drawings and short labels.
- **PDF output choices:** Generate translated-only, bilingual, or both PDF variants.
- **Technical-token protection:** Drawing numbers, material IDs, KKS tags, standards, dimensions, units, and URLs are protected with placeholders.
- **Batch queue:** Supports files, folders, and drag-and-drop. Completed files are not processed again automatically.
- **Long-document recovery:** Repairs only omitted segments and recursively splits invalid batches instead of failing the whole file.
- **Real progress:** Tracks text units, current PDF page, elapsed time, and a dynamic ETA without falsely showing 100% after failure.
- **Translation review:** Can retry likely untranslated material names and ordinary technical terms.
- **Glossaries:** Supports CSV, TSV, TXT, and XLSX. The selected path is remembered and reused for later files.
- **Target-only mode:** Optionally merges bilingual fields into the target language only. It is off by default.
- **Cache and cost control:** Reuses identical text across files. The cache is capped at 100 MB and compacted to about 90 MB after removing the oldest entries.
- **API-key security:** The key is encrypted with Windows DPAPI for the current user and is never written to the repository or reports.

### High-quality PDF engine

Smart PDF layout uses the optional [BabelDOC](https://github.com/funstory-ai/BabelDOC) backend. Select its `babeldoc.exe` under **Settings → Advanced → High-quality engine**. Automatic mode uses smart reflow for prose documents and strict placement for drawings, falling back safely when BabelDOC is unavailable.

The backend, layout models, and fonts currently require roughly 1 GB. They are optional application resources, not part of the 100 MB translation cache. The API key is passed through a per-task temporary configuration, deleted after the task, and redacted from backend errors.

### Which download should I choose?

The **Full** archive includes BabelDOC, layout models, and fonts and is ready for smart PDF layout after extracting the complete folder. The smaller **Lite** archive omits BabelDOC and uses strict in-place PDF placement unless you install the engine yourself. Both contain the same application version and support Word, Excel, CSV, and PDF. See [Download Editions](docs/DOWNLOADS.md) for the comparison and manual installation steps.

### Glossary format

Use the first two columns for the source and target terms:

```csv
lube oil,润滑油
bearing pedestal,轴承座
```

Human-approved glossary files are reused across documents. Smart PDF mode also enables BabelDOC's per-document automatic term extraction. A permanent, reviewable auto-built terminology library remains planned; the translation cache is not a terminology database.

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
- Smart PDF mode requires a separate BabelDOC installation and uses more disk space than strict placement.
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
