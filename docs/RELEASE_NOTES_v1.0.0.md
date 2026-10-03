# ArtefactsOrthoMaker v1.0.0 — Release notes

- UV-seam-safe OBJ loading; no manual V flip.
- Repeated pottery orthographic/cylindrical/fan output.
- Cylindrical manual Z breakpoints and per-segment diameters.
- Cylindrical/fan outer / inner / upper views.
- 3D breakpoint click no longer enters camera-rotation mode.
- Overwrite confirmation and numbered _01, _02, ... Save As sets.
- Cylindrical breakpoint/segment settings JSON.
- Advisory warning before loading files >300 MB; loading may continue.
- No automatic point/mesh proxy or decimation in v1.0.0.
- Large-raster reduction preflight.
- Historical apps archived; patches and tracked __pycache__ removed.
- Current release license: MIT; pre-v0.4.10 CC0 history preserved.

## Tested environment

- macOS 27.0 (Build 26A428)
- Python 3.13.7
- NumPy 2.5.2
- SciPy 1.18.0
- Trimesh 5.0.0
- PyVista 0.48.4
- VTK 9.6.2
- PySide6 6.10.3
- Pillow 12.3.0

All v1.0.0 code checks and GUI regression tests passed in this environment.

