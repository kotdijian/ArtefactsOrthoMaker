from __future__ import annotations

import importlib
import sys
from importlib import metadata
from pathlib import Path

REQUIRED = [
    ("NumPy", "numpy", "numpy"),
    ("SciPy", "scipy", "scipy"),
    ("Trimesh", "trimesh", "trimesh"),
    ("PyVista", "pyvista", "pyvista"),
    ("PyVistaQt", "pyvistaqt", "pyvistaqt"),
    ("VTK", "vtk", "vtk"),
    ("PySide6", "PySide6", "PySide6"),
    ("QtPy", "qtpy", "QtPy"),
    ("Pillow", "PIL", "Pillow"),
]

def version_of(dist_name: str) -> str:
    try:
        return metadata.version(dist_name)
    except metadata.PackageNotFoundError:
        return "unknown"

def main() -> int:
    print("Artifact Pose Normalizer v0.4.2 - environment check")
    print("Python:", sys.version.split()[0])
    print("Executable:", sys.executable)
    print()

    failed = False
    for label, module_name, dist_name in REQUIRED:
        try:
            importlib.import_module(module_name)
            print(f"[OK] {label:<10} {version_of(dist_name)}")
        except Exception as exc:
            failed = True
            print(f"[NG] {label:<10} {exc}")

    try:
        import pose_core
        print("[OK] pose_core   local project module")
    except Exception as exc:
        failed = True
        print(f"[NG] pose_core   {exc}")
        print("     app.py と同じフォルダに pose_core.py があるか確認してください。")

    if failed:
        print("\n依存関係に不足があります。")
        print("仮想環境 venv を有効にしたうえで、次を再実行してください:")
        print("  python -m pip install -r requirements.txt")
        return 1

    print("\nPython modules: OK")

    # Desktop Qt smoke test. This checks the Qt platform plugin as well.
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        print("[OK] Qt QApplication / platform plugin")
        app.quit()
    except Exception as exc:
        print(f"[NG] Qt QApplication: {exc}")
        print("macOS の場合は docs/macos_qt_venv_issue.md も参照してください。")
        return 2

    print("\nENVIRONMENT CHECK PASSED")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
