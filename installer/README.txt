Document Translator Windows release build
=========================================

Requirements
------------

1. Windows 10 or 11 x64.
2. 64-bit Python 3.12 available as "python".
3. Internet access the first time Python build dependencies are installed.
4. Inno Setup 6 for the Setup Full EXE:

   winget install --id JRSoftware.InnoSetup --exact

5. A read-only BabelDOC source, either:
   - an existing Full-edition folder containing backend or TranslationEngine; or
   - a BabelDOC 0.6.4 virtual environment containing Scripts\python.exe.
6. BabelDOC assets in %USERPROFILE%\.cache\babeldoc, unless they already exist
   in the portable source.

Build all three editions
------------------------

From the project root:

  powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 `
    -Version 1.3.0 `
    -BabelDocSource "C:\path\to\existing-full-edition"

The source directory is only read. The script never edits or removes it.

Expected output
---------------

  release\DocumentTranslator-v1.3.0-Windows-Setup-Full.exe
  release\DocumentTranslator-v1.3.0-Windows-Portable-Full.zip
  release\DocumentTranslator-v1.3.0-Windows-Portable-Lite.zip
  release\SHA256SUMS.txt

Build only Portable Lite
------------------------

  powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 `
    -Version 1.3.0 -LiteOnly -SkipInstaller

Inspect staging before it is removed
------------------------------------

Add -KeepStaging. Verified staging directories will remain under:

  release\staging\

Rebuild after installing Inno Setup
-----------------------------------

If the ZIP files were built before Inno Setup was installed, rerun with
-SkipAppBuild. The Full staging directory is rebuilt and checked before the
installer is compiled.

Release design
--------------

- The application uses PyInstaller onedir, not onefile, to improve cold start.
- Runtime files use the descriptive ASCII folder ApplicationFiles.
- Full editions use TranslationEngine; Lite does not contain it.
- User documentation is ReadMe.html and ReadMe.txt, not Markdown.
- Legal files are collected under Legal.
- ZIP entry names are validated as ASCII to avoid Windows locale mojibake.
- API keys, config, translation databases, reports, source PDFs, tests,
  __pycache__, and development files fail release verification.
- The Full runtime is pruned conservatively. Models, fonts, CMaps, translation
  logic, and all Python source required by BabelDOC remain unchanged.
