# 更新日志 / Changelog

本项目使用语义化版本号。正式安装包请从 [GitHub Releases](https://github.com/WANG40929/engineering-document-translator/releases) 下载。

This project follows semantic versioning. Stable builds are available from [GitHub Releases](https://github.com/WANG40929/engineering-document-translator/releases).

## 1.4.2

### 中文

- 修复智能 PDF 质检的漏报：从整段可见性检查改为逐字检查，可识别只裁掉部分文字或半行文字的情况。
- 新增文字行重叠与结构行异常合并检测，可发现安全标志说明、项目符号和多栏内容被挤到同一位置的问题。
- 提示框排版不再合并不同颜色的标题与正文；表格译文严格使用所属单元格边界，不再跨列或跨行。
- 自适应修复若有任何文字框无法完整写入，将保留原智能排版页，不再用缺字页面覆盖原结果。
- 使用真实 294 页工程手册进行全量扫描，并以加长中文字符压力样本复检全部问题页；新增相关自动化回归。
- 同时包含 v1.4.1 的紧急插队与任务表格焦点优化。

### English

- Replaced whole-span visibility checks with per-glyph inspection so partially clipped text and half-hidden lines are detected.
- Added line-overlap and severe structured-line-collapse detection for safety labels, bullets, and multi-column content.
- Prevented differently colored notice headings and body text from being merged, and confined table translations to their original cell boundaries.
- Keeps the original smart-layout page whenever adaptive repair cannot place every text group.
- Regressed the complete 294-page engineering manual and reran every flagged page with deliberately expanded CJK text.
- Includes the v1.4.1 urgent-preemption and task-focus improvements.

## 1.4.1

### 中文

- 新增真正的紧急插队：正在翻译时可将等待中或新添加的文件设为紧急任务，当前文件会在安全检查点暂停，紧急文件完成后再从缓存继续。
- 插队采用协作式暂停：等待正在进行的接口请求结束，并避免在保存成品时强制终止，从而防止损坏输出文件。
- 紧急任务、暂停中和已暂停状态会在任务列表与底部状态栏明确显示，紧急任务会自动移动到队列前方。
- 移除任务表格的单元格虚线焦点框，同时保留整行选择和键盘操作。
- 新增动态任务队列、运行中新文件插入及“原任务—紧急任务—原任务恢复”回归测试。

### English

- Added true urgent preemption: a waiting or newly added file can become urgent while translation is running; the active file pauses at a safe checkpoint and resumes from cache after urgent work completes.
- Uses cooperative pausing: finishes the in-flight API request and avoids force termination while an output file is being saved.
- Shows clear urgent, pausing, and paused states in the task list and footer, and moves urgent work to the front automatically.
- Removed the dotted table-cell focus frame while preserving row selection and keyboard access.
- Added regressions for the dynamic queue, newly inserted urgent files, and the active–urgent–resume execution order.

## 1.4.0

### 中文

- 智能 PDF 生成后新增逐页排版质检，自动识别文字隐藏或裁切、内容纵向塌缩、段落异常合并和低于 5.5 pt 的不可读字号。
- 命中问题时只重新翻译并替换相应页面，不重复处理已经通过检查的页面。
- 新增自适应 PDF 修复引擎：正文自然换行可合并处理，表格、固定区域、项目符号、页眉和技术编号保持独立。
- 修复任务按页隔离翻译上下文，避免大型文档跨页映射污染；清理由模型生成的重复项目符号、私用区字符和残留源文首字母。
- 为每个接口段落增加不会写入成品的身份标记校验，拒绝串段、重复编号和意外编号；为避免复用旧的潜在污染结果，v1.4.0 使用新的缓存策略。
- 纯译文与双语对照 PDF 会同步重建修复页，同时保持页数、页面尺寸和其他页面不变。
- 修复完成后执行第二次质量复检，并在任务报告中记录初检、修复和复检结果；页码列表改为紧凑区间显示。
- 新增真实 294 页工程手册回归，覆盖目录挤压、警告文本裁切、项目符号塌缩、说明框错位和表格小字号等问题。

### English

- Added a post-generation page-by-page quality scan for smart PDFs, detecting hidden or clipped text, vertical collapse, merged blocks, and fonts below the 5.5 pt readability floor.
- Retranslates and replaces only flagged pages, leaving pages that passed untouched.
- Added an adaptive PDF repair engine that groups natural prose wrapping while keeping tables, fixed regions, bullets, headers, and technical identifiers separate.
- Isolated repair translation by page to prevent cross-page mapping contamination in large documents, and removed generated bullets, private-use glyphs, and stray source initials.
- Added per-segment identity-marker validation to reject swapped, duplicate, and unexpected IDs; v1.4.0 uses a new cache policy so potentially polluted older mappings are not reused.
- Rebuilds repaired pages consistently in translated-only and bilingual PDFs while preserving page count, page size, and unaffected pages.
- Runs a second verification scan after repair and records initial scan, repair, and verification results in the task report; page lists are shown as compact ranges.
- Added a real 294-page engineering-manual regression covering contents-page crowding, clipped warning text, collapsed bullets, notice-box displacement, and unreadably small table text.

## 1.3.0

### 中文

- 界面新增简体中文、英语、俄语、西班牙语、法语和德语，可跟随 Windows 或在设置中手动切换。
- Windows 发布版调整为安装完整版、免安装完整版和免安装轻量版；安装完整版默认内置 BabelDOC。
- 发布包和内部文件使用 ASCII 安全名称，并附带可直接阅读的 `ReadMe.html` 与 `ReadMe.txt`。
- 改为文件夹式程序结构并延迟加载翻译组件，配合轻量启动画面，明显缩短双击后的等待时间。
- PDF 进度现在显示解析、版面分析、术语、翻译、排版、字体和保存等真实阶段，并提供动态预计剩余时间。
- 已完成任务新增“打开文件”和“打开文件夹”操作。
- 在不降低模型、术语检查或排版质量的前提下并行处理独立翻译批次；加入自适应限速、失败退让和逐批缓存检查点。
- 截断或损坏的大批次 JSON 会自动拆小重试；重复 PDF 会完整复用纯译文和双语输出。
- 增加 Excel 内嵌图片保护；完整版优先使用随软件验证过的内置 PDF 引擎。
- 运行中关闭窗口会先停止任务并清理后台引擎；修复最小窗口下的控件重叠和多语言截字。
- 保持 100 MB 译文缓存上限不变，超限后仍按时间清理最旧记录。
- 修正多语言输出文件识别，避免已翻译文件被再次加入任务。
- Windows 安装程序现已内置简体中文语言包，并在每次启动时按 Windows 界面语言自动选择，避免旧安装程序记住非中文选项。
- 修复纯目标语言合并德英双语段落时重复技术编号被误判为缺失的问题，并避免把 `Endverwender`、`end-user` 等普通词误识别为 EN 标准号。
- Word 合并单元格现在只处理一次真实段落；大型箱单显著减少重复遍历，同时保留表格结构。
- 删除最后一个任务后底部状态恢复为“就绪”；停止时不再被旧进度覆盖，也不再弹出孤立的小进度窗。
- 重新绘制“打开文件”“打开文件夹”和“删除”线条图标，并补齐禁用、悬停和按下状态。

### English

- Added Simplified Chinese, English, Russian, Spanish, French, and German interfaces with automatic Windows-language detection and a manual setting.
- Added Windows Setup Full, Portable Full, and Portable Lite editions; Setup Full includes BabelDOC by default.
- The Windows installer now includes Simplified Chinese and detects the Windows UI language on every launch, preventing an older non-Chinese choice from being carried forward.
- Switched release and internal filenames to ASCII-safe names and included readable `ReadMe.html` and `ReadMe.txt` files.
- Reduced launch delay with a folder-based build, lazy loading of translation components, and a lightweight splash screen.
- Added real PDF stage progress for parsing, layout analysis, terminology, translation, typesetting, fonts, and saving, together with a dynamic ETA.
- Added **Open file** and **Open folder** actions for completed tasks.
- Improved throughput without lowering model, terminology-review, or layout quality by using concurrent independent batches, adaptive rate limiting, retry backoff, and per-batch cache checkpoints.
- Added automatic split recovery for truncated or malformed batch JSON and complete reuse of translated-only plus bilingual outputs for duplicate PDFs.
- Preserved embedded Excel images and made Full editions prefer their tested bundled PDF engine over stale system copies.
- Closing during a task now waits for background-engine cleanup; minimum-window overlap and multilingual clipping were fixed.
- Kept the translation cache limit at 100 MB with age-based cleanup of the oldest entries.
- Improved recognition of translated filenames in all supported languages to prevent accidental reprocessing.
- Fixed false missing-code failures when target-only translation merges parallel German/English text, and stopped ordinary words such as `Endverwender` and `end-user` from being mistaken for EN standard numbers.
- Processed each real Word paragraph only once across merged cells, reducing duplicate work in large packing lists while preserving table structure.
- Restored the footer to **Ready** after the last task is removed, prevented stale progress from overwriting **Stopping**, and removed the orphan progress popup.
- Redrew the **Open file**, **Open folder**, and **Remove** line icons with proper disabled, hover, and pressed states.

## 1.2.0

### 中文

- 新增双 PDF 引擎：报告和说明书可使用 BabelDOC 智能重建段落，图纸和短标签保留原位保版模式。
- PDF 可输出纯译文、中外文对照，或同时生成两种文件；附加输出会写入任务报告。
- 自动模式根据段落密度选择引擎；未安装 BabelDOC 时自动回退，不影响原有格式。
- 接入 BabelDOC 真实处理阶段、进度与停止检查，大文件按最多40页分段处理。
- DeepSeek Key 使用任务专用临时配置传递，结束即删除，后端错误统一脱敏。
- CSV、TSV、TXT、XLSX 术语表都会转换成 BabelDOC 标准术语格式并在智能 PDF 中使用。
- 区分100 MB译文缓存与约1 GB可选布局模型资源，模型不会被缓存清理误删。
- GitHub Release 同时提供内置 BabelDOC 的完整版和不含 BabelDOC 的轻量版，并新增独立的中英文安装说明。

### English

- Added dual PDF engines: BabelDOC smart paragraph reconstruction for reports and manuals, plus strict in-place placement for drawings and short labels.
- Added translated-only, bilingual, and combined PDF output choices with additional outputs recorded in reports.
- Added automatic engine routing with safe fallback when BabelDOC is unavailable.
- Connected backend stages, progress, stop checks, and 40-page splitting for large documents.
- Passed the DeepSeek key through a per-task temporary configuration and redacted backend errors.
- Converted all supported glossary formats into BabelDOC's standard glossary schema.
- Separated the 100 MB translation cache from optional layout-model resources.
- Added Full and Lite Windows release archives plus bilingual engine-installation instructions.

## 1.1.1

### 中文

- PDF 译文固定以原文字形框的起点为锚点，不再因误判居中而横向移动正文。
- 译文优先保持原字号，并利用相邻空白区域换行；页眉、页码及长句不再被压缩成极小字体。
- 增强 `UDT_0000` 内部占位符还原，兼容模型删除下划线或插入空格的情况。
- DeepSeek 返回多余、缺失或损坏的占位符时只重试受影响文本段，异常结果不会写入缓存。
- 旧缓存中的占位符污染会按条目自动修复；无法安全还原的条目会被删除并重新翻译，无需清空全部缓存。

### English

- Anchored PDF translations to the original glyph-box origin so body text no longer shifts after false center detection.
- Preserved source font sizes by using adjacent whitespace and safe wrapping instead of shrinking headers and long lines to unreadable sizes.
- Restored mangled internal placeholders such as `UDT_0000`, including variants with removed underscores or inserted spaces.
- Retried only segments with missing, extra, or malformed placeholders and prevented invalid responses from entering the cache.
- Added selective self-healing for previously polluted cache entries without clearing unrelated translation history.

## 1.1.0

### 中文

- 按确认视觉稿重新设计无边框主界面：集中显示语言、模型、输出位置、拖放区域、文件状态和单文件进度。
- 界面使用蓝色线条图标；桌面快捷方式与任务栏保留原有黑橙线条和白色圆角背景。
- 翻译运行时显示“停止”按钮，空闲状态自动隐藏。
- 新增设置窗口，包含翻译设置、高级参数和软件介绍。
- 进度改为按实际文字段落计算，并动态显示已用时间和预计剩余时间。
- DeepSeek 返回缺少段落时，保留有效结果并只补译缺失内容；必要时自动拆分批次。
- 翻译任务默认关闭 V4 思考模式，并记录接口结束原因、修复请求和拆分重试信息。
- 失败报告现在包含准确的 PDF 页码和已完成段落数；失败任务不再错误显示 100%。
- 修复批量大小和请求超时配置未真正传入翻译任务的问题。
- 修复 Windows 显示缩放下无边框窗口误判鼠标区域、开始按钮无法点击的问题。
- 使用 Qt 原生缩放手柄恢复四边和四角窗口缩放，避免覆盖内部控件。

### English

- Redesigned the frameless main window around language, model, output, drag-and-drop, file status, and per-file progress.
- Added a lightweight blue line icon in the interface while retaining the original black/orange shortcut icon on a white rounded tile.
- Added a Stop button that appears only while a translation job is running.
- Added a settings dialog with translation options, advanced controls, and an About page.
- Progress now uses real text-unit counts and shows elapsed time plus a dynamic ETA.
- Incomplete DeepSeek JSON responses preserve valid segments and repair only missing IDs, recursively splitting when needed.
- V4 thinking mode is disabled for translation, with finish reasons and recovery diagnostics recorded.
- PDF failures report the exact page and completed segment count, without falsely showing 100% progress.
- Fixed batch-size and request-timeout settings not being passed to translation jobs.
- Fixed incorrect mouse hit testing and an unclickable Start button on scaled Windows displays.
- Restored edge and corner resizing with Qt-native handles that do not overlap application controls.

## 1.0.0

首个正式公开版本 / First stable public release.

### 中文

- 支持 PDF、DOCX、XLSX/XLSM、CSV/TSV 和旧版 DOC。
- PDF 仅处理已有文字层，保留图片、矢量线条、页面尺寸和页数。
- DOCX 使用完整段落上下文，改善拆分文字和双语字段翻译。
- 默认使用 `deepseek-v4-flash`，可选择 `deepseek-v4-pro`。
- 旧模型配置 `deepseek-chat` / `deepseek-reasoner` 自动迁移。
- 增加拖放文件队列、状态管理和避免重复处理。
- 增加纯目标语言模式、残留源语言复核和忽略旧缓存选项。
- 翻译缓存设置 100 MB 上限，超限后按时间清理至约 90 MB。
- API Key 使用 Windows DPAPI 加密保存。
- 主窗口自动居中，并使用正式程序图标。

### English

- Added PDF, DOCX, XLSX/XLSM, CSV/TSV, and legacy DOC support.
- PDF processing translates existing text layers while preserving images, vector drawings, page size, and page count.
- DOCX translation uses full-paragraph context for split runs and bilingual fields.
- Uses `deepseek-v4-flash` by default with optional `deepseek-v4-pro`.
- Migrates legacy `deepseek-chat` and `deepseek-reasoner` configurations automatically.
- Added a drag-and-drop queue, status management, and duplicate-processing prevention.
- Added target-only mode, residual-language review, and cache bypass controls.
- Caps the translation cache at 100 MB and trims it to about 90 MB by age.
- Encrypts the API key with Windows DPAPI.
- Centers the main window on launch and includes the production application icon.
