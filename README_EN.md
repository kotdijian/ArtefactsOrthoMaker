<a id="top"></a>
# ArtefactsOrthoMaker (formerly Artifact Pose Normalizer)

ArtefactsOrthoMaker is a Python GUI application for loading archaeological 3D models in OBJ / PLY / GLB format, normalizing their pose and coordinate system as either **pottery** or **lithic artifacts**, and generating normalized models, transformation matrices, orthographic images, outlines, and section drawings.

The application was upgraded from the original pose-estimation and coordinate-normalization workflow (`pose_core.py`) into a tool for producing orthographic projection layouts.

The current official executable is **`app.py`**. It integrates the pottery functions completed in the v0.1.x series with the lithic functions added in the v0.2–0.3 series. The current `APP_VERSION` is `0.4.3`.

**Important: download this repository as a ZIP file or clone the entire repository.**

**Do not download `app.py` by itself. `pose_core.py` and `requirements.txt` are also required.**

## Navigation

- [Common Specifications](#common)
- [Pottery](#pottery)
- [Lithic Artifacts](#lithic)
- [Measurement CSV Files](#measurements)
- [Output Files and Transforms](#outputs)
- [Python Environment and Running the Application](#environment)

---

<a id="common"></a>
# Common Specifications

## 1. Input and Model Type

Place 3D models in the `input/` folder in the application directory.

Supported formats:

```text
.obj
.ply
.glb
```

STL is not supported.

For OBJ files, referenced appearance information such as MTL and JPEG textures is used whenever possible. PLY vertex colors and GLB appearance information are also supported.

Select the model type in the GUI using `モデル種別` (Model Type).

```text
モデル種別 [ 土器 / 石器 ]
Model Type  [ Pottery / Lithic ]
```

The default is `土器` (Pottery). The model type can be changed after the mesh has been loaded without reloading the mesh, but the current pose-determination state will be reset.

## 2. Input Unit

```text
入力単位 [ mm / cm / m ]
Input Unit [ mm / cm / m ]
```

The unit setting is used to convert view spacing, scale bars, SVG physical dimensions, and related values to millimeters. **The numeric coordinates of the model itself are not rescaled to millimeters.**

Example: if a coordinate value of `1.0` represents 1 m in the source model, select `m`.

## 3. Input Queue and Processed-File Detection

- Supported files in `input/` are processed in ascending filename order.
- If `output/<input-stem>/` already exists, that model is treated as already processed and skipped.
- If files with the same stem but different supported extensions coexist, processing stops to prevent output collisions.
- If `input/` or `output/` does not exist, it is created at startup.

During saving, a temporary folder that does not begin with a dot is used:

```text
output/<stem>.__working__/
```

Only after all outputs have completed successfully is it renamed to:

```text
output/<stem>/
```

This avoids a macOS behavior observed during development in which the hidden attribute of a dot-prefixed temporary directory could persist after renaming.

## 4. Mesh QA, Normals, and Appearance

Mesh information is checked during loading. If normals are missing, the normals required for display and processing are calculated.

Basic policy:

- Do not automatically reduce input mesh vertex density or face count.
- Do not perform automatic decimation.
- Use texture / vertex color information when available.
- Do not assume that outward-facing normals are guaranteed for non-watertight meshes.

## 5. Normalized Model

Regardless of the input format, the normalized model is saved as PLY:

```text
<stem>_rev.ply
```

---

<a id="pottery"></a>
# Pottery

[Back to top](#top) / [Go to Lithic Artifacts](#lithic)

## 1. Basic Pottery Workflow

1. Load the model.
2. Set `モデル種別 = 土器` (Model Type = Pottery).
3. Confirm the input unit and Mesh QA information.
4. Determine the pose using Slice / Rim / Base / Manual.
5. Determine the front orientation by rotation around the Z axis.
6. Configure orthographic views, rendering modes, special drawings, and output formats.
7. Review the orthographic preview if necessary.
8. Click `計測一覧出力` (Export Measurement Inventory).
9. Click `保存して次へ` (Save and Next).

## 2. Pose Determination

Available methods for determining horizontal orientation / tilt:

- `Slice`
- `Rim`
- `Base`
- `Manual (3 points)`

Basic policy:

- Slice determines the pose Z axis from the center axis.
- Rim / Base / Manual fix the tilt using a reference plane.
- When Slice is applied after Rim / Base / Manual, the model is not rotated again; Slice is used only to determine the center-axis position within the fixed pose.
- `orientation_z_axis` and `center_axis` are treated as separate concepts.
- The origin is defined as the intersection between the center axis and the lower `z_min` plane of the post-pose AABB.
- The front orientation is determined manually at the end using only a rotation around the Z axis.

Transform convention:

```text
p_normalized = M_raw_to_normalized @ [x, y, z, 1]^T
```

## 3. Pottery Main 3D View

View directions:

- `Ortho Front`
- `Oblique`

Parallel projection is used.

Display functions:

- Texture / vertex color ON/OFF
- Normal shading ON/OFF
- 20 / 50 / 100 mm display scale
- Zoom 25–400%
- `- / 100% / +` controls and slider
- Mouse-wheel zoom synchronization
- Center axis shown as a purple guide line
- Unnecessary PyVista `Distance` scalar bar is hidden

## 4. Pottery Orthographic Views

Selectable views:

```text
Front
Back
Left
Right
Top
Bottom
```

Basic six-view layout:

```text
              TOP
LEFT        FRONT        RIGHT        BACK
            BOTTOM
```

All views use the same orthographic scale.

Pottery Front camera convention:

- camera side: `-Y`
- looking toward: `+Y`
- up: `+Z`

## 5. Pottery Orthographic Rendering

Basic rendering modes:

1. `テクスチャ / 頂点カラー` (Texture / Vertex Color)
2. `テクスチャ / 頂点カラー + Normal` (Texture / Vertex Color + Normal)
3. `Normalのみ（シェード）` (Normal Only / Shade)

Special drawings:

- `縦断面` (Vertical Section)
- `半截` (Half-Section View)
- `1/4半截` (Quarter Half-Section View)

### Vertical Section

A vertical section is created in the X-Z plane at:

```text
y = (y_min + y_max) / 2
```

using the vertical axis through the X-Y midpoint of the AABB after pose and position normalization.

Since v0.4.2, section line topology and section fill processing have been separated. Paths returned by `vtkCutter` / `vtkStripper` preserve their original **open / closed topology** in line drawings and SVG output. Open paths are not unconditionally connected from end to start, preventing long artificial diagonal lines from being introduced across missing or non-watertight regions.

### Half-Section View

The Front-side half is removed and the model is displayed from the front, with the cut surface shown in black. This is placed inside the composite image rather than saved as an independent panel.

For the black cut-surface fill, the linework paths are not forcibly closed. Instead, a dedicated fill reconstruction is performed in the following order:

```text
section paths from Cutter / Stripper
        ↓
snap nearby endpoints
        ↓
stitch only small gaps with compatible tangent directions
        ↓
fill closed contours using the even-odd rule
        ↓
apply limited raster closing to remaining very small gaps
        ↓
fill the cut surface in black
```

This preserves the original section lines while repairing only small fill gaps caused by minor mesh discontinuities. Large gaps are not automatically bridged.

When multiple closed contours are nested, the even-odd rule alternates filled and unfilled regions so that inner areas are not indiscriminately filled in black.

### Quarter Half-Section View

- Left half: normal Front view
- Right half: half-section state

The Half-Section and Quarter Half-Section views use the same dedicated fill reconstruction described above. Lithic section extraction and layout logic are not part of the v0.4.2 pottery section repair.

### Example Composite Layout

```text
Front Outline | Left | Front | Quarter Half-Section | Half-Section | Right | Back | Vertical Section
```

Top / Bottom are placed above and below Front at the same horizontal position.

## 6. Pottery Outlines and SVG

Output formats:

```text
PNG only
SVG
PNG + outline (derived from SVG)
```

PNG + outline overlays can be applied to:

- Front
- Back
- Left
- Right
- Top
- Bottom

They are not applied to:

- Independent Front-outline panel
- Vertical Section
- Half-Section View
- Quarter Half-Section View

PNG outline widths:

```text
1 px
2 px
3 px
5 px
```

Composite SVG:

```text
<stem>_ortho_outline.svg
```

If Vertical Section is selected, it is also included in the SVG. Half-Section and Quarter Half-Section views are not included because they contain raster rendering.

## 7. Individual Pottery Outputs

When `各面を個別ファイルでも出力` (Also Export Each View as an Individual File) is ON, the selected view PNG / SVG files, Front outline, and section outputs are exported individually.

Half-Section and Quarter Half-Section views are treated as elements of the composite image.

## 8. Pottery Tick Marks

Default view spacing:

```text
10 mm
```

Specifications for the Front center-axis ticks and Top half-section-line ticks:

- Line width: `5 px`
- Gap from the model edge: `1/4` of the view spacing
- Tick length: `1/2` of the view spacing
- Remaining outer gap: `1/4` of the view spacing

For 10 mm spacing:

```text
2.5 mm gap + 5 mm tick + 2.5 mm
```

## 9. Pottery Orthographic Preview

Click `オルソ画像プレビューを開く` (Open Orthographic Image Preview) to open a separate window.

The preview uses the same layout logic as the saved PNG and updates to reflect changes in:

- six-view selection
- Texture / Texture+Normal / Shade
- Vertical Section / Half-Section / Quarter Half-Section
- PNG / PNG + outline
- view spacing
- scale bar
- outline width

The initial display mode is `Fit width`.

Mac:

- trackpad pinch → Zoom
- two-finger scroll → Scroll

Mouse:

- `Ctrl + wheel` → Zoom
- wheel → Scroll

---

<a id="lithic"></a>
# Lithic Artifacts

[Back to top](#top) / [Go to Pottery](#pottery)

## 1. Basic Lithic Workflow

1. Load the model.
2. Select `モデル種別 = 石器` (Model Type = Lithic).
3. Run automatic initial-pose estimation using `oriented_bounds()`.
4. Apply automatic Y-axis correction from the central X-Z section.
5. Review the Front / Right / Bottom three-view display.
6. If necessary, manually adjust rotation around the Y / X / Z axes.
7. Click `姿勢決定` (Confirm Pose).
8. Set the minimum corner of the final bounding box to the origin `(0,0,0)`.
9. Configure orthographic, outline, and section settings.
10. Click `プレビュー確認` (Preview).
11. Move, add, or delete blue section guide lines as necessary.
12. Click `プレビュー確認` again to regenerate the sections.
13. Click `計測一覧出力` (Export Measurement Inventory).
14. Click `保存して次へ` (Save and Next).

Even after `姿勢決定` (Confirm Pose), you can return to the pose-adjustment view using `石器姿勢に戻る` (Return to Lithic Pose), make further adjustments, and confirm the pose again.

## 2. Automatic Initial Pose Estimation for Lithics

When Lithic is selected, a Trimesh minimum-volume oriented bounding box is applied first.

```python
trimesh.bounds.oriented_bounds(
    mesh,
    angle_digits=1,
    ordered=False,
)
```

The three OBB axes are interpreted by dimension and assigned to the lithic coordinate system as:

```text
X = width
Y = length (maximum-length axis)
Z = thickness
```

### Additional Correction Using the Central X-Z Section

After the OBB is applied, the X-Z section at the OBB center is extracted at:

```text
y = 0
```

To handle large meshes efficiently, triangle-plane intersections are computed directly in chunks.

Instead of relying on a single extreme vertex at each end, representative Z values are derived from candidates within the outermost 2% regions. The slope of the line joining the left and right endpoints is then evaluated, and an automatic **Y-axis rotation** is applied so that this line becomes parallel to the X axis.

The automatic lithic pose workflow is therefore:

```text
original
  ↓
minimum-volume OBB
  ↓
X=width / Y=length / Z=thickness
  ↓
central X-Z section
  ↓
automatic Y-axis leveling
  ↓
automatic lithic pose
```

## 3. Lithic Model View

After automatic pose estimation, the main panel on the right displays:

```text
Front (X-Y)
Right (Y-Z)
Bottom (X-Z)
```

The **default display is Shade**.

### Orthographic Net Orientation Convention

Since v0.4.3, the six lithic views follow the same principle as the pottery views: they are arranged according to the **unfolding relationship of a rectangular prism from the Front view**.

```text
              TOP
LEFT        FRONT        RIGHT        BACK
            BOTTOM
```

Corresponding edges of adjacent views are oriented so that they match the connections produced by unfolding a rectangular prism.

In particular, Top / Bottom are oriented as follows:

```text
TOP:
  upper side = side corresponding to Back (-Z)
  lower side = side corresponding to Front (+Z)

BOTTOM:
  upper side = side corresponding to Front (+Z)
  lower side = side corresponding to Back (-Z)
```

Therefore, in Top, which is placed above Front, the **Front side is at the bottom and the Back side is at the top**. In Bottom, which is placed below Front, the **Front side is at the top and the Back side is at the bottom**.

The horizontal orientation also follows the net relationship: screen-right is `+X` in Front, Top, and Bottom.

## 4. Manual Lithic Rotation

The rotation controls in the left panel are ordered:

```text
Y
X
Z
```

Their coordinate meanings are:

```text
Y = length
X = width
Z = thickness
```

Each axis provides:

- `-90°`
- `0°`
- `+90°`
- dial
- numeric input

Manual rotations are additional rotations applied after automatic pose estimation.

## 5. Confirming the Lithic Pose and Setting the Origin

The current pose is finalized when `姿勢決定` (Confirm Pose) is clicked.

After confirmation, the coordinate origin is translated so that the minimum corner of the final axis-aligned bounding box:

```text
(Xmin, Ymin, Zmin)
```

becomes:

```text
(0, 0, 0)
```

You can still return to pose adjustment using `石器姿勢に戻る` (Return to Lithic Pose).

## 6. Lithic Transformation Matrices

For lithic artifacts, transformations are retained in stages.

### original → OBB

Always saved:

```text
transform_original_to_obb.csv
transform_original_to_obb_cloudcompare.txt
```

### OBB → result

If there are automatic corrections, manual rotations, origin translation, or other changes after OBB, and the OBB→result transform is not the identity transform, the following files are saved:

```text
transform_obb_to_result.csv
transform_obb_to_result_cloudcompare.txt
```

If the OBB alone is the final result and OBB→result is the identity transform, the second matrix is not output.

The final combined transformation is saved in `transform.json`.

```text
p_result = M_obb_to_result @ M_original_to_obb @ [x,y,z,1]^T
```

## 7. Lithic Output Panel

The basic lithic outputs are similar to the pottery outputs.

Selectable projection views:

```text
Front
Back
Left
Right
Top
Bottom
```

Basic six-view layout:

```text
              TOP
LEFT        FRONT        RIGHT        BACK
            BOTTOM
```

Rendering modes:

1. `テクスチャ / 頂点カラー` (Texture / Vertex Color)
2. `テクスチャ / 頂点カラー + Normal` (Texture / Vertex Color + Normal)
3. `Normalのみ（シェード）` (Normal Only / Shade)

Output formats:

```text
PNG only
SVG
PNG + outline (derived from SVG)
```

Outline widths:

```text
1 px
2 px
3 px
5 px
```

The lithic version does not provide:

- Half-Section View
- Quarter Half-Section View

## 8. Lithic Preview

Clicking `プレビュー確認` (Preview) **switches the right-side main panel to the orthographic-net preview instead of opening a separate window**.

The default model rendering in the preview is **Shade**. If Shade is turned OFF in the output panel, another selected rendering mode is used.

After changing output-view settings, click `プレビュー確認` again to refresh the preview.

## 9. Lithic Section Settings

Blue section-position guide lines are displayed in the preview.

The blue lines extend **continuously across the entire preview canvas**, not only across the model silhouette.

They are used only for positioning and are not drawn into saved orthographic images. Saved images instead show tick marks indicating section positions.

### Initial Sections

Two sections are defined at the center position by default.

#### Section (X)

An X-Z section extending along the X direction:

```text
y = constant
```

It appears as a horizontal blue guide line in the preview.

#### Section (Y)

A Y-Z section extending along the Y direction:

```text
x = constant
```

It appears as two linked vertical blue guide lines corresponding to Front and Back. Moving one automatically moves the other.

### Section-Line Controls

- Click a blue line to select it.
- Drag to move it.
- `断面追加（X）` (Add Section X)
- `断面追加（Y）` (Add Section Y)
- `削除` (Delete)

Line selection is based on the guide line nearest to the click position in the View, rather than on drawing order.

To avoid exact overlap, newly added sections of the same orientation are staggered alternately away from the center:

```text
60%, 40%, 70%, 30%, 80%, 20% ...
```

After moving a blue guide line, click `プレビュー確認` (Preview) to regenerate the corresponding section.

## 10. Lithic Section Layout

### X-Z Sections

If `Bottom` is selected, X-Z sections are placed:

```text
below Bottom
```

If `Bottom` is not selected, they are placed:

```text
below Front
```

Multiple X-Z sections extend downward. Their order is based on model position rather than the order in which the section lines were added or drawn: they are arranged in **top-to-bottom order as seen on Front**. The uppermost transverse section comes first, followed by sections farther down.

### Y-Z Sections

Y-Z sections are placed at the far right of the orthographic layout.

When all six main views are displayed, they are placed:

```text
to the right of Back
```

Multiple Y-Z sections are also ordered by model position rather than creation / drawing order: they are arranged **left-to-right as seen on Back**. Because Back is horizontally mirrored, this corresponds internally to sorting normalized section positions from larger to smaller values.

## 11. Lithic Section-Position Tick Marks

Section positions are shown as black tick marks in the saved composite image.

The specifications are the same as for pottery. If view spacing is `S`:

- gap from model edge: `S / 4`
- tick length: `S / 2`
- remaining outer gap: `S / 4`
- line width: `5 px`

### Tick Marks for Y-Z Sections

For each `x = constant` section, vertical ticks are drawn:

- above and below Front
- above and below Back

### Tick Marks for X-Z Sections

For each `y = constant` section, horizontal ticks are drawn:

- to the left and right of Front
- to the left and right of Back
- to the left and right of Left
- to the left and right of Right

## 12. Individual Lithic Outputs

When `各面・断面を個別ファイルでも出力` (Also Export Each View and Section as Individual Files) is ON, the following are additionally exported as applicable:

- PNG files for selected views
- SVG outlines for selected views
- PNG files for X-Z / Y-Z sections
- SVG files for X-Z / Y-Z sections

---

<a id="measurements"></a>
# Measurement CSV Files

[Back to top](#top) / [Go to Pottery](#pottery) / [Go to Lithic Artifacts](#lithic)

Since v0.4.0, measurement values based on the normalized coordinate system are exported as CSV.

## 1. Per-Artifact Measurement CSV

When `保存して次へ` (Save and Next) is executed, one measurement CSV is always created in the output folder for each artifact:

```text
output/<stem>/<stem>_measurements.csv
```

### Common to Pottery and Lithics

The final axis-aligned bounding-box dimensions are recorded as:

```text
bbox_x
bbox_y
bbox_z
```

In addition to values in the input unit, millimeter-converted values are recorded for convenient inventory use:

```text
bbox_x_mm
bbox_y_mm
bbox_z_mm
```

### Lithics Only: Section Bounding Boxes

Each configured section is added as one row in the same `<stem>_measurements.csv`.

The current section definitions are:

```text
Section (X) = X-Z section / y = constant
Section (Y) = Y-Z section / x = constant
```

Therefore, dimensions corresponding to the actual section plane are recorded as:

```text
X-Z section → bbox_x, bbox_z
Y-Z section → bbox_y, bbox_z
```

The dimension perpendicular to the section plane is left blank.

The following fields are also recorded:

```text
record_id
section_plane
section_position
section_coordinate
status
```

If a section does not intersect the model, dimensional values are left blank and:

```text
status = no_intersection
```

is recorded.

## 2. Measurement Inventory Export

The intended sequence in both pottery and lithic output panels is:

```text
Preview
↓
Export Measurement Inventory
↓
Save and Next
```

The `計測一覧出力` (Export Measurement Inventory) button is located immediately above `保存して次へ` (Save and Next).

If the current artifact has not yet been exported to the inventory, or if the pose, front orientation, or unit has been changed after inventory export, `保存して次へ` cannot be executed until the inventory is exported again.

One click on `計測一覧出力` updates the following **two inventories** simultaneously.

### 2-1. Geometry Summary Inventory

Pottery:

```text
output/inventory-pottery.csv
```

Lithics:

```text
output/inventory-lithic.csv
```

Only representative geometry values are included:

```text
source_stem
bbox_x_mm
bbox_y_mm
bbox_z_mm
```

If the same `source_stem` already exists, its row is updated rather than duplicated.

### 2-2. 3D Model / Data Inventory

Pottery:

```text
output/inventory-model-pottery.csv
```

Lithics:

```text
output/inventory-model-lithic.csv
```

Columns:

```text
source_file
source_stem
source_sha256
mesh_count
file_size_bytes
file_size_mb
surface_area_mm2
volume_mm3
is_watertight
volume_status
```

`mesh_count` is the number of triangular faces after loading with Trimesh.

`file_size_bytes` / `file_size_mb` record the size of the **source 3D mesh file itself**. For OBJ, only the `.obj` file is counted; associated MTL and JPEG/PNG texture files are not included.

`surface_area_mm2` records the source mesh surface area converted from the input unit to mm². Because rotation and translation do not change surface area, the value is identical before and after normalization.

`volume_mm3` records the absolute value of the Trimesh mesh volume converted to mm³. For closed meshes, this can be used as the mesh volume. Trimesh may also return a value for non-watertight meshes; in that case:

```text
is_watertight = False
volume_status = non_watertight_estimate
```

is recorded to distinguish the value from the physical volume of a closed mesh.

`source_sha256` is used to identify updates to the same 3D model.

CSV files are created automatically on first use and are saved as UTF-8 with BOM.

<a id="outputs"></a>
# Output Files and Transforms

## 1. Common Output Folder

For an input file:

```text
input/sample.obj
```

outputs are written to:

```text
output/sample/
```

## 2. Typical Pottery Outputs

```text
output/pot001/
├── pot001_rev.ply
├── transform.json
├── transform_matrix.csv
├── transform_matrix_cloudcompare.txt
├── pot001_ortho_texture.png
├── pot001_ortho_texture_normal.png
├── pot001_ortho_shade.png
├── pot001_ortho_texture_outline.png
├── pot001_ortho_texture_normal_outline.png
├── pot001_ortho_shade_outline.png
└── pot001_ortho_outline.svg
```

The actual number of files depends on the selected views, rendering modes, special drawings, and output formats.

## 3. Typical Lithic Outputs

```text
output/lithic001/
├── lithic001_rev.ply
├── transform.json
├── transform_original_to_obb.csv
├── transform_original_to_obb_cloudcompare.txt
├── transform_obb_to_result.csv                  # only when required
├── transform_obb_to_result_cloudcompare.txt     # only when required
├── lithic001_ortho_texture.png
├── lithic001_ortho_texture_normal.png
├── lithic001_ortho_shade.png
├── lithic001_ortho_*_outline.png                # when PNG + outline is ON
└── lithic001_ortho_outline.svg                  # when SVG is ON
```

When individual output is ON, PNG / SVG files for individual projection views and sections are also added.

## 4. Scale Bar

Available scale bars for orthographic output:

```text
20 mm
50 mm
100 mm
```

Default:

```text
50 mm
```

## 5. Large Meshes

This application does not automatically reduce model quality.

Practical guidelines:

- approximately 700,000–1,000,000 faces: generally convenient for routine operation
- several million faces: OBB and section calculations are still possible, but memory use and processing time should be considered when generating multiple orthographic views, outlines, and high-resolution renders

For the lithic automatic correction based on the central section, triangle-plane intersections are processed in chunks to reduce memory load on large meshes.

---

<a id="environment"></a>
# Python Environment and Running the Application

## 1. Recommended Folder Structure

```text
ArtifactPoseNormalizer/
├── app.py
├── pose_core.py
├── check_environment.py
├── self_test.py
├── requirements.txt
├── README.md
├── docs/
│   └── macos_qt_venv_issue.md
├── input/
└── output/
```

`pose_core.py` is **not a package installed with pip. It is a required file included with this application.** Place it in the same folder as `app.py`.

If `input/` and `output/` do not exist, they are created when the application starts.

## 2. Verified `requirements.txt`

The imports used by v0.4.3 `app.py` and `pose_core.py` were reviewed, and the third-party packages directly used by the application are explicitly listed in `requirements.txt`.

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
```

Purpose of each package:

| Package | Main purpose |
|---|---|
| NumPy | coordinate, matrix, and array calculations |
| SciPy | convex-hull calculation for lithic OBB; image processing for pottery section fill |
| Trimesh | OBJ / PLY / GLB loading, OBB, mesh measurements |
| PyVista | 3D display, orthographic rendering, VTK operations |
| PyVistaQt | embedding PyVista in the Qt GUI |
| VTK | 3D rendering, section Cutter / Stripper, outline processing |
| PySide6 | GUI |
| QtPy | Qt abstraction layer used by PyVistaQt |
| Pillow | PNG images, outlines, sections, and scale-bar drawing |

Python standard-library modules such as `csv`, `json`, `math`, `pathlib`, `tempfile`, and `xml` are included with Python itself and therefore are not listed in `requirements.txt`.

Dependencies required internally by the packages above are installed automatically by `pip`. **Beginners do not need to install modules one by one.**

**SciPy is required.** It is used by `trimesh.bounds.oriented_bounds()` for lithic processing and by the pottery section fill-repair pipeline through `scipy.ndimage`.

## 3. Check Python First

Python 3.13.x is recommended.

macOS:

```bash
python3.13 --version
```

Windows PowerShell:

```powershell
python --version
```

If `Python 3.13.x` is displayed, the standard setup instructions below can be used.

## 4. macOS: First-Time Setup

Open Terminal and move to the project folder:

```bash
cd /path/to/ArtifactPoseNormalizer
```

Create and activate a virtual environment named `venv`:

```bash
python3.13 -m venv venv
source venv/bin/activate
```

Upgrade the basic packaging tools, then install **all required external packages at once from `requirements.txt`**:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

Check dependency consistency:

```bash
python -m pip check
python check_environment.py
```

Then start the application:

```bash
python app.py
```

### Qt Startup Error on macOS

During project testing, a Qt platform-plugin file-flag issue was observed in one environment named `.venv`. For reproducibility, the standard instructions therefore use the virtual-environment name **`venv`**. This does not mean that `.venv` is generally unsupported.

See:

```text
docs/macos_qt_venv_issue.md
```

To test only the minimum Qt startup:

```bash
python -c 'from PySide6.QtWidgets import QApplication; app=QApplication([]); print("QApplication OK"); app.quit()'
```

## 5. Windows / PowerShell: First-Time Setup

Open PowerShell and move to the project folder:

```powershell
cd C:\path\to\ArtifactPoseNormalizer
```

Create the virtual environment:

```powershell
python -m venv venv
```

Activate it:

```powershell
.\venv\Scripts\Activate.ps1
```

Only if PowerShell reports `running scripts is disabled on this system`, temporarily allow script execution for the **current PowerShell session** and then activate the environment again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

Because `-Scope Process` applies only to the current PowerShell process, this command may need to be repeated after closing PowerShell and opening a new PowerShell session. It is not necessary to repeat it every time `app.py` is run within the same session.

Install all required external packages:

```powershell
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

Check the environment:

```powershell
python -m pip check
python check_environment.py
```

Start the application:

```powershell
python app.py
```

## 6. `check_environment.py`

This is a beginner-oriented environment verification script.

```bash
python check_environment.py
```

It checks:

- NumPy
- SciPy
- Trimesh
- PyVista
- PyVistaQt
- VTK
- PySide6
- QtPy
- Pillow
- local `pose_core.py`
- Qt `QApplication` / platform plugin

If everything is working, the last line is:

```text
ENVIRONMENT CHECK PASSED
```

## 7. Common Errors

### `ModuleNotFoundError: No module named '...'`

First confirm that the virtual environment is active.

macOS:

```bash
which python
```

It should point to something similar to:

```text
.../ArtifactPoseNormalizer/venv/bin/python
```

Windows PowerShell:

```powershell
Get-Command python
```

It should point to:

```text
...\ArtifactPoseNormalizer\venv\Scripts\python.exe
```

Then run:

```bash
python -m pip install -r requirements.txt
python -m pip check
python check_environment.py
```

again.

### `No module named 'pose_core'`

`pose_core.py` is not a pip package.

Confirm that:

```text
app.py
pose_core.py
```

are in the same folder.

### `No module named 'scipy'`

SciPy is mandatory in v0.4.3 (and has been required since the v0.4.2 section-fill update).

Run:

```bash
python -m pip install -r requirements.txt
```

There is no need to install SciPy separately.

### Qt Platform Plugin Error

First run:

```bash
python check_environment.py
```

to determine whether only the Qt startup stage is failing. On macOS, also see `docs/macos_qt_venv_issue.md`.

## 8. SELF TEST

Run the basic test for the shared computational core:

```bash
python self_test.py
```

Successful completion prints:

```text
SELF TEST PASSED
```

`self_test.py` primarily checks pose, normal, and mesh calculations. GUI operation for pottery / lithics, 3D views, interactive section lines, and orthographic layout should be checked by running `app.py`.

## 9. Recommended Procedure After Updates

If `requirements.txt` changes, run the following inside the existing `venv`:

```bash
python -m pip install -r requirements.txt
python -m pip check
python check_environment.py
```

If the environment becomes substantially corrupted, rebuilding `venv` from `requirements.txt` is generally more reproducible than installing individual modules one by one.

---

# Development Files

For normal use, launch:

```text
app.py
```

Files such as `app_v0_1_xx.py`, `app_v0_2_x.py`, and `app_v0_3_x.py` are retained as development / verification history and are not the normal executable files.
