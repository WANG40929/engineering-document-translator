"""Create a Windows-friendly release ZIP with deterministic ASCII member names.

The public package layout intentionally uses ASCII names.  This avoids the
mojibake seen when archives made on one Windows locale are opened on another.
Only the *contents* of the staging directory are written, so users see the
application and ReadMe immediately when opening the archive.
"""

from __future__ import annotations

import argparse
import os
import stat
import zipfile
from pathlib import Path


def validate_member_name(name: str) -> None:
    try:
        name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(f"Release member name is not ASCII: {name}") from exc
    if "\\" in name:
        raise ValueError(f"ZIP member must use forward slashes: {name}")
    if name.startswith("/") or ".." in Path(name).parts:
        raise ValueError(f"Unsafe ZIP member name: {name}")


def zip_directory(source: Path, destination: Path) -> None:
    source = source.resolve(strict=True)
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary = destination.with_suffix(destination.suffix + ".partial")
    temporary.unlink(missing_ok=True)

    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            allowZip64=True,
        ) as archive:
            for path in sorted(source.rglob("*"), key=lambda item: item.as_posix().lower()):
                relative = path.relative_to(source).as_posix()
                validate_member_name(relative)
                if path.is_dir():
                    # Empty folders are intentionally omitted. Runtime folders
                    # are created by the application or engine when needed.
                    continue
                info = zipfile.ZipInfo.from_file(path, arcname=relative)
                info.compress_type = zipfile.ZIP_DEFLATED
                info._compresslevel = 9
                # Preserve a normal read/write file mode for extraction tools
                # while retaining the executable bit if built on another host.
                mode = stat.S_IMODE(path.stat().st_mode)
                info.external_attr = (mode & 0xFFFF) << 16
                with path.open("rb") as source_file, archive.open(info, "w") as target_file:
                    while chunk := source_file.read(1024 * 1024):
                        target_file.write(chunk)
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    zip_directory(args.source, args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
