# Prototype verification report

- Automated offline tests: 13 passed (including PDF/DOCX/XLSX/CSV, split-run DOCX context, cache deduplication and size trimming, model/config migration, token protection, and Windows DPAPI).
- Real engineering sample: `KZ5001-MB-&MPB010-R-370022_-_0.pdf` processed offline with an identity translator.
- PDF result: 6/6 pages retained, all page sizes equal, 335/335 vector drawing objects retained.
- Visual check: rotated component-list page retained table geometry after Unicode font correction.
- Packaged EXE: self-test launch returned exit code 0.
- Queue check: a completed first file is excluded when a second file is added; only the pending file is returned.
- Drag-and-drop check: dropped PDF and DOCX paths are added to the four-column status list.

No DeepSeek API request was made during verification, so no user token was consumed.
