import sys
from pathlib import Path


vendor = Path(__file__).resolve().parent / ".qt-deps"
if vendor.exists():
    sys.path.insert(0, str(vendor))

from translator_app.qt_gui import main


if __name__ == "__main__":
    main()
