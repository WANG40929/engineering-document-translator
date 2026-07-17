from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

from .engines import CsvEngine, DocEngine, DocxEngine, PdfEngine, XlsxEngine
from .models import FileResult, ProgressCallback, TranslationOptions


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".xlsm", ".csv", ".tsv"}


class TranslationPipeline:
    def __init__(self):
        self.engines = [PdfEngine(), DocxEngine(), XlsxEngine(), CsvEngine(), DocEngine()]

    def engine_for(self, path: Path):
        return next((engine for engine in self.engines if engine.supports(path)), None)

    @staticmethod
    def output_path(source: Path, options: TranslationOptions) -> Path:
        folder = options.output_dir or source.parent
        suffix = options.target_language.upper()
        candidate = Path(folder) / f"{source.stem}_{suffix}{source.suffix}"
        number = 2
        while candidate.exists() or candidate.resolve() == source.resolve():
            candidate = Path(folder) / f"{source.stem}_{suffix}_{number}{source.suffix}"
            number += 1
        return candidate

    @staticmethod
    def _digest(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def run(self, files, translator, options, progress: ProgressCallback | None = None):
        sources = [Path(value) for value in files]
        results: list[FileResult] = []
        # Hash only size groups that may contain duplicates.
        size_counts: dict[int, int] = {}
        for source in sources:
            if source.exists() and source.is_file():
                size_counts[source.stat().st_size] = size_counts.get(source.stat().st_size, 0) + 1
        completed_by_hash: dict[str, FileResult] = {}
        total = len(sources)
        for index, source in enumerate(sources):
            if progress:
                progress(str(source), index / max(total, 1), f"准备处理 {index + 1}/{total}：{source.name}")
            if not source.exists():
                results.append(FileResult(str(source), status="failed", errors=["文件不存在"])); continue
            engine = self.engine_for(source)
            if not engine:
                results.append(FileResult(str(source), status="unsupported", errors=[f"暂不支持 {source.suffix} 格式"])); continue
            digest = self._digest(source) if size_counts.get(source.stat().st_size, 0) > 1 else ""
            previous = completed_by_hash.get(digest) if digest else None
            destination = self.output_path(source, options)
            if previous and previous.output_path and Path(previous.output_path).exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(previous.output_path, destination)
                duplicate = FileResult(str(source), str(destination), "completed", "duplicate copy")
                duplicate.warnings.append(f"与 {Path(previous.input_path).name} 内容相同，复用翻译结果，未调用 API")
                results.append(duplicate)
                continue

            def file_progress(_file, fraction, message):
                if progress:
                    progress(str(source), (index + fraction) / max(total, 1), message)

            result = engine.translate(source, destination, translator, options, file_progress)
            results.append(result)
            if digest and result.status == "completed":
                completed_by_hash[digest] = result
        if progress:
            progress("", 1.0, "批处理完成")
        return results


def write_report(results: list[FileResult], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"translation_report_{timestamp}.json"
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "files": len(results),
            "completed": sum(r.status == "completed" for r in results),
            "failed": sum(r.status == "failed" for r in results),
            "translated_units": sum(r.translated_units for r in results),
        },
        "files": [result.to_dict() for result in results],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def collect_files(path: Path, recursive: bool = True) -> list[Path]:
    iterator = path.rglob("*") if recursive else path.glob("*")
    return sorted(p for p in iterator if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS and not p.stem.endswith(("_ZH", "_EN", "_RU")))

