# v1.3.0 验证报告 / Verification Report

## 中文

### 自动化测试

- **结果：58 项全部通过。**
- 覆盖范围包括 PDF、DOCX、XLSX、CSV、Excel 内嵌图片、缓存清理、配置迁移、密钥保护、占位符修复、截断 JSON 拆分、失败重试、并行批次、限速恢复、PDF 多输出复用、内置引擎优先级、后台进程清理、PDF 阶段进度、界面多语言、最小窗口布局和安装器中文配置。

### 真实 PDF 回归

- 样本：4 页 EHS 报告 PDF，包含正文、项目符号、页眉页脚和中英混排内容。
- 本次真实质量验证使用了已配置的 DeepSeek API；报告和日志未记录或暴露 API Key。
- 完成时间：**48.55 秒**。
- 进度反馈：节流后共 **53 次有意义的更新**，覆盖解析、扫描、版面分析、段落、公式与样式、术语、翻译、排版、字体和保存阶段。
- 页面结果：输入和输出均为 **4 页**，每一页的页面尺寸完全一致。
- 文本安全检查：未发现 `UDT_` / `__UDT` 内部占位符、Unicode 替换字符或超出页面边界的文字范围。
- 字号范围：原文 **6–12 pt**，译文 **5.98–11.04 pt**，未出现异常极小或异常放大的字体。
- 视觉检查：已逐页渲染并检查全部 4 页，未发现页面丢失、页面尺寸变化或明显越界文字。

### 结论

v1.3.0 的核心翻译流程、真实 PDF 进度、版式安全检查和六种界面语言均通过本轮回归验证。

### Windows 成品验证

- 免安装轻量版：67.80 MiB；免安装完整版：506.10 MiB；安装完整版：314.66 MiB。
- 全新免安装构建显示启动画面约 2.37 秒、主窗口约 2.65 秒；安装版主窗口约 2.31 秒。
- 两个 ZIP 均通过完整 CRC 检查，内部没有非 ASCII 或不安全路径。
- 完整版与安装版内置 BabelDOC 0.6.4；Excel 图片所需的 Pillow 及许可证已包含。
- 安装器无参数启动时自动选择简体中文，语言列表完整显示六种语言；欢迎页、按钮和退出提示均通过中文界面检查。
- 中文静默安装测试用时约 46.47 秒，卸载约 5.16 秒，退出码均为 0，卸载后安装目录完整删除。

---

## English

### Automated tests

- **Result: all 58 tests passed.**
- Coverage includes PDF, DOCX, XLSX, CSV, embedded Excel images, cache cleanup, configuration migration, key protection, placeholder recovery, truncated-JSON splitting, retry behavior, concurrent batches, rate-limit recovery, duplicate multi-output PDFs, bundled-engine precedence, background-process cleanup, PDF stage progress, interface localization, minimum-window layout, and installer localization.

### Real-PDF regression

- Sample: a four-page EHS report PDF containing body text, bullet lists, headers, footers, and mixed-language content.
- The configured DeepSeek API was used for this real quality-assurance run only; no API key was written to the report or logs.
- Completion time: **48.55 seconds**.
- Progress feedback: **53 meaningful updates** after throttling, covering parsing, scanning, layout analysis, paragraphs, formulas and styles, terminology, translation, typesetting, fonts, and saving.
- Page result: both input and output contain **four pages**, with identical dimensions on every page.
- Text safety checks: no `UDT_` / `__UDT` internal placeholders, Unicode replacement characters, or out-of-bounds text spans were found.
- Font-size range: **6–12 pt** in the source and **5.98–11.04 pt** in the output, with no abnormal tiny or enlarged text.
- Visual inspection: all four rendered pages were reviewed; no missing pages, page-size changes, or obvious text overflow were found.

### Conclusion

The v1.3.0 core translation flow, real PDF progress, layout-safety checks, and all six interface languages passed this regression cycle.

### Windows artifact verification

- Portable Lite: 67.80 MiB; Portable Full: 506.10 MiB; Setup Full: 314.66 MiB.
- A fresh portable build showed the splash at about 2.37 seconds and the main window at about 2.65 seconds; the installed main window appeared at about 2.31 seconds.
- Both ZIP files passed complete CRC checks and contained no non-ASCII or unsafe paths.
- Full and Setup include BabelDOC 0.6.4; Pillow and its license are bundled for embedded Excel-image preservation.
- Without a language argument, Setup automatically selected Simplified Chinese and displayed all six languages; the welcome page, buttons, and exit prompt were verified in Chinese.
- A silent Chinese installation took about 46.47 seconds and uninstallation about 5.16 seconds. Both returned code 0, and the installation directory was removed completely.
