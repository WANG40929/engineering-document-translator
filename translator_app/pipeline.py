from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

from .engines import BabelDocEngine, CsvEngine, DocEngine, DocxEngine, PdfEngine, XlsxEngine
from .file_types import SUPPORTED_EXTENSIONS, collect_files
from .i18n import tr
from .models import FileResult, ProgressCallback, TranslationOptions


class TranslationPipeline:
    def __init__(self):
        self.strict_pdf_engine = PdfEngine()
        self.smart_pdf_engine = BabelDocEngine()
        self.engines = [self.strict_pdf_engine, DocxEngine(), XlsxEngine(), CsvEngine(), DocEngine()]
        self._dynamic_completed_by_hash: dict[str, FileResult] | None = None

    def begin_dynamic_batch(self) -> None:
        """Preserve exact-duplicate reuse across separately scheduled files.

        The desktop queue runs one file at a time so it can pause between safe
        checkpoints. A persistent digest map keeps the previous whole-batch
        optimization even when urgent files change the execution order.
        """

        self._dynamic_completed_by_hash = {}

    def engine_for(self, path: Path, options: TranslationOptions | None = None):
        if path.suffix.lower() == ".pdf" and options is not None:
            if options.pdf_mode == "smart":
                return self.smart_pdf_engine
            if options.pdf_mode == "auto":
                if self.smart_pdf_engine.available(options) and self.smart_pdf_engine.looks_like_prose(path):
                    return self.smart_pdf_engine
                return self.strict_pdf_engine
        return next((engine for engine in self.engines if engine.supports(path)), None)

    @staticmethod
    def output_path(source: Path, options: TranslationOptions) -> Path:
        folder = options.output_dir or source.parent
        suffix = options.target_language.upper()
        output_tag = f"_{suffix}_DUAL" if source.suffix.lower() == ".pdf" and options.pdf_output == "dual" else f"_{suffix}"
        candidate = Path(folder) / f"{source.stem}{output_tag}{source.suffix}"
        number = 2
        while candidate.exists() or candidate.resolve() == source.resolve():
            candidate = Path(folder) / f"{source.stem}{output_tag}_{number}{source.suffix}"
            number += 1
        return candidate

    @staticmethod
    def _digest(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def _duplicate_additional_path(
        previous_primary: Path,
        previous_additional: Path,
        duplicate_primary: Path,
        index: int,
    ) -> Path:
        relative_tag = ""
        if previous_additional.stem.startswith(previous_primary.stem):
            relative_tag = previous_additional.stem[len(previous_primary.stem):]
        if not relative_tag:
            relative_tag = f"_EXTRA_{index}"
        extension = previous_additional.suffix or duplicate_primary.suffix
        candidate = duplicate_primary.with_name(
            f"{duplicate_primary.stem}{relative_tag}{extension}"
        )
        number = 2
        while candidate.exists():
            candidate = duplicate_primary.with_name(
                f"{duplicate_primary.stem}{relative_tag}_{number}{extension}"
            )
            number += 1
        return candidate

    def run(self, files, translator, options, progress: ProgressCallback | None = None):
        sources = [Path(value) for value in files]
        results: list[FileResult] = []
        # Hash only size groups that may contain duplicates.
        size_counts: dict[int, int] = {}
        for source in sources:
            if source.exists() and source.is_file():
                size_counts[source.stat().st_size] = size_counts.get(source.stat().st_size, 0) + 1
        dynamic_batch = self._dynamic_completed_by_hash is not None
        completed_by_hash = (
            self._dynamic_completed_by_hash if dynamic_batch else {}
        )
        total = len(sources)
        file_fractions = [0.0] * total
        for index, source in enumerate(sources):
            if progress:
                progress(
                    str(source),
                    sum(file_fractions) / max(total, 1),
                    tr(
                        "progress.preparing_file",
                        current=index + 1,
                        total=total,
                        name=source.name,
                    ),
                )
            if not source.exists():
                results.append(
                    FileResult(
                        str(source),
                        status="failed",
                        errors=[tr("error.file_not_found")],
                    )
                )
                continue
            engine = self.engine_for(source, options)
            if not engine:
                results.append(
                    FileResult(
                        str(source),
                        status="unsupported",
                        errors=[
                            tr(
                                "error.unsupported_format",
                                extension=source.suffix,
                            )
                        ],
                    )
                )
                continue
            digest = (
                self._digest(source)
                if dynamic_batch or size_counts.get(source.stat().st_size, 0) > 1
                else ""
            )
            previous = completed_by_hash.get(digest) if digest else None
            destination = self.output_path(source, options)
            if previous and previous.output_path and Path(previous.output_path).exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                previous_primary = Path(previous.output_path)
                shutil.copy2(previous_primary, destination)
                duplicate = FileResult(
                    input_path=str(source),
                    output_path=str(destination),
                    status="completed",
                    engine="duplicate copy",
                    translated_units=previous.translated_units,
                    skipped_units=previous.skipped_units,
                    skipped_pages=list(previous.skipped_pages),
                )
                for additional_index, previous_output in enumerate(
                    previous.additional_outputs,
                    start=1,
                ):
                    previous_additional = Path(previous_output)
                    if not previous_additional.is_file():
                        continue
                    additional_destination = self._duplicate_additional_path(
                        previous_primary,
                        previous_additional,
                        destination,
                        additional_index,
                    )
                    shutil.copy2(previous_additional, additional_destination)
                    duplicate.additional_outputs.append(str(additional_destination))
                duplicate.warnings.append(
                    tr(
                        "error.duplicate_reused",
                        name=Path(previous.input_path).name,
                    )
                )
                results.append(duplicate)
                file_fractions[index] = 1.0
                continue

            def file_progress(_file, fraction, message):
                file_fractions[index] = max(file_fractions[index], min(1.0, max(0.0, fraction)))
                if progress:
                    progress(str(source), sum(file_fractions) / max(total, 1), message)

            result = engine.translate(source, destination, translator, options, file_progress)
            if engine is self.smart_pdf_engine and result.status == "failed":
                smart_errors = list(result.errors)
                result = self.strict_pdf_engine.translate(
                    source, destination, translator, options, file_progress
                )
                if result.status == "completed":
                    result.warnings.insert(
                        0,
                        tr(
                            "warning.smart_pdf_fallback",
                            reason=smart_errors[-1] if smart_errors else "",
                        ),
                    )
            results.append(result)
            if result.status == "completed":
                file_fractions[index] = 1.0
            if digest and result.status == "completed":
                completed_by_hash[digest] = result
        if progress:
            fraction = sum(file_fractions) / max(total, 1) if total else 1.0
            message = (
                tr("progress.batch_complete")
                if all(result.status == "completed" for result in results)
                else tr("progress.batch_with_failures")
            )
            progress("", fraction, message)
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
