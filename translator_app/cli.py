from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .cache import TranslationCache
from .deepseek import DeepSeekTranslator
from .models import TranslationOptions
from .pipeline import SUPPORTED_EXTENSIONS, TranslationPipeline, collect_files, write_report
from .secret_store import SecretStore
from .text_utils import load_glossary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="保留版式的 DeepSeek 文档批量翻译器")
    parser.add_argument("paths", nargs="+", help="文件或文件夹")
    parser.add_argument("--target", default="zh")
    parser.add_argument("--source", default="auto")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--glossary", type=Path)
    parser.add_argument("--api-key", help="建议使用 DEEPSEEK_API_KEY 环境变量或 GUI 安全保存")
    parser.add_argument("--keep-source-language", action="store_true", help="允许译文保留源语言对照")
    parser.add_argument("--no-quality-review", action="store_true", help="关闭残留源语言自动复核")
    parser.add_argument("--force-refresh", action="store_true", help="忽略翻译缓存")
    parser.add_argument("--pdf-mode", choices=("auto", "smart", "strict"), default="auto")
    parser.add_argument("--pdf-output", choices=("mono", "dual", "both"), default="mono")
    parser.add_argument("--babeldoc-path", type=Path)
    args = parser.parse_args(argv)
    files: list[Path] = []
    for value in args.paths:
        path = Path(value)
        files.extend(collect_files(path) if path.is_dir() else [path])
    files = list(dict.fromkeys(path.resolve() for path in files if path.suffix.lower() in SUPPORTED_EXTENSIONS))
    if not files:
        print("没有找到支持的文件。", file=sys.stderr); return 2
    key = args.api_key or SecretStore().load()
    options = TranslationOptions(
        args.source, args.target, args.model, output_dir=args.output_dir, glossary_path=args.glossary,
        pure_target_language=not args.keep_source_language,
        quality_review=not args.no_quality_review,
        force_refresh=args.force_refresh,
        pdf_mode=args.pdf_mode,
        pdf_output=args.pdf_output,
        babeldoc_path=args.babeldoc_path,
    )
    translator = DeepSeekTranslator(
        key, args.model, args.source, args.target, load_glossary(args.glossary), TranslationCache(),
        pure_target_language=options.pure_target_language,
        quality_review=options.quality_review,
        force_refresh=options.force_refresh,
    )
    results = TranslationPipeline().run(files, translator, options, lambda _f, p, m: print(f"[{p:6.1%}] {m}"))
    report_dir = args.output_dir or files[0].parent
    report = write_report(results, report_dir)
    print(f"报告：{report}")
    return 0 if all(item.status == "completed" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
