# v1.5.0 验证报告 / Verification Report

## v1.5.0 多供应商回归 / Multi-provider regression

- 2026-08-06 使用项目 PySide6 打包环境运行 120 项自动化测试，全部通过。
- 覆盖 OpenAI-compatible、Anthropic Messages、Azure OpenAI 请求格式与响应解析；使用模拟响应，没有调用付费 API。
- 覆盖 18 个内置预设、本地无密钥接口、旧 DeepSeek 配置与密钥迁移、多配置 DPAPI 加密、缓存隔离、连接模型列表、故障备用和智能 PDF 降级。
- 六种界面语言、设置页滚动布局、主窗口、紧急插队以及原有 PDF/DOCX/XLSX/CSV 回归全部通过。

- On 2026-08-06, all 120 automated tests passed in the packaged PySide6 environment.
- Coverage includes OpenAI-compatible, Anthropic Messages, and Azure OpenAI request/response formats using mocked network responses only.
- Coverage includes 18 presets, keyless local servers, legacy migration, per-profile DPAPI storage, cache isolation, model discovery, failover, and smart-PDF fallback.
- All six UI languages, settings layout, main window, urgent preemption, and existing PDF/DOCX/XLSX/CSV regressions passed.

## 中文

### 自动化测试

- 正式 Windows 构建环境发现 75 项：**75 项通过，0 项跳过，0 项失败**。
- 打包后的主程序使用隔离用户数据目录和离屏界面启动，7 秒后进程仍正常响应；随后由测试脚本正常清理。
- 新增覆盖：PDF 坏页检测、隐藏文字、不可读字号、内部占位符泄漏、选择性换页、双语页重建、段落身份标记错配、项目符号清理和源文碎片清理。
- `compileall` 和 `git diff --check` 均通过。

### 294 页真实 PDF 回归

- 样本：`KZ5001-MBL-&ADZ050-R-355315_B_0.pdf`，共 294 页，包含目录、警告框、项目符号、照片、工程示意图和密集表格。
- 对旧智能排版译文的初检耗时 **8.78 秒**，自动命中 **46 页**，覆盖文字隐藏或裁切、内容塌缩、段落合并、异常小字号和占位符泄漏。
- 自适应修复处理 **981 个文字段落**；正常页面不重译，页数和页面尺寸保持不变。
- 修复后第二次全量扫描耗时 **9.00 秒**，结果为 **0 个异常页**。
- 第 2、7、27、33、50、60、87、162、197、257、292 页已使用 Poppler 渲染检查；目录、警告框、长项目符号、说明框和表格均未见裁切或错位。
- 第 50 页曾在中间验证中暴露短行串段和 `UDT_0000` 泄漏；加入段落身份标记后重新验证，21 个段落全部正确映射，最终整份 PDF 未发现内部占位符或 Unicode 替换字符。
- 第 87 页改为使用原提示框右边界而不是页面右边界，长中文段落正确换行；该规则随后重新应用到全部命中页。
- 最终纯译文 PDF 为 294 页、22.87 MB；最终双语 PDF 为 294 页、43.53 MB。双语页按原文/译文左右并排重建，抽检第 27、50、87 页通过。

### Windows 成品与覆盖升级验证

- 轻量免安装版为 **67.8 MiB**，内置引擎免安装版为 **506.0 MiB**，内置引擎安装版为 **314.3 MiB**。
- 三个发布文件的 SHA-256 均与 `SHA256SUMS.txt` 独立复算结果一致；两个 ZIP 的顶层结构、文件数量和隐私文件扫描通过。
- 完整包包含通过版本冒烟测试的 BabelDOC 0.6.4，且没有启动器构建目录、Python 缓存、用户配置、API 密钥或翻译缓存。
- v1.4.0 与已安装的 v1.3.0 使用相同 `AppId`；安装器启用旧目录继承、旧进程关闭和版本管理目录原位替换。电脑上现有 v1.3.0 的自定义安装目录 `E:\APP\DocumentTranslator` 可被识别，用户配置和缓存位于独立的 LocalAppData 目录，不参与程序文件替换。

### 结论

v1.4.0 的“智能排版 → 全文质量扫描 → 选择性问题页修复 → 再次复检”流程在真实 294 页工程手册上可行。已知典型问题页和自动检出的风险页均得到修复，自动化与视觉回归通过。

---

## English

### Automated tests

- The Windows release environment discovered 75 tests: **75 passed, 0 skipped, and 0 failed**.
- The packaged GUI was started with an isolated data directory and an off-screen display. It remained responsive after seven seconds and was then cleanly removed by the smoke-test script.
- New coverage includes PDF defect detection, hidden text, unreadable fonts, internal-placeholder leakage, selective page replacement, bilingual-page rebuild, segment-identity swaps, generated-bullet cleanup, and stray-source-fragment cleanup.
- `compileall` and `git diff --check` passed.

### Real 294-page PDF regression

- Sample: `KZ5001-MBL-&ADZ050-R-355315_B_0.pdf`, 294 pages with a contents section, warning boxes, bullets, photographs, engineering diagrams, and dense tables.
- The initial scan of the former smart-layout output took **8.78 seconds** and flagged **46 pages** for hidden or clipped text, collapsed content, merged blocks, unreadably small fonts, or leaked placeholders.
- Adaptive repair processed **981 text segments** while leaving pages that passed untouched and preserving page count and page dimensions.
- The second full-document scan took **9.00 seconds** and reported **zero remaining issues**.
- Pages 2, 7, 27, 33, 50, 60, 87, 162, 197, 257, and 292 were rendered with Poppler and reviewed. Contents entries, warning boxes, long bullets, notice panels, and tables showed no clipping or displacement.
- An intermediate page-50 run exposed short-line mapping corruption and `UDT_0000` leakage. Segment identity markers eliminated the swap; the final document contains no internal placeholders or Unicode replacement characters.
- Page 87 now wraps to the original notice-container boundary instead of the page edge, and that boundary rule was reapplied to every flagged page.
- The final translated-only PDF has 294 pages and is 22.87 MB. The rebuilt bilingual PDF has 294 pages and is 43.53 MB; side-by-side pages 27, 50, and 87 passed visual review.

### Windows artifacts and in-place upgrade

- Portable Lite is **67.8 MiB**, Portable Full is **506.0 MiB**, and Setup Full is **314.3 MiB**.
- Independently recomputed SHA-256 hashes match `SHA256SUMS.txt` for all three artifacts. Both ZIP topologies, file counts, and privacy scans passed.
- The Full package includes a version-smoke-tested BabelDOC 0.6.4 runtime and excludes launcher build trees, Python caches, user configuration, API credentials, and translation caches.
- v1.4.0 retains the v1.3.0 `AppId`, previous-directory discovery, application shutdown, and atomic replacement of version-managed directories. The existing custom v1.3.0 location `E:\APP\DocumentTranslator` is discoverable, while settings and cache remain in a separate LocalAppData directory.

### Conclusion

The v1.4.0 smart-layout, full-document scan, selective repair, and verification pipeline is feasible on the real 294-page engineering manual. All known representative failures and every automatically flagged page were repaired, and automated plus visual regression passed.

---

## v1.3.0 历史验证 / Historical verification

## 中文

### 自动化测试

- **结果：66 项全部通过。**
- 覆盖范围包括 PDF、DOCX、Word 合并单元格去重、XLSX、CSV、Excel 内嵌图片、缓存清理、配置迁移、密钥保护、双语占位符计数、截断 JSON 拆分、长段隔离、失败重试、并行批次、限速恢复、PDF 多输出复用、内置引擎优先级、后台进程清理、删除/停止状态、孤立窗口检查、界面多语言、最小窗口布局和安装器中文配置。

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

### 真实 Word 箱单回归

- 样本：`Packing_List_Almaty_PS_101_20250604_093541.DOCX`，包含 9 个表格、3 个节、合并单元格及 1767 字符的德英双语出口管制说明。
- 完成时间：**46.17 秒**；438 个不同文本全部完成，报告为 0 个失败。
- 合并单元格去重后实际翻译 2946 个段落，避免重复处理同一 XML 段落。
- 输入和输出均保留 9 个表格、3 个节及 11703 个表格/页眉页脚段落引用。
- 长说明合并为自然中文，`AL:9X9999` 与 `ECCN: 9X9999` 各保留一次；未发现 `UDT_` 内部占位符泄漏。

### Windows 成品验证

- 免安装轻量版：67.80 MiB；免安装完整版：506.10 MiB；安装完整版：314.66 MiB。
- 本次新构建的轻量版主窗口约 **1.85 秒**出现，桌面完整版约 **2.14 秒**出现；两次自动退出冒烟测试的退出码均为 0。
- 两个 ZIP 均通过完整 CRC 检查，内部没有非 ASCII 或不安全路径。
- 完整版与安装版内置 BabelDOC 0.6.4；Excel 图片所需的 Pillow 及许可证已包含。
- 安装器无参数启动时自动选择简体中文，语言列表完整显示六种语言；欢迎页、按钮和退出提示均通过中文界面检查。
- 中文静默安装测试用时约 46.47 秒，卸载约 5.16 秒，退出码均为 0，卸载后安装目录完整删除。

---

## English

### Automated tests

- **Result: all 66 tests passed.**
- Coverage includes PDF, DOCX, merged-cell deduplication, XLSX, CSV, embedded Excel images, cache cleanup, configuration migration, key protection, bilingual placeholder counting, truncated-JSON splitting, long-segment isolation, retry behavior, concurrent batches, rate-limit recovery, duplicate multi-output PDFs, bundled-engine precedence, background-process cleanup, delete/stop state handling, orphan-window checks, interface localization, minimum-window layout, and installer localization.

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

### Real Word packing-list regression

- Sample: `Packing_List_Almaty_PS_101_20250604_093541.DOCX`, containing nine tables, three sections, merged cells, and a 1,767-character German/English export-control notice.
- Completion time: **46.17 seconds**; all 438 unique texts completed with zero failed files.
- The merged-cell pass translated 2,946 real paragraphs without repeatedly processing the same XML paragraph.
- Input and output both retained nine tables, three sections, and 11,703 table/header/footer paragraph references.
- The long notice was merged into natural Chinese with one `AL:9X9999` and one `ECCN: 9X9999`; no internal `UDT_` placeholder leaked.

### Windows artifact verification

- Portable Lite: 67.80 MiB; Portable Full: 506.10 MiB; Setup Full: 314.66 MiB.
- In the fresh build, the Lite main window appeared in about **1.85 seconds** and the desktop Full build in about **2.14 seconds**; both auto-exit smoke tests returned code 0.
- Both ZIP files passed complete CRC checks and contained no non-ASCII or unsafe paths.
- Full and Setup include BabelDOC 0.6.4; Pillow and its license are bundled for embedded Excel-image preservation.
- Without a language argument, Setup automatically selected Simplified Chinese and displayed all six languages; the welcome page, buttons, and exit prompt were verified in Chinese.
- A silent Chinese installation took about 46.47 seconds and uninstallation about 5.16 seconds. Both returned code 0, and the installation directory was removed completely.
