# Version 1.1.0 verification report

- Automated offline tests: 18 passed, covering PDF/DOCX/XLSX/CSV, cache trimming, model migration, DPAPI, incomplete-response recovery, recursive batch splitting, exact PDF failure progress, and queue failure behavior.
- Long-document sample: `KZ5001-MBR10-&ADZ050-R-357315_-_0.pdf` processed offline with an identity translator.
- Long PDF result: 67/67 pages completed, 1,652/1,652 text units processed, 0 warnings, and final progress 100%.
- Visual PDF review: pages 1, 11, 46, and 67 rendered without clipped text, broken drawings, overlaps, or page-geometry changes.
- UI smoke test: the PySide6 application started and exited normally in offscreen mode.
- Packaged EXE: the 68.5 MB PyInstaller build launched successfully and exited through the built-in smoke-test timer.
- UI visual review: the frameless main window and About page match the approved blue-and-white design, with readable Chinese fonts, the line-only header icon, per-file status, progress, ETA, and run-only Stop button.
- UI state check: frameless flag, idle Stop visibility, and stop-request transition were verified programmatically.
- Failure handling: incomplete DeepSeek responses preserve valid IDs and request only missing segments; full invalid batches split recursively instead of failing the entire document immediately.

No live DeepSeek API request was made during verification, so no user token was consumed.
