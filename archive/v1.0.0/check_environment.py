from __future__ import annotations
import importlib, sys
from importlib import metadata

REQUIRED=[("NumPy","numpy","numpy"),("SciPy","scipy","scipy"),("Trimesh","trimesh","trimesh"),("PyVista","pyvista","pyvista"),("PyVistaQt","pyvistaqt","pyvistaqt"),("VTK","vtk","vtk"),("PySide6","PySide6","PySide6"),("QtPy","qtpy","QtPy"),("Pillow","PIL","Pillow")]

def ver(name):
    try: return metadata.version(name)
    except metadata.PackageNotFoundError: return "unknown"

def main():
    print("ArtefactsOrthoMaker v1.0.0 - environment check")
    print("Python:",sys.version.split()[0]); print("Executable:",sys.executable)
    failed=False
    for label,module,dist in REQUIRED:
        try: importlib.import_module(module); print(f"[OK] {label:<10} {ver(dist)}")
        except Exception as e: failed=True; print(f"[NG] {label:<10} {e}")
    try: import pose_core; print("[OK] pose_core   local project module")
    except Exception as e: failed=True; print(f"[NG] pose_core   {e}")
    if failed: return 1
    try:
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        print("[OK] Qt QApplication / platform plugin"); app.quit()
    except Exception as e:
        print(f"[NG] Qt QApplication: {e}")
        print("See docs/macos_qt_venv_issue.md on macOS."); return 2
    print("ENVIRONMENT CHECK PASSED"); return 0

if __name__=="__main__": raise SystemExit(main())
