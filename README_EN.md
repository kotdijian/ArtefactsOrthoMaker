# ArtefactsOrthoMaker

[日本語版はこちら](README.md)

**Desktop GUI for orientation normalization, orthographic layouts, surface unwrapping, and measurement export of archaeological 3D models**

> **Current version:** **v2.1.0**
>
> **License:** Releases from v0.4.10 onward use the **MIT License**. Releases through v0.4.9 retain the **CC0 1.0 Universal** terms under which they were published.

<a id="migration-v2"></a>
## Moving from v1 to v2

Version 2.0.0 made AOM an artifact export module for 3D digital archiving. After confirming the orientation, select **Export artifact** to save the selected drawings, normalized PLY, transforms, measurement CSV, quality-control JSON, and input/output manifest together for each artifact. For pottery you can select any combination of orthographic, cylindrical, and fan drawings. Switch between output types to check each one's settings and preview, then select the drawings to save in the export panel.

**Append to inventory** is a separate action. It appends one row containing the QA and measurements for the exported processing revision to `output/inventory-qa-measurements.csv`. The first append creates the CSV, and subsequent appends preserve existing rows. Appending the same revision again adds another row. Lithic section measurements are collected in the `sections_json` column.

Use `item_manifest.json` to hand off results to BagIt or report-generation tools. It records input dependencies and SHA-256 digests, each output file's role and SHA-256 digest, and the artifact and processing revision IDs. The initial artifact ID is the input filename without its extension. Declared OBJ references are recorded. GLB files with external references are marked as unsupported. Downstream tools create BagIt packages and human-readable reports.

The earlier release is available in the [v1.0.0 archive](archive/v1.0.0/README.md).

- [Development report](docs/DEVELOPMENT_REPORT.md)
- [Full code review](docs/CODE_REVIEW_v1.0.0.md)
- [Release notes](docs/RELEASE_NOTES_v1.0.0.md)
- [Repository](https://github.com/kotdijian/ArtefactsOrthoMaker)

Created by **Atsushi Noguchi (@fujimicho on X)**.

## Contents

- [Moving from v1 to v2](#migration-v2)
- [Overview](#overview)
- [Getting started](#python-environment)
  - [1. Install Python](#python-install)
  - [2. Set up the project folder](#folder-setup)
    - [Where to put input files](#input-files)
    - [Supported input files](#supported-input-files)
    - [Output location and when items are skipped](#output-skip)
  - [3. Set up and launch the app](#initial-setup)
    - [First-time setup on macOS](#macos-setup)
    - [First-time setup on Windows](#windows-setup)
    - [Launching again](#run-again)
  - [Environment check script](#environment-check-script)
  - [Troubleshooting](#troubleshooting)
  - [Self-test](#self-test)
  - [Updating an existing installation](#update-procedure)
- [Shared behavior](#common)
- [Pottery mode](#pottery)
  - [Orientation estimation and Slice decisions](#pottery-pose)
- [Lithic mode](#lithic)
- [Image output size](#image-output-size)
- [Large meshes](#large-mesh)
- [Python modules](#python-modules)
- [Environment checks](#environment-check)
- [Limitations](#limitations)
- [License](#license)
- [Development history](#history)

<a id="model-size-warning"></a>
> [!WARNING]
> ## Model size and mesh face count
>
> AOM processes the full input mesh. As a practical guide, **0.7–1 million faces leaves substantial headroom, 1–2 million is the recommended range, and approximately 2.5 million is a practical upper guide**.
>
> For ASCII OBJ files, **2 million faces may use about 150 MB and 2.5 million about 200 MB**. File size varies with the attributes and numeric precision.
>
> **For inputs larger than 300 MB (300,000,000 bytes), AOM warns before loading and lets you decide whether to proceed.** Normal validation, 3D display, orthographic or surface unwrapping, and image generation can take substantially more time and RAM. AOM uses the full mesh without automatic decimation or conversion to a point-cloud proxy.

<a id="overview"></a>
## Overview

ArtefactsOrthoMaker is a Python/PySide6 desktop application. It loads archaeological 3D models in OBJ, PLY, and GLB formats, normalizes their orientation and coordinates as **pottery** or **lithics**, and exports images, measurements, normalized models, and transforms for research, documentation, and desktop publishing.

- Normalized PLY
- Transform JSON, CSV, and CloudCompare text
- Six-view orthographic layouts, SVG outlines, and sections
- Cylindrical and fan unwrap drawings for pottery
- Surface unwrap settings JSON
- Per-artifact measurement CSV
- Quality-control JSON and input/output manifest
- QA and measurement inventory CSV, updated with a dedicated button

<a id="python-environment"></a>
<a id="quick-start"></a>
## Getting started

Use **言語 / Language** at the top of the left panel to switch between **日本語** and **English**. The app remembers your choice across launches.

On your first run, follow steps **1. Install Python → 2. Set up the project folder → 3. Set up and launch the app**. Enter each command on its own line and press Enter in Terminal on macOS or PowerShell on Windows.

<a id="python-install"></a>
### 1. Install Python

**Python 3.13.x** is recommended. Follow the instructions for your operating system.

#### Windows

If `py -3.13 --version` already reports `Python 3.13.x` in PowerShell, proceed to [step 2](#folder-setup).

1. Open the official release page and select **Download Installer (MSIX)**. The same installer supports x64 and ARM64. [Python Install Manager](https://www.python.org/downloads/release/pymanager-264/)
2. Double-click the downloaded `.msix` and select **Install** in Windows App Installer.
3. Open a new **PowerShell** window from the Start menu. Run the first command to install Python 3.13 and the second to check its version.

```powershell
py install 3.13
py -3.13 --version
```

If the displayed version starts with `Python 3.13.`, proceed to [step 2](#folder-setup). When several Python versions are installed, `python --version` may report a different version, so the check above explicitly selects 3.13.

If the legacy Python launcher prevents `py install 3.13` from working, use `pymanager install 3.13` and check it with `pymanager exec -V:3.13 --version`.

#### macOS

If `python3.13 --version` already reports `Python 3.13.x` in Terminal, proceed to [step 2](#folder-setup).

1. Under **Files**, download the **macOS installer** for Apple Silicon and Intel Macs. [Official Python 3.13.17 release](https://www.python.org/downloads/release/python-31317/#files)
2. Open the downloaded `.pkg` and follow the installer prompts.
3. Open a new Terminal window and run the following command.

```bash
python3.13 --version
```

If the output starts with `Python 3.13.`, such as `Python 3.13.17`, proceed to [step 2](#folder-setup).

<a id="folder-setup"></a>
### 2. Set up the project folder

1. Open the repository in a browser and select the green **Code → Download ZIP** option. [GitHub repository](https://github.com/kotdijian/ArtefactsOrthoMaker)
2. Extract the ZIP. On Windows, right-click it and select **Extract All**. On macOS, double-click it.
3. Find the folder containing `app.py`, `pose_core.py`, and `requirements.txt`. A ZIP download normally extracts into `ArtefactsOrthoMaker-main`. This is the project folder. Keep the extracted files together, including the required local modules `pose_core.py`, `item_output.py`, and `ui_language.py`.
4. Put the 3D models to process in the lowercase `input` folder inside the project folder. Create it if needed. Supported formats and output locations are described below.

If you use Git, run `git clone https://github.com/kotdijian/ArtefactsOrthoMaker.git` instead of downloading the ZIP. If you already cloned the repository, use the existing project folder containing `app.py`.

<a id="input-output"></a>
#### Input, output, and the processing queue

> [!IMPORTANT]
> Use the lowercase folder names **`input/` and `output/`**. Both sit next to **`app.py`** in a Git clone or an extracted ZIP.

AOM uses the folder containing `app.py` as its working root. It reads models from `input/` and saves results in `output/`.

```text
ArtefactsOrthoMaker/
├── app.py
├── pose_core.py
├── item_output.py
├── ui_language.py
├── requirements.txt
├── input/                 ← Put the 3D models here
│   ├── pot001.obj
│   ├── pot001.mtl         ← If referenced by the OBJ
│   └── pot001.jpg         ← If referenced by the OBJ
└── output/                ← Results are saved here
    └── pot001/
        ├── pot001_rev.ply
        ├── transform.json
        └── ...
```

If `input` is missing, create it alongside `app.py`. The app creates `output` at startup.

<a id="input-files"></a>
##### Where to put input files

Place each `.obj`, `.ply`, or `.glb` model directly in **`input/` inside your cloned or extracted ArtefactsOrthoMaker folder**.

- The queue scans files directly in `input/`.
- If an OBJ references an MTL file or JPEG/PNG textures, preserve the relative paths used by the OBJ and MTL. A typical setup places the OBJ, MTL, and texture images together in `input/`.
- The app uses `.mtl`, `.jpg`, and `.png` as model assets. The queue lists only the model files.
- Supported model formats are OBJ, PLY, and GLB. STL is unsupported.
- The queue is sorted by filename.
- Input models with the same filename stem collide at the same output folder. The app stops and prompts you to rename them. For example, give `pot001.obj` and `pot001.ply` different stems before adding both.

<a id="supported-input-files"></a>
##### Supported input files

| Format | Extension | Support |
|---|---|---|
| Wavefront OBJ | `.obj` | Supported. Preserve relative paths to referenced MTL files and textures. |
| Polygon File Format | `.ply` | Supported, including vertex colors. |
| glTF Binary | `.glb` | Supported. The app uses embedded appearance information where possible. |
| STL | `.stl` | Unsupported and omitted from the queue. |

OBJ models with appearance information may have the following companion files.

| Companion file | Examples | How it is used |
|---|---|---|
| Material file | `.mtl` | Loaded when referenced by an OBJ. |
| Texture image | `.jpg`, `.jpeg`, `.png` | Loaded when referenced by the MTL or OBJ. |

A textured OBJ typically looks like this.

```text
ArtefactsOrthoMaker/
└── input/
    ├── pot001.obj
    ├── pot001.mtl
    └── pot001.jpg
```

> [!NOTE]
> Only the `.obj`, `.ply`, or `.glb` model itself appears in the processing queue.

<a id="output-skip"></a>
##### Output location and when items are skipped

Each model uses a folder in `output/` with the same filename stem.

```text
input/pot001.obj
        ↓
output/pot001/
```

A completed export saves `item_manifest.json` in its artifact folder. The first export goes into `output/<stem>/`. Further exports go into `output/<stem>/revisions/<revision-id>/`. Select **Next file** to advance to the next pending artifact.

At startup, the queue skips an artifact with a finalized manifest. For compatibility with earlier versions, an existing artifact folder without `.aom_in_progress` also counts as completed. To process an artifact again, move its existing output folder aside before launching the app.

The inventory is saved to `output/inventory-qa-measurements.csv`. If you want to add an exported artifact to the inventory, select **Append to inventory** before advancing.

<a id="initial-setup"></a>
### 3. Set up and launch the app

The first-time steps create a virtual environment named `venv` and install the packages listed in `requirements.txt`.

<a id="macos-setup"></a>
#### macOS first-time setup

In Terminal, type `cd` followed by a space, drag the project folder from Finder into Terminal, and press Enter. Run `ls` to check that `app.py` and `requirements.txt` are listed.

Create and activate the virtual environment.

```bash
python3.13 -m venv venv
source venv/bin/activate
```

Update the installation tools and install the required packages.

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

Check installed dependencies and the runtime environment.

```bash
python -m pip check
python check_environment.py
```

You can also run the core self-test.

```bash
python self_test.py
```

Before launching, use Finder to copy the `.obj`, `.ply`, or `.glb` models into the lowercase `input/` folder alongside `app.py`. Arrange any OBJ material and texture files as described in [Where to put input files](#input-files). Then launch the app.

```bash
python app.py
```

##### Qt startup errors on macOS

Project testing found a Qt platform-plugin file flags issue in an environment named `.venv`. The standard setup uses the name **`venv`**. [macOS Qt virtual environment issue](docs/macos_qt_venv_issue.md)

Run this command for a minimal Qt startup check.

```bash
python -c 'from PySide6.QtWidgets import QApplication; app=QApplication([]); print("QApplication OK"); app.quit()'
```

<a id="windows-setup"></a>
#### Windows / PowerShell first-time setup

Open the project folder in File Explorer. Type `powershell` in the address bar and press Enter to open PowerShell in that folder. Run `dir` to check that `app.py` and `requirements.txt` are listed.

Create the virtual environment with Python 3.13.

```powershell
py -3.13 -m venv venv
```

If you used `pymanager exec` to check your version in step 1, create the environment with `pymanager exec -V:3.13 -m venv venv`.

Activate the environment.

```powershell
.\venv\Scripts\Activate.ps1
```

If PowerShell displays `running scripts is disabled on this system`, allow script execution for the current PowerShell session, then activate again.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

Install the required packages.

```powershell
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

Run the checks.

```powershell
python -m pip check
python check_environment.py
python self_test.py
```

Before launching, use File Explorer to copy the `.obj`, `.ply`, or `.glb` models into the lowercase `input/` folder alongside `app.py`. Arrange any OBJ material and texture files as described in [Where to put input files](#input-files). Then launch the app.

```powershell
python app.py
```

#### requirements.txt

`requirements.txt` pins the versions of the app's main third-party packages.

```text
numpy==2.5.2
scipy==1.18.0
trimesh==5.0.0
pyvista==0.48.4
pyvistaqt==0.12.0
vtk==9.6.2
PySide6==6.10.3
QtPy==2.4.3
Pillow==12.3.0
psutil==7.2.2
```

Python includes its standard library. Pip automatically installs additional dependencies required by the listed packages. Use `requirements.txt` to install the pinned packages together. See [Python modules](#python-modules) for each package's role.

<a id="run-again"></a>
#### Launching again

Before running `app.py`, check that your models are in the project folder's `input/` directory. Copy in any new models first. Open the same project folder in Terminal or PowerShell, activate the virtual environment, and launch the app.

macOS

```bash
source venv/bin/activate
python app.py
```

Windows

```powershell
.\venv\Scripts\Activate.ps1
python app.py
```

If Windows blocks script execution, follow the steps under [Windows first-time setup](#windows-setup). The queue skips completed artifacts according to the [output and skip rules](#output-skip).

<a id="environment-check-script"></a>
#### `check_environment.py`

This script checks dependencies and the Qt startup environment.

```bash
python check_environment.py
```

It checks NumPy, SciPy, Trimesh, PyVista, PyVistaQt, VTK, PySide6, QtPy, Pillow, psutil, the local `pose_core.py`, and Qt `QApplication` and its platform plugin. A successful check ends with the following message.

```text
ENVIRONMENT CHECK PASSED
```

<a id="troubleshooting"></a>
#### Troubleshooting

##### `ModuleNotFoundError: No module named '...'`

First check that the virtual environment is active.

On macOS, run the following command and look for a path ending in `ArtefactsOrthoMaker/venv/bin/python`.

```bash
which python
```

In Windows PowerShell, run the following command and check that it resolves to `ArtefactsOrthoMaker\venv\Scripts\python.exe`.

```powershell
Get-Command python
```

Then run the installation and checks again.

```bash
python -m pip install -r requirements.txt
python -m pip check
python check_environment.py
```

##### `No module named 'pose_core'`

`pose_core.py` is bundled with the repository. Check that it is alongside `app.py`.

##### `No module named 'scipy'`

Install the required packages together, including SciPy.

```bash
python -m pip install -r requirements.txt
```

##### Qt platform plugin errors

Run the environment check to see whether the Qt step is the only one that fails.

```bash
python check_environment.py
```

On macOS, see [macOS Qt virtual environment issue](docs/macos_qt_venv_issue.md).

<a id="self-test"></a>
#### Self-test

Run the core computation checks.

```bash
python self_test.py
```

On success, the script prints the following message.

```text
SELF TEST PASSED
```

The self-test mainly covers orientation, normals, and mesh I/O. Launch `app.py` to check the pottery and lithic GUIs, 3D views, interactive controls, and orthographic and surface unwrap output.

<a id="update-procedure"></a>
#### Updating an existing installation

From a cloned repository, run these commands.

```bash
git pull
source venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
python check_environment.py
python self_test.py
```

In Windows PowerShell, use this activation command.

```powershell
.\venv\Scripts\Activate.ps1
```

If the virtual environment has multiple dependency problems, recreate `venv` from `requirements.txt` to recover a reproducible setup.

<a id="common"></a>
# Shared behavior

Input units are `mm`, `cm`, or `m`. AOM processes the full mesh, preserves textures or vertex colors where possible, and computes normals for display and processing as needed.

## OBJ UV seams

OBJ uses separate indices for `v` and `vt`, so one geometric vertex can reference multiple UV coordinates. Version 1.0.0 introduced loading with `process=False, maintain_order=False`, which keeps separate render vertices where needed to preserve UV seams. PyVista/VTK receives the original OBJ V coordinates.

## Export workflow

After confirming orientation, select **Export artifact** to save drawings, PLY and transforms, measurements, quality-control data, and the manifest together. Exporting the same artifact again saves a new processing revision.

<a id="pottery"></a>
# Pottery mode

After normalization, `+Z` points up and `X-Y` is horizontal. The selected orientation mode determines the reference for `+Z`.

<a id="pottery-pose"></a>
## Orientation estimation and Slice decisions

The automatic modes **Rim**, **Base**, and **Slice** first find the opening to determine which side is up. If the evidence for the opening direction is insufficient, use **Manual (3 points)** to set the reference plane.

| Mode | Reference for `+Z` |
|---|---|
| **Rim** | Levels the estimated representative rim plane. |
| **Base** | Estimates and levels the base plane on the side opposite the opening. A rounded or incomplete base can make the support plane difficult to determine. |
| **Slice** | Aligns the vessel axis vertically using opposing contours of mesh sections at multiple heights. The geometric median gives section centers that are independent of the in-plane coordinate axes. For shallow bowls or dishes, opposing rim contours and broad vessel surfaces support the axis estimate. |
| **Manual (3 points)** | Levels the plane formed by three points selected in the 3D view. |

Slice checks how much of the vessel contour supports the axis and how stable the estimate is when section positions change.

| Slice decision | App behavior |
|---|---|
| **Accepted** | Applies the estimated orientation. |
| **Provisional** | Asks for confirmation because support for the estimated axis is limited. Select **Yes** to apply it. |
| **Withheld** | Retains the previous orientation. You can set it again using Rim, Base, or Manual. |

When comparing spill-out volume estimates under different orientations, use accepted Slice results in the main comparison and identify any estimates based on a provisional orientation. Angular differences to Rim and Base provide comparison data. When you apply Slice and export, `transform.json` records the decision, reason, and available angular differences to Rim and Base candidates under `posture.pose_quality.slice`.

## Cylindrical unwrapping

```text
rho   = sqrt(X^2 + Y^2)
theta = atan2(X, -Y)
u     = Rref * theta
v     = Z
```

Front (−Y) is `theta=0`, and Back (+Y) is the seam. You can divide the Z range into segments, each with a lower Z, upper Z, reference Z, and reference outer diameter D. Set breakpoints numerically, with the slider, or by clicking the 3D view. In position-picking mode, the 3D click sets the position with camera rotation paused.

The settings JSON records `breakpoints_z_mm` and each segment's `z0_mm / z1_mm / reference_z_mm / diameter_mm`.

## Fan unwrapping

The outer diameters at the base, rim, and optional Z breakpoints define independent conical frusta between adjacent points. Where wall slope changes, the shared circumference maps to arcs of different curvature in the plane. The app outputs these segments separately.

See the equations in the [development report](docs/DEVELOPMENT_REPORT.md#8-土器の円筒扇形展開アルゴリズム).

## Exterior, interior, and top

- **Exterior** renders the unwrapped X–Z geometry as seen from the outside.
- **Interior** reverses depth while keeping the left–right order. Where the reverse side of an outward-facing source triangle is visible, the app uses flat blue (RGB `#6699CC`). It determines triangle orientation from the source mesh's face winding.
- **Top** is a diagnostic projection of the **unwrapped 3D mesh** viewed from +Z. It shows the geometry after unwrapping.

<a id="lithic"></a>
# Lithic mode

Normalized axes are `X=width`, `Y=length`, and `Z=thickness`. You can keep the loaded orientation or run minimum-volume OBB orientation explicitly. The app supports leveling the central X–Z section by rotating about Y, manual X/Y/Z rotations, and export of custom sections.

<a id="image-output-size"></a>
# Image output size

Print settings offer 150 or 300 dpi and 50, 66.6667, or 100% scale.

```text
px/mm(source) = dpi / 25.4 × print_scale
```

File-size targets are S ≤ 10 MB, M ≤ 50 MB, L ≤ 100 MB, and Maximum. The basic safety limits are 16,384 px per edge and 100 MP. The preflight dialog for large images can offer a reduced output scale, such as 50%.

<a id="large-mesh"></a>
# Large meshes

| Mesh size | Approximate ASCII OBJ size | Guidance |
|---:|---:|---|
| 0.7–1 million faces | 50–75 MB | Substantial headroom |
| 1–2 million faces | 75–150 MB | Recommended range |
| About 2.5 million faces | About 200 MB | Practical upper guide |
| 2.5–4 million faces | 200–300 MB | High resource use |
| Over 300 MB | Varies with face count | Warning before loading, with the option to continue |

OBJ file size varies with `v / vt / vn` attributes, numeric precision, and material declarations.

<a id="python-modules"></a>
# Python modules

| Module or package | Main use |
|---|---|
| `numpy` | Vertex and face arrays, coordinates, matrices, and image arrays |
| `scipy` / `scipy.ndimage` | OBB processing and section-fill repair |
| `trimesh` | OBJ, PLY, and GLB I/O, OBB, measurement, and export |
| `pyvista` | 3D display, off-screen rendering, and a VTK wrapper |
| `pyvistaqt` | Embedding PyVista in Qt |
| `vtkmodules` / VTK | Cutting, stripping, planes, picking, and image processing |
| `PySide6` | GUI and event handling |
| `PIL` (Pillow) | PNG generation and compositing, outlines, sections, and scale bars |
| `QtPy` | Qt abstraction used by PyVistaQt |
| `psutil` | Available-memory check before OBJ UV seam analysis |

Standard-library modules include `csv`, `io`, `json`, `math`, `shutil`, `sys`, `tempfile`, `traceback`, `pathlib`, `time`, `xml.etree.ElementTree`, `itertools`, `hashlib`, `struct`, `dataclasses`, and `typing`. The bundled `pose_core.py` provides `MeshAsset`, orientation estimation, transforms, and mesh I/O.

See [requirements.txt](requirements.txt) for tested package versions.

<a id="environment-check"></a>
# Environment checks

```bash
python -m pip check
python check_environment.py
python self_test.py
```

[Qt / PySide6 issues on macOS](docs/macos_qt_venv_issue.md)

<a id="limitations"></a>
# Limitations

- Interpret volume and normals with care for non-watertight meshes.
- Cylindrical unwrapping depends on the reference diameter.
- Multi-segment fan unwrapping uses a piecewise conical-frustum approximation.
- Strong asymmetry, handles, and complex concavities can introduce distortion.
- Faces at segment boundaries are assigned by face centroid and clipped.
- Segment unwrapping currently has no overlap buffer.
- Large models require more RAM and processing time.

<a id="license"></a>
# License

Releases from v0.4.10 onward use the MIT License. Releases through v0.4.9 retain their original CC0 1.0 Universal terms. [License history](LICENSE_HISTORY.md)

Attribution is optional for images, measurements, research results, and work products created with the app. Redistribution of the software follows the license terms of the version being redistributed.

An optional link to this repository and the credit **Created by Atsushi Noguchi (@fujimicho on X)** in publications, web pages, presentations, and other work help people find examples and direct bug reports or feature requests to the repository.

<a id="history"></a>
# Development history

| Version | Main changes |
|---|---|
| v0.1.x | Pottery orientation, Z-up, basic orthographic projection |
| v0.2–0.3 | Lithic mode, OBB, three-axis rotation, sections |
| v0.4.0–0.4.5 | Measurements, sections, six views, and AABB display |
| v0.4.6 | Retain the loaded lithic orientation |
| v0.4.7 | Separate lithic exports |
| v0.4.8 | Print-scale and file-size modes for raster output |
| v0.4.9 | Cylindrical and fan unwrapping for pottery |
| v0.4.10 | Surface unwrap workflow and manual Z breakpoints |
| **v1.0.0** | OBJ UV seam fix, exterior/interior/top views, cylindrical breakpoints, camera rotation paused while picking Z, overwrite confirmation and `_01` suffixes, expanded settings JSON, 300 MB input warning, raster scale reduction during preflight, and repository cleanup |
| **v2.0.0** | Combined artifact export, quality-control JSON, input/output manifest, and independent QA and measurement inventory append |
| **v2.0.1** | Blue (`#6699CC`) for reverse sides of outward-facing triangles in cylindrical and fan interior views |
| **v2.1.0** | Opening-first pottery orientation, plus Slice axis estimation from opposing contours and accepted, provisional, or withheld decisions |

Run **`app.py`** in the repository root. Previous versions are in `archive/versions/`.
