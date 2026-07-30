<p align="center">
  <img src="translator_app/assets/app_icon.png" width="104" alt="Document Translator icon">
</p>

<h1 align="center">文档智能翻译器</h1>
<h3 align="center">Document Translator · v1.4.2</h3>

<p align="center">
  保留版式、保护技术编号，批量翻译 PDF、Word、Excel 和 CSV 等文档。<br>
  Translate PDF, Word, Excel, and CSV documents while preserving layout and technical identifiers.
</p>

<p align="center">
  <a href="https://github.com/WANG40929/engineering-document-translator/releases/latest"><img alt="Release" src="https://img.shields.io/github/v/release/WANG40929/engineering-document-translator?style=flat-square&color=276EF1"></a>
  <img alt="Platform" src="https://img.shields.io/badge/platform-Windows-23262B?style=flat-square">
  <a href="LICENSE.txt"><img alt="License" src="https://img.shields.io/badge/license-AGPL--3.0-23262B?style=flat-square"></a>
</p>

<p align="center">
  <strong><a href="https://github.com/WANG40929/engineering-document-translator/releases/latest">下载 Windows 版本 / Windows downloads</a></strong>
  · <a href="#中文">中文</a>
  · <a href="#english">English</a>
  · <a href="CHANGELOG.md">更新日志 / Changelog</a>
</p>

![应用界面 / Application screenshot](docs/app-screenshot.png)

---

<a id="中文"></a>

## 中文

### 选择下载版本

v1.4.2 提供三种 Windows 版本：

| 版本 | 包含 BabelDOC 智能 PDF 引擎 | 适合谁 |
|---|---:|---|
| **Windows Setup Full（安装完整版）** | 是 | 推荐大多数用户；按向导安装，智能 PDF 引擎默认内置 |
| **Portable Full（免安装完整版）** | 是 | 不希望安装；解压完整文件夹后使用 |
| **Portable Lite（免安装轻量版）** | 否 | 主要翻译 Word、Excel、CSV、图纸或短标签 PDF；也可自行安装 BabelDOC |

安装向导支持简体中文、英语、俄语、西班牙语、法语和德语，并在每次启动时按 Windows 界面语言自动选择。

安装包和压缩包名称均使用英文、数字等 ASCII 字符，避免在不同解压软件中出现乱码。每个发布包都提供浏览器可直接打开的 `ReadMe.html` 和普通文本 `ReadMe.txt`，不要求用户会打开 Markdown 文件。详细区别和 Lite 版安装引擎的方法见 [下载版本说明](docs/DOWNLOADS.md)。

### 开始使用

1. 从 [Releases](https://github.com/WANG40929/engineering-document-translator/releases/latest) 选择上面的一种 Windows 安装包或压缩包。
2. 打开软件，在“设置”中填写自己的 DeepSeek API Key，并选择目标语言。
3. 拖入文件或文件夹，点击“开始翻译”。
4. 完成后直接点击“打开文件”或“打开文件夹”查看结果。

翻译过程中如有紧急文件，点击该任务右侧的“紧急优先”箭头。软件会在当前接口请求结束后的安全检查点暂停当前文件，先完成紧急文件，再利用缓存继续原文件；不会在写入成品时强行中断。

源文件不会被覆盖，译文会自动添加语言后缀。程序界面支持跟随系统语言，也可手动切换为：

- 简体中文
- English
- Русский（俄语）
- Español（西班牙语）
- Français（法语）
- Deutsch（德语）

### 支持的文档

| 格式 | 处理方式 | 主要保留内容 |
|---|---|---|
| PDF | 自动选择智能排版或原位保版；可生成纯译文或双语 PDF | 图片、矢量线条、页面尺寸和页数 |
| DOCX | 翻译正文、表格、页眉和页脚 | 段落、表格和主要字符样式 |
| XLSX / XLSM | 只翻译字符串单元格 | 公式、数值、样式和工作表结构 |
| CSV / TSV | 按检测到的编码和分隔符读写 | 行列结构和分隔符 |
| DOC | 通过本机 Microsoft Word 转换并回存 | 原 `.doc` 格式；需要安装 Word |

只翻译已有文字层；扫描图片、PDF 转曲文字和没有文字层的页面不会翻译。

### v1.4.2 重点改进

- **真正的紧急插队：** 安全暂停正在处理的文件，优先翻译指定文件，完成后从缓存继续原任务。
- **任务焦点优化：** 移除表格单元格的虚线焦点框，同时保留整行选择和键盘操作。
- **PDF 漏检修复：** 逐字检查局部裁切，并新增文字行重叠和结构行异常合并检测。
- **复杂版面保护：** 提示框不同颜色内容不会错误合并，表格译文严格限制在所属单元格内。
- **失败保护：** 自适应修复如果仍有文字无法放入，不再替换原智能排版页。

### v1.4.0 PDF 质量改进

- **PDF 生成后自动质检：** 逐页比较原文与译文的文字分布，检查隐藏或裁切文字、内容异常聚集和低于可读下限的字号。
- **只修问题页：** 自动命中的页面改用保留表格和固定区域的自适应原位排版重新翻译，其余已通过页面不重复处理。
- **修复后再次复检：** 质量报告记录初检、修复页和复检结果；仍需关注的页码会明确提示。
- **长段落与目录保护：** 按页面隔离翻译上下文，合并自然换行的正文，同时避免目录、表格、项目符号和技术编号被错误拼接。
- **纯译文和双语输出同步：** 修复页会同时写回纯译文和双语对照 PDF，保持页数、页面尺寸和未命中页不变。
- **字号可读性底线：** 自适应修复不会把正文压缩到 5.5 pt 以下。

### PDF 引擎与术语

“智能排版”使用 [BabelDOC](https://github.com/funstory-ai/BabelDOC)，适合报告、手册和连续正文；v1.4.0 会在其输出后逐页自检，并只对命中的问题页使用自适应原位排版修复。“原位保版”仍适合工程图纸、图签、设备标签和短文本。Setup Full 和 Portable Full 已包含 BabelDOC；Portable Lite 找不到该引擎时会安全回退到原位保版。

BabelDOC 的程序、布局模型和字体不属于 100 MB 译文缓存，也不会被缓存清理。API Key 仅通过任务临时配置传递，任务结束后删除，并从错误信息中脱敏。

软件支持 CSV、TSV、TXT 和 XLSX 术语表。用户选择的术语表会被记住，并在后续文件中继续使用。智能 PDF 可进行当前文档内的术语提取，但本版本**不会自动建立并永久积累一个可审核的术语库**；译文缓存也不等于术语库。

### 已知限制

- 扫描件需要 OCR；本版本默认不处理没有文字层的页面。
- 很密集的 PDF 图签或明显变长的译文可能需要缩小字体。
- DOCX 文本框、SmartArt 和嵌入对象中的文字暂未处理。
- 旧版 `.doc` 支持依赖本机 Microsoft Word。
- 建议先用代表性文件验证术语和版式，再批量处理大型项目。

### 从源码运行

需要 Python 3.10 或更高版本：

```powershell
git clone https://github.com/WANG40929/engineering-document-translator.git
cd engineering-document-translator
python -m pip install -r requirements.txt
python -m translator_app
```

### 后续计划

- [ ] 可审核、可复用的自动术语库
- [ ] 可选 OCR 模块
- [ ] 更直观的翻译质量报告
- [ ] 自动更新提示

如果这个项目对你有帮助，欢迎点一个 **Star**，或通过 [Issues](https://github.com/WANG40929/engineering-document-translator/issues) 提交问题和建议。

---

<a id="english"></a>

## English

### Choose a download

Version 1.4.2 provides three Windows editions:

| Edition | BabelDOC smart PDF engine included | Recommended for |
|---|---:|---|
| **Windows Setup Full** | Yes | Recommended for most users; guided installation with the engine included by default |
| **Portable Full** | Yes | No installation; extract the complete folder before use |
| **Portable Lite** | No | Word, Excel, CSV, drawings, and short-label PDFs; BabelDOC can be installed separately |

The setup wizard supports Simplified Chinese, English, Russian, Spanish, French, and German, and detects the Windows UI language on every launch.

Package and archive names use ASCII characters to prevent garbled filenames in older archive tools. Every package contains a browser-friendly `ReadMe.html` and plain-text `ReadMe.txt`; users do not need a Markdown reader. See [Download Editions](docs/DOWNLOADS.md) for details and Lite-edition engine setup.

### Get started

1. Choose a Windows installer or portable archive from [Releases](https://github.com/WANG40929/engineering-document-translator/releases/latest).
2. Open the application, enter your DeepSeek API key under **Settings**, and select a target language.
3. Drop files or folders into the window and click **Start Translation**.
4. When a task finishes, use **Open file** or **Open folder** to view the result.

If an urgent document arrives during translation, select its **Urgent priority** arrow. The application pauses the current file at a safe checkpoint after the in-flight API request, completes the urgent file first, and then resumes the original file from cache. It never force-interrupts while writing an output document.

Source files are never overwritten; translated files receive a language suffix. The interface can follow Windows automatically or be set to Simplified Chinese, English, Russian, Spanish, French, or German.

### Supported documents

| Format | Processing | Mainly preserved |
|---|---|---|
| PDF | Automatic smart reflow or strict in-place placement; translated-only and bilingual output | Images, vector drawings, page sizes, and page count |
| DOCX | Body text, tables, headers, and footers | Paragraphs, tables, and primary character styles |
| XLSX / XLSM | String cells only | Formulas, values, styles, and workbook structure |
| CSV / TSV | Detected encoding and delimiter | Rows, columns, and delimiters |
| DOC | Conversion and save through local Microsoft Word | Legacy `.doc` format; Word is required |

Only existing text layers are translated. Scanned images, outlined PDF text, and pages without a text layer are left unchanged.

### Version 1.4.2 highlights

- **True urgent preemption:** safely pauses the active file, translates the selected urgent file first, then resumes the original task from cache.
- **Cleaner task selection:** removes the dotted current-cell focus frame while retaining row selection and keyboard access.
- **Stronger PDF defect detection:** checks partial glyph clipping, newly introduced line overlap, and severe structured-line collapse.
- **Safer complex layouts:** prevents differently colored notice content from being merged and confines translated table text to its original cell.
- **Fail-safe repair:** keeps the original smart-layout page when a repair cannot place every text group.

### Version 1.4.0 PDF quality highlights

- **Post-generation PDF quality scan:** Every page is checked for hidden or clipped text, collapsed content, abnormal distribution, and unreadably small fonts.
- **Selective repair:** Only flagged pages are retranslated with an adaptive in-place layout that protects tables and fixed regions.
- **Verification after repair:** Reports record the initial scan, repaired pages, and a second verification pass, with residual pages called out for review.
- **Safer long paragraphs and contents pages:** Translation context is isolated by page, natural wrapped lines are grouped, and tables, bullets, technical identifiers, and contents entries are kept separate.
- **Mono and bilingual consistency:** Repaired pages are written back to both translated-only and bilingual PDFs without changing page count or page size.
- **Readable font floor:** Adaptive repair does not shrink translated body text below 5.5 pt.

### PDF engine and terminology

Smart layout uses [BabelDOC](https://github.com/funstory-ai/BabelDOC) for reports, manuals, and prose-heavy documents. Version 1.4.0 checks its output page by page and selectively repairs flagged pages with adaptive in-place placement. Strict placement remains available for drawings, title blocks, equipment labels, and short text. Windows Setup Full and Portable Full include BabelDOC. Portable Lite falls back safely to strict placement when the engine is unavailable.

BabelDOC, its layout models, and fonts are application resources, not part of the 100 MB translation cache. The API key is passed through a per-task temporary configuration, deleted after the task, and redacted from backend errors.

User-supplied glossaries can be CSV, TSV, TXT, or XLSX. The selected glossary is remembered and reused for later files. Smart PDF mode can extract terms within the current document, but v1.4.0 **does not automatically build a permanent, reviewable terminology library**. The translation cache is not a terminology database.

### Known limitations

- Scanned pages require OCR; pages without a text layer are left unchanged by default.
- Dense PDF title blocks or substantially longer translations may require smaller fonts.
- Text inside DOCX text boxes, SmartArt, and embedded objects is not currently processed.
- Legacy `.doc` support requires Microsoft Word.
- Test representative files for terminology and layout before a large batch.

### Run from source

Python 3.10 or later is required:

```powershell
git clone https://github.com/WANG40929/engineering-document-translator.git
cd engineering-document-translator
python -m pip install -r requirements.txt
python -m translator_app
```

### Roadmap

- [ ] Reviewable, reusable automatic terminology library
- [ ] Optional OCR module
- [ ] Clearer translation quality reports
- [ ] Automatic update notifications

If this project is useful, please consider giving it a **Star**. Bug reports and suggestions are welcome in [Issues](https://github.com/WANG40929/engineering-document-translator/issues).

---

## License / 许可

AGPL-3.0-or-later. PyMuPDF is available under the AGPL or a commercial license. Closed-source commercial distribution requires an appropriate commercial license or a replacement PDF engine. See [LICENSE.txt](LICENSE.txt) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

本项目采用 AGPL-3.0-or-later。PyMuPDF 使用 AGPL / 商业双重许可；闭源商业分发需要购买相应商业许可或更换 PDF 引擎。
