# 更新日志 / Changelog

本项目使用语义化版本号。正式安装包请从 [GitHub Releases](https://github.com/WANG40929/engineering-document-translator/releases) 下载。

This project follows semantic versioning. Stable builds are available from [GitHub Releases](https://github.com/WANG40929/engineering-document-translator/releases).

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
