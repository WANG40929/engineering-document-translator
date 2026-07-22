"""Small Windows launcher for the relocatable BabelDOC runtime bundle."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    backend_dir = Path(sys.executable).resolve().parent
    python_dir = backend_dir / "python"
    python_exe = python_dir / "python.exe"
    site_packages = backend_dir / "site-packages"
    runtime_home = backend_dir / "runtime"

    if not python_exe.is_file() or not site_packages.is_dir():
        print("BabelDOC portable runtime is incomplete.", file=sys.stderr)
        return 2

    runtime_home.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["PYTHONHOME"] = str(python_dir)
    environment["PYTHONPATH"] = str(site_packages)
    # BabelDOC stores its models below Path.home()/.cache/babeldoc. Pointing
    # HOME and USERPROFILE at the bundle keeps the full edition self-contained.
    environment["HOME"] = str(runtime_home)
    environment["USERPROFILE"] = str(runtime_home)

    command = [
        str(python_exe),
        "-c",
        "from babeldoc.main import cli; cli()",
        *sys.argv[1:],
    ]
    return subprocess.call(command, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
