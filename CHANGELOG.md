# 更新日志 / Changelog

本项目使用语义化版本号。正式安装包请从 [GitHub Releases](https://github.com/WANG40929/engineering-document-translator/releases) 下载。

This project follows semantic versioning. Stable builds are available from [GitHub Releases](https://github.com/WANG40929/engineering-document-translator/releases).

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
