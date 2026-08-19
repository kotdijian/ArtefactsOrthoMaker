from __future__ import annotations

import json
import math
import shutil
import sys
import traceback
from pathlib import Path

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDial,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from pose_core import (
    AxisEstimate,
    MeshAsset,
    PlaneEstimate,
    UNIT_TO_MM,
    angle_between_deg,
    build_pose_transform,
    estimate_base_plane,
    estimate_rim_plane,
    estimate_slice_axis,
    export_matrix_csv,
    export_matrix_txt,
    export_normalized_mesh,
    export_transform_json,
    final_transform_matrix,
    load_mesh_asset,
    plane_from_three_points,
    transform_points,
)

APP_NAME = "Artifact Pose Normalizer"
APP_VERSION = "0.1.5"
SUPPORTED_SUFFIXES = {".obj", ".ply", ".glb"}
WORK_DIR = Path(__file__).resolve().parent
INPUT_DIR = WORK_DIR / "input"
OUTPUT_DIR = WORK_DIR / "output"
ORTHO_COMPOSITE_LONG_EDGE_PX = 3600


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1500, 900)

        self.asset: MeshAsset | None = None
        self.initial_axis: AxisEstimate | None = None
        self.reference_plane: PlaneEstimate | None = None
        self.pose_matrix = np.eye(4)
        self.front_angle_deg = 0.0
        self.center_axis_after_pose: AxisEstimate | None = None
        self.pose_info: dict = {}
        self.posture_done = False
        self.manual_points: list[np.ndarray] = []
        self.pick_mode = False
        self.front_drag_enabled = False
        self.dragging_front = False
        self.last_mouse_x = 0.0
        self.actor = None
        self.current_poly = None
        self._viewer_scale_actor = None
        self._viewer_scale_text_actor = None
        self._setting_dial = False
        self.queue_all: list[Path] = []
        self.current_queue_path: Path | None = None

        self._build_ui()
        self._build_menu()
        self.statusBar().showMessage("inputフォルダを確認しています…")
        QTimer.singleShot(0, self.scan_queue_and_load)

    # ---------- UI ----------
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(splitter)

        controls = QWidget()
        left_layout = QVBoxLayout(controls)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        file_group = QGroupBox("1. 入力キュー / 単位")
        file_form = QFormLayout(file_group)
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["mm", "cm", "m"])
        self.unit_combo.setCurrentText("mm")
        self.unit_combo.currentTextChanged.connect(self._unit_changed)
        self.reload_queue_btn = QPushButton("inputフォルダを再読込")
        self.reload_queue_btn.clicked.connect(self.scan_queue_and_load)
        self.queue_label = QLabel("—")
        self.queue_label.setWordWrap(True)
        self.file_label = QLabel("未読込")
        self.file_label.setWordWrap(True)
        file_form.addRow("入力単位", self.unit_combo)
        file_form.addRow(self.reload_queue_btn)
        file_form.addRow("キュー", self.queue_label)
        file_form.addRow("現在", self.file_label)
        left_layout.addWidget(file_group)

        qa_group = QGroupBox("Mesh QA")
        qa_layout = QVBoxLayout(qa_group)
        self.qa_label = QLabel("—")
        self.qa_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.qa_label.setWordWrap(True)
        qa_layout.addWidget(self.qa_label)
        left_layout.addWidget(qa_group)

        display_group = QGroupBox("表示")
        display_layout = QVBoxLayout(display_group)
        self.show_appearance = QCheckBox("テクスチャ / 頂点カラー")
        self.show_appearance.setChecked(True)
        self.show_appearance.stateChanged.connect(self.refresh_view)
        self.smooth_shading = QCheckBox("Normalシェード")
        self.smooth_shading.setChecked(True)
        self.smooth_shading.stateChanged.connect(self.refresh_view)

        view_mode_row = QHBoxLayout()
        view_mode_row.addWidget(QLabel("表示方向"))
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems(["Ortho Front", "Oblique"])
        self.view_mode_combo.setCurrentText("Oblique")
        self.view_mode_combo.currentTextChanged.connect(self._view_mode_changed)
        view_mode_row.addWidget(self.view_mode_combo)

        viewer_scale_row = QHBoxLayout()
        viewer_scale_row.addWidget(QLabel("表示スケール"))
        self.viewer_scale_combo = QComboBox()
        self.viewer_scale_combo.addItems(["20 mm", "50 mm", "100 mm"])
        self.viewer_scale_combo.setCurrentText("50 mm")
        self.viewer_scale_combo.currentTextChanged.connect(self._viewer_scale_changed)
        viewer_scale_row.addWidget(self.viewer_scale_combo)

        display_layout.addWidget(self.show_appearance)
        display_layout.addWidget(self.smooth_shading)
        display_layout.addLayout(view_mode_row)
        display_layout.addLayout(viewer_scale_row)
        display_layout.addWidget(QLabel("Ortho Front＝正面平行投影 / Oblique＝斜め平行投影"))
        left_layout.addWidget(display_group)

        posture_group = QGroupBox("2. 水平・傾き")
        posture_layout = QVBoxLayout(posture_group)
        self.method_combo = QComboBox()
        self.method_combo.addItems(["Slice", "Rim", "Base", "Manual (3 points)"])
        posture_layout.addWidget(self.method_combo)

        row = QHBoxLayout()
        self.estimate_btn = QPushButton("推定 / 適用")
        self.estimate_btn.clicked.connect(self.estimate_and_apply_posture)
        self.flip_z_btn = QPushButton("Z上下反転")
        self.flip_z_btn.clicked.connect(self.flip_z_and_reapply)
        row.addWidget(self.estimate_btn)
        row.addWidget(self.flip_z_btn)
        posture_layout.addLayout(row)

        self.manual_pick_btn = QPushButton("手動水平：3点を選択")
        self.manual_pick_btn.clicked.connect(self.start_manual_pick)
        posture_layout.addWidget(self.manual_pick_btn)
        self.manual_pick_label = QLabel("選択点: 0 / 3")
        posture_layout.addWidget(self.manual_pick_label)
        self.pose_label = QLabel("姿勢未確定")
        self.pose_label.setWordWrap(True)
        self.pose_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        posture_layout.addWidget(self.pose_label)
        left_layout.addWidget(posture_group)

        front_group = QGroupBox("3. 正面（Z軸回転）")
        front_layout = QVBoxLayout(front_group)
        self.front_drag_check = QCheckBox("3D画面の左ドラッグでZ回転")
        self.front_drag_check.setChecked(True)
        self.front_drag_check.stateChanged.connect(self._front_drag_changed)
        front_layout.addWidget(self.front_drag_check)
        self.front_dial = QDial()
        self.front_dial.setRange(-1800, 1800)
        self.front_dial.setNotchesVisible(True)
        self.front_dial.valueChanged.connect(self._dial_changed)
        front_layout.addWidget(self.front_dial)
        angle_row = QHBoxLayout()
        self.angle_spin = QDoubleSpinBox()
        self.angle_spin.setRange(-180.0, 180.0)
        self.angle_spin.setDecimals(1)
        self.angle_spin.setSuffix("°")
        self.angle_spin.valueChanged.connect(self._spin_changed)
        angle_row.addWidget(QLabel("Z回転"))
        angle_row.addWidget(self.angle_spin)
        front_layout.addLayout(angle_row)
        presets = QHBoxLayout()
        for label, deg in [("0°", 0), ("90°", 90), ("180°", 180), ("-90°", -90)]:
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, d=deg: self.set_front_angle(d))
            presets.addWidget(b)
        front_layout.addLayout(presets)
        self.front_hint = QLabel("通常の左ドラッグ＝モデルのZ回転。Shift+左ドラッグ＝カメラ操作。")
        self.front_hint.setWordWrap(True)
        front_layout.addWidget(self.front_hint)
        left_layout.addWidget(front_group)

        ortho_group = QGroupBox("4. オルソ画像")
        ortho_layout = QVBoxLayout(ortho_group)
        ortho_layout.addWidget(QLabel("出力面（デフォルト6面）"))
        self.view_checks = {}
        for key, label in [
            ("front", "Front"), ("back", "Back"), ("left", "Left"),
            ("right", "Right"), ("top", "Top"), ("bottom", "Bottom")
        ]:
            cb = QCheckBox(label)
            cb.setChecked(True)
            self.view_checks[key] = cb
            ortho_layout.addWidget(cb)

        ortho_layout.addWidget(QLabel("表現（デフォルト全ON）"))
        self.mode_texture = QCheckBox("テクスチャ / 頂点カラー")
        self.mode_texture_normal = QCheckBox("テクスチャ / 頂点カラー + Normal")
        self.mode_shade = QCheckBox("Normalのみ（シェード）")
        for cb in (self.mode_texture, self.mode_texture_normal, self.mode_shade):
            cb.setChecked(True)
            ortho_layout.addWidget(cb)

        spacing_row = QHBoxLayout()
        spacing_row.addWidget(QLabel("面間隔"))
        self.view_spacing = QDoubleSpinBox()
        self.view_spacing.setRange(0.0, 10000.0)
        self.view_spacing.setValue(10.0)
        self.view_spacing.setDecimals(1)
        self.view_spacing.setSuffix(" mm")
        spacing_row.addWidget(self.view_spacing)
        ortho_layout.addLayout(spacing_row)

        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("スケールバー"))
        self.scale_bar_combo = QComboBox()
        self.scale_bar_combo.addItems(["20 mm", "50 mm", "100 mm"])
        self.scale_bar_combo.setCurrentText("50 mm")
        scale_row.addWidget(self.scale_bar_combo)
        ortho_layout.addLayout(scale_row)

        self.export_individual = QCheckBox("各面を個別PNGでも出力")
        self.export_individual.setChecked(False)
        ortho_layout.addWidget(self.export_individual)
        left_layout.addWidget(ortho_group)

        export_group = QGroupBox("5. 保存 / 次のファイル")
        export_layout = QVBoxLayout(export_group)
        self.save_next_btn = QPushButton("保存して次へ")
        self.save_next_btn.clicked.connect(self.save_current_and_next)
        self.export_stage_label = QLabel("待機")
        self.export_progress = QProgressBar()
        self.export_progress.setRange(0, 100)
        self.export_progress.setValue(0)
        export_layout.addWidget(self.save_next_btn)
        export_layout.addWidget(self.export_stage_label)
        export_layout.addWidget(self.export_progress)
        export_layout.addWidget(QLabel(
            "output/<元ファイル名>/ に _revモデル、transform、合成オルソPNGを保存します。"
        ))
        left_layout.addWidget(export_group)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(controls)
        scroll.setMinimumWidth(390)
        splitter.addWidget(scroll)

        view_widget = QWidget()
        view_layout = QVBoxLayout(view_widget)
        self.plotter = QtInteractor(view_widget, auto_update=False, multi_samples=0)
        self.plotter.set_background("white")
        self.plotter.add_axes()
        self.plotter.installEventFilter(self)
        self._vtk_widget = self.plotter.interactor
        try:
            self._vtk_widget.installEventFilter(self)
        except Exception:
            pass
        view_layout.addWidget(self._vtk_widget)
        splitter.addWidget(view_widget)
        splitter.setStretchFactor(1, 1)

        self._set_enabled(False)

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("File")
        reload_action = QAction("Reload input queue", self)
        reload_action.triggered.connect(self.scan_queue_and_load)
        file_menu.addAction(reload_action)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _set_enabled(self, loaded: bool):
        widgets = [
            self.show_appearance, self.smooth_shading, self.method_combo,
            self.estimate_btn, self.flip_z_btn, self.manual_pick_btn,
            self.front_drag_check, self.front_dial, self.angle_spin,
            self.mode_texture, self.mode_texture_normal, self.mode_shade,
            self.view_spacing, self.scale_bar_combo, self.export_individual,
            self.view_mode_combo, self.viewer_scale_combo,
            self.save_next_btn,
        ] + list(self.view_checks.values())
        for w in widgets:
            w.setEnabled(loaded)

    # ---------- Input queue / Loading / QA ----------
    def _scan_files(self) -> list[Path]:
        INPUT_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(
            [p for p in INPUT_DIR.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES and not p.name.startswith(".")],
            key=lambda p: p.name.casefold(),
        )
        stems: dict[str, list[Path]] = {}
        for p in files:
            stems.setdefault(p.stem.casefold(), []).append(p)
        collisions = [items for items in stems.values() if len(items) > 1]
        if collisions:
            names = "\n".join(" / ".join(x.name for x in group) for group in collisions)
            raise ValueError(
                "同じファイル名（拡張子を除く）の入力が複数あります。出力フォルダが衝突するため名前を変更してください。\n\n" + names
            )
        return files

    def scan_queue_and_load(self):
        try:
            self.queue_all = self._scan_files()
            pending = [p for p in self.queue_all if not (OUTPUT_DIR / p.stem).exists()]
            done = len(self.queue_all) - len(pending)
            self.queue_label.setText(
                f"全 {len(self.queue_all)} / 完了 {done} / 未処理 {len(pending)}\n"
                f"input: {INPUT_DIR}\noutput: {OUTPUT_DIR}"
            )
            if not pending:
                self.asset = None
                self.current_queue_path = None
                self.file_label.setText("未処理ファイルなし")
                self.qa_label.setText("—")
                self._set_enabled(False)
                self.plotter.clear()
                self.plotter.add_axes()
                self.plotter.render()
                if self.queue_all:
                    self.statusBar().showMessage("すべての入力ファイルが処理済みです。")
                else:
                    self.statusBar().showMessage(f"{INPUT_DIR} に OBJ / PLY / GLB を入れてください。")
                return
            self._load_path(pending[0])
        except Exception as e:
            self._show_error("入力キューエラー", e)

    def _load_path(self, path: Path):
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.statusBar().showMessage(f"読み込み・Normal検証中: {path.name}")
            QApplication.processEvents()
            self.asset = load_mesh_asset(path, self.unit_combo.currentText())
            self.current_queue_path = path
            self.initial_axis = None
            self.reference_plane = None
            self.pose_matrix = np.eye(4)
            self.front_angle_deg = 0.0
            self.posture_done = False
            self.center_axis_after_pose = None
            self.pose_info = {}
            self.manual_points = []
            self.manual_pick_label.setText("選択点: 0 / 3")
            self.pose_label.setText("姿勢未確定")
            self.file_label.setText(path.name)
            self._update_qa()
            self._set_enabled(True)
            self._configure_appearance_options()
            self.set_front_angle(0.0)
            self.statusBar().showMessage(f"3D表示を更新中: {path.name}")
            QApplication.processEvents()
            self.refresh_view(reset_camera=True)
            pending = [p for p in self.queue_all if not (OUTPUT_DIR / p.stem).exists()]
            index = pending.index(path) + 1 if path in pending else 1
            self.statusBar().showMessage(
                f"未処理 {index}/{len(pending)}: {path.name} — 姿勢方式を選んでください。"
            )
        except Exception as e:
            self._show_error("読み込みエラー", e)
        finally:
            QApplication.restoreOverrideCursor()

    def _unit_changed(self, unit: str):
        # Coordinate values are never rescaled; changing unit only changes the mm conversion.
        if self.asset is not None and unit in UNIT_TO_MM:
            self.asset.input_unit = unit
            self.asset.unit_to_mm = UNIT_TO_MM[unit]
            self._update_qa()

    def _update_qa(self):
        if not self.asset:
            self.qa_label.setText("—")
            return
        m = self.asset.mesh
        appearance = {
            "texture": "OBJ texture (UV + image)",
            "vertex_color": "vertex color",
            "none": "none",
        }[self.asset.appearance_kind]
        notes = "<br>".join(self.asset.notes) if self.asset.notes else "—"
        self.qa_label.setText(
            f"Vertices: {len(m.vertices):,}<br>"
            f"Faces: {len(m.faces):,}<br>"
            f"Input unit: {self.asset.input_unit}（座標値は変更しません）<br>"
            f"Normals: {self.asset.normals_status}<br>"
            f"Appearance: {appearance}<br>"
            f"Watertight: {bool(m.is_watertight)}<br>"
            f"Notes: {notes}"
        )

    def _configure_appearance_options(self):
        has_appearance = bool(self.asset and self.asset.appearance_kind != "none")
        self.show_appearance.setEnabled(has_appearance)
        self.show_appearance.setChecked(has_appearance)
        self.mode_texture.setEnabled(has_appearance)
        self.mode_texture_normal.setEnabled(has_appearance)
        self.mode_texture.setChecked(has_appearance)
        self.mode_texture_normal.setChecked(has_appearance)
        self.mode_shade.setEnabled(True)
        self.mode_shade.setChecked(True)
        if not has_appearance:
            # Required behavior: OBJ without texture image and PLY without vertex color => shade only.
            self.mode_texture.setChecked(False)
            self.mode_texture_normal.setChecked(False)

    # ---------- PyVista construction / view ----------
    def _current_base_matrix(self) -> np.ndarray:
        return self.pose_matrix if self.posture_done else np.eye(4)

    def _current_final_matrix(self) -> np.ndarray:
        return final_transform_matrix(self.pose_matrix, self.front_angle_deg) if self.posture_done else np.eye(4)

    def _make_polydata(self, matrix: np.ndarray | None = None) -> pv.PolyData:
        if not self.asset:
            raise RuntimeError("No mesh loaded")
        if matrix is None:
            matrix = self._current_base_matrix()
        vertices = transform_points(np.asarray(self.asset.mesh.vertices), matrix)
        faces = np.asarray(self.asset.mesh.faces, dtype=np.int64)
        vtk_faces = np.column_stack([np.full(len(faces), 3, dtype=np.int64), faces]).ravel()
        poly = pv.PolyData(vertices, vtk_faces)

        # Reuse normals already validated/calculated at file load.  PyVista computes
        # normals itself when smooth_shading=True and no active normals are present;
        # on large meshes that duplicate calculation can make the Qt viewer appear frozen.
        normals = np.asarray(self.asset.vertex_normals, dtype=float)
        if len(normals) == len(vertices):
            rot = np.asarray(matrix, dtype=float)[:3, :3]
            transformed_normals = normals @ rot.T
            lengths = np.linalg.norm(transformed_normals, axis=1)
            good = lengths > 1e-12
            transformed_normals[good] /= lengths[good, None]
            transformed_normals[~good] = np.array([0.0, 0.0, 1.0])
            poly.point_data.set_array(transformed_normals.astype(np.float32), "Normals")
            poly.point_data.active_normals_name = "Normals"

        if self.asset.appearance_kind == "vertex_color" and self.asset.vertex_colors is not None:
            colors = np.asarray(self.asset.vertex_colors, dtype=np.uint8)
            if colors.shape[1] == 4:
                colors = colors[:, :3]
            poly.point_data["RGB"] = colors
        elif self.asset.appearance_kind == "texture" and self.asset.uv is not None:
            uv = np.asarray(self.asset.uv, dtype=float).copy()
            # Trimesh/PIL and VTK commonly use opposite image-V origins.
            uv[:, 1] = 1.0 - uv[:, 1]
            poly.active_texture_coordinates = uv
        return poly

    def _add_mesh_actor(self, plotter, poly: pv.PolyData, appearance: bool, lighting: bool):
        kwargs = dict(smooth_shading=bool(lighting), lighting=bool(lighting), show_edges=False)
        if appearance and self.asset and self.asset.appearance_kind == "texture" and self.asset.texture_image is not None:
            tex = pv.Texture(self.asset.texture_image)
            return plotter.add_mesh(poly, texture=tex, **kwargs)
        if appearance and self.asset and self.asset.appearance_kind == "vertex_color" and "RGB" in poly.point_data:
            return plotter.add_mesh(poly, scalars="RGB", rgb=True, **kwargs)
        return plotter.add_mesh(poly, color="lightgray", **kwargs)

    def refresh_view(self, *_args, reset_camera=False):
        if not self.asset:
            return
        try:
            angle = self.front_angle_deg if self.posture_done else 0.0
            self.current_poly = self._make_polydata(self._current_base_matrix())
            self.plotter.renderer.clear_actors()
            self._viewer_scale_actor = None
            self._viewer_scale_text_actor = None
            self.plotter.set_background("white")
            self.actor = self._add_mesh_actor(
                self.plotter,
                self.current_poly,
                appearance=self.show_appearance.isChecked(),
                lighting=self.smooth_shading.isChecked(),
            )
            if self.actor is not None and self.posture_done:
                try:
                    self.actor.origin = (0.0, 0.0, 0.0)
                    self.actor.orientation = (0.0, 0.0, angle)
                except AttributeError:
                    pass
            if self.posture_done and self.center_axis_after_pose is not None:
                self._draw_center_axis()
            if self.manual_points:
                pts = pv.PolyData(np.asarray(self.manual_points))
                self.plotter.add_mesh(pts, render_points_as_spheres=True, point_size=12)

            if reset_camera:
                self._apply_view_mode_camera(reset=True)
            else:
                # Both viewer modes use parallel projection so the on-screen
                # ruler has a stable physical scale.
                self.plotter.enable_parallel_projection()

            self._update_viewer_scale_overlay(render=False)
            self.plotter.render()
        except Exception as e:
            self.statusBar().showMessage(f"表示更新エラー: {e}")

    def _view_mode_changed(self, *_args):
        if not self.asset:
            return
        try:
            self._apply_view_mode_camera(reset=True)
            self._update_viewer_scale_overlay(render=False)
            self.plotter.render()
        except Exception as e:
            self.statusBar().showMessage(f"表示方向変更エラー: {e}")

    def _viewer_scale_changed(self, *_args):
        self._update_viewer_scale_overlay(render=True)

    def _selected_viewer_scale_mm(self) -> float:
        try:
            return float(self.viewer_scale_combo.currentText().split()[0])
        except Exception:
            return 50.0

    def _actor_bounds(self) -> np.ndarray:
        if self.actor is not None:
            try:
                b = np.asarray(self.actor.GetBounds(), dtype=float)
                if b.shape == (6,) and np.isfinite(b).all():
                    return b
            except Exception:
                pass
        if self.current_poly is not None:
            return np.asarray(self.current_poly.bounds, dtype=float)
        raise RuntimeError("No displayed mesh bounds")

    def _apply_view_mode_camera(self, reset: bool = True):
        if not self.asset or self.current_poly is None:
            return
        bounds = self._actor_bounds()
        center = np.array([
            (bounds[0] + bounds[1]) * 0.5,
            (bounds[2] + bounds[3]) * 0.5,
            (bounds[4] + bounds[5]) * 0.5,
        ], dtype=float)
        max_extent = max(
            float(bounds[1] - bounds[0]),
            float(bounds[3] - bounds[2]),
            float(bounds[5] - bounds[4]),
            1e-9,
        )
        dist = max_extent * 3.0
        mode = self.view_mode_combo.currentText()
        if mode == "Ortho Front":
            pos = center + np.array([0.0, -dist, 0.0])
            up = np.array([0.0, 0.0, 1.0])
        else:
            # Fixed three-quarter oblique view. It remains an orthographic
            # projection so the display ruler is metrically meaningful.
            direction = np.array([1.25, -1.55, 0.95], dtype=float)
            direction /= np.linalg.norm(direction)
            pos = center + direction * dist
            up = np.array([0.0, 0.0, 1.0])

        self.plotter.camera_position = [pos.tolist(), center.tolist(), up.tolist()]
        self.plotter.enable_parallel_projection()
        if reset:
            self.plotter.reset_camera()

    def _remove_viewer_scale_overlay(self):
        renderer = getattr(self.plotter, "renderer", None)
        if renderer is None:
            return
        for actor in (self._viewer_scale_actor, self._viewer_scale_text_actor):
            if actor is not None:
                try:
                    renderer.RemoveViewProp(actor)
                except Exception:
                    try:
                        renderer.RemoveActor(actor)
                    except Exception:
                        pass
        self._viewer_scale_actor = None
        self._viewer_scale_text_actor = None

    def _update_viewer_scale_overlay(self, render: bool = True):
        """Draw a true-scale 2D ruler for the current parallel-projection camera."""
        if not self.asset or not hasattr(self, "plotter"):
            return
        try:
            self._remove_viewer_scale_overlay()
            camera = self.plotter.camera
            if not bool(camera.GetParallelProjection()):
                return

            window_size = self.plotter.window_size
            width_px = max(int(window_size[0]), 1)
            height_px = max(int(window_size[1]), 1)
            parallel_scale = float(camera.GetParallelScale())
            if parallel_scale <= 0:
                return
            world_per_px = (2.0 * parallel_scale) / float(height_px)
            model_length = self._selected_viewer_scale_mm() / float(self.asset.unit_to_mm)
            bar_px = max(1.0, model_length / world_per_px)

            x0 = 30.0
            y0 = 32.0
            x1 = x0 + bar_px
            tick = 7.0

            from vtkmodules.vtkCommonCore import vtkPoints
            from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
            from vtkmodules.vtkRenderingCore import vtkActor2D, vtkPolyDataMapper2D, vtkTextActor

            points = vtkPoints()
            coords = [
                (x0, y0, 0.0), (x1, y0, 0.0),
                (x0, y0 - tick, 0.0), (x0, y0 + tick, 0.0),
                (x1, y0 - tick, 0.0), (x1, y0 + tick, 0.0),
            ]
            for c in coords:
                points.InsertNextPoint(*c)
            lines = vtkCellArray()
            for a, b in ((0, 1), (2, 3), (4, 5)):
                lines.InsertNextCell(2)
                lines.InsertCellPoint(a)
                lines.InsertCellPoint(b)
            poly = vtkPolyData()
            poly.SetPoints(points)
            poly.SetLines(lines)
            mapper = vtkPolyDataMapper2D()
            mapper.SetInputData(poly)
            actor = vtkActor2D()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(0.0, 0.0, 0.0)
            actor.GetProperty().SetLineWidth(2.0)

            text_actor = vtkTextActor()
            text_actor.SetInput(f"{self._selected_viewer_scale_mm():g} mm")
            text_actor.SetPosition((x0 + x1) * 0.5, y0 + 12.0)
            prop = text_actor.GetTextProperty()
            prop.SetColor(0.0, 0.0, 0.0)
            prop.SetFontSize(14)
            prop.SetJustificationToCentered()
            prop.SetVerticalJustificationToBottom()

            renderer = self.plotter.renderer
            renderer.AddViewProp(actor)
            renderer.AddViewProp(text_actor)
            self._viewer_scale_actor = actor
            self._viewer_scale_text_actor = text_actor
            if render:
                self.plotter.render()
        except Exception as e:
            self.statusBar().showMessage(f"表示スケール更新エラー: {e}")

    def _draw_center_axis(self):
        axis = self.center_axis_after_pose
        if axis is None or self.current_poly is None:
            return
        b = self.current_poly.bounds
        extent = max(b[1] - b[0], b[3] - b[2], b[5] - b[4])
        p0 = axis.point - axis.direction * extent
        p1 = axis.point + axis.direction * extent
        line = pv.Line(p0, p1)
        self.plotter.add_mesh(line, line_width=2)

    # ---------- Pose estimation ----------
    def _ensure_initial_axis(self):
        if self.initial_axis is not None:
            return
        if not self.asset:
            raise RuntimeError("No mesh loaded")
        self.statusBar().showMessage("Slice中心軸候補を推定中…")
        QApplication.processEvents()
        self.initial_axis = estimate_slice_axis(np.asarray(self.asset.mesh.vertices))

    def estimate_and_apply_posture(self):
        if not self.asset:
            return
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self._ensure_initial_axis()
            method_text = self.method_combo.currentText()
            method = method_text.split()[0].lower()
            self.reference_plane = None
            ref_normal = None

            if method == "rim":
                self.statusBar().showMessage("口縁を放射セクタ抽出し、robust planeを最適化中…")
                QApplication.processEvents()
                self.reference_plane = estimate_rim_plane(np.asarray(self.asset.mesh.vertices), self.initial_axis)
                ref_normal = self.reference_plane.normal
            elif method == "base":
                self.statusBar().showMessage("底面支持点を放射セクタ抽出し、robust planeを最適化中…")
                QApplication.processEvents()
                self.reference_plane = estimate_base_plane(np.asarray(self.asset.mesh.vertices), self.initial_axis)
                ref_normal = self.reference_plane.normal
            elif method == "manual":
                if len(self.manual_points) != 3:
                    raise ValueError("Manualでは先に「手動水平：3点を選択」で3点を指定してください。")
                self.reference_plane = plane_from_three_points(np.asarray(self.manual_points), preferred_up=self.initial_axis.direction)
                ref_normal = self.reference_plane.normal
            elif method != "slice":
                raise ValueError(f"Unknown method: {method_text}")

            self.pose_matrix, self.center_axis_after_pose, origin, info = build_pose_transform(
                np.asarray(self.asset.mesh.vertices),
                method,
                self.initial_axis,
                reference_normal=ref_normal,
            )
            self.pose_info = info
            self.posture_done = True
            self.set_front_angle(0.0)

            axis_angle = angle_between_deg(self.center_axis_after_pose.direction, np.array([0.0, 0.0, 1.0]))
            ref_text = ""
            if self.reference_plane is not None:
                ref_text = (
                    f"<br>Reference plane RMS: {self.reference_plane.residual_rms:.4g} input-unit"
                    f" / confidence: {self.reference_plane.confidence:.2f}"
                )
            self.pose_label.setText(
                f"Method: {method_text}<br>"
                f"Center-axis confidence: {self.center_axis_after_pose.confidence:.2f}<br>"
                f"Center axis ↔ Z: {axis_angle:.3f}°<br>"
                f"Origin: center axis × posture BBox lower plane{ref_text}"
            )
            self.refresh_view(reset_camera=True)
            self.statusBar().showMessage("姿勢と原点を確定しました。次にZ軸回転で正面を決めてください。")
        except Exception as e:
            self._show_error("姿勢推定エラー", e)
        finally:
            QApplication.restoreOverrideCursor()

    def flip_z_and_reapply(self):
        if not self.asset:
            return
        try:
            self._ensure_initial_axis()
            self.initial_axis.direction *= -1.0
            self.initial_axis.diagnostics["manual_flip_z"] = not self.initial_axis.diagnostics.get("manual_flip_z", False)
            self.estimate_and_apply_posture()
        except Exception as e:
            self._show_error("Z反転エラー", e)

    # ---------- Manual plane picking ----------
    def start_manual_pick(self):
        if not self.asset:
            return
        # Manual plane points must be picked in raw coordinates. Return the view to raw pose first.
        self.posture_done = False
        self.pose_matrix = np.eye(4)
        self.front_angle_deg = 0.0
        self.center_axis_after_pose = None
        self.manual_points = []
        self.manual_pick_label.setText("選択点: 0 / 3")
        self.method_combo.setCurrentText("Manual (3 points)")
        self.refresh_view(reset_camera=True)
        self.pick_mode = True
        try:
            self.plotter.disable_picking()
        except Exception:
            pass
        self.plotter.enable_surface_point_picking(
            callback=self._picked_point,
            left_clicking=True,
            show_message=True,
            show_point=True,
            pickable_window=False,
        )
        self.statusBar().showMessage("水平にしたい面上の3点を順にクリックしてください。")

    def _picked_point(self, point):
        if not self.pick_mode:
            return
        p = np.asarray(point, dtype=float)
        if p.shape != (3,) or not np.isfinite(p).all():
            return
        self.manual_points.append(p)
        self.manual_pick_label.setText(f"選択点: {len(self.manual_points)} / 3")
        if len(self.manual_points) >= 3:
            self.pick_mode = False
            try:
                self.plotter.disable_picking()
            except Exception:
                pass
            self.statusBar().showMessage("3点を取得しました。「推定 / 適用」を押してください。")

    # ---------- Front rotation ----------
    def _front_drag_changed(self):
        self.front_drag_enabled = self.front_drag_check.isChecked()

    def eventFilter(self, watched, event):
        """Handle only relevant mouse events for front Z rotation.

        eventFilter also receives paint/timer/focus events. Those events do not
        implement mouse-specific methods such as modifiers(), button(), or position().
        """
        is_view = watched in (self.plotter, getattr(self, "_vtk_widget", None))
        etype = event.type()
        if is_view and etype in (QEvent.Type.Wheel, QEvent.Type.MouseButtonRelease):
            # Camera interaction changes the world-units-per-pixel ratio.
            QTimer.singleShot(0, self._update_viewer_scale_overlay)

        if is_view and self.front_drag_check.isChecked() and self.posture_done:
            mouse_types = (
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseMove,
                QEvent.Type.MouseButtonRelease,
            )
            if etype not in mouse_types:
                return super().eventFilter(watched, event)

            if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
                if etype == QEvent.Type.MouseButtonRelease:
                    QTimer.singleShot(0, self._update_viewer_scale_overlay)
                return super().eventFilter(watched, event)

            if etype == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self.dragging_front = True
                self.last_mouse_x = float(event.position().x())
                return True
            if etype == QEvent.Type.MouseMove and self.dragging_front:
                x = float(event.position().x())
                dx = x - self.last_mouse_x
                self.last_mouse_x = x
                self.set_front_angle(self.front_angle_deg + dx * 0.35)
                return True
            if etype == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self.dragging_front = False
                QTimer.singleShot(0, self._update_viewer_scale_overlay)
                return True
        return super().eventFilter(watched, event)

    def _dial_changed(self, value: int):
        if self._setting_dial:
            return
        self.set_front_angle(value / 10.0, source="dial")

    def _spin_changed(self, value: float):
        if self._setting_dial:
            return
        self.set_front_angle(value, source="spin")

    @staticmethod
    def _wrap_angle(deg: float) -> float:
        d = ((float(deg) + 180.0) % 360.0) - 180.0
        if d == -180.0:
            d = 180.0
        return d

    def set_front_angle(self, deg: float, source="other"):
        self.front_angle_deg = self._wrap_angle(deg)
        self._setting_dial = True
        try:
            if source != "dial":
                self.front_dial.setValue(int(round(self.front_angle_deg * 10)))
            if source != "spin":
                self.angle_spin.setValue(self.front_angle_deg)
        finally:
            self._setting_dial = False
        if self.actor is not None and self.posture_done:
            try:
                self.actor.origin = (0.0, 0.0, 0.0)
                self.actor.orientation = (0.0, 0.0, self.front_angle_deg)
                self.plotter.render()
            except Exception:
                self.refresh_view()

    # ---------- Export / batch completion ----------
    def _selected_render_modes(self) -> list[str]:
        modes = []
        if self.mode_texture.isChecked() and self.mode_texture.isEnabled():
            modes.append("texture")
        if self.mode_texture_normal.isChecked() and self.mode_texture_normal.isEnabled():
            modes.append("texture_normal")
        if self.mode_shade.isChecked():
            modes.append("shade")
        return modes

    def _selected_scale_bar_mm(self) -> float:
        return float(self.scale_bar_combo.currentText().split()[0])

    def _metadata(self, final_matrix: np.ndarray) -> dict:
        if not self.asset:
            return {}
        inverse = np.linalg.inv(final_matrix)
        center = self.center_axis_after_pose
        ref = self.reference_plane
        return {
            "application": APP_NAME,
            "version": APP_VERSION,
            "source": {
                "file": str(self.asset.source_path),
                "sha256": self.asset.source_sha256,
                "input_unit": self.asset.input_unit,
                "unit_to_mm": self.asset.unit_to_mm,
                "coordinate_values_rescaled": False,
                "normals_status": self.asset.normals_status,
                "appearance_kind": self.asset.appearance_kind,
            },
            "coordinate_system": {
                "handedness": "right-handed",
                "z_axis": "up",
                "front_definition": "manual Z-axis rotation",
                "origin_definition": "center_axis_intersection_with_posture_AABB_lower_plane",
            },
            "posture": {
                **self.pose_info,
                "initial_slice_axis": None if self.initial_axis is None else {
                    "point": self.initial_axis.point,
                    "direction": self.initial_axis.direction,
                    "confidence": self.initial_axis.confidence,
                    "diagnostics": self.initial_axis.diagnostics,
                },
                "reference_plane": None if ref is None else {
                    "point": ref.point,
                    "normal": ref.normal,
                    "residual_rms_input_unit": ref.residual_rms,
                    "confidence": ref.confidence,
                    "diagnostics": ref.diagnostics,
                },
                "center_axis_after_posture": None if center is None else {
                    "point": center.point,
                    "direction": center.direction,
                    "confidence": center.confidence,
                    "diagnostics": center.diagnostics,
                    "angle_to_z_deg": angle_between_deg(center.direction, np.array([0.0, 0.0, 1.0])),
                },
                "front_rotation_deg": self.front_angle_deg,
            },
            "transform": {
                "matrix_convention": "row-major storage; column homogeneous vector application",
                "transform_direction": "raw_to_normalized",
                "equation": "p_normalized = M_raw_to_normalized @ [x, y, z, 1]^T",
                "matrix_4x4": final_matrix,
                "inverse_matrix_4x4": inverse,
            },
            "orthographic_export": {
                "views": [k for k, cb in self.view_checks.items() if cb.isChecked()],
                "view_spacing_mm": self.view_spacing.value(),
                "projection": "parallel/orthographic",
                "render_modes": self._selected_render_modes(),
                "composite": True,
                "individual_views": self.export_individual.isChecked(),
                "scale_bar_mm": self._selected_scale_bar_mm(),
                "scale_bar_style": "simple black line with end ticks; centered label above",
                "format": "PNG",
            },
        }

    def _set_export_progress(self, value: int, text: str):
        value = int(max(0, min(100, value)))
        self.export_progress.setValue(value)
        self.export_stage_label.setText(text)
        self.statusBar().showMessage(text)
        QApplication.processEvents()

    def save_current_and_next(self):
        if not self.asset or not self.posture_done:
            QMessageBox.warning(self, "未確定", "先に姿勢と正面を確定してください。")
            return
        views = [k for k, cb in self.view_checks.items() if cb.isChecked()]
        modes = self._selected_render_modes()
        if not views:
            QMessageBox.warning(self, "未選択", "少なくとも1つのオルソ面を選択してください。")
            return
        if not modes:
            QMessageBox.warning(self, "未選択", "少なくとも1つのオルソ表現を選択してください。")
            return

        stem = self.asset.source_path.stem
        final_dir = OUTPUT_DIR / stem
        if final_dir.exists():
            QMessageBox.warning(self, "処理済み", f"{final_dir} が存在するため処理済みです。再処理する場合はこのフォルダを削除してください。")
            self.scan_queue_and_load()
            return
        staging = OUTPUT_DIR / f".{stem}.__working__"
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self._set_export_progress(2, f"保存準備中: {self.asset.source_path.name}")
            self.save_next_btn.setEnabled(False)
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True, exist_ok=False)

            final_m = self._current_final_matrix()
            suffix = self.asset.source_path.suffix.lower()
            mesh_path = staging / f"{stem}_rev{suffix}"

            self._set_export_progress(10, f"正規化モデルを書き出し中: {mesh_path.name}")
            export_normalized_mesh(self.asset, final_m, mesh_path)

            self._set_export_progress(22, "Transform情報を書き出し中")
            export_transform_json(staging / "transform.json", self._metadata(final_m))
            export_matrix_csv(staging / "transform_matrix.csv", final_m)
            export_matrix_txt(staging / "transform_matrix_cloudcompare.txt", final_m)

            def ortho_progress(frac: float, message: str):
                self._set_export_progress(25 + int(68 * float(frac)), message)

            self._set_export_progress(25, "オルソ画像生成を開始")
            self.export_orthos(
                staging,
                views=views,
                modes=modes,
                spacing_mm=float(self.view_spacing.value()),
                scale_bar_mm=self._selected_scale_bar_mm(),
                individual=self.export_individual.isChecked(),
                progress_callback=ortho_progress,
            )

            self._set_export_progress(96, "出力フォルダを確定中")
            # Folder existence is the completion flag. Only expose the final folder
            # after every model/transform/PNG export succeeded.
            staging.rename(final_dir)
            self._set_export_progress(100, f"保存完了: {final_dir}")
            self.scan_queue_and_load()
        except Exception as e:
            try:
                if staging.exists():
                    shutil.rmtree(staging)
            except Exception:
                pass
            self._set_export_progress(0, "保存失敗")
            self._show_error("保存エラー", e)
        finally:
            QApplication.restoreOverrideCursor()
            if self.asset is not None:
                self.save_next_btn.setEnabled(True)

    # ---------- Orthographic composite export ----------
    @staticmethod
    def _view_size(bounds: np.ndarray, view: str) -> tuple[float, float]:
        dx = float(bounds[1] - bounds[0])
        dy = float(bounds[3] - bounds[2])
        dz = float(bounds[5] - bounds[4])
        if view in ("front", "back"):
            return dx, dz
        if view in ("left", "right"):
            return dy, dz
        if view in ("top", "bottom"):
            return dx, dy
        raise ValueError(view)

    @staticmethod
    def _layout_rects(bounds: np.ndarray, spacing_model: float) -> dict[str, tuple[float, float, float, float]]:
        dx = float(bounds[1] - bounds[0])
        dy = float(bounds[3] - bounds[2])
        dz = float(bounds[5] - bounds[4])
        s = float(spacing_model)
        return {
            "front": (0.0, 0.0, dx, dz),
            "left": (-(s + dy), 0.0, -s, dz),
            "right": (dx + s, 0.0, dx + s + dy, dz),
            "back": (dx + 2.0 * s + dy, 0.0, 2.0 * dx + 2.0 * s + dy, dz),
            "top": (0.0, dz + s, dx, dz + s + dy),
            "bottom": (0.0, -(s + dy), dx, -s),
        }

    @staticmethod
    def _camera_for_view(bounds: np.ndarray, view: str):
        center = np.array([
            (bounds[0] + bounds[1]) / 2,
            (bounds[2] + bounds[3]) / 2,
            (bounds[4] + bounds[5]) / 2,
        ], dtype=float)
        max_extent = max(bounds[1]-bounds[0], bounds[3]-bounds[2], bounds[5]-bounds[4], 1e-9)
        dist = float(max_extent) * 3.0
        if view == "front":
            pos, up = center + np.array([0, -dist, 0]), np.array([0, 0, 1])
        elif view == "back":
            pos, up = center + np.array([0, dist, 0]), np.array([0, 0, 1])
        elif view == "right":
            pos, up = center + np.array([dist, 0, 0]), np.array([0, 0, 1])
        elif view == "left":
            pos, up = center + np.array([-dist, 0, 0]), np.array([0, 0, 1])
        elif view == "top":
            pos, up = center + np.array([0, 0, dist]), np.array([0, 1, 0])
        elif view == "bottom":
            pos, up = center + np.array([0, 0, -dist]), np.array([0, 1, 0])
        else:
            raise ValueError(view)
        return pos, center, up

    def _render_views_for_mode(
        self,
        poly: pv.PolyData,
        bounds: np.ndarray,
        views: list[str],
        mode: str,
        pixels_per_model_unit: float,
        progress_callback=None,
        progress_base: int = 0,
        progress_total: int = 1,
    ) -> dict[str, np.ndarray]:
        """Render all selected views for one appearance mode using one VTK plotter.

        Reusing a single off-screen plotter avoids repeatedly copying a 700k-face
        PolyData and repeatedly constructing/destroying the VTK scene.
        """
        rendered: dict[str, np.ndarray] = {}
        pl = None
        try:
            # ``multi_samples`` is a QtInteractor option, not a portable
            # pv.Plotter constructor keyword.  Create the off-screen plotter
            # with public Plotter arguments only, then disable AA explicitly.
            pl = pv.Plotter(off_screen=True, window_size=(512, 512))
            try:
                pl.disable_anti_aliasing()
            except (AttributeError, TypeError):
                # Compatibility fallback for older PyVista/VTK combinations.
                try:
                    pl.ren_win.SetMultiSamples(0)
                except Exception:
                    pass
            pl.set_background("white")
            use_appearance = mode in ("texture", "texture_normal")
            lighting = mode in ("texture_normal", "shade")
            self._add_mesh_actor(pl, poly, use_appearance, lighting)
            pl.enable_parallel_projection()

            for i, view in enumerate(views):
                world_w, world_h = self._view_size(bounds, view)
                world_w = max(world_w, 1e-9)
                world_h = max(world_h, 1e-9)
                width = max(64, int(round(world_w * pixels_per_model_unit)))
                height = max(64, int(round(world_h * pixels_per_model_unit)))
                pl.window_size = [width, height]

                pos, center, up = self._camera_for_view(bounds, view)
                pl.camera_position = [pos.tolist(), center.tolist(), up.tolist()]
                pl.enable_parallel_projection()
                pl.camera.parallel_scale = world_h / 2.0
                pl.reset_camera_clipping_range()
                rendered[view] = pl.screenshot(
                    return_img=True,
                    transparent_background=True,
                    window_size=[width, height],
                )
                if progress_callback is not None:
                    done = progress_base + i + 1
                    progress_callback(
                        done / max(progress_total, 1),
                        f"オルソ生成中: {mode} / {view} ({done}/{progress_total})",
                    )
        finally:
            if pl is not None:
                try:
                    pl.close()
                except Exception:
                    pass
        return rendered

    @staticmethod
    def _paste_rgba(canvas, rgba, xy: tuple[int, int]):
        from PIL import Image
        arr = np.asarray(rgba, dtype=np.uint8)
        im = Image.fromarray(arr, mode="RGBA") if arr.shape[-1] == 4 else Image.fromarray(arr).convert("RGBA")
        canvas.alpha_composite(im, dest=xy)

    @staticmethod
    def _load_scale_font(size_px: int):
        from PIL import ImageFont
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size_px)
        except Exception:
            return ImageFont.load_default()

    def _draw_scale_bar(self, canvas, pixels_per_model_unit: float, scale_bar_mm: float, left_px: int, baseline_y: int):
        from PIL import ImageDraw
        model_length = float(scale_bar_mm) / float(self.asset.unit_to_mm)
        bar_px = max(1, int(round(model_length * pixels_per_model_unit)))
        draw = ImageDraw.Draw(canvas)
        line_w = max(2, int(round(canvas.width / 1600)))
        tick_h = max(10, line_w * 4)
        x0 = int(left_px)
        x1 = x0 + bar_px
        y = int(baseline_y)
        draw.line([(x0, y), (x1, y)], fill="black", width=line_w)
        draw.line([(x0, y - tick_h // 2), (x0, y + tick_h // 2)], fill="black", width=line_w)
        draw.line([(x1, y - tick_h // 2), (x1, y + tick_h // 2)], fill="black", width=line_w)

        label = f"{scale_bar_mm:g} mm"
        font = self._load_scale_font(max(18, int(round(canvas.width / 150))))
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = x0 + (bar_px - tw) / 2.0
        ty = y - tick_h / 2.0 - th - max(7, line_w * 2)
        draw.text((tx, ty), label, fill="black", font=font)

    def _compose_mode(
        self,
        rendered: dict[str, np.ndarray],
        views: list[str],
        rects: dict[str, tuple[float, float, float, float]],
        ppu: float,
        out_path: Path,
        scale_bar_mm: float,
    ) -> None:
        from PIL import Image

        selected_rects = [rects[v] for v in views]
        min_x = min(r[0] for r in selected_rects)
        min_y = min(r[1] for r in selected_rects)
        max_x = max(r[2] for r in selected_rects)
        max_y = max(r[3] for r in selected_rects)
        content_w = max(1, int(round((max_x - min_x) * ppu)))
        content_h = max(1, int(round((max_y - min_y) * ppu)))
        margin = 36
        scale_block_h = 110
        bar_px = int(round((scale_bar_mm / self.asset.unit_to_mm) * ppu))
        canvas_w = max(content_w + 2 * margin, bar_px + 2 * margin)
        canvas_h = content_h + 2 * margin + scale_block_h
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))

        for view in views:
            img = rendered[view]
            x0, _y0, _x1, y1 = rects[view]
            px = margin + int(round((x0 - min_x) * ppu))
            py = margin + int(round((max_y - y1) * ppu))
            self._paste_rgba(canvas, img, (px, py))

        baseline = canvas_h - 32
        self._draw_scale_bar(canvas, ppu, scale_bar_mm, margin, baseline)
        canvas.convert("RGB").save(out_path, format="PNG")

    def _save_individual_view(self, rgba, ppu: float, path: Path, scale_bar_mm: float):
        from PIL import Image
        arr = np.asarray(rgba, dtype=np.uint8)
        view_im = Image.fromarray(arr, mode="RGBA") if arr.shape[-1] == 4 else Image.fromarray(arr).convert("RGBA")
        margin = 30
        scale_block_h = 100
        bar_px = int(round((scale_bar_mm / self.asset.unit_to_mm) * ppu))
        width = max(view_im.width + 2 * margin, bar_px + 2 * margin)
        height = view_im.height + 2 * margin + scale_block_h
        canvas = Image.new("RGBA", (width, height), (255, 255, 255, 255))
        canvas.alpha_composite(view_im, dest=(margin, margin))
        self._draw_scale_bar(canvas, ppu, scale_bar_mm, margin, height - 30)
        canvas.convert("RGB").save(path, format="PNG")

    def export_orthos(
        self,
        out_dir: Path,
        views: list[str],
        modes: list[str],
        spacing_mm: float,
        scale_bar_mm: float,
        individual: bool,
        progress_callback=None,
    ) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        final_m = self._current_final_matrix()
        poly = self._make_polydata(final_m)
        pts = np.asarray(poly.points)
        bounds = np.array([
            pts[:, 0].min(), pts[:, 0].max(),
            pts[:, 1].min(), pts[:, 1].max(),
            pts[:, 2].min(), pts[:, 2].max(),
        ], dtype=float)
        spacing_model = float(spacing_mm) / float(self.asset.unit_to_mm)
        rects = self._layout_rects(bounds, spacing_model)
        selected_rects = [rects[v] for v in views]
        sheet_w = max(r[2] for r in selected_rects) - min(r[0] for r in selected_rects)
        sheet_h = max(r[3] for r in selected_rects) - min(r[1] for r in selected_rects)
        max_sheet = max(float(sheet_w), float(sheet_h), 1e-9)
        ppu = ORTHO_COMPOSITE_LONG_EDGE_PX / max_sheet
        stem = self.asset.source_path.stem
        written: list[Path] = []

        total_renders = max(len(modes) * len(views), 1)
        completed = 0
        for mode in modes:
            rendered = self._render_views_for_mode(
                poly,
                bounds,
                views,
                mode,
                ppu,
                progress_callback=progress_callback,
                progress_base=completed,
                progress_total=total_renders,
            )
            completed += len(views)

            composite = out_dir / f"{stem}_ortho_{mode}.png"
            self._compose_mode(rendered, views, rects, ppu, composite, scale_bar_mm)
            written.append(composite)
            if individual:
                for view in views:
                    path = out_dir / f"{stem}_{view}_{mode}.png"
                    self._save_individual_view(rendered[view], ppu, path, scale_bar_mm)
                    written.append(path)
            del rendered
        if progress_callback is not None:
            progress_callback(1.0, "オルソ画像生成完了")
        return written

    # ---------- Error ----------
    def _show_error(self, title: str, exc: Exception):
        traceback.print_exc()
        QMessageBox.critical(self, title, f"{exc}\n\n詳細はターミナル出力を確認してください。")
        self.statusBar().showMessage(str(exc))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
