# ArtefactsOrthoMaker

**Desktop GUI for archaeological 3D artifact pose normalization, orthographic layouts, curved developments, measurements, and reproducible transforms**

> **Current version:** **v2.1.0**.
>
> **License:** v0.4.10 and later use the MIT License. Releases through v0.4.9 published under CC0 1.0 Universal retain their original terms.

## Moving from v1 to v2

After confirming the pose, **Export item** (資料を書き出す) saves the selected drawings, normalized PLY, transforms, one measurement CSV, one QA JSON, and `item_manifest.json` together under `output/<stem>/`. Subsequent exports for the same item are saved as separate revisions. Pottery exports can include orthographic, cylindrical, and fan drawings in the same revision.

**Add data to inventory** (一覧表にデータを追加) appends one row from the saved revision to `output/inventory-qa-measurements.csv`. The item manifest is the handoff for downstream BagIt packaging and report generation. The [v1.0.0 application](archive/v1.0.0/README.md) is archived.

Japanese: [README.md](README.md)  
Development report: [docs/DEVELOPMENT_REPORT.md](docs/DEVELOPMENT_REPORT.md)  
Code review: [docs/CODE_REVIEW_v1.0.0.md](docs/CODE_REVIEW_v1.0.0.md)

> [!WARNING]
> **Model size / triangle count:** AOM does not automatically decimate meshes. About 0.7–1.0 M faces is a comfortable range, 1–2 M faces is recommended, and ~2.5 M faces is a practical upper guide. For broadly comparable ASCII OBJ files, ~2 M faces may be around 150 MB and ~2.5 M around 200 MB, but actual size varies. Inputs larger than **300 MB (300,000,000 bytes)** trigger an advisory warning before load; the user may still continue.

## Overview

Inputs: OBJ / PLY / GLB. Outputs include normalized PLY, Transform JSON/CSV/TXT, orthographic layouts, SVG outlines, sections, pottery cylindrical/fan developments, settings JSON, measurement CSV, and inventories.

OBJ UV seams are preserved by loading OBJ with `process=False, maintain_order=False`; no manual V-coordinate inversion is applied before PyVista/VTK rendering.

Pottery coordinates are Z-up. Cylindrical mapping uses `rho=sqrt(X^2+Y^2)`, `theta=atan2(X,-Y)`, `u=Rref*theta`. Fan development treats adjacent Z/diameter breakpoints as independent frusta; see [docs/DEVELOPMENT_REPORT.md](docs/DEVELOPMENT_REPORT.md) for equations.

Automatic pottery posture estimates the opening side first. Slice estimates the vessel axis from opposing section contours, or from the rim and broad surface orientation for flat forms. It can apply the pose, offer it as a reference, or leave the previous pose in place when the evidence is insufficient. See the [pottery posture guide](README.md#pottery-pose).

Cylindrical/fan output supports **outer / inner / upper** views. Z breakpoints can be set numerically, by slider, or by 3D click; the click is consumed for position selection rather than camera rotation. Existing output names trigger Overwrite / Save As / Cancel; Save As adds `_01`, `_02`, ... consistently across the output set.

Lithic normalized coordinates: X=width, Y=length, Z=thickness. Loaded pose can be preserved or an explicit minimum-volume OBB workflow can be run.

In cylindrical and fan inner views, visible reverse sides of radially outward-facing source triangles are shown in flat blue (`#6699CC`). Classification uses the original triangle winding.

## Raster sizing

Print mode: 150/300 dpi and 50/66.6667/100%. File-size mode: S<=10 MB, M<=50 MB, L<=100 MB, Maximum. Basic raster limits are 16,384 px per side and 100 MP; large-raster preflight can offer reduced output scale.

## Python modules

Main third-party packages: NumPy, SciPy, Trimesh, PyVista, PyVistaQt, VTK/vtkmodules, PySide6, Pillow/PIL, QtPy. See `requirements.txt` for pinned versions.

## Validation

```bash
python -m pip check
python check_environment.py
python self_test.py
```

## Limitations

No automatic large-model proxy is used. Curved-development segment boundary faces are currently assigned by face-centroid Z and clipped, not exactly split. Overlap-buffered segment output is planned but not included.

## Development history

| Version | Main milestone |
|---|---|
| v0.1.x | Pottery pose, Z-up, orthographic core |
| v0.2–0.3 | Lithic mode, OBB, sections |
| v0.4.6 | Preserve loaded lithic pose |
| v0.4.8 | Print/file-size raster output |
| v0.4.9 | Cylindrical/fan developments |
| v0.4.10 | Repeated curved-output workflow, manual Z breakpoints |
| **v1.0.0** | UV-seam-safe OBJ, outer/inner/upper views, cylindrical breakpoints, click/camera separation, overwrite/save-as numbering, settings JSON, >300 MB warning, raster reduction preflight, stable repository cleanup |
| **v2.0.0** | Item export, QA and file manifest, independent append to the inventory |
| **v2.0.1** | Mark exterior backsides in cylindrical and fan inner views in blue (`#6699CC`) |
| **v2.1.0** | Estimate pottery posture from the opening, with section-based Slice axis estimation and quality decisions |

License history: [LICENSE_HISTORY.md](LICENSE_HISTORY.md). Normal use: root `app.py`; historical standalone versions: `archive/versions/`.
