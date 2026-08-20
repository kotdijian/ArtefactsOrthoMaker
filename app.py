from __future__ import annotations

import csv
import json
import math
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np
import pyvista as pv
import trimesh
from pyvistaqt import QtInteractor
from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QAction, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDial,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
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
APP_VERSION = "0.4.1"
SUPPORTED_SUFFIXES = {".obj", ".ply", ".glb"}
WORK_DIR = Path(__file__).resolve().parent
INPUT_DIR = WORK_DIR / "input"
OUTPUT_DIR = WORK_DIR / "output"
ORTHO_COMPOSITE_LONG_EDGE_PX = 3600
OUTLINE_ALPHA_THRESHOLD = 127.5
OUTLINE_PNG_WIDTH_PX = 2
OUTLINE_SVG_STROKE_MM = 0.25
MAX_PNG_DIMENSION_PX = 16384
MAX_PNG_PIXELS = 100_000_000



class OrthoPreviewWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("オルソ画像プレビュー")
        self.resize(1280, 900)

        self._items: list[tuple[str, QLabel, QPixmap]] = []
        self._zoom_percent = 100
        self._fit_width_mode = True

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        self.info_label = QLabel("姿勢決定後にプレビューできます。")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("表示倍率"))
        self.zoom_out_btn = QPushButton("-")
        self.zoom_out_btn.clicked.connect(lambda: self._step_zoom(-10))
        toolbar.addWidget(self.zoom_out_btn)

        self.zoom_label = QLabel("Fit width")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setMinimumWidth(90)
        toolbar.addWidget(self.zoom_label)

        self.zoom_reset_btn = QPushButton("100%")
        self.zoom_reset_btn.clicked.connect(self._set_actual_size)
        toolbar.addWidget(self.zoom_reset_btn)

        self.zoom_fit_btn = QPushButton("Fit width")
        self.zoom_fit_btn.clicked.connect(self._set_fit_width)
        toolbar.addWidget(self.zoom_fit_btn)

        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.clicked.connect(lambda: self._step_zoom(10))
        toolbar.addWidget(self.zoom_in_btn)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.gesture_hint = QLabel(
            "トラックパッド: ピンチでZoom / 2本指スクロールで移動　"
            "マウス: Ctrl+ホイールでZoom"
        )
        self.gesture_hint.setWordWrap(True)
        layout.addWidget(self.gesture_hint)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.viewport().installEventFilter(self)
        try:
            self.scroll.viewport().setAttribute(
                Qt.WidgetAttribute.WA_AcceptTouchEvents, True
            )
        except Exception:
            pass
        layout.addWidget(self.scroll)

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.container)

        self._update_zoom_label()

    def _clear_items(self):
        self._items.clear()
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _update_zoom_label(self):
        if self._fit_width_mode:
            self.zoom_label.setText(f"Fit width ({self._zoom_percent}%)")
        else:
            self.zoom_label.setText(f"{self._zoom_percent}%")

    def _fit_base_width(self) -> int:
        vw = max(200, self.scroll.viewport().width() - 24)
        return vw

    def _apply_zoom(self):
        if not self._items:
            return
        fit_w = self._fit_base_width()
        for _title, image_label, pix in self._items:
            if pix.isNull():
                continue
            if self._fit_width_mode:
                target_w = fit_w
            else:
                target_w = int(round(fit_w * (self._zoom_percent / 100.0)))
            target_w = max(100, target_w)
            scaled = pix.scaledToWidth(target_w, Qt.TransformationMode.SmoothTransformation)
            image_label.setPixmap(scaled)
        self._update_zoom_label()

    def _set_fit_width(self):
        self._fit_width_mode = True
        self._zoom_percent = 100
        self._apply_zoom()

    def _set_actual_size(self):
        self._fit_width_mode = False
        self._zoom_percent = 100
        self._apply_zoom()

    def _step_zoom(self, delta: int):
        if self._fit_width_mode:
            self._fit_width_mode = False
            self._zoom_percent = 100
        self._zoom_percent = max(10, min(800, self._zoom_percent + delta))
        self._apply_zoom()

    def set_message(self, message: str):
        self.info_label.setText(message)
        self._clear_items()

    def set_images(self, items: list[tuple[str, str]], summary: str = ""):
        self.info_label.setText(summary or "")
        self._clear_items()
        if not items:
            empty = QLabel("表示できるオルソPNGがありません。")
            empty.setWordWrap(True)
            self.container_layout.addWidget(empty)
            return

        for title, path in items:
            title_label = QLabel(title)
            title_label.setWordWrap(True)
            self.container_layout.addWidget(title_label)

            pix = QPixmap(path)
            image_label = QLabel()
            image_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            if pix.isNull():
                image_label.setText(f"画像を読み込めませんでした: {path}")
            else:
                self._items.append((title, image_label, pix))
            self.container_layout.addWidget(image_label)

        self._set_fit_width()

    def _native_pinch_zoom(self, value: float):
        """Apply macOS trackpad pinch zoom.

        QNativeGestureEvent.value() is a signed zoom delta.  Use an
        exponential scale factor so repeated small deltas feel smooth and
        symmetric for pinch-in / pinch-out.
        """
        try:
            value = float(value)
        except Exception:
            return
        if not math.isfinite(value) or abs(value) < 1e-9:
            return

        if self._fit_width_mode:
            self._fit_width_mode = False
            self._zoom_percent = 100

        factor = math.exp(value)
        target = int(round(self._zoom_percent * factor))
        self._zoom_percent = max(10, min(800, target))
        self._apply_zoom()

    def wheelEvent(self, event):
        # Ctrl + wheel = zoom, plain wheel = normal scroll.
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta != 0:
                self._step_zoom(10 if delta > 0 else -10)
                event.accept()
                return
        super().wheelEvent(event)

    def eventFilter(self, watched, event):
        if watched is self.scroll.viewport():
            etype = event.type()

            if etype == QEvent.Type.NativeGesture:
                try:
                    if (
                        event.gestureType()
                        == Qt.NativeGestureType.ZoomNativeGesture
                    ):
                        self._native_pinch_zoom(event.value())
                        event.accept()
                        return True
                except (AttributeError, TypeError):
                    pass

            if etype == QEvent.Type.Wheel:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    delta = event.angleDelta().y()
                    if delta != 0:
                        self._step_zoom(10 if delta > 0 else -10)
                        event.accept()
                        return True

            elif etype == QEvent.Type.Resize:
                self._apply_zoom()

        return super().eventFilter(watched, event)


class LithicPreviewGraphicsView(QGraphicsView):
    """Embedded lithic unfolded-view preview with robust line interaction."""

    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self.owner = owner
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(
            QGraphicsView.ViewportAnchor.AnchorViewCenter
        )
        self._fit_on_next_resize = True
        self._drag_section: tuple[str, str, str] | None = None

    def fit_scene(self):
        if self.scene() is None or self.scene().sceneRect().isEmpty():
            return
        self.fitInView(
            self.scene().sceneRect(),
            Qt.AspectRatioMode.KeepAspectRatio,
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_on_next_resize:
            self.fit_scene()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        factor = 1.12 if delta > 0 else 1.0 / 1.12
        self.scale(factor, factor)
        self._fit_on_next_resize = False
        event.accept()

    def _event_scene_pos(self, event):
        try:
            point = event.position().toPoint()
        except AttributeError:
            point = event.pos()
        return self.mapToScene(point)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self._event_scene_pos(event)
            hit = self.owner._pick_lithic_section_line(scene_pos)
            if hit is not None:
                self._drag_section = hit
                section_id, _axis, _panel_key = hit
                self.owner._select_lithic_section(section_id)
                event.accept()
                return
        self._drag_section = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_section is not None:
            section_id, axis, panel_key = self._drag_section
            self.owner._drag_lithic_section_line(
                section_id,
                axis,
                panel_key,
                self._event_scene_pos(event),
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if (
            self._drag_section is not None
            and event.button() == Qt.MouseButton.LeftButton
        ):
            section_id, _axis, _panel_key = self._drag_section
            self.owner._lithic_section_line_released(section_id)
            self._drag_section = None
            event.accept()
            return
        self._drag_section = None
        super().mouseReleaseEvent(event)


class LithicSectionLineItem(QGraphicsLineItem):
    """Passive blue section line; mouse interaction is handled by the view."""

    def __init__(
        self,
        owner,
        section_id: str,
        axis: str,
        panel_key: str,
        selected: bool = False,
    ):
        super().__init__()
        self.owner = owner
        self.section_id = section_id
        self.axis = axis
        self.panel_key = panel_key
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(50.0)
        self._set_pen(selected)

    def _set_pen(self, selected: bool):
        pen = QPen(QColor(0, 110, 255))
        pen.setWidth(5 if selected else 3)
        pen.setCosmetic(True)
        self.setPen(pen)


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

        # Lithic mode: minimum-volume OBB is the automatic initial pose.
        # Axis convention after OBB:
        #   X = short axis
        #   Y = long axis (maximum extent)
        #   Z = thickness axis (minimum extent)
        self.lithic_angles_deg = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.lithic_obb_native_extents: np.ndarray | None = None
        self.lithic_obb_extents: np.ndarray | None = None
        self.lithic_obb_elapsed_sec: float | None = None
        self.lithic_section_level_angle_deg: float = 0.0
        self.lithic_section_level_residual_deg: float | None = None
        self.lithic_section_left_point: np.ndarray | None = None
        self.lithic_section_right_point: np.ndarray | None = None
        self.lithic_section_point_count: int = 0

        # Lithic transform decomposition:
        # original -> OBB and OBB -> result are retained separately.
        self.lithic_raw_to_obb_centered_matrix = np.eye(4)
        self.lithic_original_to_obb_matrix = np.eye(4)
        self.lithic_auto_rotation_matrix = np.eye(4)
        self.lithic_confirmed_final_matrix: np.ndarray | None = None
        self.lithic_obb_to_result_matrix = np.eye(4)
        self.lithic_pose_confirmed = False

        # Interactive section definitions.  Axis "X" means an X-Z section
        # (plane y=constant); axis "Y" means a Y-Z section (plane x=constant).
        self.lithic_sections: list[dict] = []
        self.lithic_section_counter = {"X": 0, "Y": 0}
        self.lithic_active_section_id: str | None = None
        self.lithic_preview_panel_rects: dict[str, tuple[float, float, float, float]] = {}
        self.lithic_preview_line_items: dict[str, list[LithicSectionLineItem]] = {}
        self.lithic_preview_scene: QGraphicsScene | None = None
        self.lithic_preview_pixmap_path: Path | None = None
        self._lithic_preview_temp_dir: Path | None = None

        self._setting_lithic_rotation = False
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
        self._zoom_base_parallel_scale: float | None = None
        self._zoom_percent = 100
        self._updating_zoom_ui = False
        self._ortho_preview_window: OrthoPreviewWindow | None = None
        self._preview_temp_dir: Path | None = None
        self._preview_refresh_pending = False
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
        self.artifact_type_combo = QComboBox()
        self.artifact_type_combo.addItems(["土器", "石器"])
        self.artifact_type_combo.setCurrentText("土器")
        self.artifact_type_combo.currentTextChanged.connect(self._artifact_type_changed)

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
        file_form.addRow("モデル種別", self.artifact_type_combo)
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

        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Zoom"))
        self.zoom_out_btn = QPushButton("-")
        self.zoom_out_btn.clicked.connect(lambda: self._step_zoom(-10))
        zoom_row.addWidget(self.zoom_out_btn)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setMinimumWidth(56)
        zoom_row.addWidget(self.zoom_label)
        self.zoom_reset_btn = QPushButton("100%")
        self.zoom_reset_btn.clicked.connect(self._reset_zoom)
        zoom_row.addWidget(self.zoom_reset_btn)
        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.clicked.connect(lambda: self._step_zoom(10))
        zoom_row.addWidget(self.zoom_in_btn)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(25, 400)
        self.zoom_slider.setSingleStep(5)
        self.zoom_slider.setPageStep(25)
        self.zoom_slider.setValue(100)
        self.zoom_slider.valueChanged.connect(self._zoom_slider_changed)

        display_layout.addWidget(self.show_appearance)
        display_layout.addWidget(self.smooth_shading)
        display_layout.addLayout(view_mode_row)
        display_layout.addLayout(viewer_scale_row)
        display_layout.addLayout(zoom_row)
        display_layout.addWidget(self.zoom_slider)
        display_layout.addWidget(QLabel("Ortho Front＝正面平行投影 / Oblique＝斜め平行投影"))
        left_layout.addWidget(display_group)

        self.pottery_posture_group = QGroupBox("2. 水平・傾き")
        posture_layout = QVBoxLayout(self.pottery_posture_group)
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
        left_layout.addWidget(self.pottery_posture_group)

        self.pottery_front_group = QGroupBox("3. 正面（Z軸回転）")
        front_layout = QVBoxLayout(self.pottery_front_group)
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
        left_layout.addWidget(self.pottery_front_group)

        self.lithic_pose_group = QGroupBox("2. 石器姿勢（OBB + 3軸回転）")
        lithic_layout = QVBoxLayout(self.lithic_pose_group)

        self.lithic_obb_label = QLabel(
            "石器を選択すると minimum-volume oriented_bounds() を自動適用します。"
        )
        self.lithic_obb_label.setWordWrap(True)
        self.lithic_obb_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        lithic_layout.addWidget(self.lithic_obb_label)

        self.lithic_rotation_controls = {}
        for axis, axis_label, meaning in [("y", "Y", "長さ"), ("x", "X", "幅"), ("z", "Z", "厚さ")]:
            axis_box = QGroupBox(f"{axis_label}軸回転（{meaning}）")
            axis_layout = QVBoxLayout(axis_box)

            button_row = QHBoxLayout()
            minus90 = QPushButton("-90°")
            minus90.clicked.connect(
                lambda _=False, a=axis: self._increment_lithic_axis(a, -90.0)
            )
            zero = QPushButton("0°")
            zero.clicked.connect(
                lambda _=False, a=axis: self._set_lithic_axis_angle(a, 0.0)
            )
            plus90 = QPushButton("+90°")
            plus90.clicked.connect(
                lambda _=False, a=axis: self._increment_lithic_axis(a, 90.0)
            )
            button_row.addWidget(minus90)
            button_row.addWidget(zero)
            button_row.addWidget(plus90)
            axis_layout.addLayout(button_row)

            dial = QDial()
            dial.setRange(-1800, 1800)
            dial.setNotchesVisible(True)
            dial.setWrapping(False)
            dial.valueChanged.connect(
                lambda value, a=axis: self._lithic_dial_changed(a, value)
            )
            axis_layout.addWidget(dial)

            spin = QDoubleSpinBox()
            spin.setRange(-180.0, 180.0)
            spin.setDecimals(1)
            spin.setSingleStep(1.0)
            spin.setSuffix("°")
            spin.valueChanged.connect(
                lambda value, a=axis: self._lithic_spin_changed(a, value)
            )
            axis_layout.addWidget(spin)

            self.lithic_rotation_controls[axis] = {
                "dial": dial,
                "spin": spin,
                "minus90": minus90,
                "zero": zero,
                "plus90": plus90,
            }
            lithic_layout.addWidget(axis_box)

        self.lithic_reset_btn = QPushButton("自動姿勢に戻す（手動回転 0°）")
        self.lithic_reset_btn.clicked.connect(self._reset_lithic_rotations)
        lithic_layout.addWidget(self.lithic_reset_btn)

        self.lithic_hint = QLabel(
            "自動初期姿勢: ① minimum-volume OBBで X=幅 / Y=長さ / "
            "Z=厚さ、②中央X-Z断面の左右端を結ぶ線がX軸に平行になるよう "
            "Y軸回転で自動補正。各軸の±90°ボタン、ダイヤル、数値入力は "
            "この自動姿勢に対する追加回転です。"
        )
        self.lithic_hint.setWordWrap(True)
        lithic_layout.addWidget(self.lithic_hint)

        self.lithic_confirm_btn = QPushButton("姿勢決定")
        self.lithic_confirm_btn.clicked.connect(self._confirm_lithic_pose)
        lithic_layout.addWidget(self.lithic_confirm_btn)
        left_layout.addWidget(self.lithic_pose_group)

        # Lithic output panel.  It becomes visible after "姿勢決定".
        self.lithic_output_group = QGroupBox("3. 石器 出力 / 断面設定")
        lithic_output_layout = QVBoxLayout(self.lithic_output_group)

        self.lithic_return_pose_btn = QPushButton("石器姿勢に戻る")
        self.lithic_return_pose_btn.clicked.connect(self._return_to_lithic_pose)
        lithic_output_layout.addWidget(self.lithic_return_pose_btn)

        lithic_output_layout.addWidget(QLabel("出力面（デフォルト6面）"))
        self.lithic_view_checks = {}
        for key, label in [
            ("front", "Front"),
            ("back", "Back"),
            ("left", "Left"),
            ("right", "Right"),
            ("top", "Top"),
            ("bottom", "Bottom"),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(True)
            self.lithic_view_checks[key] = cb
            lithic_output_layout.addWidget(cb)

        lithic_output_layout.addWidget(QLabel("表現"))
        self.lithic_mode_texture = QCheckBox("テクスチャ / 頂点カラー")
        self.lithic_mode_texture_normal = QCheckBox(
            "テクスチャ / 頂点カラー + Normal"
        )
        self.lithic_mode_shade = QCheckBox("Normalのみ（シェード）")
        for cb in (
            self.lithic_mode_texture,
            self.lithic_mode_texture_normal,
            self.lithic_mode_shade,
        ):
            cb.setChecked(True)
            lithic_output_layout.addWidget(cb)

        lithic_spacing_row = QHBoxLayout()
        lithic_spacing_row.addWidget(QLabel("面間隔"))
        self.lithic_view_spacing = QDoubleSpinBox()
        self.lithic_view_spacing.setRange(0.0, 10000.0)
        self.lithic_view_spacing.setValue(10.0)
        self.lithic_view_spacing.setDecimals(1)
        self.lithic_view_spacing.setSuffix(" mm")
        lithic_spacing_row.addWidget(self.lithic_view_spacing)
        lithic_output_layout.addLayout(lithic_spacing_row)

        lithic_scale_row = QHBoxLayout()
        lithic_scale_row.addWidget(QLabel("スケールバー"))
        self.lithic_scale_bar_combo = QComboBox()
        self.lithic_scale_bar_combo.addItems(["20 mm", "50 mm", "100 mm"])
        self.lithic_scale_bar_combo.setCurrentText("50 mm")
        lithic_scale_row.addWidget(self.lithic_scale_bar_combo)
        lithic_output_layout.addLayout(lithic_scale_row)

        lithic_output_layout.addWidget(QLabel("出力形式"))
        self.lithic_output_png = QCheckBox("PNGのみ")
        self.lithic_output_png.setChecked(True)
        self.lithic_output_svg = QCheckBox("SVG")
        self.lithic_output_svg.setChecked(False)
        self.lithic_outline_overlay = QCheckBox("PNG+輪郭（SVG由来）")
        self.lithic_outline_overlay.setChecked(False)
        lithic_output_layout.addWidget(self.lithic_output_png)
        lithic_output_layout.addWidget(self.lithic_output_svg)
        lithic_output_layout.addWidget(self.lithic_outline_overlay)

        lithic_outline_width_row = QHBoxLayout()
        lithic_outline_width_row.addWidget(QLabel("PNG輪郭線太さ"))
        self.lithic_outline_width_combo = QComboBox()
        self.lithic_outline_width_combo.addItems(["1 px", "2 px", "3 px", "5 px"])
        self.lithic_outline_width_combo.setCurrentText("2 px")
        lithic_outline_width_row.addWidget(self.lithic_outline_width_combo)
        lithic_output_layout.addLayout(lithic_outline_width_row)

        self.lithic_export_individual = QCheckBox(
            "各面・断面を個別ファイルでも出力"
        )
        self.lithic_export_individual.setChecked(False)
        lithic_output_layout.addWidget(self.lithic_export_individual)

        lithic_output_layout.addWidget(QLabel("断面設定"))
        section_buttons = QHBoxLayout()
        self.lithic_add_section_x_btn = QPushButton("断面追加（X）")
        self.lithic_add_section_x_btn.clicked.connect(
            lambda: self._add_lithic_section("X")
        )
        self.lithic_add_section_y_btn = QPushButton("断面追加（Y）")
        self.lithic_add_section_y_btn.clicked.connect(
            lambda: self._add_lithic_section("Y")
        )
        self.lithic_delete_section_btn = QPushButton("削除")
        self.lithic_delete_section_btn.clicked.connect(
            self._delete_selected_lithic_section
        )
        section_buttons.addWidget(self.lithic_add_section_x_btn)
        section_buttons.addWidget(self.lithic_add_section_y_btn)
        section_buttons.addWidget(self.lithic_delete_section_btn)
        lithic_output_layout.addLayout(section_buttons)

        self.lithic_section_status_label = QLabel(
            "初期断面: X=Y長さ1/2（X-Z断面） / "
            "Y=X幅1/2（Y-Z断面）"
        )
        self.lithic_section_status_label.setWordWrap(True)
        lithic_output_layout.addWidget(self.lithic_section_status_label)

        self.lithic_preview_btn = QPushButton("プレビュー確認")
        self.lithic_preview_btn.clicked.connect(self._show_lithic_output_preview)
        lithic_output_layout.addWidget(self.lithic_preview_btn)

        self.lithic_save_next_btn = QPushButton("保存して次へ")
        self.lithic_save_next_btn.clicked.connect(self.save_current_and_next)
        self.lithic_inventory_btn = QPushButton("計測一覧出力")
        self.lithic_inventory_btn.clicked.connect(self.export_measurement_inventory)
        self.lithic_export_stage_label = QLabel("待機")
        self.lithic_export_progress = QProgressBar()
        self.lithic_export_progress.setRange(0, 100)
        self.lithic_export_progress.setValue(0)
        lithic_output_layout.addWidget(self.lithic_inventory_btn)
        lithic_output_layout.addWidget(QLabel(
            "計測一覧出力: geometry inventory と 3D model inventory を更新します。"
            "「保存して次へ」の前に実行してください。"
        ))
        lithic_output_layout.addWidget(self.lithic_save_next_btn)
        lithic_output_layout.addWidget(self.lithic_export_stage_label)
        lithic_output_layout.addWidget(self.lithic_export_progress)
        left_layout.addWidget(self.lithic_output_group)

        self.ortho_group = QGroupBox("4. オルソ画像 / 輪郭線")
        ortho_layout = QVBoxLayout(self.ortho_group)
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

        ortho_layout.addWidget(QLabel("表現（基本3種はデフォルトON、特殊図はデフォルトOFF）"))
        self.mode_texture = QCheckBox("テクスチャ / 頂点カラー")
        self.mode_texture_normal = QCheckBox("テクスチャ / 頂点カラー + Normal")
        self.mode_shade = QCheckBox("Normalのみ（シェード）")
        self.mode_section = QCheckBox("縦断面")
        self.mode_half_section = QCheckBox("半截")
        self.mode_quarter_half = QCheckBox("1/4半截")
        for cb in (self.mode_texture, self.mode_texture_normal, self.mode_shade):
            cb.setChecked(True)
            ortho_layout.addWidget(cb)
        for cb in (self.mode_section, self.mode_half_section, self.mode_quarter_half):
            cb.setChecked(False)
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

        ortho_layout.addWidget(QLabel("出力形式"))
        self.output_png = QCheckBox("PNGのみ")
        self.output_png.setChecked(True)
        self.output_svg = QCheckBox("SVG")
        self.output_svg.setChecked(False)
        self.outline_overlay = QCheckBox("PNG+輪郭（SVG由来）")
        self.outline_overlay.setChecked(False)
        ortho_layout.addWidget(self.output_png)
        ortho_layout.addWidget(self.output_svg)
        ortho_layout.addWidget(self.outline_overlay)

        outline_width_row = QHBoxLayout()
        outline_width_row.addWidget(QLabel("PNG輪郭線太さ"))
        self.outline_width_combo = QComboBox()
        self.outline_width_combo.addItems(["1 px", "2 px", "3 px", "5 px"])
        self.outline_width_combo.setCurrentText("2 px")
        outline_width_row.addWidget(self.outline_width_combo)
        ortho_layout.addLayout(outline_width_row)

        self.export_individual = QCheckBox("各面を個別ファイルでも出力")
        self.export_individual.setChecked(False)
        ortho_layout.addWidget(self.export_individual)
        left_layout.addWidget(self.ortho_group)

        self.export_group = QGroupBox("5. 保存 / 次のファイル")
        export_layout = QVBoxLayout(self.export_group)
        self.preview_btn = QPushButton("オルソ画像プレビューを開く")
        self.preview_btn.clicked.connect(self.open_ortho_preview)
        self.save_next_btn = QPushButton("保存して次へ")
        self.save_next_btn.clicked.connect(self.save_current_and_next)
        self.inventory_btn = QPushButton("計測一覧出力")
        self.inventory_btn.clicked.connect(self.export_measurement_inventory)
        self.export_stage_label = QLabel("待機")
        self.export_progress = QProgressBar()
        self.export_progress.setRange(0, 100)
        self.export_progress.setValue(0)
        export_layout.addWidget(self.preview_btn)
        export_layout.addWidget(self.inventory_btn)
        export_layout.addWidget(QLabel(
            "計測一覧出力: geometry inventory と 3D model inventory を更新します。"
            "「保存して次へ」の前に実行してください。"
        ))
        export_layout.addWidget(self.save_next_btn)
        export_layout.addWidget(self.export_stage_label)
        export_layout.addWidget(self.export_progress)
        export_layout.addWidget(QLabel(
            "output/<元ファイル名>/ に _revモデル、transform、合成オルソPNGを保存します。"
        ))
        left_layout.addWidget(self.export_group)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(controls)
        scroll.setMinimumWidth(390)
        splitter.addWidget(scroll)

        self.viewer_stack = QStackedWidget()

        # Pottery viewer: the proven single interactive view from v0.1.x.
        view_widget = QWidget()
        view_layout = QVBoxLayout(view_widget)
        self.plotter = QtInteractor(view_widget, auto_update=False, multi_samples=0)
        self.plotter.set_background("white")
        self.plotter.add_axes()

        # GUI shading fix retained from the pottery implementation.
        try:
            self.plotter.renderer.AutomaticLightCreationOn()
            self.plotter.renderer.LightFollowCameraOn()
        except AttributeError:
            pass

        self.plotter.installEventFilter(self)
        self._vtk_widget = self.plotter.interactor
        try:
            self._vtk_widget.installEventFilter(self)
        except Exception:
            pass
        view_layout.addWidget(self._vtk_widget)
        self.viewer_stack.addWidget(view_widget)

        # Lithic provisional viewer: three synchronized orthographic views.
        self.lithic_view_widget = QWidget()
        lithic_view_layout = QGridLayout(self.lithic_view_widget)
        self.lithic_plotters = {}
        self.lithic_vtk_widgets = {}

        lithic_specs = [
            ("front", "Front (X-Y)", 0, 0, 2, 1),
            ("right", "Right (Y-Z)", 0, 1, 1, 1),
            ("bottom", "Bottom (X-Z)", 1, 1, 1, 1),
        ]
        for key, title, row, col, rowspan, colspan in lithic_specs:
            panel = QGroupBox(title)
            panel_layout = QVBoxLayout(panel)
            plotter = QtInteractor(panel, auto_update=False, multi_samples=0)
            plotter.set_background("white")
            plotter.add_axes()
            try:
                plotter.renderer.AutomaticLightCreationOn()
                plotter.renderer.LightFollowCameraOn()
            except AttributeError:
                pass
            vtk_widget = plotter.interactor
            panel_layout.addWidget(vtk_widget)
            self.lithic_plotters[key] = plotter
            self.lithic_vtk_widgets[key] = vtk_widget
            lithic_view_layout.addWidget(panel, row, col, rowspan, colspan)

        lithic_view_layout.setColumnStretch(0, 2)
        lithic_view_layout.setColumnStretch(1, 1)
        lithic_view_layout.setRowStretch(0, 1)
        lithic_view_layout.setRowStretch(1, 1)
        self.viewer_stack.addWidget(self.lithic_view_widget)

        # Lithic unfolded-layout preview.  Unlike the pottery preview this is
        # embedded in the right-hand main area, not a separate window.
        self.lithic_preview_widget = QWidget()
        lithic_preview_layout = QVBoxLayout(self.lithic_preview_widget)
        self.lithic_preview_info = QLabel(
            "「プレビュー確認」で6面展開・断面を生成します。"
        )
        self.lithic_preview_info.setWordWrap(True)
        lithic_preview_layout.addWidget(self.lithic_preview_info)
        self.lithic_preview_view = LithicPreviewGraphicsView(self)
        self.lithic_preview_scene = QGraphicsScene(self.lithic_preview_view)
        self.lithic_preview_view.setScene(self.lithic_preview_scene)
        lithic_preview_layout.addWidget(self.lithic_preview_view)
        self.viewer_stack.addWidget(self.lithic_preview_widget)

        splitter.addWidget(self.viewer_stack)
        splitter.setStretchFactor(1, 1)

        self._update_zoom_label()
        self._set_enabled(False)
        self._connect_preview_refresh_signals()
        self._update_artifact_type_ui()

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
            self.mode_section, self.mode_half_section, self.mode_quarter_half,
            self.view_spacing, self.scale_bar_combo, self.outline_width_combo,
            self.output_png, self.output_svg, self.outline_overlay, self.export_individual,
            self.view_mode_combo, self.viewer_scale_combo,
            self.zoom_out_btn, self.zoom_reset_btn, self.zoom_in_btn, self.zoom_slider,
            self.preview_btn, self.save_next_btn, self.inventory_btn,
            self.lithic_reset_btn, self.lithic_confirm_btn,
            self.lithic_return_pose_btn, self.lithic_preview_btn,
            self.lithic_save_next_btn, self.lithic_inventory_btn,
            self.lithic_view_spacing, self.lithic_scale_bar_combo,
            self.lithic_outline_width_combo,
            self.lithic_output_png, self.lithic_output_svg,
            self.lithic_outline_overlay, self.lithic_export_individual,
            self.lithic_mode_texture, self.lithic_mode_texture_normal,
            self.lithic_mode_shade,
            self.lithic_add_section_x_btn, self.lithic_add_section_y_btn,
            self.lithic_delete_section_btn,
        ] + list(self.view_checks.values()) + list(self.lithic_view_checks.values())
        for controls in self.lithic_rotation_controls.values():
            widgets.extend(controls.values())
        for w in widgets:
            w.setEnabled(loaded)
        if loaded:
            self._update_artifact_type_ui()


    def _connect_preview_refresh_signals(self):
        for cb in [
            self.mode_texture,
            self.mode_texture_normal,
            self.mode_shade,
            self.mode_section,
            self.mode_half_section,
            self.mode_quarter_half,
            self.output_png,
            self.output_svg,
            self.outline_overlay,
            self.export_individual,
            *self.view_checks.values(),
        ]:
            cb.stateChanged.connect(self._schedule_preview_refresh)

        self.view_spacing.valueChanged.connect(self._schedule_preview_refresh)
        self.scale_bar_combo.currentTextChanged.connect(self._schedule_preview_refresh)
        self.outline_width_combo.currentTextChanged.connect(self._schedule_preview_refresh)
        self.view_mode_combo.currentTextChanged.connect(self._schedule_preview_refresh)
        self.viewer_scale_combo.currentTextChanged.connect(self._schedule_preview_refresh)

    @staticmethod
    def _preview_mode_title(mode: str) -> str:
        return {
            "texture": "テクスチャ / 頂点カラー",
            "texture_normal": "テクスチャ / 頂点カラー + Normal",
            "shade": "Normalのみ（シェード）",
        }.get(mode, mode)

    def open_ortho_preview(self):
        if self._ortho_preview_window is None:
            self._ortho_preview_window = OrthoPreviewWindow(self)
        self._ortho_preview_window.show()
        self._ortho_preview_window.raise_()
        self._ortho_preview_window.activateWindow()
        self._refresh_ortho_preview()

    def _schedule_preview_refresh(self, *_args):
        if self._ortho_preview_window is None or not self._ortho_preview_window.isVisible():
            return
        if self._preview_refresh_pending:
            return
        self._preview_refresh_pending = True
        QTimer.singleShot(120, self._refresh_ortho_preview)

    def _clear_preview_temp_dir(self):
        try:
            if self._preview_temp_dir is not None and self._preview_temp_dir.exists():
                shutil.rmtree(self._preview_temp_dir)
        except Exception:
            pass
        self._preview_temp_dir = None

    def _refresh_ortho_preview(self):
        self._preview_refresh_pending = False
        if self._ortho_preview_window is None or not self._ortho_preview_window.isVisible():
            return
        if not self.asset:
            self._ortho_preview_window.set_message("モデル未読込です。")
            return
        if not self.posture_done:
            self._ortho_preview_window.set_message("姿勢決定後にオルソ画像プレビューを表示します。")
            return

        views = [k for k, cb in self.view_checks.items() if cb.isChecked()]
        if not views:
            self._ortho_preview_window.set_message("少なくとも1つのオルソ面を選択してください。")
            return

        modes = self._selected_render_modes()
        base_modes = [m for m in modes if m in ("texture", "texture_normal", "shade")]
        export_png_plain = self.output_png.isChecked()
        export_png_outline = self.outline_overlay.isChecked()

        if not export_png_plain and not export_png_outline:
            self._ortho_preview_window.set_message(
                "プレビューはPNG系のみ対応です。"
                "「PNGのみ」または「PNG+輪郭」をONにしてください。"
            )
            return
        if not base_modes:
            self._ortho_preview_window.set_message(
                "プレビュー対象の基本表現がありません。"
                "テクスチャ / テクスチャ+Normal / シェードの少なくとも1つをONにしてください。"
            )
            return

        try:
            self._ortho_preview_window.set_message("プレビュー生成中…")
            QApplication.processEvents()

            self._clear_preview_temp_dir()
            self._preview_temp_dir = Path(tempfile.mkdtemp(prefix="artifact_pose_preview_"))

            written = self.export_orthos(
                self._preview_temp_dir,
                views=views,
                modes=modes,
                spacing_mm=float(self.view_spacing.value()),
                scale_bar_mm=self._selected_scale_bar_mm(),
                outline_width_px=self._selected_outline_width_px(),
                individual=False,
                export_png_plain=export_png_plain,
                export_svg=False,
                export_png_outline=export_png_outline,
                progress_callback=None,
            )

            items: list[tuple[str, str]] = []
            stem = self.asset.source_path.stem
            for mode in base_modes:
                title = self._preview_mode_title(mode)
                if export_png_plain:
                    p = self._preview_temp_dir / f"{stem}_ortho_{mode}.png"
                    if p.exists():
                        items.append((f"{title} / PNG", str(p)))
                if export_png_outline:
                    p = self._preview_temp_dir / f"{stem}_ortho_{mode}_outline.png"
                    if p.exists():
                        items.append((f"{title} / PNG+輪郭", str(p)))

            if not items:
                self._ortho_preview_window.set_message("表示できるプレビュー画像が生成されませんでした。")
                return

            summary = (
                f"プレビュー対象: {self.asset.source_path.name} / "
                f"面: {', '.join(views)} / "
                f"表現数: {len(items)}"
            )
            self._ortho_preview_window.set_images(items, summary=summary)
        except Exception as e:
            self._ortho_preview_window.set_message(f"プレビュー生成エラー: {e}")

    # ---------- Artifact type / Lithic initial pose ----------
    def _is_lithic(self) -> bool:
        return self.artifact_type_combo.currentText() == "石器"

    def _update_artifact_type_ui(self):
        lithic = self._is_lithic()

        self.pottery_posture_group.setVisible(not lithic)
        self.pottery_front_group.setVisible(not lithic)
        self.ortho_group.setVisible(not lithic)
        self.export_group.setVisible(not lithic)

        if lithic:
            self.lithic_pose_group.setVisible(not self.lithic_pose_confirmed)
            self.lithic_output_group.setVisible(self.lithic_pose_confirmed)
            if hasattr(self, "viewer_stack"):
                # Preserve preview page while confirmed; otherwise show pose.
                if not self.lithic_pose_confirmed:
                    self.viewer_stack.setCurrentIndex(1)
                elif self.viewer_stack.currentIndex() not in (1, 2):
                    self.viewer_stack.setCurrentIndex(1)
        else:
            self.lithic_pose_group.setVisible(False)
            self.lithic_output_group.setVisible(False)
            if hasattr(self, "viewer_stack"):
                self.viewer_stack.setCurrentIndex(0)

        # The single-view camera controls belong to the pottery viewer.
        for w in (
            self.view_mode_combo,
            self.viewer_scale_combo,
            self.zoom_out_btn,
            self.zoom_reset_btn,
            self.zoom_in_btn,
            self.zoom_slider,
        ):
            w.setEnabled(bool(self.asset) and not lithic)

        if self.asset is not None:
            has_appearance = self.asset.appearance_kind != "none"
            self.show_appearance.setEnabled(has_appearance)
            self.smooth_shading.setEnabled(True)

    def _artifact_type_changed(self, *_args):
        self._update_artifact_type_ui()
        if not self.asset:
            return

        # Changing artifact type resets all pose state; the mesh itself is
        # retained and does not need to be reloaded.
        self.initial_axis = None
        self.reference_plane = None
        self.pose_matrix = np.eye(4)
        self.front_angle_deg = 0.0
        self.center_axis_after_pose = None
        self.pose_info = {}
        self.posture_done = False
        self.lithic_section_level_angle_deg = 0.0
        self.lithic_section_level_residual_deg = None
        self.lithic_section_left_point = None
        self.lithic_section_right_point = None
        self.lithic_section_point_count = 0
        self.lithic_raw_to_obb_centered_matrix = np.eye(4)
        self.lithic_original_to_obb_matrix = np.eye(4)
        self.lithic_auto_rotation_matrix = np.eye(4)
        self.lithic_confirmed_final_matrix = None
        self.lithic_obb_to_result_matrix = np.eye(4)
        self.lithic_pose_confirmed = False
        self._reset_lithic_section_definitions()
        self.manual_points = []
        self.manual_pick_label.setText("選択点: 0 / 3")

        self._configure_appearance_options()
        if self._is_lithic():
            self._apply_lithic_oriented_bounds()
        else:
            self.pose_label.setText("姿勢未確定")
            self.refresh_view(reset_camera=True)

    @staticmethod
    def _axis_rotation_matrix(axis: str, deg: float) -> np.ndarray:
        a = math.radians(float(deg))
        c = math.cos(a)
        s = math.sin(a)
        R = np.eye(4)
        if axis == "x":
            R[:3, :3] = np.array([
                [1.0, 0.0, 0.0],
                [0.0, c, -s],
                [0.0, s, c],
            ])
        elif axis == "y":
            R[:3, :3] = np.array([
                [c, 0.0, s],
                [0.0, 1.0, 0.0],
                [-s, 0.0, c],
            ])
        elif axis == "z":
            R[:3, :3] = np.array([
                [c, -s, 0.0],
                [s, c, 0.0],
                [0.0, 0.0, 1.0],
            ])
        else:
            raise ValueError(axis)
        return R

    @staticmethod
    def _translation_matrix_xyz(x: float, y: float, z: float) -> np.ndarray:
        T = np.eye(4)
        T[:3, 3] = [float(x), float(y), float(z)]
        return T

    def _lithic_adjustment_matrix(self) -> np.ndarray:
        # GUI/control order is Y (length), X (width), Z (thickness).
        # Column-vector application order: Y -> X -> Z.
        Ry = self._axis_rotation_matrix("y", self.lithic_angles_deg["y"])
        Rx = self._axis_rotation_matrix("x", self.lithic_angles_deg["x"])
        Rz = self._axis_rotation_matrix("z", self.lithic_angles_deg["z"])
        return Rz @ Rx @ Ry

    def _current_lithic_unorigin_matrix(self) -> np.ndarray:
        """Raw -> current orientation, still centered around the OBB center."""
        return (
            self._lithic_adjustment_matrix()
            @ self.lithic_auto_rotation_matrix
            @ self.lithic_raw_to_obb_centered_matrix
        )

    def _current_lithic_matrix(self) -> np.ndarray:
        if self.lithic_pose_confirmed and self.lithic_confirmed_final_matrix is not None:
            return np.asarray(self.lithic_confirmed_final_matrix, dtype=float)
        return self._current_lithic_unorigin_matrix()

    def _compute_lithic_confirmed_transform(self) -> tuple[np.ndarray, np.ndarray]:
        """Set result origin to the final AABB min corner.

        Returns:
            final raw->result matrix,
            OBB->result matrix.
        """
        if not self.asset:
            raise RuntimeError("No mesh loaded")

        unorigin = self._current_lithic_unorigin_matrix()
        vertices = trimesh.transform_points(
            np.asarray(self.asset.mesh.vertices, dtype=float),
            unorigin,
        )
        if len(vertices) == 0:
            raise RuntimeError("石器の座標原点を計算できません。")
        corner = np.min(vertices, axis=0)
        origin_shift = self._translation_matrix_xyz(
            -corner[0], -corner[1], -corner[2]
        )
        final_matrix = origin_shift @ unorigin
        obb_to_result = (
            final_matrix @ np.linalg.inv(self.lithic_original_to_obb_matrix)
        )
        return final_matrix, obb_to_result

    def _lithic_mid_xz_section_points(
        self,
        raw_to_obb: np.ndarray,
        face_chunk_size: int = 200_000,
    ) -> np.ndarray:
        """Return exact central X-Z triangle/plane intersections.

        The automatic OBB pose is centered, so the section plane is y=0.
        For large archaeological scans, trimesh.section() can spend substantial
        time constructing Path topology.  Here only the section geometry needed
        for leveling is required, so triangle edges are intersected with y=0
        directly in chunks.

        This preserves the actual mesh section while keeping peak memory and
        runtime practical for multi-million-face models.
        """
        if not self.asset:
            raise RuntimeError("No mesh loaded")

        T = np.asarray(raw_to_obb, dtype=float)
        vertices_raw = np.asarray(self.asset.mesh.vertices, dtype=float)
        faces = np.asarray(self.asset.mesh.faces, dtype=np.int64)

        if len(vertices_raw) == 0 or len(faces) == 0:
            raise RuntimeError("中央X-Z断面を計算できるメッシュがありません。")

        # Transform vertices once.  For the sample 1.28M-vertex lithic this is
        # much cheaper than building a transformed mesh copy and section Path.
        vertices = trimesh.transform_points(vertices_raw, T)

        y_span = float(np.ptp(vertices[:, 1]))
        eps = max(y_span * 1.0e-12, 1.0e-12)
        intersections: list[np.ndarray] = []

        edges = ((0, 1), (1, 2), (2, 0))
        chunk = max(10_000, int(face_chunk_size))

        for start_face in range(0, len(faces), chunk):
            face_ids = faces[start_face:start_face + chunk]
            tri = vertices[face_ids]

            for a, b in edges:
                p0 = tri[:, a, :]
                p1 = tri[:, b, :]
                y0 = p0[:, 1]
                y1 = p1[:, 1]
                denom = y0 - y1

                crosses = (
                    (
                        ((y0 <= eps) & (y1 >= -eps))
                        | ((y1 <= eps) & (y0 >= -eps))
                    )
                    & (np.abs(denom) > eps)
                )

                if not np.any(crosses):
                    continue

                t = y0[crosses] / denom[crosses]
                pts = (
                    p0[crosses]
                    + t[:, None] * (p1[crosses] - p0[crosses])
                )
                intersections.append(pts)

            # Rare coplanar vertices/edges: add vertices lying almost exactly
            # on y=0.  Duplicates are harmless for robust percentile statistics.
            near_plane = np.abs(tri[:, :, 1]) <= eps
            if np.any(near_plane):
                coplanar_pts = tri[near_plane]
                if len(coplanar_pts):
                    intersections.append(coplanar_pts)

        if not intersections:
            raise RuntimeError("中央X-Z断面 (y=0) がモデルと交差しません。")

        points = np.vstack(intersections)
        finite = np.isfinite(points).all(axis=1)
        points = points[finite]

        if len(points) < 4:
            raise RuntimeError("中央X-Z断面に有効な点が不足しています。")

        # Force the numerical plane coordinate to zero; only X/Z are used.
        points[:, 1] = 0.0
        return points

    @staticmethod
    def _lithic_robust_section_endpoints(
        points_obb: np.ndarray,
        tail_fraction: float = 0.02,
    ) -> tuple[np.ndarray, np.ndarray, dict]:
        """Estimate robust left/right endpoints of the central X-Z section.

        A literal single min/max vertex is unstable on scanned lithics.
        Therefore:
          * X location = global left/right extreme
          * Z location = median Z of the outer 2% tails
        """
        pts = np.asarray(points_obb, dtype=float)
        x = pts[:, 0]
        z = pts[:, 2]

        if len(pts) < 4:
            raise RuntimeError("断面端点推定に十分な点がありません。")

        q = float(max(0.001, min(0.20, tail_fraction)))
        q_left = float(np.quantile(x, q))
        q_right = float(np.quantile(x, 1.0 - q))

        left_mask = x <= q_left
        right_mask = x >= q_right
        left_count = int(np.count_nonzero(left_mask))
        right_count = int(np.count_nonzero(right_mask))

        if left_count == 0 or right_count == 0:
            raise RuntimeError("断面左右端の候補点を取得できません。")

        left = np.array(
            [float(np.min(x)), 0.0, float(np.median(z[left_mask]))],
            dtype=float,
        )
        right = np.array(
            [float(np.max(x)), 0.0, float(np.median(z[right_mask]))],
            dtype=float,
        )

        dx = float(right[0] - left[0])
        if abs(dx) <= 1e-12:
            raise RuntimeError("断面左右端のX距離がゼロです。")

        angle_deg = math.degrees(
            math.atan2(
                float(right[2] - left[2]),
                dx,
            )
        )

        diagnostics = {
            "tail_fraction": q,
            "left_tail_count": left_count,
            "right_tail_count": right_count,
            "left_quantile_x": q_left,
            "right_quantile_x": q_right,
            "angle_before_deg": float(angle_deg),
        }
        return left, right, diagnostics

    def _lithic_section_level_correction(
        self,
        raw_to_obb: np.ndarray,
    ) -> tuple[np.ndarray, dict]:
        """Level the central X-Z section by a rotation about the Y long axis."""
        points_obb = self._lithic_mid_xz_section_points(raw_to_obb)
        left, right, diag = self._lithic_robust_section_endpoints(
            points_obb,
            tail_fraction=0.02,
        )

        angle_before = float(diag["angle_before_deg"])

        # With this application's Ry convention:
        #   x' = cos(a)x + sin(a)z
        #   z' = -sin(a)x + cos(a)z
        # a line at angle theta in X-Z becomes theta-a, hence a=theta.
        correction = self._axis_rotation_matrix("y", angle_before)

        left_after = trimesh.transform_points(left.reshape(1, 3), correction)[0]
        right_after = trimesh.transform_points(right.reshape(1, 3), correction)[0]
        residual = math.degrees(
            math.atan2(
                float(right_after[2] - left_after[2]),
                float(right_after[0] - left_after[0]),
            )
        )

        diag.update(
            {
                "section_point_count": int(len(points_obb)),
                "left_point_obb": left.tolist(),
                "right_point_obb": right.tolist(),
                "correction_axis": "Y",
                "correction_angle_deg": angle_before,
                "residual_angle_deg": float(residual),
                "endpoint_method": (
                    "global X extremes with median Z of outer 2% X tails"
                ),
                "section_plane": "OBB-centered y=0 (X-Z plane); exact triangle-edge intersections",
            }
        )
        return correction, diag

    def _apply_lithic_oriented_bounds(self):
        if not self.asset:
            return
        try:
            # trimesh.bounds.oriented_bounds() needs SciPy for the 3D convex
            # hull (scipy.spatial.ConvexHull).  Check explicitly here because
            # Trimesh may otherwise fall through to its coplanar fallback and
            # surface the misleading "Points must be coplanar" error.
            try:
                import scipy  # noqa: F401
            except ModuleNotFoundError as e:
                raise RuntimeError(
                    "石器の oriented_bounds() には SciPy が必要です。\n"
                    "現在の仮想環境で次を実行してください:\n\n"
                    "python -m pip install scipy==1.18.0\n\n"
                    "インストール後にアプリを再起動してください。"
                ) from e

            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.statusBar().showMessage(
                "石器: minimum-volume oriented_bounds() を計算中…"
            )
            QApplication.processEvents()

            import time
            t0 = time.perf_counter()
            to_origin, native_extents = trimesh.bounds.oriented_bounds(
                self.asset.mesh,
                angle_digits=1,
                ordered=False,
            )
            elapsed = time.perf_counter() - t0
            native_extents = np.asarray(native_extents, dtype=float)

            i_long = int(np.argmax(native_extents))
            i_thickness = int(np.argmin(native_extents))
            remaining = [i for i in range(3) if i not in (i_long, i_thickness)]
            if len(remaining) != 1:
                raise RuntimeError("OBB軸の割当てに失敗しました。")
            i_short = remaining[0]

            # Reorder the OBB axes:
            # X <- short, Y <- long, Z <- thickness.
            P = np.zeros((4, 4), dtype=float)
            P[0, i_short] = 1.0
            P[1, i_long] = 1.0
            P[2, i_thickness] = 1.0
            P[3, 3] = 1.0

            # Keep a right-handed coordinate system.
            if np.linalg.det(P[:3, :3]) < 0:
                P[2, :3] *= -1.0

            raw_to_obb_centered = P @ np.asarray(to_origin, dtype=float)

            # Saved original->OBB transform uses the OBB AABB min corner as
            # coordinate origin.  The centered version is retained internally
            # because automatic and manual rotations are most stable about the
            # OBB center.
            obb_centered_vertices = trimesh.transform_points(
                np.asarray(self.asset.mesh.vertices, dtype=float),
                raw_to_obb_centered,
            )
            obb_min = np.min(obb_centered_vertices, axis=0)
            obb_origin_shift = self._translation_matrix_xyz(
                -obb_min[0], -obb_min[1], -obb_min[2]
            )
            original_to_obb = obb_origin_shift @ raw_to_obb_centered

            self.statusBar().showMessage(
                "石器: 中央X-Z断面の左右端を水平化中…"
            )
            QApplication.processEvents()
            section_correction, section_diag = (
                self._lithic_section_level_correction(raw_to_obb_centered)
            )

            # Automatic lithic initial pose:
            #   Step 1: minimum-volume OBB
            #   Step 2: rotate about Y so the robust left/right line of the
            #           central X-Z section is parallel to X.
            self.lithic_raw_to_obb_centered_matrix = raw_to_obb_centered
            self.lithic_original_to_obb_matrix = original_to_obb
            self.lithic_auto_rotation_matrix = section_correction
            self.pose_matrix = raw_to_obb_centered

            self.lithic_confirmed_final_matrix = None
            self.lithic_obb_to_result_matrix = np.eye(4)
            self.lithic_pose_confirmed = False

            self.lithic_obb_native_extents = native_extents
            self.lithic_obb_extents = np.array(
                [
                    native_extents[i_short],
                    native_extents[i_long],
                    native_extents[i_thickness],
                ],
                dtype=float,
            )
            self.lithic_obb_elapsed_sec = float(elapsed)

            self.lithic_section_level_angle_deg = float(
                section_diag["correction_angle_deg"]
            )
            self.lithic_section_level_residual_deg = float(
                section_diag["residual_angle_deg"]
            )
            self.lithic_section_left_point = np.asarray(
                section_diag["left_point_obb"], dtype=float
            )
            self.lithic_section_right_point = np.asarray(
                section_diag["right_point_obb"], dtype=float
            )
            self.lithic_section_point_count = int(
                section_diag["section_point_count"]
            )

            # Manual X/Y/Z controls are additional rotations after the full
            # automatic pose, therefore they start from 0°.
            self.lithic_angles_deg = {"x": 0.0, "y": 0.0, "z": 0.0}
            self._sync_lithic_rotation_controls()
            self._reset_lithic_section_definitions()

            self.center_axis_after_pose = None
            self.front_angle_deg = 0.0
            self.posture_done = True
            self.pose_info = {
                "artifact_type": "lithic",
                "method": "obb_plus_mid_xz_section_leveling",
                "automatic_pose_steps": [
                    "trimesh.bounds.oriented_bounds",
                    "central_xz_section_y_axis_leveling",
                ],
                "obb": {
                    "angle_digits": 1,
                    "ordered": False,
                    "axis_assignment": {
                        "X": "width",
                        "Y": "length",
                        "Z": "thickness",
                    },
                    "native_extents": native_extents.tolist(),
                    "assigned_extents_xyz": self.lithic_obb_extents.tolist(),
                    "elapsed_seconds": float(elapsed),
                },
                "section_leveling": section_diag,
            }

            unit = self.asset.input_unit
            scale = float(self.asset.unit_to_mm)
            ex = self.lithic_obb_extents
            self.lithic_obb_label.setText(
                "自動姿勢推定済み<br>"
                "① minimum-volume OBB<br>"
                f"X = 幅: {ex[0]:.3f} {unit} "
                f"({ex[0] * scale:.2f} mm)<br>"
                f"Y = 長さ: {ex[1]:.3f} {unit} "
                f"({ex[1] * scale:.2f} mm)<br>"
                f"Z = 厚さ: {ex[2]:.3f} {unit} "
                f"({ex[2] * scale:.2f} mm)<br>"
                "② 中央X-Z断面水平化<br>"
                f"Y軸自動補正: {self.lithic_section_level_angle_deg:+.3f}°<br>"
                f"補正後残差: {self.lithic_section_level_residual_deg:+.4f}°<br>"
                f"断面点数: {self.lithic_section_point_count:,}<br>"
                f"oriented_bounds: {elapsed:.3f} s"
            )

            self.refresh_view(reset_camera=True)
            self.statusBar().showMessage(
                "石器の自動姿勢推定（OBB＋中央X-Z断面水平化）を適用しました。"
                "必要に応じてX/Y/Z軸回転で微調整してください。"
            )
        except Exception as e:
            self.posture_done = False
            self.pose_matrix = np.eye(4)
            self.lithic_obb_label.setText(f"石器自動姿勢推定エラー: {e}")
            self._show_error("石器 自動姿勢推定エラー", e)
        finally:
            QApplication.restoreOverrideCursor()

    def _sync_lithic_rotation_controls(self):
        self._setting_lithic_rotation = True
        try:
            for axis, controls in self.lithic_rotation_controls.items():
                deg = float(self.lithic_angles_deg[axis])
                controls["dial"].setValue(int(round(deg * 10.0)))
                controls["spin"].setValue(deg)
        finally:
            self._setting_lithic_rotation = False

    def _set_lithic_axis_angle(self, axis: str, deg: float, source: str = "other"):
        if axis not in self.lithic_angles_deg:
            return
        deg = self._wrap_angle(deg)
        self.lithic_angles_deg[axis] = deg

        self._setting_lithic_rotation = True
        try:
            controls = self.lithic_rotation_controls[axis]
            if source != "dial":
                controls["dial"].setValue(int(round(deg * 10.0)))
            if source != "spin":
                controls["spin"].setValue(deg)
        finally:
            self._setting_lithic_rotation = False

        if self.asset and self._is_lithic() and self.posture_done:
            self.lithic_pose_confirmed = False
            self.lithic_confirmed_final_matrix = None
            self.lithic_obb_to_result_matrix = np.eye(4)
            self._update_artifact_type_ui()
            self.refresh_view(reset_camera=True)

    def _increment_lithic_axis(self, axis: str, delta_deg: float):
        self._set_lithic_axis_angle(
            axis,
            self.lithic_angles_deg.get(axis, 0.0) + float(delta_deg),
        )

    def _lithic_dial_changed(self, axis: str, value: int):
        if self._setting_lithic_rotation:
            return
        self._set_lithic_axis_angle(axis, float(value) / 10.0, source="dial")

    def _lithic_spin_changed(self, axis: str, value: float):
        if self._setting_lithic_rotation:
            return
        self._set_lithic_axis_angle(axis, float(value), source="spin")

    def _reset_lithic_rotations(self):
        self.lithic_angles_deg = {"x": 0.0, "y": 0.0, "z": 0.0}
        self._sync_lithic_rotation_controls()
        self.lithic_pose_confirmed = False
        self.lithic_confirmed_final_matrix = None
        self.lithic_obb_to_result_matrix = np.eye(4)
        self._update_artifact_type_ui()
        if self.asset and self._is_lithic() and self.posture_done:
            self.refresh_view(reset_camera=True)

    def _set_lithic_camera(self, plotter, bounds: np.ndarray, view: str):
        center = np.array([
            (bounds[0] + bounds[1]) * 0.5,
            (bounds[2] + bounds[3]) * 0.5,
            (bounds[4] + bounds[5]) * 0.5,
        ], dtype=float)
        extent = max(
            float(bounds[1] - bounds[0]),
            float(bounds[3] - bounds[2]),
            float(bounds[5] - bounds[4]),
            1e-9,
        )
        dist = extent * 3.0

        if view == "front":
            # X-Y plane, Y (long axis) is vertical on screen.
            pos = center + np.array([0.0, 0.0, dist])
            up = np.array([0.0, 1.0, 0.0])
        elif view == "right":
            # Y-Z plane, Y (long axis) is vertical on screen.
            pos = center + np.array([dist, 0.0, 0.0])
            up = np.array([0.0, 1.0, 0.0])
        elif view == "bottom":
            # X-Z plane.
            pos = center + np.array([0.0, -dist, 0.0])
            up = np.array([0.0, 0.0, 1.0])
        else:
            raise ValueError(view)

        plotter.camera_position = [pos.tolist(), center.tolist(), up.tolist()]
        plotter.enable_parallel_projection()
        plotter.reset_camera()

    def _refresh_lithic_views(self):
        if not self.asset or not self.posture_done:
            return

        poly = self._make_polydata(self._current_lithic_matrix())
        bounds = np.asarray(poly.bounds, dtype=float)
        appearance = self.show_appearance.isChecked()
        lighting = self.smooth_shading.isChecked()

        for view, plotter in self.lithic_plotters.items():
            plotter.renderer.clear_actors()
            plotter.set_background("white")
            plotter.add_axes()
            actor = self._add_mesh_actor(
                plotter,
                poly,
                appearance=appearance,
                lighting=lighting,
            )
            self._configure_gui_actor_shading(actor, lighting)
            self._set_lithic_camera(plotter, bounds, view)
            plotter.render()

    # ---------- Lithic pose confirmation / section settings ----------
    def _reset_lithic_section_definitions(self):
        self.lithic_sections = []
        self.lithic_section_counter = {"X": 0, "Y": 0}
        self.lithic_active_section_id = None

        # Default:
        #   Y-section line at X = 1/2 on Front/Back (vertical linked line)
        #   X-section line at Y = 1/2 on all Y-bearing views (horizontal line)
        self._add_lithic_section("Y", position=0.5, refresh_overlay=False)
        self._add_lithic_section("X", position=0.5, refresh_overlay=False)
        self._update_lithic_section_status()

    def _confirm_lithic_pose(self):
        if not self.asset or not self.posture_done:
            QMessageBox.warning(
                self, "未確定", "石器の自動姿勢推定が完了していません。"
            )
            return
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.statusBar().showMessage(
                "石器姿勢を確定し、bbox左下隅へ座標原点を設定中…"
            )
            QApplication.processEvents()

            final_matrix, obb_to_result = self._compute_lithic_confirmed_transform()
            self.lithic_confirmed_final_matrix = final_matrix
            self.lithic_obb_to_result_matrix = obb_to_result
            self.lithic_pose_confirmed = True
            current_label = self.lithic_obb_label.text()
            if "座標原点:" not in current_label:
                self.lithic_obb_label.setText(
                    current_label
                    + "<br>座標原点: final bbox 左下隅 "
                    "(Xmin, Ymin, Zmin) = (0, 0, 0)"
                )

            if not self.lithic_sections:
                self._reset_lithic_section_definitions()

            self._update_artifact_type_ui()
            self.viewer_stack.setCurrentIndex(1)
            self.refresh_view(reset_camera=True)
            self.statusBar().showMessage(
                "石器姿勢を決定しました。出力設定またはプレビュー確認へ進んでください。"
            )
        except Exception as e:
            self._show_error("石器 姿勢決定エラー", e)
        finally:
            QApplication.restoreOverrideCursor()

    def _return_to_lithic_pose(self):
        if not self._is_lithic():
            return
        self.lithic_pose_confirmed = False
        self.lithic_confirmed_final_matrix = None
        self.lithic_obb_to_result_matrix = np.eye(4)
        self._update_artifact_type_ui()
        self.viewer_stack.setCurrentIndex(1)
        self.refresh_view(reset_camera=True)
        self.statusBar().showMessage(
            "石器姿勢調整へ戻りました。再度「姿勢決定」で確定できます。"
        )

    def _add_lithic_section(
        self,
        axis: str,
        position: float | None = None,
        refresh_overlay: bool = True,
    ):
        axis = str(axis).upper()
        if axis not in ("X", "Y"):
            return

        existing_count = sum(
            1 for section in self.lithic_sections
            if section["axis"] == axis
        )

        if position is None:
            # Avoid exact overlap of newly added section lines.
            # Sequence: 0.60, 0.40, 0.70, 0.30, 0.80, 0.20 ...
            step_index = existing_count + 1
            magnitude = 0.10 * ((step_index + 1) // 2)
            sign = 1.0 if step_index % 2 == 1 else -1.0
            position = 0.5 + sign * magnitude

        self.lithic_section_counter[axis] = (
            int(self.lithic_section_counter.get(axis, 0)) + 1
        )
        section_id = f"{axis}{self.lithic_section_counter[axis]:02d}"
        self.lithic_sections.append(
            {
                "id": section_id,
                "axis": axis,
                "position": float(max(0.02, min(0.98, position))),
            }
        )
        self.lithic_active_section_id = section_id
        self._update_lithic_section_status()
        if refresh_overlay and self.viewer_stack.currentIndex() == 2:
            self._rebuild_lithic_preview_lines()

    def _delete_selected_lithic_section(self):
        sid = self.lithic_active_section_id
        if not sid:
            QMessageBox.information(
                self, "断面未選択", "削除する青線をプレビュー上で選択してください。"
            )
            return
        before = len(self.lithic_sections)
        self.lithic_sections = [
            s for s in self.lithic_sections if s["id"] != sid
        ]
        if len(self.lithic_sections) == before:
            return
        self.lithic_active_section_id = None
        self._update_lithic_section_status()

        # If a generated section panel exists, regenerate the preview now so
        # that both the line and the previously acquired section disappear.
        if self.viewer_stack.currentIndex() == 2:
            self._show_lithic_output_preview()

    def _find_lithic_section(self, section_id: str) -> dict | None:
        for section in self.lithic_sections:
            if section["id"] == section_id:
                return section
        return None

    def _select_lithic_section(self, section_id: str):
        if self._find_lithic_section(section_id) is None:
            return
        self.lithic_active_section_id = section_id
        self._update_lithic_section_status()
        self._update_lithic_preview_line_geometries()

    def _update_lithic_section_status(self, dirty: bool = False):
        if self.lithic_active_section_id:
            s = self._find_lithic_section(self.lithic_active_section_id)
        else:
            s = None
        counts = {
            "X": sum(1 for x in self.lithic_sections if x["axis"] == "X"),
            "Y": sum(1 for x in self.lithic_sections if x["axis"] == "Y"),
        }
        selected = (
            "未選択"
            if s is None
            else f'{s["id"]}: {s["position"] * 100.0:.1f}%'
        )
        suffix = (
            " / 位置変更後は「プレビュー確認」で断面を再生成"
            if dirty else ""
        )
        self.lithic_section_status_label.setText(
            f'断面 X={counts["X"]} / Y={counts["Y"]} / 選択: {selected}{suffix}'
        )

    def _drag_lithic_section_line(
        self,
        section_id: str,
        axis: str,
        panel_key: str,
        scene_pos,
    ):
        section = self._find_lithic_section(section_id)
        rect = self.lithic_preview_panel_rects.get(panel_key)
        if section is None or rect is None:
            return

        x0, y0, x1, y1 = rect
        w = max(float(x1 - x0), 1e-9)
        h = max(float(y1 - y0), 1e-9)

        if axis == "Y":
            # Vertical linked X-position line.  Back is horizontally mirrored.
            frac = (float(scene_pos.x()) - x0) / w
            if panel_key == "back":
                frac = 1.0 - frac
            section["position"] = float(max(0.0, min(1.0, frac)))
        elif axis == "X":
            # Horizontal Y-position line; +Y is upward in all four long views.
            frac_down = (float(scene_pos.y()) - y0) / h
            section["position"] = float(
                max(0.0, min(1.0, 1.0 - frac_down))
            )
        else:
            return

        self.lithic_active_section_id = section_id
        self._update_lithic_preview_line_geometries()
        self._update_lithic_section_status(dirty=True)

    def _lithic_section_line_released(self, section_id: str):
        self.lithic_active_section_id = section_id
        self._update_lithic_section_status(dirty=True)

    def _clear_lithic_preview_line_items(self):
        if self.lithic_preview_scene is None:
            return
        for items in self.lithic_preview_line_items.values():
            for item in items:
                try:
                    self.lithic_preview_scene.removeItem(item)
                except Exception:
                    pass
        self.lithic_preview_line_items = {}

    def _line_geometry_for_lithic_section(
        self,
        section: dict,
        panel_key: str,
    ):
        rect = self.lithic_preview_panel_rects.get(panel_key)
        if rect is None or self.lithic_preview_scene is None:
            return None

        x0, y0, x1, y1 = [float(v) for v in rect]
        pos = float(section["position"])
        axis = section["axis"]
        scene = self.lithic_preview_scene.sceneRect()
        scene_left = float(scene.left())
        scene_right = float(scene.right())
        scene_top = float(scene.top())
        scene_bottom = float(scene.bottom())

        if axis == "Y":
            # Two linked vertical section markers: Front and Back.
            # Extend continuously over the entire preview canvas.
            if panel_key not in ("front", "back"):
                return None
            frac = pos if panel_key == "front" else (1.0 - pos)
            x = x0 + frac * (x1 - x0)
            return (x, scene_top, x, scene_bottom)

        if axis == "X":
            # One horizontal marker across the entire preview canvas.
            # Its Y coordinate is derived from the Front panel.
            if panel_key != "front":
                return None
            y = y0 + (1.0 - pos) * (y1 - y0)
            return (scene_left, y, scene_right, y)

        return None

    @staticmethod
    def _distance_point_to_line_segment(
        px: float,
        py: float,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> float:
        vx = x2 - x1
        vy = y2 - y1
        wx = px - x1
        wy = py - y1
        denom = vx * vx + vy * vy
        if denom <= 1e-18:
            return math.hypot(px - x1, py - y1)
        t = max(0.0, min(1.0, (wx * vx + wy * vy) / denom))
        qx = x1 + t * vx
        qy = y1 + t * vy
        return math.hypot(px - qx, py - qy)

    def _pick_lithic_section_line(self, scene_pos):
        """Pick the nearest blue line independent of paint/add order.

        Interaction is handled at QGraphicsView level instead of by each
        QGraphicsLineItem, avoiding the previous behavior where the last
        painted/overlapping item could capture mouse interaction.
        """
        if not self.lithic_preview_line_items:
            return None

        try:
            view_scale = abs(
                float(self.lithic_preview_view.transform().m11())
            )
        except Exception:
            view_scale = 1.0
        if view_scale <= 1e-9:
            view_scale = 1.0

        # Approximately 10 screen pixels regardless of preview zoom.
        tolerance_scene = 10.0 / view_scale
        px = float(scene_pos.x())
        py = float(scene_pos.y())

        candidates = []
        for section_id, items in self.lithic_preview_line_items.items():
            for item in items:
                line = item.line()
                d = self._distance_point_to_line_segment(
                    px,
                    py,
                    float(line.x1()),
                    float(line.y1()),
                    float(line.x2()),
                    float(line.y2()),
                )
                if d <= tolerance_scene:
                    candidates.append(
                        (
                            d,
                            section_id,
                            item.axis,
                            item.panel_key,
                        )
                    )

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0])
        best_distance = candidates[0][0]
        close = [
            candidate
            for candidate in candidates
            if abs(candidate[0] - best_distance)
            <= tolerance_scene * 0.20
        ]

        # If several lines truly overlap, prefer the already-selected line
        # for stable dragging; otherwise use the nearest one.
        if self.lithic_active_section_id is not None:
            for _d, sid, axis, panel_key in close:
                if sid == self.lithic_active_section_id:
                    return (sid, axis, panel_key)

        _d, sid, axis, panel_key = close[0]
        return (sid, axis, panel_key)

    def _rebuild_lithic_preview_lines(self):
        if self.lithic_preview_scene is None:
            return
        self._clear_lithic_preview_line_items()

        for section in self.lithic_sections:
            axis = section["axis"]
            panels = (
                ("front", "back")
                if axis == "Y"
                else ("front",)
            )
            items: list[LithicSectionLineItem] = []
            for panel_key in panels:
                geom = self._line_geometry_for_lithic_section(
                    section, panel_key
                )
                if geom is None:
                    continue
                item = LithicSectionLineItem(
                    self,
                    section["id"],
                    axis,
                    panel_key,
                    selected=(
                        section["id"] == self.lithic_active_section_id
                    ),
                )
                item.setLine(*geom)
                self.lithic_preview_scene.addItem(item)
                items.append(item)
            self.lithic_preview_line_items[section["id"]] = items

    def _update_lithic_preview_line_geometries(self):
        for section in self.lithic_sections:
            items = self.lithic_preview_line_items.get(section["id"], [])
            for item in items:
                geom = self._line_geometry_for_lithic_section(
                    section, item.panel_key
                )
                if geom is not None:
                    item.setLine(*geom)
                item._set_pen(
                    section["id"] == self.lithic_active_section_id
                )

    def _selected_lithic_views(self) -> list[str]:
        return [
            key for key, cb in self.lithic_view_checks.items()
            if cb.isChecked()
        ]

    def _selected_lithic_modes(self) -> list[str]:
        modes = []
        if (
            self.lithic_mode_texture.isChecked()
            and self.lithic_mode_texture.isEnabled()
        ):
            modes.append("texture")
        if (
            self.lithic_mode_texture_normal.isChecked()
            and self.lithic_mode_texture_normal.isEnabled()
        ):
            modes.append("texture_normal")
        if self.lithic_mode_shade.isChecked():
            modes.append("shade")
        return modes

    def _selected_lithic_scale_bar_mm(self) -> float:
        return float(
            self.lithic_scale_bar_combo.currentText().split()[0]
        )

    def _selected_lithic_outline_width_px(self) -> int:
        return int(
            self.lithic_outline_width_combo.currentText().split()[0]
        )

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
                for plotter in getattr(self, "lithic_plotters", {}).values():
                    try:
                        plotter.clear()
                        plotter.add_axes()
                        plotter.render()
                    except Exception:
                        pass
                if self.lithic_preview_scene is not None:
                    self.lithic_preview_scene.clear()
                if self.queue_all:
                    self.statusBar().showMessage("すべての入力ファイルが処理済みです。")
                else:
                    self.statusBar().showMessage(f"{INPUT_DIR} に OBJ / PLY / GLB を入れてください。")
                self._schedule_preview_refresh()
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

            self.lithic_raw_to_obb_centered_matrix = np.eye(4)
            self.lithic_original_to_obb_matrix = np.eye(4)
            self.lithic_auto_rotation_matrix = np.eye(4)
            self.lithic_confirmed_final_matrix = None
            self.lithic_obb_to_result_matrix = np.eye(4)
            self.lithic_pose_confirmed = False
            self.lithic_angles_deg = {"x": 0.0, "y": 0.0, "z": 0.0}
            self.lithic_obb_native_extents = None
            self.lithic_obb_extents = None
            self.lithic_obb_elapsed_sec = None
            self.lithic_section_level_angle_deg = 0.0
            self.lithic_section_level_residual_deg = None
            self.lithic_section_left_point = None
            self.lithic_section_right_point = None
            self.lithic_section_point_count = 0
            self._reset_lithic_section_definitions()

            self.manual_points = []
            self.manual_pick_label.setText("選択点: 0 / 3")
            self.pose_label.setText("姿勢未確定")
            self.file_label.setText(path.name)
            self._update_qa()
            self._set_enabled(True)
            self._configure_appearance_options()
            self.set_front_angle(0.0)
            self._update_artifact_type_ui()
            self.statusBar().showMessage(f"3D表示を更新中: {path.name}")
            QApplication.processEvents()
            if self._is_lithic():
                self._apply_lithic_oriented_bounds()
            else:
                self.refresh_view(reset_camera=True)
                self._schedule_preview_refresh()
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
            if self._is_lithic() and self.lithic_obb_extents is not None:
                ex = self.lithic_obb_extents
                scale = float(self.asset.unit_to_mm)
                elapsed = self.lithic_obb_elapsed_sec or 0.0
                residual = (
                    self.lithic_section_level_residual_deg
                    if self.lithic_section_level_residual_deg is not None
                    else 0.0
                )
                self.lithic_obb_label.setText(
                    "自動姿勢推定済み<br>"
                    "① minimum-volume OBB<br>"
                    f"X = 幅: {ex[0]:.3f} {unit} ({ex[0] * scale:.2f} mm)<br>"
                    f"Y = 長さ: {ex[1]:.3f} {unit} ({ex[1] * scale:.2f} mm)<br>"
                    f"Z = 厚さ: {ex[2]:.3f} {unit} ({ex[2] * scale:.2f} mm)<br>"
                    "② 中央X-Z断面水平化<br>"
                    f"Y軸自動補正: {self.lithic_section_level_angle_deg:+.3f}°<br>"
                    f"補正後残差: {residual:+.4f}°<br>"
                    f"断面点数: {self.lithic_section_point_count:,}<br>"
                    f"oriented_bounds: {elapsed:.3f} s"
                )

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
        # Model-view default:
        #   pottery -> appearance when available
        #   lithic  -> shade-only
        self.show_appearance.setChecked(
            False if self._is_lithic() else has_appearance
        )
        self.smooth_shading.setChecked(True)
        self.mode_texture.setEnabled(has_appearance)
        self.mode_texture_normal.setEnabled(has_appearance)
        self.mode_texture.setChecked(has_appearance)
        self.mode_texture_normal.setChecked(has_appearance)
        self.mode_shade.setEnabled(True)
        self.mode_shade.setChecked(True)

        self.lithic_mode_texture.setEnabled(has_appearance)
        self.lithic_mode_texture_normal.setEnabled(has_appearance)
        self.lithic_mode_texture.setChecked(has_appearance)
        self.lithic_mode_texture_normal.setChecked(has_appearance)
        self.lithic_mode_shade.setEnabled(True)
        self.lithic_mode_shade.setChecked(True)

        self.mode_section.setEnabled(True)
        self.mode_half_section.setEnabled(True)
        self.mode_quarter_half.setEnabled(True)
        self.mode_section.setChecked(False)
        self.mode_half_section.setChecked(False)
        self.mode_quarter_half.setChecked(False)
        if not has_appearance:
            # Required behavior: OBJ without texture image and PLY without vertex color => shade only.
            self.mode_texture.setChecked(False)
            self.mode_texture_normal.setChecked(False)
            self.lithic_mode_texture.setChecked(False)
            self.lithic_mode_texture_normal.setChecked(False)

    # ---------- PyVista construction / view ----------
    def _current_base_matrix(self) -> np.ndarray:
        if not self.posture_done:
            return np.eye(4)
        if self._is_lithic():
            return self._current_lithic_matrix()
        return self.pose_matrix

    def _current_final_matrix(self) -> np.ndarray:
        if not self.posture_done:
            return np.eye(4)
        if self._is_lithic():
            return self._current_lithic_matrix()
        return final_transform_matrix(self.pose_matrix, self.front_angle_deg)

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
        color = "white" if (not appearance and not lighting) else "lightgray"
        return plotter.add_mesh(poly, color=color, **kwargs)

    def _configure_gui_actor_shading(self, actor, lighting: bool):
        """Apply deterministic VTK shading only to the interactive GUI actor."""
        if actor is None:
            return
        try:
            prop = actor.GetProperty()
        except (AttributeError, TypeError):
            return

        prop.SetLighting(bool(lighting))
        if lighting:
            prop.SetInterpolationToPhong()
            prop.SetAmbient(0.12)
            prop.SetDiffuse(0.88)
            prop.SetSpecular(0.05)
            prop.SetSpecularPower(12.0)

    def _report_gui_shading_state(self, lighting: bool):
        """Print a diagnostic line whenever the GUI shading state changes."""
        try:
            ren = self.plotter.renderer
            prop = self.actor.GetProperty() if self.actor is not None else None
            state = (
                bool(lighting),
                int(ren.GetAutomaticLightCreation()),
                int(ren.GetLightFollowCamera()),
                int(ren.GetLights().GetNumberOfItems()),
                int(prop.GetLighting()) if prop is not None else -1,
                int(prop.GetInterpolation()) if prop is not None else -1,
            )
            if state != getattr(self, "_last_gui_shading_state", None):
                print(
                    "GUI shading:",
                    f"requested={state[0]}",
                    f"auto_light={state[1]}",
                    f"follow_camera={state[2]}",
                    f"lights={state[3]}",
                    f"actor_lighting={state[4]}",
                    f"interpolation={state[5]}",
                )
                self._last_gui_shading_state = state
        except (AttributeError, TypeError):
            pass

    def refresh_view(self, *_args, reset_camera=False):
        if not self.asset:
            return
        if self._is_lithic():
            try:
                self._refresh_lithic_views()
            except Exception as e:
                self.statusBar().showMessage(f"石器3面表示更新エラー: {e}")
            return
        try:
            angle = self.front_angle_deg if self.posture_done else 0.0
            self.current_poly = self._make_polydata(self._current_base_matrix())
            self.plotter.renderer.clear_actors()
            self._viewer_scale_actor = None
            self._viewer_scale_text_actor = None
            self.plotter.set_background("white")
            gui_lighting = self.smooth_shading.isChecked()
            self.actor = self._add_mesh_actor(
                self.plotter,
                self.current_poly,
                appearance=self.show_appearance.isChecked(),
                lighting=gui_lighting,
            )
            self._configure_gui_actor_shading(self.actor, gui_lighting)

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
                self._sync_zoom_ui_from_camera()

            self._update_viewer_scale_overlay(render=False)
            self.plotter.render()
            self._report_gui_shading_state(gui_lighting)
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


    def _update_zoom_label(self):
        self.zoom_label.setText(f"{int(round(self._zoom_percent))}%")

    def _zoom_slider_changed(self, value: int):
        if self._updating_zoom_ui:
            return
        self._zoom_percent = int(max(25, min(400, value)))
        self._update_zoom_label()
        self._apply_zoom_to_camera(render=True)

    def _set_zoom_ui(self, percent: int):
        percent = int(max(25, min(400, percent)))
        self._updating_zoom_ui = True
        try:
            self.zoom_slider.setValue(percent)
        finally:
            self._updating_zoom_ui = False
        self._zoom_percent = percent
        self._update_zoom_label()

    def _step_zoom(self, delta_percent: int):
        self._set_zoom_ui(self._zoom_percent + delta_percent)
        self._apply_zoom_to_camera(render=True)

    def _reset_zoom(self):
        self._set_zoom_ui(100)
        self._apply_zoom_to_camera(render=True)

    def _capture_zoom_base_from_camera(self):
        try:
            camera = self.plotter.camera
            if camera is None or not bool(camera.GetParallelProjection()):
                return
            scale = float(camera.GetParallelScale())
            if scale > 0:
                self._zoom_base_parallel_scale = scale
        except Exception:
            pass

    def _apply_zoom_to_camera(self, render: bool = True):
        if not self.asset or not hasattr(self, "plotter"):
            return
        try:
            camera = self.plotter.camera
            if camera is None:
                return
            self.plotter.enable_parallel_projection()
            if self._zoom_base_parallel_scale is None or self._zoom_base_parallel_scale <= 0:
                self._capture_zoom_base_from_camera()
            if self._zoom_base_parallel_scale is None or self._zoom_base_parallel_scale <= 0:
                return
            target = float(self._zoom_base_parallel_scale) * (100.0 / float(self._zoom_percent))
            camera.SetParallelScale(target)
            self._update_viewer_scale_overlay(render=False)
            if render:
                self.plotter.render()
        except Exception as e:
            self.statusBar().showMessage(f"Zoom更新エラー: {e}")

    def _sync_zoom_ui_from_camera(self):
        if not self.asset or not hasattr(self, "plotter"):
            return
        try:
            camera = self.plotter.camera
            if camera is None or not bool(camera.GetParallelProjection()):
                return
            current_scale = float(camera.GetParallelScale())
            base = self._zoom_base_parallel_scale
            if not base or base <= 0 or current_scale <= 0:
                return
            percent = int(round(100.0 * base / current_scale))
            percent = max(25, min(400, percent))
            self._set_zoom_ui(percent)
        except Exception:
            pass

    def _sync_overlay_and_zoom(self):
        self._sync_zoom_ui_from_camera()
        self._update_viewer_scale_overlay(render=True)

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
        self._capture_zoom_base_from_camera()
        self._apply_zoom_to_camera(render=False)

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
        self.plotter.add_mesh(
            line,
            color="purple",
            line_width=2,
            show_scalar_bar=False,
            lighting=False,
        )

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
            self._schedule_preview_refresh()
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
        self._schedule_preview_refresh()
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
            QTimer.singleShot(0, self._sync_overlay_and_zoom)

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
                    QTimer.singleShot(0, self._sync_overlay_and_zoom)
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
                QTimer.singleShot(0, self._sync_overlay_and_zoom)
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
        self._schedule_preview_refresh()

    # ---------- Measurement CSV / inventory ----------
    def _measurement_final_matrix(self) -> np.ndarray:
        if not self.asset:
            raise RuntimeError("モデルが読み込まれていません。")

        if self._is_lithic():
            if (
                not self.lithic_pose_confirmed
                or self.lithic_confirmed_final_matrix is None
            ):
                raise RuntimeError(
                    "石器は先に「姿勢決定」を押してください。"
                )
            return np.asarray(
                self.lithic_confirmed_final_matrix,
                dtype=float,
            )

        if not self.posture_done:
            raise RuntimeError(
                "土器は先に姿勢と正面を確定してください。"
            )
        return np.asarray(self._current_final_matrix(), dtype=float)

    def _measurement_model_bbox(
        self,
        final_matrix: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        if not self.asset:
            raise RuntimeError("モデルが読み込まれていません。")

        vertices = trimesh.transform_points(
            np.asarray(self.asset.mesh.vertices, dtype=float),
            np.asarray(final_matrix, dtype=float),
        )
        if len(vertices) == 0:
            raise RuntimeError("bboxを計測できる頂点がありません。")

        bmin = np.min(vertices, axis=0)
        bmax = np.max(vertices, axis=0)
        extents = bmax - bmin
        return bmin, bmax, extents

    def _measurement_section_rows(
        self,
        final_matrix: np.ndarray,
    ) -> list[dict]:
        """Return lithic section bbox rows.

        Current lithic section geometry is:
          axis X -> X-Z section (y = constant)
          axis Y -> Y-Z section (x = constant)

        Therefore the section bbox reports X/Z or Y/Z dimensions.
        The axis normal to the section plane is left blank in the CSV.
        """
        if not self.asset or not self._is_lithic():
            return []

        poly = self._make_polydata(final_matrix)
        bounds = np.asarray(poly.bounds, dtype=float)

        x_sections, y_sections = self._ordered_lithic_sections_for_output(
            self.lithic_sections
        )
        ordered = [*x_sections, *y_sections]
        rows: list[dict] = []

        for section in ordered:
            coord = self._lithic_section_coordinate(section, bounds)
            paths = self._lithic_section_paths_3d(
                poly,
                section["axis"],
                coord,
            )

            row = {
                "record_type": "section_bbox",
                "record_id": section["id"],
                "section_plane": (
                    "X-Z" if section["axis"] == "X" else "Y-Z"
                ),
                "section_position": float(section["position"]),
                "section_coordinate": float(coord),
                "bbox_x": "",
                "bbox_y": "",
                "bbox_z": "",
                "bbox_x_mm": "",
                "bbox_y_mm": "",
                "bbox_z_mm": "",
                "status": "ok",
            }

            if not paths:
                row["status"] = "no_intersection"
                rows.append(row)
                continue

            points = np.vstack(
                [
                    np.asarray(path, dtype=float)
                    for path in paths
                    if len(path) >= 2
                ]
            )
            if len(points) == 0:
                row["status"] = "no_intersection"
                rows.append(row)
                continue

            ext = np.max(points, axis=0) - np.min(points, axis=0)
            unit_to_mm = float(self.asset.unit_to_mm)

            if section["axis"] == "X":
                # X-Z section: width along X, thickness along Z.
                row["bbox_x"] = float(ext[0])
                row["bbox_z"] = float(ext[2])
                row["bbox_x_mm"] = float(ext[0] * unit_to_mm)
                row["bbox_z_mm"] = float(ext[2] * unit_to_mm)
            else:
                # Y-Z section: length along Y, thickness along Z.
                row["bbox_y"] = float(ext[1])
                row["bbox_z"] = float(ext[2])
                row["bbox_y_mm"] = float(ext[1] * unit_to_mm)
                row["bbox_z_mm"] = float(ext[2] * unit_to_mm)

            rows.append(row)

        return rows

    def _measurement_rows(
        self,
        final_matrix: np.ndarray,
    ) -> list[dict]:
        if not self.asset:
            raise RuntimeError("モデルが読み込まれていません。")

        _bmin, _bmax, ext = self._measurement_model_bbox(final_matrix)
        unit_to_mm = float(self.asset.unit_to_mm)

        rows = [
            {
                "record_type": "model_bbox",
                "record_id": "model",
                "section_plane": "",
                "section_position": "",
                "section_coordinate": "",
                "bbox_x": float(ext[0]),
                "bbox_y": float(ext[1]),
                "bbox_z": float(ext[2]),
                "bbox_x_mm": float(ext[0] * unit_to_mm),
                "bbox_y_mm": float(ext[1] * unit_to_mm),
                "bbox_z_mm": float(ext[2] * unit_to_mm),
                "status": "ok",
            }
        ]

        if self._is_lithic():
            rows.extend(self._measurement_section_rows(final_matrix))

        return rows

    @staticmethod
    def _measurement_csv_fieldnames() -> list[str]:
        return [
            "artifact_type",
            "source_file",
            "source_stem",
            "source_sha256",
            "input_unit",
            "record_type",
            "record_id",
            "section_plane",
            "section_position",
            "section_coordinate",
            "bbox_x",
            "bbox_y",
            "bbox_z",
            "bbox_x_mm",
            "bbox_y_mm",
            "bbox_z_mm",
            "status",
        ]

    def _write_individual_measurement_csv(
        self,
        out_dir: Path,
        final_matrix: np.ndarray,
    ) -> Path:
        if not self.asset:
            raise RuntimeError("モデルが読み込まれていません。")

        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{self.asset.source_path.stem}_measurements.csv"
        artifact_type = "lithic" if self._is_lithic() else "pottery"

        rows = self._measurement_rows(final_matrix)
        fieldnames = self._measurement_csv_fieldnames()

        with path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                common = {
                    "artifact_type": artifact_type,
                    "source_file": self.asset.source_path.name,
                    "source_stem": self.asset.source_path.stem,
                    "source_sha256": self.asset.source_sha256,
                    "input_unit": self.asset.input_unit,
                }
                writer.writerow({**common, **row})

        return path

    @staticmethod
    def _geometry_inventory_fieldnames() -> list[str]:
        """Representative geometry inventory: requested minimal four columns."""
        return [
            "source_stem",
            "bbox_x_mm",
            "bbox_y_mm",
            "bbox_z_mm",
        ]

    @staticmethod
    def _model_inventory_fieldnames() -> list[str]:
        """3D model / source-data inventory."""
        return [
            "source_file",
            "source_stem",
            "source_sha256",
            "mesh_count",
            "file_size_bytes",
            "file_size_mb",
            "surface_area_mm2",
            "volume_mm3",
            "is_watertight",
            "volume_status",
        ]

    def _current_geometry_inventory_row(
        self,
        final_matrix: np.ndarray,
    ) -> dict:
        if not self.asset:
            raise RuntimeError("モデルが読み込まれていません。")

        _bmin, _bmax, ext = self._measurement_model_bbox(final_matrix)
        unit_to_mm = float(self.asset.unit_to_mm)

        return {
            "source_stem": self.asset.source_path.stem,
            "bbox_x_mm": float(ext[0] * unit_to_mm),
            "bbox_y_mm": float(ext[1] * unit_to_mm),
            "bbox_z_mm": float(ext[2] * unit_to_mm),
        }

    def _current_model_inventory_row(self) -> dict:
        """Return source 3D-model metadata and geometry invariants.

        mesh_count is the number of triangle faces after Trimesh loading.
        source_path.stat() measures only the source mesh file.  Therefore an
        OBJ entry counts the OBJ file itself and intentionally excludes MTL /
        texture files, as requested.

        Surface area and volume are converted from the input coordinate unit
        to mm^2 / mm^3.  Trimesh can return a volume for a non-watertight
        mesh, but that value is not guaranteed to represent a closed physical
        volume, so the inventory also records watertight/status.
        """
        if not self.asset:
            raise RuntimeError("モデルが読み込まれていません。")

        mesh = self.asset.mesh
        unit_to_mm = float(self.asset.unit_to_mm)
        file_size_bytes = int(self.asset.source_path.stat().st_size)

        area_native = float(mesh.area)
        raw_volume_native = float(mesh.volume)
        volume_native = abs(raw_volume_native)
        watertight = bool(mesh.is_watertight)

        return {
            "source_file": self.asset.source_path.name,
            "source_stem": self.asset.source_path.stem,
            "source_sha256": self.asset.source_sha256,
            "mesh_count": int(len(mesh.faces)),
            "file_size_bytes": file_size_bytes,
            "file_size_mb": float(file_size_bytes / (1024.0 ** 2)),
            "surface_area_mm2": float(
                area_native * (unit_to_mm ** 2)
            ),
            "volume_mm3": float(
                volume_native * (unit_to_mm ** 3)
            ),
            "is_watertight": watertight,
            "volume_status": (
                "closed_mesh"
                if watertight
                else "non_watertight_estimate"
            ),
        }

    @staticmethod
    def _upsert_csv_row(
        path: Path,
        fieldnames: list[str],
        row: dict,
        key_field: str,
    ) -> str:
        """Create or update one CSV row; return '追加' or '更新'."""
        existing: list[dict] = []
        if path.exists():
            with path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as f:
                existing = list(csv.DictReader(f))

        key = str(row.get(key_field, ""))
        replaced = False
        updated: list[dict] = []

        for existing_row in existing:
            if (
                key
                and str(existing_row.get(key_field, "")) == key
            ):
                if not replaced:
                    updated.append(row)
                    replaced = True
                continue
            updated.append(existing_row)

        if not replaced:
            updated.append(row)

        with path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=fieldnames,
                extrasaction="ignore",
            )
            writer.writeheader()
            for current in updated:
                writer.writerow(
                    {
                        name: current.get(name, "")
                        for name in fieldnames
                    }
                )

        return "更新" if replaced else "追加"

    def _inventory_paths(self) -> tuple[Path, Path]:
        """Return geometry inventory path and model-data inventory path."""
        lithic = self._is_lithic()
        geometry_path = OUTPUT_DIR / (
            "inventory-lithic.csv"
            if lithic
            else "inventory-pottery.csv"
        )
        model_path = OUTPUT_DIR / (
            "inventory-model-lithic.csv"
            if lithic
            else "inventory-model-pottery.csv"
        )
        return geometry_path, model_path

    def _inventory_is_current(
        self,
        final_matrix: np.ndarray,
    ) -> bool:
        """Check that both inventories already contain the current values.

        This enforces the intended workflow: inventory output must occur after
        the final pose and before "保存して次へ".
        """
        if not self.asset:
            return False

        geometry_path, model_path = self._inventory_paths()
        if not geometry_path.exists() or not model_path.exists():
            return False

        geometry_row = self._current_geometry_inventory_row(final_matrix)
        model_row = self._current_model_inventory_row()

        try:
            with geometry_path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as f:
                geometry_rows = list(csv.DictReader(f))
            with model_path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as f:
                model_rows = list(csv.DictReader(f))
        except Exception:
            return False

        stem = str(geometry_row["source_stem"])
        geometry_existing = next(
            (
                row for row in geometry_rows
                if str(row.get("source_stem", "")) == stem
            ),
            None,
        )
        if geometry_existing is None:
            return False

        def close_number(csv_value, expected) -> bool:
            try:
                return bool(
                    np.isclose(
                        float(csv_value),
                        float(expected),
                        rtol=1e-9,
                        atol=1e-6,
                    )
                )
            except Exception:
                return False

        for field in ("bbox_x_mm", "bbox_y_mm", "bbox_z_mm"):
            if not close_number(
                geometry_existing.get(field, ""),
                geometry_row[field],
            ):
                return False

        sha = str(model_row["source_sha256"])
        model_existing = next(
            (
                row for row in model_rows
                if str(row.get("source_sha256", "")) == sha
            ),
            None,
        )
        if model_existing is None:
            return False

        if str(model_existing.get("source_file", "")) != str(
            model_row["source_file"]
        ):
            return False
        if str(model_existing.get("source_stem", "")) != str(
            model_row["source_stem"]
        ):
            return False

        numeric_fields = (
            "mesh_count",
            "file_size_bytes",
            "surface_area_mm2",
            "volume_mm3",
        )
        for field in numeric_fields:
            if not close_number(
                model_existing.get(field, ""),
                model_row[field],
            ):
                return False

        return True

    def export_measurement_inventory(self):
        """Write both inventory types for the current specimen.

        Geometry representative values:
            output/inventory-(pottery|lithic).csv

        3D model/source-data values:
            output/inventory-model-(pottery|lithic).csv
        """
        try:
            if not self.asset:
                raise RuntimeError("モデルが読み込まれていません。")

            final_matrix = self._measurement_final_matrix()
            geometry_row = self._current_geometry_inventory_row(
                final_matrix
            )
            model_row = self._current_model_inventory_row()

            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            geometry_path, model_path = self._inventory_paths()

            geometry_action = self._upsert_csv_row(
                geometry_path,
                self._geometry_inventory_fieldnames(),
                geometry_row,
                key_field="source_stem",
            )
            model_action = self._upsert_csv_row(
                model_path,
                self._model_inventory_fieldnames(),
                model_row,
                key_field="source_sha256",
            )

            self.statusBar().showMessage(
                "計測一覧出力完了: "
                f"{geometry_path.name} / {model_path.name}"
            )

            volume_note = (
                ""
                if model_row["is_watertight"]
                else (
                    "\n\n注意: このモデルは watertight ではありません。"
                    "volume_mm3 は Trimesh の非閉合メッシュ推定値として"
                    "記録されています。"
                )
            )
            QMessageBox.information(
                self,
                "計測一覧出力",
                f"Geometry inventory: {geometry_path.name} "
                f"({geometry_action})\n"
                f"3D model inventory: {model_path.name} "
                f"({model_action})"
                f"{volume_note}",
            )
        except Exception as e:
            self._show_error("計測一覧出力エラー", e)


    # ---------- Lithic orthographic rendering / preview / export ----------
    @staticmethod
    def _lithic_camera_for_view(bounds: np.ndarray, view: str):
        center = np.array([
            (bounds[0] + bounds[1]) * 0.5,
            (bounds[2] + bounds[3]) * 0.5,
            (bounds[4] + bounds[5]) * 0.5,
        ], dtype=float)
        extent = max(
            float(bounds[1] - bounds[0]),
            float(bounds[3] - bounds[2]),
            float(bounds[5] - bounds[4]),
            1e-9,
        )
        dist = extent * 3.0

        # Lithic coordinate semantics:
        #   X = width, Y = length, Z = thickness
        if view == "front":
            pos = center + np.array([0.0, 0.0, dist])
            up = np.array([0.0, 1.0, 0.0])
        elif view == "back":
            pos = center + np.array([0.0, 0.0, -dist])
            up = np.array([0.0, 1.0, 0.0])
        elif view == "right":
            pos = center + np.array([dist, 0.0, 0.0])
            up = np.array([0.0, 1.0, 0.0])
        elif view == "left":
            pos = center + np.array([-dist, 0.0, 0.0])
            up = np.array([0.0, 1.0, 0.0])
        elif view == "top":
            pos = center + np.array([0.0, dist, 0.0])
            up = np.array([0.0, 0.0, 1.0])
        elif view == "bottom":
            pos = center + np.array([0.0, -dist, 0.0])
            up = np.array([0.0, 0.0, 1.0])
        else:
            raise ValueError(view)
        return pos, center, up

    @staticmethod
    def _lithic_view_size(bounds: np.ndarray, view: str) -> tuple[float, float]:
        dx = float(bounds[1] - bounds[0])
        dy = float(bounds[3] - bounds[2])
        dz = float(bounds[5] - bounds[4])
        if view in ("front", "back"):
            return dx, dy
        if view in ("left", "right"):
            return dz, dy
        if view in ("top", "bottom"):
            return dx, dz
        raise ValueError(view)

    def _render_lithic_poly_views(
        self,
        poly: pv.PolyData,
        bounds: np.ndarray,
        views: list[str],
        pixels_per_model_unit: float,
        use_appearance: bool,
        lighting: bool,
        progress_callback=None,
        progress_base: int = 0,
        progress_total: int = 1,
        progress_mode_label: str = "render",
    ) -> dict[str, np.ndarray]:
        rendered: dict[str, np.ndarray] = {}
        pl = None
        try:
            pl = pv.Plotter(off_screen=True, window_size=(512, 512))
            try:
                pl.disable_anti_aliasing()
            except (AttributeError, TypeError):
                try:
                    pl.ren_win.SetMultiSamples(0)
                except Exception:
                    pass
            pl.set_background("white")
            self._add_mesh_actor(
                pl,
                poly,
                appearance=use_appearance,
                lighting=lighting,
            )
            pl.enable_parallel_projection()

            for i, view in enumerate(views):
                world_w, world_h = self._lithic_view_size(bounds, view)
                world_w = max(world_w, 1e-9)
                world_h = max(world_h, 1e-9)
                width = max(64, int(round(world_w * pixels_per_model_unit)))
                height = max(64, int(round(world_h * pixels_per_model_unit)))
                pl.window_size = [width, height]

                pos, center, up = self._lithic_camera_for_view(bounds, view)
                pl.camera_position = [
                    pos.tolist(),
                    center.tolist(),
                    up.tolist(),
                ]
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
                        f"石器オルソ生成中: {progress_mode_label} / "
                        f"{view} ({done}/{progress_total})",
                    )
        finally:
            if pl is not None:
                try:
                    pl.close()
                except Exception:
                    pass
        return rendered

    def _render_lithic_views_for_mode(
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
        if mode == "texture":
            appearance, lighting = True, False
        elif mode == "texture_normal":
            appearance, lighting = True, True
        elif mode == "shade":
            appearance, lighting = False, True
        elif mode == "outline_mask":
            appearance, lighting = False, False
        else:
            raise ValueError(mode)

        return self._render_lithic_poly_views(
            poly,
            bounds,
            views,
            pixels_per_model_unit,
            use_appearance=appearance,
            lighting=lighting,
            progress_callback=progress_callback,
            progress_base=progress_base,
            progress_total=progress_total,
            progress_mode_label=mode,
        )

    @staticmethod
    def _lithic_main_layout_rects(
        bounds: np.ndarray,
        spacing_model: float,
    ) -> dict[str, tuple[float, float, float, float]]:
        dx = float(bounds[1] - bounds[0])
        dy = float(bounds[3] - bounds[2])
        dz = float(bounds[5] - bounds[4])
        s = float(spacing_model)
        return {
            "front": (0.0, 0.0, dx, dy),
            "left": (-(s + dz), 0.0, -s, dy),
            "right": (dx + s, 0.0, dx + s + dz, dy),
            "back": (
                dx + 2.0 * s + dz,
                0.0,
                2.0 * dx + 2.0 * s + dz,
                dy,
            ),
            "top": (0.0, dy + s, dx, dy + s + dz),
            "bottom": (0.0, -(s + dz), dx, -s),
        }

    @staticmethod
    def _ordered_lithic_sections_for_output(
        sections: list[dict],
    ) -> tuple[list[dict], list[dict]]:
        """Order section drawings by position, never by creation/paint order.

        Y-Z longitudinal sections (axis == "Y"):
            Back view, left -> right.
            Back is horizontally mirrored, so position is sorted descending.

        X-Z transverse sections (axis == "X"):
            Front view, top -> bottom.
            +Y is screen-up in Front, so position is sorted descending.
        """
        x_sections = sorted(
            [
                sdef for sdef in sections
                if str(sdef.get("axis", "")).upper() == "X"
            ],
            key=lambda sdef: float(sdef.get("position", 0.5)),
            reverse=True,
        )
        y_sections = sorted(
            [
                sdef for sdef in sections
                if str(sdef.get("axis", "")).upper() == "Y"
            ],
            key=lambda sdef: float(sdef.get("position", 0.5)),
            reverse=True,
        )
        return x_sections, y_sections

    def _lithic_layout_rects(
        self,
        bounds: np.ndarray,
        spacing_model: float,
        views: list[str],
        sections: list[dict],
    ) -> tuple[
        dict[str, tuple[float, float, float, float]],
        dict[str, tuple[float, float, float, float]],
    ]:
        main = self._lithic_main_layout_rects(bounds, spacing_model)
        dx = float(bounds[1] - bounds[0])
        dy = float(bounds[3] - bounds[2])
        dz = float(bounds[5] - bounds[4])
        s = float(spacing_model)

        section_rects: dict[str, tuple[float, float, float, float]] = {}

        # Section drawings are ordered by model position, not by the order
        # in which their blue guide lines were added/drawn.
        #   X-Z: Front top -> bottom
        #   Y-Z: Back left -> right
        x_sections, y_sections = self._ordered_lithic_sections_for_output(
            sections
        )

        # X-axis sections (X-Z):
        #   - when Bottom is selected, place them below Bottom
        #   - otherwise place them below Front
        if "bottom" in views:
            anchor_bottom = float(main["bottom"][1])
        else:
            anchor_bottom = float(main["front"][1])

        y_cursor = anchor_bottom - s - dz
        for sdef in x_sections:
            key = f'section_{sdef["id"]}'
            section_rects[key] = (0.0, y_cursor, dx, y_cursor + dz)
            y_cursor -= dz + s

        selected = [main[v] for v in views]
        max_x = max(r[2] for r in selected)

        # Y-axis sections (Y-Z) remain at the far right; with all six
        # views selected this means immediately to the right of Back.
        # y_sections is already ordered as Back left -> right.
        x_cursor = max_x + s
        for sdef in y_sections:
            key = f'section_{sdef["id"]}'
            section_rects[key] = (x_cursor, 0.0, x_cursor + dz, dy)
            x_cursor += dz + s

        return main, section_rects

    @staticmethod
    def _lithic_section_paths_3d(
        poly: pv.PolyData,
        axis: str,
        coordinate: float,
    ) -> list[np.ndarray]:
        from vtkmodules.vtkCommonDataModel import vtkPlane
        from vtkmodules.vtkFiltersCore import (
            vtkCleanPolyData,
            vtkCutter,
            vtkStripper,
        )

        axis = axis.upper()
        plane = vtkPlane()
        if axis == "X":
            # X-axis section = X-Z plane, normal Y.
            plane.SetOrigin(0.0, float(coordinate), 0.0)
            plane.SetNormal(0.0, 1.0, 0.0)
        elif axis == "Y":
            # Y-axis section = Y-Z plane, normal X.
            plane.SetOrigin(float(coordinate), 0.0, 0.0)
            plane.SetNormal(1.0, 0.0, 0.0)
        else:
            raise ValueError(axis)

        cutter = vtkCutter()
        cutter.SetCutFunction(plane)
        cutter.SetInputData(poly)
        cutter.Update()

        clean = vtkCleanPolyData()
        clean.SetInputConnection(cutter.GetOutputPort())
        clean.PointMergingOn()

        stripper = vtkStripper()
        stripper.SetInputConnection(clean.GetOutputPort())
        stripper.JoinContiguousSegmentsOn()
        stripper.Update()

        wrapped = pv.wrap(stripper.GetOutput())
        if wrapped.n_points == 0 or wrapped.n_lines == 0:
            return []

        pts = np.asarray(wrapped.points, dtype=float)
        lines = np.asarray(wrapped.lines, dtype=np.int64)
        paths: list[np.ndarray] = []
        i = 0
        while i < len(lines):
            n = int(lines[i])
            if n >= 2:
                ids = lines[i + 1:i + 1 + n]
                path = pts[ids]
                if len(path) >= 2:
                    paths.append(path)
            i += n + 1
        return paths

    def _lithic_section_coordinate(
        self,
        section: dict,
        bounds: np.ndarray,
    ) -> float:
        pos = float(section["position"])
        if section["axis"] == "X":
            return float(bounds[2] + pos * (bounds[3] - bounds[2]))
        if section["axis"] == "Y":
            return float(bounds[0] + pos * (bounds[1] - bounds[0]))
        raise ValueError(section["axis"])

    def _lithic_project_section_paths(
        self,
        paths: list[np.ndarray],
        bounds: np.ndarray,
        axis: str,
        ppu: float,
    ) -> list[np.ndarray]:
        projected: list[np.ndarray] = []
        axis = axis.upper()

        for path in paths:
            p = np.asarray(path, dtype=float)
            if len(p) < 2:
                continue

            if axis == "X":
                # Match Bottom: screen right=+X, screen up=+Z.
                x = (p[:, 0] - bounds[0]) * ppu
                y = (bounds[5] - p[:, 2]) * ppu
            elif axis == "Y":
                # Match Right: screen right=-Z, screen up=+Y.
                x = (bounds[5] - p[:, 2]) * ppu
                y = (bounds[3] - p[:, 1]) * ppu
            else:
                raise ValueError(axis)

            projected.append(np.column_stack([x, y]))
        return projected

    def _lithic_section_panel_rgba(
        self,
        paths_3d: list[np.ndarray],
        bounds: np.ndarray,
        axis: str,
        ppu: float,
        width_px: int,
    ) -> tuple[np.ndarray, list[np.ndarray]]:
        from PIL import Image, ImageDraw

        axis = axis.upper()
        if axis == "X":
            world_w = float(bounds[1] - bounds[0])
            world_h = float(bounds[5] - bounds[4])
        elif axis == "Y":
            world_w = float(bounds[5] - bounds[4])
            world_h = float(bounds[3] - bounds[2])
        else:
            raise ValueError(axis)

        width = max(64, int(round(max(world_w, 1e-9) * ppu)))
        height = max(64, int(round(max(world_h, 1e-9) * ppu)))
        image = Image.new("RGBA", (width, height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)
        projected = self._lithic_project_section_paths(
            paths_3d, bounds, axis, ppu
        )
        self._draw_polyline_paths(draw, projected, width_px)
        return np.asarray(image, dtype=np.uint8), projected

    def _prepare_lithic_sections(
        self,
        poly: pv.PolyData,
        bounds: np.ndarray,
        ppu: float,
        width_px: int,
    ) -> tuple[
        dict[str, np.ndarray],
        dict[str, list[np.ndarray]],
    ]:
        images: dict[str, np.ndarray] = {}
        projected_paths: dict[str, list[np.ndarray]] = {}

        x_sections, y_sections = self._ordered_lithic_sections_for_output(
            self.lithic_sections
        )
        for section in [*x_sections, *y_sections]:
            coord = self._lithic_section_coordinate(section, bounds)
            paths3d = self._lithic_section_paths_3d(
                poly, section["axis"], coord
            )
            if not paths3d:
                continue
            image, projected = self._lithic_section_panel_rgba(
                paths3d,
                bounds,
                section["axis"],
                ppu,
                width_px,
            )
            key = f'section_{section["id"]}'
            images[key] = image
            projected_paths[key] = projected

        return images, projected_paths

    @staticmethod
    def _draw_lithic_section_ticks(
        canvas,
        main_rects: dict[str, tuple[float, float, float, float]],
        views: list[str],
        sections: list[dict],
        ppu: float,
        spacing_model: float,
        margin_px: int,
        min_x: float,
        max_y: float,
    ) -> None:
        """Draw section-position ticks with the pottery tick specification.

        For view spacing S:
            model-edge gap = S/4
            tick length    = S/2
            remaining gap  = S/4
        Stroke width is fixed at 5 px.

        Y section (x=constant; Y-Z section):
            vertical ticks above and below Front/Back.

        X section (y=constant; X-Z section):
            horizontal ticks left and right of Front/Back/Left/Right.
        """
        from PIL import ImageDraw

        if spacing_model <= 0:
            return

        draw = ImageDraw.Draw(canvas)
        gap = float(spacing_model) / 4.0
        length = float(spacing_model) / 2.0
        width_px = 5

        def px_x(x_model: float) -> int:
            return int(round(
                margin_px + (x_model - min_x) * ppu
            ))

        def px_y(y_model: float) -> int:
            return int(round(
                margin_px + (max_y - y_model) * ppu
            ))

        for section in sections:
            axis = str(section.get("axis", "")).upper()
            pos = float(section.get("position", 0.5))
            pos = max(0.0, min(1.0, pos))

            if axis == "Y":
                # Y-section is x=constant.  Mark the same section position
                # on Front and Back. Back is horizontally mirrored.
                for view in ("front", "back"):
                    if view not in views or view not in main_rects:
                        continue
                    x0, y0, x1, y1 = main_rects[view]
                    frac = pos if view == "front" else (1.0 - pos)
                    x = x0 + frac * (x1 - x0)

                    # Upper tick.
                    draw.line(
                        [
                            (px_x(x), px_y(y1 + gap)),
                            (px_x(x), px_y(y1 + gap + length)),
                        ],
                        fill="black",
                        width=width_px,
                    )
                    # Lower tick.
                    draw.line(
                        [
                            (px_x(x), px_y(y0 - gap)),
                            (px_x(x), px_y(y0 - gap - length)),
                        ],
                        fill="black",
                        width=width_px,
                    )

            elif axis == "X":
                # X-section is y=constant.  Mark it on all selected views
                # whose vertical display axis is Y.
                for view in ("front", "back", "left", "right"):
                    if view not in views or view not in main_rects:
                        continue
                    x0, y0, x1, y1 = main_rects[view]
                    y = y0 + pos * (y1 - y0)

                    # Left tick.
                    draw.line(
                        [
                            (px_x(x0 - gap), px_y(y)),
                            (px_x(x0 - gap - length), px_y(y)),
                        ],
                        fill="black",
                        width=width_px,
                    )
                    # Right tick.
                    draw.line(
                        [
                            (px_x(x1 + gap), px_y(y)),
                            (px_x(x1 + gap + length), px_y(y)),
                        ],
                        fill="black",
                        width=width_px,
                    )

    def _compose_lithic_mode(
        self,
        rendered: dict[str, np.ndarray],
        views: list[str],
        main_rects: dict[str, tuple[float, float, float, float]],
        section_images: dict[str, np.ndarray],
        section_rects: dict[str, tuple[float, float, float, float]],
        ppu: float,
        scale_bar_mm: float,
        spacing_model: float,
        outlines: dict[str, list[np.ndarray]] | None = None,
        outline_width_px: int = OUTLINE_PNG_WIDTH_PX,
    ):
        from PIL import Image

        all_rects = [main_rects[v] for v in views]
        all_rects.extend(
            section_rects[key]
            for key in section_images
            if key in section_rects
        )
        min_x = min(r[0] for r in all_rects)
        min_y = min(r[1] for r in all_rects)
        max_x = max(r[2] for r in all_rects)
        max_y = max(r[3] for r in all_rects)

        # Same reservation as the pottery ticks: S/4 gap + S/2 tick.
        # Reserve only where a selected view can actually receive that tick.
        tick_extent = max(0.0, float(spacing_model) * 0.75)
        has_x_section = any(
            str(s.get("axis", "")).upper() == "X"
            for s in self.lithic_sections
        )
        has_y_section = any(
            str(s.get("axis", "")).upper() == "Y"
            for s in self.lithic_sections
        )

        if has_x_section:
            for view in ("front", "back", "left", "right"):
                if view in views and view in main_rects:
                    rect = main_rects[view]
                    min_x = min(min_x, rect[0] - tick_extent)
                    max_x = max(max_x, rect[2] + tick_extent)

        if has_y_section:
            for view in ("front", "back"):
                if view in views and view in main_rects:
                    rect = main_rects[view]
                    min_y = min(min_y, rect[1] - tick_extent)
                    max_y = max(max_y, rect[3] + tick_extent)

        content_w = max(1, int(round((max_x - min_x) * ppu)))
        content_h = max(1, int(round((max_y - min_y) * ppu)))
        margin = 36
        scale_block_h = 120
        bar_px = int(
            round((scale_bar_mm / self.asset.unit_to_mm) * ppu)
        )
        canvas_w = max(content_w + 2 * margin, bar_px + 2 * margin)
        canvas_h = content_h + 2 * margin + scale_block_h
        self._validate_png_dimensions(
            canvas_w, canvas_h, scale_bar_mm
        )
        canvas = Image.new(
            "RGBA",
            (canvas_w, canvas_h),
            (255, 255, 255, 255),
        )

        panel_px: dict[str, tuple[float, float, float, float]] = {}

        for view in views:
            x0, _y0, x1, y1 = main_rects[view]
            px = margin + int(round((x0 - min_x) * ppu))
            py = margin + int(round((max_y - y1) * ppu))
            self._paste_rgba(canvas, rendered[view], (px, py))
            arr = np.asarray(rendered[view])
            h, w = arr.shape[:2]
            panel_px[view] = (px, py, px + w, py + h)
            if outlines is not None:
                self._draw_outline_paths(
                    canvas,
                    outlines.get(view, []),
                    offset=(px, py),
                    width_px=outline_width_px,
                )

        for key, image in section_images.items():
            if key not in section_rects:
                continue
            x0, _y0, _x1, y1 = section_rects[key]
            px = margin + int(round((x0 - min_x) * ppu))
            py = margin + int(round((max_y - y1) * ppu))
            self._paste_rgba(canvas, image, (px, py))
            arr = np.asarray(image)
            h, w = arr.shape[:2]
            panel_px[key] = (px, py, px + w, py + h)

        self._draw_lithic_section_ticks(
            canvas,
            main_rects,
            views,
            self.lithic_sections,
            ppu,
            spacing_model,
            margin,
            min_x,
            max_y,
        )

        self._draw_scale_bar(
            canvas,
            ppu,
            scale_bar_mm,
            margin,
            canvas_h - 34,
        )
        return canvas, panel_px

    def _write_lithic_section_svg(
        self,
        path: Path,
        section: dict,
        paths: list[np.ndarray],
        bounds: np.ndarray,
        ppu: float,
    ):
        axis = section["axis"]
        if axis == "X":
            world_w = float(bounds[1] - bounds[0])
            world_h = float(bounds[5] - bounds[4])
        else:
            world_w = float(bounds[5] - bounds[4])
            world_h = float(bounds[3] - bounds[2])

        unit_to_mm = float(self.asset.unit_to_mm)
        width_mm = world_w * unit_to_mm
        height_mm = world_h * unit_to_mm
        pixel_to_mm = unit_to_mm / float(ppu)
        body = []
        for contour in paths:
            d = self._svg_path_d(contour, pixel_to_mm)
            if d:
                body.append(
                    f'  <path d="{d}" fill="none" stroke="black" '
                    f'stroke-width="{OUTLINE_SVG_STROKE_MM:g}" '
                    f'stroke-linejoin="round" stroke-linecap="round"/>'
                )
        svg = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {width_mm:.9g} {height_mm:.9g}" '
            f'preserveAspectRatio="xMidYMid meet" '
            f'data-coordinate-unit="mm">',
            f'  <metadata>Lithic section {section["id"]}; '
            f'coordinates are millimetres.</metadata>',
            *body,
            '</svg>',
            '',
        ]
        path.write_text("\n".join(svg), encoding="utf-8")

    def export_lithic_orthos(
        self,
        out_dir: Path,
        views: list[str],
        modes: list[str],
        spacing_mm: float,
        scale_bar_mm: float,
        outline_width_px: int,
        individual: bool,
        export_png_plain: bool = True,
        export_svg: bool = False,
        export_png_outline: bool = False,
        progress_callback=None,
    ) -> list[Path]:
        if not self.lithic_pose_confirmed:
            raise RuntimeError("石器姿勢が未決定です。")
        if self.lithic_confirmed_final_matrix is None:
            raise RuntimeError("石器最終変換行列がありません。")

        out_dir.mkdir(parents=True, exist_ok=True)
        poly = self._make_polydata(self.lithic_confirmed_final_matrix)
        bounds = np.asarray(poly.bounds, dtype=float)

        spacing_model = float(spacing_mm) / float(self.asset.unit_to_mm)
        main_rects, section_rects = self._lithic_layout_rects(
            bounds,
            spacing_model,
            views,
            self.lithic_sections,
        )
        all_rects = [main_rects[v] for v in views] + list(
            section_rects.values()
        )
        sheet_w = max(r[2] for r in all_rects) - min(r[0] for r in all_rects)
        sheet_h = max(r[3] for r in all_rects) - min(r[1] for r in all_rects)
        ppu = ORTHO_COMPOSITE_LONG_EDGE_PX / max(
            float(sheet_w), float(sheet_h), 1e-9
        )

        need_png = bool(export_png_plain or export_png_outline)
        need_outline = bool(export_svg or export_png_outline)
        written: list[Path] = []
        stem = self.asset.source_path.stem

        total_renders = (
            (len(views) if need_outline else 0)
            + (len(views) * len(modes) if need_png else 0)
        )
        total_renders = max(total_renders, 1)
        completed = 0

        outlines: dict[str, list[np.ndarray]] = {}
        if need_outline:
            masks = self._render_lithic_views_for_mode(
                poly,
                bounds,
                views,
                "outline_mask",
                ppu,
                progress_callback=progress_callback,
                progress_base=completed,
                progress_total=total_renders,
            )
            completed += len(views)
            for view in views:
                outlines[view] = self._outline_paths_from_rgba(masks[view])
            del masks

        section_images, section_paths = self._prepare_lithic_sections(
            poly,
            bounds,
            ppu,
            outline_width_px,
        )

        if export_svg:
            svg_paths: dict[str, list[np.ndarray]] = {
                view: outlines.get(view, [])
                for view in views
            }
            svg_rects = dict(main_rects)
            svg_keys = list(views)
            for key, paths in section_paths.items():
                svg_paths[key] = paths
                svg_rects[key] = section_rects[key]
                svg_keys.append(key)

            svg_path = out_dir / f"{stem}_ortho_outline.svg"
            self._write_composite_outline_svg(
                svg_path,
                svg_paths,
                svg_keys,
                svg_rects,
                ppu,
            )
            written.append(svg_path)

            if individual:
                for view in views:
                    p = out_dir / f"{stem}_{view}_outline.svg"
                    # Lithic individual view dimensions differ from pottery.
                    world_w, world_h = self._lithic_view_size(bounds, view)
                    unit_to_mm = float(self.asset.unit_to_mm)
                    pixel_to_mm = unit_to_mm / float(ppu)
                    body = []
                    for contour in outlines.get(view, []):
                        d = self._svg_path_d(contour, pixel_to_mm)
                        if d:
                            body.append(
                                f'  <path d="{d}" fill="none" stroke="black" '
                                f'stroke-width="{OUTLINE_SVG_STROKE_MM:g}" '
                                f'stroke-linejoin="round" stroke-linecap="round"/>'
                            )
                    svg = [
                        '<?xml version="1.0" encoding="UTF-8"?>',
                        f'<svg xmlns="http://www.w3.org/2000/svg" '
                        f'viewBox="0 0 {world_w * unit_to_mm:.9g} '
                        f'{world_h * unit_to_mm:.9g}" '
                        f'preserveAspectRatio="xMidYMid meet" '
                        f'data-coordinate-unit="mm">',
                        *body,
                        '</svg>',
                        '',
                    ]
                    p.write_text("\n".join(svg), encoding="utf-8")
                    written.append(p)

                x_sections, y_sections = self._ordered_lithic_sections_for_output(
                    self.lithic_sections
                )
                for section in [*x_sections, *y_sections]:
                    key = f'section_{section["id"]}'
                    if key not in section_paths:
                        continue
                    p = out_dir / f'{stem}_section_{section["id"]}.svg'
                    self._write_lithic_section_svg(
                        p,
                        section,
                        section_paths[key],
                        bounds,
                        ppu,
                    )
                    written.append(p)

        if need_png:
            for mode in modes:
                rendered = self._render_lithic_views_for_mode(
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

                if export_png_plain:
                    canvas, _ = self._compose_lithic_mode(
                        rendered,
                        views,
                        main_rects,
                        section_images,
                        section_rects,
                        ppu,
                        scale_bar_mm,
                        spacing_model,
                        outlines=None,
                        outline_width_px=outline_width_px,
                    )
                    p = out_dir / f"{stem}_ortho_{mode}.png"
                    canvas.convert("RGB").save(p, format="PNG")
                    written.append(p)

                if export_png_outline:
                    canvas, _ = self._compose_lithic_mode(
                        rendered,
                        views,
                        main_rects,
                        section_images,
                        section_rects,
                        ppu,
                        scale_bar_mm,
                        spacing_model,
                        outlines=outlines,
                        outline_width_px=outline_width_px,
                    )
                    p = out_dir / f"{stem}_ortho_{mode}_outline.png"
                    canvas.convert("RGB").save(p, format="PNG")
                    written.append(p)

                if individual:
                    for view in views:
                        if export_png_plain:
                            p = out_dir / f"{stem}_{view}_{mode}.png"
                            self._save_individual_view(
                                rendered[view],
                                ppu,
                                p,
                                scale_bar_mm,
                            )
                            written.append(p)
                        if export_png_outline:
                            p = out_dir / f"{stem}_{view}_{mode}_outline.png"
                            self._save_individual_view(
                                rendered[view],
                                ppu,
                                p,
                                scale_bar_mm,
                                outline_paths=outlines.get(view),
                                outline_width_px=outline_width_px,
                            )
                            written.append(p)

                    # Sections are geometry-only and do not vary by appearance;
                    # output them once, on the first selected mode.
                    if mode == modes[0]:
                        x_sections, y_sections = self._ordered_lithic_sections_for_output(
                            self.lithic_sections
                        )
                        for section in [*x_sections, *y_sections]:
                            key = f'section_{section["id"]}'
                            if key not in section_images:
                                continue
                            p = out_dir / f'{stem}_section_{section["id"]}.png'
                            self._save_individual_view(
                                section_images[key],
                                ppu,
                                p,
                                scale_bar_mm,
                            )
                            written.append(p)

                del rendered

        if progress_callback is not None:
            progress_callback(1.0, "石器オルソ / 輪郭 / 断面生成完了")
        return written

    def _show_lithic_output_preview(self):
        if not self._is_lithic() or not self.lithic_pose_confirmed:
            QMessageBox.warning(
                self, "姿勢未決定", "先に「姿勢決定」を押してください。"
            )
            return

        views = self._selected_lithic_views()
        modes = self._selected_lithic_modes()
        if not views:
            QMessageBox.warning(
                self, "未選択", "少なくとも1つの出力面を選択してください。"
            )
            return
        if not modes:
            QMessageBox.warning(
                self, "未選択", "少なくとも1つの表現を選択してください。"
            )
            return

        # Interactive preview defaults to shade.  If the user disables
        # shade in the output panel, use the first remaining selected mode.
        preview_mode = "shade" if "shade" in modes else modes[0]
        outlined = self.lithic_outline_overlay.isChecked()

        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.statusBar().showMessage("石器展開図プレビューを生成中…")
            QApplication.processEvents()

            if self._lithic_preview_temp_dir is not None:
                try:
                    shutil.rmtree(self._lithic_preview_temp_dir)
                except Exception:
                    pass
            self._lithic_preview_temp_dir = Path(
                tempfile.mkdtemp(prefix="lithic_ortho_preview_")
            )

            poly = self._make_polydata(
                self.lithic_confirmed_final_matrix
            )
            bounds = np.asarray(poly.bounds, dtype=float)
            spacing_model = (
                float(self.lithic_view_spacing.value())
                / float(self.asset.unit_to_mm)
            )
            main_rects, section_rects = self._lithic_layout_rects(
                bounds,
                spacing_model,
                views,
                self.lithic_sections,
            )
            all_rects = [main_rects[v] for v in views] + list(
                section_rects.values()
            )
            sheet_w = (
                max(r[2] for r in all_rects)
                - min(r[0] for r in all_rects)
            )
            sheet_h = (
                max(r[3] for r in all_rects)
                - min(r[1] for r in all_rects)
            )
            ppu = ORTHO_COMPOSITE_LONG_EDGE_PX / max(
                float(sheet_w), float(sheet_h), 1e-9
            )

            rendered = self._render_lithic_views_for_mode(
                poly,
                bounds,
                views,
                preview_mode,
                ppu,
            )

            outlines = None
            if outlined:
                masks = self._render_lithic_views_for_mode(
                    poly,
                    bounds,
                    views,
                    "outline_mask",
                    ppu,
                )
                outlines = {
                    view: self._outline_paths_from_rgba(masks[view])
                    for view in views
                }

            section_images, _section_paths = self._prepare_lithic_sections(
                poly,
                bounds,
                ppu,
                self._selected_lithic_outline_width_px(),
            )

            canvas, panel_px = self._compose_lithic_mode(
                rendered,
                views,
                main_rects,
                section_images,
                section_rects,
                ppu,
                self._selected_lithic_scale_bar_mm(),
                spacing_model,
                outlines=outlines,
                outline_width_px=self._selected_lithic_outline_width_px(),
            )

            preview_path = (
                self._lithic_preview_temp_dir / "lithic_preview.png"
            )
            canvas.convert("RGB").save(preview_path, format="PNG")
            self.lithic_preview_pixmap_path = preview_path
            self.lithic_preview_panel_rects = panel_px

            pixmap = QPixmap(str(preview_path))
            if pixmap.isNull():
                raise RuntimeError("プレビュー画像を読み込めませんでした。")

            self.lithic_preview_scene.clear()
            self.lithic_preview_line_items = {}
            self.lithic_preview_scene.addPixmap(pixmap)
            self.lithic_preview_scene.setSceneRect(
                0.0, 0.0, float(pixmap.width()), float(pixmap.height())
            )
            self._rebuild_lithic_preview_lines()

            self.lithic_preview_info.setText(
                f"石器展開図 / {preview_mode} / "
                f"青線=画面全体に連続する断面位置 / X断面={sum(s['axis']=='X' for s in self.lithic_sections)} "
                f"/ Y断面={sum(s['axis']=='Y' for s in self.lithic_sections)}"
            )
            self.viewer_stack.setCurrentIndex(2)
            self.lithic_preview_view._fit_on_next_resize = True
            self.lithic_preview_view.fit_scene()
            self._update_lithic_section_status()
            self.statusBar().showMessage(
                "石器展開図プレビュー。青線をドラッグし、"
                "「プレビュー確認」で断面を再生成できます。"
            )
        except Exception as e:
            self._show_error("石器プレビューエラー", e)
        finally:
            QApplication.restoreOverrideCursor()

    # ---------- Export / batch completion ----------
    def _selected_render_modes(self) -> list[str]:
        modes = []
        if self.mode_texture.isChecked() and self.mode_texture.isEnabled():
            modes.append("texture")
        if self.mode_texture_normal.isChecked() and self.mode_texture_normal.isEnabled():
            modes.append("texture_normal")
        if self.mode_shade.isChecked():
            modes.append("shade")
        if self.mode_section.isChecked():
            modes.append("section")
        if self.mode_half_section.isChecked():
            modes.append("half_section")
        if self.mode_quarter_half.isChecked():
            modes.append("quarter_half_section")
        return modes

    def _selected_scale_bar_mm(self) -> float:
        return float(self.scale_bar_combo.currentText().split()[0])

    def _selected_outline_width_px(self) -> int:
        return int(self.outline_width_combo.currentText().split()[0])

    def _lithic_metadata(self, final_matrix: np.ndarray) -> dict:
        if not self.asset:
            return {}

        inverse = np.linalg.inv(final_matrix)
        transformed = trimesh.transform_points(
            np.asarray(self.asset.mesh.vertices, dtype=float),
            final_matrix,
        )
        bounds = np.array([
            transformed[:, 0].min(),
            transformed[:, 0].max(),
            transformed[:, 1].min(),
            transformed[:, 1].max(),
            transformed[:, 2].min(),
            transformed[:, 2].max(),
        ], dtype=float)

        sections = []
        for section in self.lithic_sections:
            coordinate = self._lithic_section_coordinate(section, bounds)
            sections.append(
                {
                    "id": section["id"],
                    "axis": section["axis"],
                    "normalized_position": float(section["position"]),
                    "coordinate_input_unit": float(coordinate),
                    "coordinate_mm": float(
                        coordinate * self.asset.unit_to_mm
                    ),
                    "plane": (
                        "y=constant / X-Z section"
                        if section["axis"] == "X"
                        else "x=constant / Y-Z section"
                    ),
                }
            )

        second_matrix_written = not np.allclose(
            self.lithic_obb_to_result_matrix,
            np.eye(4),
            atol=1e-9,
            rtol=0.0,
        )

        return {
            "application": APP_NAME,
            "version": APP_VERSION,
            "artifact_type": "lithic",
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
                "axes": {
                    "X": "width",
                    "Y": "length",
                    "Z": "thickness",
                },
                "origin_definition": (
                    "final axis-aligned bounding-box minimum corner "
                    "(x_min, y_min, z_min)"
                ),
                "origin_expected": [0.0, 0.0, 0.0],
            },
            "posture": {
                **self.pose_info,
                "manual_axis_rotations_deg": dict(
                    self.lithic_angles_deg
                ),
                "pose_confirmed": bool(self.lithic_pose_confirmed),
                "final_bounds_input_unit": bounds.tolist(),
            },
            "transform": {
                "matrix_convention": (
                    "row-major storage; column homogeneous vector application"
                ),
                "equation_final": (
                    "p_result = M_obb_to_result @ "
                    "M_original_to_obb @ [x,y,z,1]^T"
                ),
                "original_to_obb_matrix_4x4": (
                    self.lithic_original_to_obb_matrix
                ),
                "obb_to_result_matrix_4x4": (
                    self.lithic_obb_to_result_matrix
                ),
                "obb_to_result_is_identity": bool(
                    not second_matrix_written
                ),
                "final_original_to_result_matrix_4x4": final_matrix,
                "final_inverse_matrix_4x4": inverse,
                "matrix_files": {
                    "original_to_obb": [
                        "transform_original_to_obb.csv",
                        "transform_original_to_obb_cloudcompare.txt",
                    ],
                    "obb_to_result": (
                        [
                            "transform_obb_to_result.csv",
                            "transform_obb_to_result_cloudcompare.txt",
                        ]
                        if second_matrix_written
                        else []
                    ),
                },
            },
            "sections": sections,
            "orthographic_export": {
                "views": self._selected_lithic_views(),
                "projection": "parallel/orthographic",
                "axis_meanings": {
                    "X": "width",
                    "Y": "length",
                    "Z": "thickness",
                },
                "render_modes": self._selected_lithic_modes(),
                "view_spacing_mm": float(
                    self.lithic_view_spacing.value()
                ),
                "scale_bar_mm": self._selected_lithic_scale_bar_mm(),
                "png_outline_width_px": (
                    self._selected_lithic_outline_width_px()
                ),
                "individual_views_and_sections": bool(
                    self.lithic_export_individual.isChecked()
                ),
                "outputs": [
                    name
                    for name, enabled in (
                        ("PNG", self.lithic_output_png.isChecked()),
                        ("SVG", self.lithic_output_svg.isChecked()),
                        (
                            "PNG+outline",
                            self.lithic_outline_overlay.isChecked(),
                        ),
                    )
                    if enabled
                ],
                "layout": (
                    "six-view cross; X sections below Bottom when selected, otherwise below Front; "
                    "Y sections at far right"
                ),
                "preview_section_lines": (
                    "blue interactive lines are preview-only and are "
                    "not drawn into saved ortho images"
                ),
            },
        }

    def _metadata(self, final_matrix: np.ndarray) -> dict:
        if not self.asset:
            return {}
        if self._is_lithic():
            return self._lithic_metadata(final_matrix)
        inverse = np.linalg.inv(final_matrix)
        center = self.center_axis_after_pose
        ref = self.reference_plane
        return {
            "application": APP_NAME,
            "version": APP_VERSION,
            "artifact_type": "lithic" if self._is_lithic() else "pottery",
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
                "lithic_axis_rotations_deg": (
                    dict(self.lithic_angles_deg) if self._is_lithic() else None
                ),
                "lithic_obb_extents_xyz": (
                    None if self.lithic_obb_extents is None
                    else self.lithic_obb_extents.tolist()
                ),
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
                "png_outline_width_px": self._selected_outline_width_px(),
                "scale_bar_style": "simple black line with end ticks; centered label above",
                "outputs": [
                    name for name, enabled in (
                        ("PNG", self.output_png.isChecked()),
                        ("SVG", self.output_svg.isChecked()),
                        ("PNG+outline", self.outline_overlay.isChecked()),
                    ) if enabled
                ],
                "png_plain": bool(self.output_png.isChecked()),
                "svg_outline": bool(self.output_svg.isChecked()),
                "png_with_svg_outline": bool(self.outline_overlay.isChecked()),
                "png_outline_scope": "orthographic base modes only; excludes section/half_section/quarter_half_section",
                "composite_layout": "front outline at far left; after front: quarter-half then half-section when selected; section at far right",
                "layout_ticks": {
                    "front_center_axis": "top and bottom; length=spacing/2; edge margin=spacing/4; width=5px",
                    "top_half_section_line": "left and right; length=spacing/2; edge margin=spacing/4; width=5px"
                },
                "section_definition": "x-z plane through post-pose AABB x-y midpoint axis",
                "svg_content": "projected silhouette contour lines plus vertical section when selected",
                "outline_method": "opaque orthographic mask -> VTK marching squares",
                "outline_alpha_threshold": OUTLINE_ALPHA_THRESHOLD,
                "svg_stroke_mm": OUTLINE_SVG_STROKE_MM,
            },
        }

    def _set_export_progress(self, value: int, text: str):
        value = int(max(0, min(100, value)))
        if self._is_lithic():
            self.lithic_export_progress.setValue(value)
            self.lithic_export_stage_label.setText(text)
        else:
            self.export_progress.setValue(value)
            self.export_stage_label.setText(text)
        self.statusBar().showMessage(text)
        QApplication.processEvents()

    def _save_lithic_current_and_next(self):
        if (
            not self.asset
            or not self.posture_done
            or not self.lithic_pose_confirmed
            or self.lithic_confirmed_final_matrix is None
        ):
            QMessageBox.warning(
                self,
                "姿勢未決定",
                "先に石器の「姿勢決定」を押してください。",
            )
            return

        final_inventory_matrix = np.asarray(
            self.lithic_confirmed_final_matrix,
            dtype=float,
        )
        if not self._inventory_is_current(final_inventory_matrix):
            QMessageBox.warning(
                self,
                "計測一覧未出力",
                "「保存して次へ」の前に「計測一覧出力」を実行してください。\n"
                "姿勢・単位を変更した場合は、計測一覧を再出力してください。",
            )
            return

        views = self._selected_lithic_views()
        modes = self._selected_lithic_modes()
        export_png_plain = self.lithic_output_png.isChecked()
        export_svg = self.lithic_output_svg.isChecked()
        export_png_outline = self.lithic_outline_overlay.isChecked()

        if not views:
            QMessageBox.warning(
                self, "未選択", "少なくとも1つの出力面を選択してください。"
            )
            return
        if not export_png_plain and not export_svg and not export_png_outline:
            QMessageBox.warning(
                self,
                "未選択",
                "PNGのみ / SVG / PNG+輪郭 の少なくとも1つを選択してください。",
            )
            return
        if (export_png_plain or export_png_outline) and not modes:
            QMessageBox.warning(
                self,
                "未選択",
                "PNG出力では少なくとも1つの表現を選択してください。",
            )
            return

        stem = self.asset.source_path.stem
        final_dir = OUTPUT_DIR / stem
        if final_dir.exists():
            QMessageBox.warning(
                self,
                "処理済み",
                f"{final_dir} が存在するため処理済みです。"
                "再処理する場合はこのフォルダを削除してください。",
            )
            self.scan_queue_and_load()
            return

        staging = OUTPUT_DIR / f"{stem}.__working__"
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.lithic_save_next_btn.setEnabled(False)
            self._set_export_progress(
                2, f"石器 保存準備中: {self.asset.source_path.name}"
            )
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True, exist_ok=False)

            final_m = np.asarray(
                self.lithic_confirmed_final_matrix, dtype=float
            )
            mesh_path = staging / f"{stem}_rev.ply"
            self._set_export_progress(
                10, f"正規化PLYを書き出し中: {mesh_path.name}"
            )
            export_normalized_mesh(self.asset, final_m, mesh_path)

            self._set_export_progress(
                20, "石器 Transform 情報を書き出し中"
            )
            export_transform_json(
                staging / "transform.json",
                self._metadata(final_m),
            )

            self._set_export_progress(
                22, "石器 計測CSVを書き出し中"
            )
            self._write_individual_measurement_csv(
                staging,
                final_m,
            )

            # Requested staged transformation matrices.
            # The combined original->result matrix remains in transform.json,
            # while standalone matrix files are kept as original->OBB and,
            # only when needed, OBB->result.
            export_matrix_csv(
                staging / "transform_original_to_obb.csv",
                self.lithic_original_to_obb_matrix,
            )
            export_matrix_txt(
                staging / "transform_original_to_obb_cloudcompare.txt",
                self.lithic_original_to_obb_matrix,
            )

            has_post_obb = not np.allclose(
                self.lithic_obb_to_result_matrix,
                np.eye(4),
                atol=1e-9,
                rtol=0.0,
            )
            if has_post_obb:
                export_matrix_csv(
                    staging / "transform_obb_to_result.csv",
                    self.lithic_obb_to_result_matrix,
                )
                export_matrix_txt(
                    staging / "transform_obb_to_result_cloudcompare.txt",
                    self.lithic_obb_to_result_matrix,
                )

            def ortho_progress(frac: float, message: str):
                self._set_export_progress(
                    25 + int(68 * float(frac)),
                    message,
                )

            self._set_export_progress(
                25, "石器オルソ / 輪郭 / 断面生成を開始"
            )
            written = self.export_lithic_orthos(
                staging,
                views=views,
                modes=modes,
                spacing_mm=float(self.lithic_view_spacing.value()),
                scale_bar_mm=self._selected_lithic_scale_bar_mm(),
                outline_width_px=(
                    self._selected_lithic_outline_width_px()
                ),
                individual=self.lithic_export_individual.isChecked(),
                export_png_plain=export_png_plain,
                export_svg=export_svg,
                export_png_outline=export_png_outline,
                progress_callback=ortho_progress,
            )

            png_files = [
                p for p in written if p.suffix.lower() == ".png"
            ]
            svg_files = [
                p for p in written if p.suffix.lower() == ".svg"
            ]

            if export_png_plain:
                plain_pngs = [
                    p for p in png_files
                    if not p.stem.endswith("_outline")
                ]
                if not plain_pngs:
                    raise RuntimeError(
                        "「PNGのみ」がONですがPNGが生成されませんでした。"
                    )
            if export_png_outline:
                outlined_pngs = [
                    p for p in png_files
                    if p.stem.endswith("_outline")
                ]
                if not outlined_pngs:
                    raise RuntimeError(
                        "「PNG+輪郭」がONですが輪郭付きPNGが生成されませんでした。"
                    )
            if export_svg and not svg_files:
                raise RuntimeError(
                    "「SVG」がONですがSVGが生成されませんでした。"
                )

            for p in png_files:
                self._verify_png_file(p)
            for p in svg_files:
                self._verify_svg_file(p)

            self._set_export_progress(96, "石器出力フォルダを確定中")
            staging.rename(final_dir)

            final_outputs = sorted(
                p for p in final_dir.iterdir() if p.is_file()
            )
            summary = (
                f"保存完了: {final_dir} "
                f"(matrix {'2段' if has_post_obb else 'OBBのみ1段'} / "
                f"全{len(final_outputs)}ファイル)"
            )
            self._set_export_progress(100, summary)
            print(summary)
            for p in final_outputs:
                print(f"  - {p.name}")

            self.scan_queue_and_load()
        except Exception as e:
            try:
                if staging.exists():
                    shutil.rmtree(staging)
            except Exception:
                pass
            self._set_export_progress(0, "石器 保存失敗")
            self._show_error("石器 保存エラー", e)
        finally:
            QApplication.restoreOverrideCursor()
            if self.asset is not None:
                self.lithic_save_next_btn.setEnabled(True)

    def save_current_and_next(self):
        if self._is_lithic():
            self._save_lithic_current_and_next()
            return
        if not self.asset or not self.posture_done:
            QMessageBox.warning(self, "未確定", "先に姿勢と正面を確定してください。")
            return

        final_inventory_matrix = np.asarray(
            self._current_final_matrix(),
            dtype=float,
        )
        if not self._inventory_is_current(final_inventory_matrix):
            QMessageBox.warning(
                self,
                "計測一覧未出力",
                "「保存して次へ」の前に「計測一覧出力」を実行してください。\n"
                "姿勢・正面・単位を変更した場合は、計測一覧を再出力してください。",
            )
            return

        views = [k for k, cb in self.view_checks.items() if cb.isChecked()]
        modes = self._selected_render_modes()
        export_png_plain = self.output_png.isChecked()
        export_svg = self.output_svg.isChecked()
        export_png_outline = self.outline_overlay.isChecked()

        if not views:
            QMessageBox.warning(self, "未選択", "少なくとも1つのオルソ面を選択してください。")
            return
        if not export_png_plain and not export_svg and not export_png_outline:
            QMessageBox.warning(
                self,
                "未選択",
                "PNGのみ / SVG / PNG+輪郭 の少なくとも1つを選択してください。",
            )
            return
        if (export_png_plain or export_png_outline) and not modes:
            QMessageBox.warning(
                self,
                "未選択",
                "PNG出力では少なくとも1つのオルソ表現を選択してください。",
            )
            return

        base_modes = [m for m in modes if m in ("texture", "texture_normal", "shade")]
        if (
            (export_png_plain or export_png_outline)
            and any(m in modes for m in ("section", "half_section", "quarter_half_section"))
            and not base_modes
        ):
            QMessageBox.warning(
                self,
                "未選択",
                "縦断面・半截・1/4半截をPNGへ配置する場合は、"
                "テクスチャ / Normal / シェードのいずれか1つ以上を選択してください。",
            )
            return

        stem = self.asset.source_path.stem
        final_dir = OUTPUT_DIR / stem
        if final_dir.exists():
            QMessageBox.warning(self, "処理済み", f"{final_dir} が存在するため処理済みです。再処理する場合はこのフォルダを削除してください。")
            self.scan_queue_and_load()
            return
        staging = OUTPUT_DIR / f"{stem}.__working__"
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self._set_export_progress(2, f"保存準備中: {self.asset.source_path.name}")
            self.save_next_btn.setEnabled(False)
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True, exist_ok=False)

            final_m = self._current_final_matrix()
            # The normalized geometry is always exported as PLY, regardless of
            # the input mesh container/format.
            mesh_path = staging / f"{stem}_rev.ply"

            self._set_export_progress(10, f"正規化PLYを書き出し中: {mesh_path.name}")
            export_normalized_mesh(self.asset, final_m, mesh_path)

            self._set_export_progress(22, "Transform情報を書き出し中")
            export_transform_json(staging / "transform.json", self._metadata(final_m))
            self._set_export_progress(23, "計測CSVを書き出し中")
            self._write_individual_measurement_csv(
                staging,
                final_m,
            )
            export_matrix_csv(staging / "transform_matrix.csv", final_m)
            export_matrix_txt(staging / "transform_matrix_cloudcompare.txt", final_m)

            def ortho_progress(frac: float, message: str):
                self._set_export_progress(25 + int(68 * float(frac)), message)

            selected_formats = []
            if export_png_plain:
                selected_formats.append("PNGのみ")
            if export_svg:
                selected_formats.append("SVG")
            if export_png_outline:
                selected_formats.append("PNG+輪郭")
            self._set_export_progress(
                25,
                f"オルソ / 輪郭線生成を開始: {', '.join(selected_formats)}",
            )
            ortho_written = self.export_orthos(
                staging,
                views=views,
                modes=modes,
                spacing_mm=float(self.view_spacing.value()),
                scale_bar_mm=self._selected_scale_bar_mm(),
                outline_width_px=self._selected_outline_width_px(),
                individual=self.export_individual.isChecked(),
                export_png_plain=export_png_plain,
                export_svg=export_svg,
                export_png_outline=export_png_outline,
                progress_callback=ortho_progress,
            )

            # Requested output products must actually exist and be parseable.
            png_files = [p for p in ortho_written if p.suffix.lower() == ".png"]
            svg_files = [p for p in ortho_written if p.suffix.lower() == ".svg"]

            if export_png_plain:
                plain_pngs = [p for p in png_files if not p.stem.endswith("_outline")]
                if not plain_pngs:
                    raise RuntimeError("「PNGのみ」がONですが、PNGファイルが生成されませんでした。")
            if export_png_outline:
                outlined_pngs = [p for p in png_files if p.stem.endswith("_outline")]
                if not outlined_pngs:
                    raise RuntimeError("「PNG+輪郭」がONですが、輪郭付きPNGが生成されませんでした。")
            if export_svg and not svg_files:
                raise RuntimeError("「SVG」がONですが、SVGファイルが生成されませんでした。")

            for p in png_files:
                self._verify_png_file(p)
            for p in svg_files:
                self._verify_svg_file(p)

            self._set_export_progress(96, "出力フォルダを確定中")
            # Folder existence is the completion flag. Only expose the final folder
            # after every model/transform/PNG/SVG export succeeded.
            staging.rename(final_dir)

            final_outputs = sorted(
                p for p in final_dir.iterdir()
                if p.is_file()
            )
            png_count = sum(p.suffix.lower() == ".png" for p in final_outputs)
            svg_count = sum(p.suffix.lower() == ".svg" for p in final_outputs)

            summary = (
                f"保存完了: {final_dir} "
                f"(PNG {png_count} / SVG {svg_count} / 全{len(final_outputs)}ファイル)"
            )
            self._set_export_progress(100, summary)
            print(summary)
            for p in final_outputs:
                print(f"  - {p.name}")

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

    @staticmethod
    def _verify_png_file(path: Path) -> None:
        from PIL import Image
        if not path.exists() or path.stat().st_size <= 0:
            raise RuntimeError(f"PNGが空または存在しません: {path.name}")
        try:
            with Image.open(path) as im:
                im.verify()
        except Exception as e:
            raise RuntimeError(f"PNGが不正です: {path.name}: {e}") from e

    @staticmethod
    def _verify_svg_file(path: Path) -> None:
        import xml.etree.ElementTree as ET
        if not path.exists() or path.stat().st_size <= 0:
            raise RuntimeError(f"SVGが空または存在しません: {path.name}")
        try:
            root = ET.parse(path).getroot()
        except Exception as e:
            raise RuntimeError(f"SVG XMLが不正です: {path.name}: {e}") from e
        view_box = root.attrib.get("viewBox", "").split()
        if len(view_box) != 4:
            raise RuntimeError(f"SVG viewBoxが不正です: {path.name}")
        ns = {"svg": "http://www.w3.org/2000/svg"}
        if not root.findall(".//svg:path", ns):
            raise RuntimeError(f"SVGに輪郭pathがありません: {path.name}")

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
    def _layout_with_auxiliary_panels(
        bounds: np.ndarray,
        spacing_model: float,
        selected_views: list[str],
        include_quarter: bool,
        include_half: bool,
        include_section: bool,
    ) -> tuple[
        dict[str, tuple[float, float, float, float]],
        dict[str, tuple[float, float, float, float]],
    ]:
        """Return shifted ortho rects and auxiliary panel rects.

        Horizontal order around the front view:
            front - quarter - half - right

        Therefore, for six views with all auxiliary panels:
            front_outline - left - front - quarter - half - right - back - section

        If quarter is OFF but half is ON:
            front_outline - left - front - half - right - back - section

        Top and bottom remain vertically aligned with front.
        """
        rects = MainWindow._layout_rects(bounds, spacing_model)
        dx = float(bounds[1] - bounds[0])
        dz = float(bounds[5] - bounds[4])
        s = float(spacing_model)

        inserted_count = int(bool(include_quarter)) + int(bool(include_half))
        if inserted_count:
            shift = inserted_count * (dx + s)
            for key in ("right", "back"):
                x0, y0, x1, y1 = rects[key]
                rects[key] = (x0 + shift, y0, x1 + shift, y1)

        selected_rects = [rects[v] for v in selected_views]
        aux: dict[str, tuple[float, float, float, float]] = {}

        _fx0, _fy0, fx1, _fy1 = rects["front"]
        cursor_x = fx1 + s

        if include_quarter:
            aux["quarter_panel"] = (cursor_x, 0.0, cursor_x + dx, dz)
            cursor_x += dx + s

        if include_half:
            aux["half_panel"] = (cursor_x, 0.0, cursor_x + dx, dz)
            cursor_x += dx + s

        left_candidates = list(selected_rects)
        left_candidates.extend(
            aux[key]
            for key in ("quarter_panel", "half_panel")
            if key in aux
        )
        min_x = min(r[0] for r in left_candidates)
        max_x = max(r[2] for r in left_candidates)

        # Front outline is always the leftmost composite panel.
        aux["front_outline_panel"] = (min_x - s - dx, 0.0, min_x - s, dz)

        # Vertical section is always the rightmost composite panel.
        if include_section:
            aux["section_panel"] = (max_x + s, 0.0, max_x + s + dx, dz)

        return rects, aux

    def _paths_to_rgba(
        self,
        paths: list[np.ndarray],
        bounds: np.ndarray,
        view: str,
        ppu: float,
        width_px: int,
        fill_section: bool = False,
    ) -> np.ndarray:
        from PIL import Image, ImageDraw

        world_w, world_h = self._view_size(bounds, view)
        width = max(64, int(round(max(world_w, 1e-9) * ppu)))
        height = max(64, int(round(max(world_h, 1e-9) * ppu)))
        img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        if fill_section:
            self._fill_section_paths(draw, paths, width_px)
        else:
            self._draw_polyline_paths(draw, paths, width_px)
        return np.asarray(img, dtype=np.uint8)

    @staticmethod
    def _mode_appearance_flags(mode: str) -> tuple[bool, bool]:
        if mode == "texture":
            return True, False
        if mode == "texture_normal":
            return True, True
        if mode == "shade":
            return False, True
        raise ValueError(mode)

    def _half_panel_for_mode(
        self,
        poly: pv.PolyData,
        bounds: np.ndarray,
        ppu: float,
        mode: str,
        section_paths_3d: list[np.ndarray],
        section_fill_width_px: int,
    ) -> np.ndarray:
        """Render the front-half-removed model and fill its cut face black."""
        from PIL import Image, ImageDraw

        use_appearance, lighting = self._mode_appearance_flags(mode)
        plane_y = (float(bounds[2]) + float(bounds[3])) / 2.0

        # Front camera is on -Y. Keep y >= mid-plane, removing the front half.
        half_poly = poly.clip(
            normal=(0, 1, 0),
            origin=(0, plane_y, 0),
            invert=False,
        )
        if half_poly.n_points == 0:
            raise RuntimeError("半截モデルの生成に失敗しました。")

        half = self._render_poly_views(
            half_poly,
            bounds,
            ["front"],
            ppu,
            use_appearance=use_appearance,
            lighting=lighting,
            progress_callback=None,
            progress_mode_label=f"{mode}_half",
        )["front"]

        projected = self._project_world_paths_to_pixels(
            section_paths_3d, bounds, "front", ppu
        )
        half_im = Image.fromarray(np.asarray(half, dtype=np.uint8), mode="RGBA")
        draw = ImageDraw.Draw(half_im)
        self._fill_section_paths(draw, projected, section_fill_width_px)
        return np.asarray(half_im, dtype=np.uint8)

    def _quarter_panel_for_mode(
        self,
        poly: pv.PolyData,
        bounds: np.ndarray,
        ppu: float,
        mode: str,
        section_paths_3d: list[np.ndarray],
        section_fill_width_px: int,
        half_panel: np.ndarray | None = None,
    ) -> np.ndarray:
        """Create 1/4 half-section: left half full front, right half half-section."""
        use_appearance, lighting = self._mode_appearance_flags(mode)

        full = self._render_poly_views(
            poly,
            bounds,
            ["front"],
            ppu,
            use_appearance=use_appearance,
            lighting=lighting,
            progress_callback=None,
            progress_mode_label=f"{mode}_quarter_full",
        )["front"]

        if half_panel is None:
            half_panel = self._half_panel_for_mode(
                poly,
                bounds,
                ppu,
                mode,
                section_paths_3d,
                section_fill_width_px,
            )

        return self._split_left_right(full, half_panel)

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


    def _projection_frame(self, bounds: np.ndarray, view: str):
        from itertools import product

        pos, center, up = self._camera_for_view(bounds, view)
        pos = np.asarray(pos, dtype=float)
        center = np.asarray(center, dtype=float)
        up = np.asarray(up, dtype=float)

        forward = center - pos
        forward /= max(np.linalg.norm(forward), 1e-12)
        right = np.cross(forward, up)
        right /= max(np.linalg.norm(right), 1e-12)
        true_up = np.cross(right, forward)
        true_up /= max(np.linalg.norm(true_up), 1e-12)

        corners = np.array(
            list(product(
                [bounds[0], bounds[1]],
                [bounds[2], bounds[3]],
                [bounds[4], bounds[5]],
            )),
            dtype=float,
        )
        rel = corners - center
        u = rel @ right
        v = rel @ true_up
        return center, right, true_up, float(u.min()), float(u.max()), float(v.min()), float(v.max())

    def _project_world_paths_to_pixels(
        self,
        paths_3d: list[np.ndarray],
        bounds: np.ndarray,
        view: str,
        pixels_per_model_unit: float,
    ) -> list[np.ndarray]:
        center, right, true_up, umin, _umax, _vmin, vmax = self._projection_frame(bounds, view)
        projected: list[np.ndarray] = []
        for path in paths_3d:
            if len(path) < 2:
                continue
            rel = np.asarray(path, dtype=float) - center
            u = rel @ right
            v = rel @ true_up
            x = (u - umin) * float(pixels_per_model_unit)
            y = (vmax - v) * float(pixels_per_model_unit)
            projected.append(np.column_stack([x, y]))
        return projected

    @staticmethod
    def _draw_polyline_paths(draw, paths: list[np.ndarray], width_px: int, fill=(0, 0, 0, 255)):
        width_px = max(1, int(width_px))
        for path in paths:
            if len(path) < 2:
                continue
            pts = [(int(round(float(x))), int(round(float(y)))) for x, y in path]
            draw.line(pts, fill=fill, width=width_px, joint="curve")

    @staticmethod
    def _fill_section_paths(draw, paths: list[np.ndarray], width_px: int):
        width_px = max(1, int(width_px))
        for path in paths:
            if len(path) < 2:
                continue
            pts = [(int(round(float(x))), int(round(float(y)))) for x, y in path]
            if len(pts) >= 3:
                x = np.asarray([p[0] for p in pts], dtype=float)
                y = np.asarray([p[1] for p in pts], dtype=float)
                area = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
                if area >= 1.0:
                    draw.polygon(pts, fill=(0, 0, 0, 255))
            draw.line(pts, fill=(0, 0, 0, 255), width=width_px, joint="curve")

    @staticmethod
    def _split_left_right(full_rgba, half_rgba):
        from PIL import Image

        full = np.asarray(full_rgba, dtype=np.uint8)
        half = np.asarray(half_rgba, dtype=np.uint8)
        full_im = Image.fromarray(full, mode="RGBA")
        half_im = Image.fromarray(half, mode="RGBA")
        out = Image.new("RGBA", full_im.size, (255, 255, 255, 0))
        split_x = full_im.width // 2
        out.alpha_composite(full_im.crop((0, 0, split_x, full_im.height)), dest=(0, 0))
        out.alpha_composite(
            half_im.crop((split_x, 0, half_im.width, half_im.height)),
            dest=(split_x, 0),
        )
        return np.asarray(out, dtype=np.uint8)

    @staticmethod
    def _section_paths_3d(poly: pv.PolyData, plane_y: float) -> list[np.ndarray]:
        from vtkmodules.vtkCommonDataModel import vtkPlane
        from vtkmodules.vtkFiltersCore import vtkCleanPolyData, vtkCutter, vtkStripper

        plane = vtkPlane()
        plane.SetOrigin(0.0, float(plane_y), 0.0)
        plane.SetNormal(0.0, 1.0, 0.0)

        cutter = vtkCutter()
        cutter.SetCutFunction(plane)
        cutter.SetInputData(poly)
        cutter.Update()

        clean = vtkCleanPolyData()
        clean.SetInputConnection(cutter.GetOutputPort())
        clean.PointMergingOn()

        stripper = vtkStripper()
        stripper.SetInputConnection(clean.GetOutputPort())
        stripper.JoinContiguousSegmentsOn()
        stripper.Update()

        wrapped = pv.wrap(stripper.GetOutput())
        if wrapped.n_points == 0 or wrapped.n_lines == 0:
            return []

        pts = np.asarray(wrapped.points, dtype=float)
        lines = np.asarray(wrapped.lines, dtype=np.int64)
        paths: list[np.ndarray] = []
        i = 0
        while i < len(lines):
            n = int(lines[i])
            if n >= 2:
                ids = lines[i + 1 : i + 1 + n]
                path = pts[ids]
                if len(path) >= 2 and np.linalg.norm(path[0] - path[-1]) > 1e-9:
                    path = np.vstack([path, path[0]])
                paths.append(path)
            i += n + 1
        return paths

    def _render_poly_views(
        self,
        poly: pv.PolyData,
        bounds: np.ndarray,
        views: list[str],
        pixels_per_model_unit: float,
        use_appearance: bool,
        lighting: bool,
        progress_callback=None,
        progress_base: int = 0,
        progress_total: int = 1,
        progress_mode_label: str = "render",
    ) -> dict[str, np.ndarray]:
        rendered: dict[str, np.ndarray] = {}
        pl = None
        try:
            pl = pv.Plotter(off_screen=True, window_size=(512, 512))
            try:
                pl.disable_anti_aliasing()
            except (AttributeError, TypeError):
                try:
                    pl.ren_win.SetMultiSamples(0)
                except Exception:
                    pass
            pl.set_background("white")
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
                        f"オルソ生成中: {progress_mode_label} / {view} ({done}/{progress_total})",
                    )
        finally:
            if pl is not None:
                try:
                    pl.close()
                except Exception:
                    pass
        return rendered

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
        if mode in ("texture", "texture_normal", "shade"):
            use_appearance = mode in ("texture", "texture_normal")
            lighting = mode in ("texture_normal", "shade")
            return self._render_poly_views(
                poly,
                bounds,
                views,
                pixels_per_model_unit,
                use_appearance=use_appearance,
                lighting=lighting,
                progress_callback=progress_callback,
                progress_base=progress_base,
                progress_total=progress_total,
                progress_mode_label=mode,
            )

        plane_y = (float(bounds[2]) + float(bounds[3])) / 2.0
        section_paths_3d = self._section_paths_3d(poly, plane_y)
        outline_width_px = self._selected_outline_width_px()

        if mode == "section":
            from PIL import Image, ImageDraw

            rendered: dict[str, np.ndarray] = {}
            for i, view in enumerate(views):
                world_w, world_h = self._view_size(bounds, view)
                width = max(64, int(round(max(world_w, 1e-9) * pixels_per_model_unit)))
                height = max(64, int(round(max(world_h, 1e-9) * pixels_per_model_unit)))
                img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
                draw = ImageDraw.Draw(img)
                projected = self._project_world_paths_to_pixels(
                    section_paths_3d, bounds, view, pixels_per_model_unit
                )
                self._draw_polyline_paths(draw, projected, outline_width_px)
                rendered[view] = np.asarray(img, dtype=np.uint8)
                if progress_callback is not None:
                    done = progress_base + i + 1
                    progress_callback(
                        done / max(progress_total, 1),
                        f"オルソ生成中: {mode} / {view} ({done}/{progress_total})",
                    )
            return rendered

        if mode in ("half_section", "quarter_half_section"):
            from PIL import Image, ImageDraw

            # Front is the -Y side in the current camera convention.
            # Remove the front half and keep the back half.
            half_poly = poly.clip(normal=(0, 1, 0), origin=(0, plane_y, 0), invert=False)
            if half_poly.n_points == 0:
                raise RuntimeError("半截モデルの生成に失敗しました。")

            projected_sections = {
                view: self._project_world_paths_to_pixels(
                    section_paths_3d, bounds, view, pixels_per_model_unit
                )
                for view in views
            }

            half_rendered = self._render_poly_views(
                half_poly,
                bounds,
                views,
                pixels_per_model_unit,
                use_appearance=bool(self.asset and self.asset.appearance_kind != "none"),
                lighting=True,
                progress_callback=progress_callback,
                progress_base=progress_base,
                progress_total=progress_total,
                progress_mode_label=mode,
            )

            result: dict[str, np.ndarray] = {}
            full_rendered_cache: dict[str, np.ndarray] | None = None
            if mode == "quarter_half_section":
                full_rendered_cache = self._render_poly_views(
                    poly,
                    bounds,
                    views,
                    pixels_per_model_unit,
                    use_appearance=bool(self.asset and self.asset.appearance_kind != "none"),
                    lighting=True,
                    progress_callback=None,
                    progress_base=0,
                    progress_total=1,
                    progress_mode_label="quarter_half_full",
                )

            for view in views:
                base = Image.fromarray(np.asarray(half_rendered[view], dtype=np.uint8), mode="RGBA")
                draw = ImageDraw.Draw(base)
                self._fill_section_paths(draw, projected_sections.get(view, []), outline_width_px)
                half_arr = np.asarray(base, dtype=np.uint8)

                if mode == "half_section":
                    result[view] = half_arr
                else:
                    result[view] = self._split_left_right(full_rendered_cache[view], half_arr)
            return result

        if mode == "outline_mask":
            return self._render_poly_views(
                poly,
                bounds,
                views,
                pixels_per_model_unit,
                use_appearance=False,
                lighting=False,
                progress_callback=progress_callback,
                progress_base=progress_base,
                progress_total=progress_total,
                progress_mode_label=mode,
            )

        raise ValueError(f"Unknown render mode: {mode}")

    @staticmethod
    def _outline_paths_from_rgba(rgba) -> list[np.ndarray]:
        """Vectorize the opaque projected region of one orthographic view.

        The renderer already produces RGBA with a transparent background.
        We contour the alpha mask at 50% opacity using VTK marching squares,
        then join adjacent line segments with vtkStripper.  A transparent
        one-pixel frame guarantees closed contours even when the model touches
        the rendered image boundary.
        """
        from vtkmodules.vtkCommonCore import VTK_UNSIGNED_CHAR, vtkIdList
        from vtkmodules.vtkCommonDataModel import vtkImageData
        from vtkmodules.vtkFiltersCore import vtkCleanPolyData, vtkMarchingSquares, vtkStripper
        from vtkmodules.util.numpy_support import numpy_to_vtk

        arr = np.asarray(rgba, dtype=np.uint8)
        if arr.ndim != 3:
            raise ValueError("Expected an HxWxC orthographic image")
        if arr.shape[2] >= 4:
            alpha = arr[:, :, 3]
        else:
            # Defensive fallback.  Dedicated outline-mask renders should be RGBA.
            alpha = np.where(np.any(arr[:, :, :3] < 250, axis=2), 255, 0).astype(np.uint8)

        h, w = alpha.shape
        pad = 1
        padded = np.pad(alpha, pad_width=pad, mode="constant", constant_values=0)

        image = vtkImageData()
        image.SetDimensions(int(padded.shape[1]), int(padded.shape[0]), 1)
        scalars = numpy_to_vtk(
            padded.ravel(order="C"),
            deep=True,
            array_type=VTK_UNSIGNED_CHAR,
        )
        image.GetPointData().SetScalars(scalars)

        contour = vtkMarchingSquares()
        contour.SetInputData(image)
        contour.SetValue(0, float(OUTLINE_ALPHA_THRESHOLD))

        clean = vtkCleanPolyData()
        clean.SetInputConnection(contour.GetOutputPort())
        clean.PointMergingOn()

        stripper = vtkStripper()
        stripper.SetInputConnection(clean.GetOutputPort())
        stripper.JoinContiguousSegmentsOn()
        stripper.Update()

        out = stripper.GetOutput()
        cells = out.GetLines()
        cells.InitTraversal()
        ids = vtkIdList()

        paths: list[np.ndarray] = []
        while cells.GetNextCell(ids):
            n = ids.GetNumberOfIds()
            if n < 2:
                continue
            pts = np.empty((n, 2), dtype=np.float64)
            for i in range(n):
                x, y, _z = out.GetPoint(ids.GetId(i))
                pts[i, 0] = x - pad
                pts[i, 1] = y - pad

            # Keep boundary contours within the actual raster extent.
            pts[:, 0] = np.clip(pts[:, 0], 0.0, float(w))
            pts[:, 1] = np.clip(pts[:, 1], 0.0, float(h))

            # Remove consecutive duplicates introduced by boundary clipping.
            if len(pts) > 1:
                keep = np.ones(len(pts), dtype=bool)
                keep[1:] = np.any(np.abs(np.diff(pts, axis=0)) > 1e-9, axis=1)
                pts = pts[keep]
            if len(pts) >= 2:
                paths.append(pts)

        return paths

    @staticmethod
    def _draw_outline_paths(canvas, paths: list[np.ndarray], offset=(0, 0), width_px: int = OUTLINE_PNG_WIDTH_PX):
        from PIL import ImageDraw

        draw = ImageDraw.Draw(canvas)
        ox, oy = int(offset[0]), int(offset[1])
        width_px = max(1, int(width_px))
        for path in paths:
            if len(path) < 2:
                continue
            points = [
                (ox + int(round(float(x))), oy + int(round(float(y))))
                for x, y in path
            ]
            draw.line(points, fill=(0, 0, 0, 255), width=width_px, joint="curve")

    @staticmethod
    def _svg_path_d(path: np.ndarray, scale_mm: float, offset_x_mm: float = 0.0, offset_y_mm: float = 0.0) -> str:
        if len(path) < 2:
            return ""
        pts = [
            (
                offset_x_mm + float(p[0]) * scale_mm,
                offset_y_mm + float(p[1]) * scale_mm,
            )
            for p in path
        ]
        parts = [f"M {pts[0][0]:.6g} {pts[0][1]:.6g}"]
        parts.extend(f"L {x:.6g} {y:.6g}" for x, y in pts[1:])
        if np.linalg.norm(np.asarray(pts[0]) - np.asarray(pts[-1])) <= max(scale_mm * 1.5, 1e-12):
            parts.append("Z")
        return " ".join(parts)

    def _write_individual_outline_svg(
        self,
        path: Path,
        view: str,
        paths: list[np.ndarray],
        bounds: np.ndarray,
        ppu: float,
    ) -> None:
        world_w, world_h = self._view_size(bounds, view)
        width_mm = world_w * float(self.asset.unit_to_mm)
        height_mm = world_h * float(self.asset.unit_to_mm)
        pixel_to_mm = float(self.asset.unit_to_mm) / float(ppu)

        d_items = []
        for contour in paths:
            d = self._svg_path_d(contour, pixel_to_mm)
            if d:
                d_items.append(
                    f'  <path d="{d}" fill="none" stroke="black" '
                    f'stroke-width="{OUTLINE_SVG_STROKE_MM:g}" '
                    f'stroke-linejoin="round" stroke-linecap="round"/>'
                )

        svg = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {width_mm:.9g} {height_mm:.9g}" '
            f'preserveAspectRatio="xMidYMid meet" data-coordinate-unit="mm">',
            '  <metadata>Outline coordinates and viewBox are in millimetres.</metadata>',
            f'  <g id="{view}" data-view="{view}">',
            *d_items,
            '  </g>',
            '</svg>',
            '',
        ]
        path.write_text("\n".join(svg), encoding="utf-8")

    def _write_composite_outline_svg(
        self,
        path: Path,
        outlines: dict[str, list[np.ndarray]],
        views: list[str],
        rects: dict[str, tuple[float, float, float, float]],
        ppu: float,
    ) -> None:
        selected_rects = [rects[v] for v in views]
        min_x = min(r[0] for r in selected_rects)
        min_y = min(r[1] for r in selected_rects)
        max_x = max(r[2] for r in selected_rects)
        max_y = max(r[3] for r in selected_rects)
        sheet_w = max_x - min_x
        sheet_h = max_y - min_y
        unit_to_mm = float(self.asset.unit_to_mm)
        width_mm = sheet_w * unit_to_mm
        height_mm = sheet_h * unit_to_mm
        pixel_to_mm = unit_to_mm / float(ppu)

        body = []
        for view in views:
            x0, _y0, _x1, y1 = rects[view]
            offset_x_mm = (x0 - min_x) * unit_to_mm
            offset_y_mm = (max_y - y1) * unit_to_mm
            body.append(f'  <g id="{view}" data-view="{view}">')
            for contour in outlines.get(view, []):
                d = self._svg_path_d(
                    contour,
                    pixel_to_mm,
                    offset_x_mm=offset_x_mm,
                    offset_y_mm=offset_y_mm,
                )
                if d:
                    body.append(
                        f'    <path d="{d}" fill="none" stroke="black" '
                        f'stroke-width="{OUTLINE_SVG_STROKE_MM:g}" '
                        f'stroke-linejoin="round" stroke-linecap="round"/>'
                    )
            body.append('  </g>')

        svg = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {width_mm:.9g} {height_mm:.9g}" '
            f'preserveAspectRatio="xMidYMid meet" data-coordinate-unit="mm">',
            '  <metadata>Outline coordinates and viewBox are in millimetres.</metadata>',
            *body,
            '</svg>',
            '',
        ]
        path.write_text("\n".join(svg), encoding="utf-8")

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
        font = self._load_scale_font(max(28, int(round(canvas.width / 100))))
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = x0 + (bar_px - tw) / 2.0
        ty = y - tick_h / 2.0 - th - max(7, line_w * 2)
        draw.text((tx, ty), label, fill="black", font=font)

    def _validate_png_dimensions(self, width: int, height: int, scale_bar_mm: float) -> None:
        width = int(width)
        height = int(height)
        pixels = width * height
        if (
            width > MAX_PNG_DIMENSION_PX
            or height > MAX_PNG_DIMENSION_PX
            or pixels > MAX_PNG_PIXELS
        ):
            raise RuntimeError(
                "PNGの計算寸法が異常に大きくなります "
                f"({width:,} x {height:,} px)。"
                f"入力単位（現在: {self.asset.input_unit}）と "
                f"スケールバー（{scale_bar_mm:g} mm）を確認してください。"
            )

    @staticmethod
    def _draw_layout_ticks(
        canvas,
        rects: dict[str, tuple[float, float, float, float]],
        views: list[str],
        ppu: float,
        spacing_model: float,
        margin_px: int,
        min_x: float,
        max_y: float,
    ) -> None:
        """Draw archaeological layout ticks in the inter-view spacing.

        Front:
            center-axis tick above and below the image.
        Top:
            half-section-line tick left and right of the image.

        For spacing S:
            edge margin = S/4
            tick length = S/2
            remaining outer margin = S/4
        Stroke width is fixed at 5 px.
        """
        from PIL import ImageDraw

        if spacing_model <= 0:
            return

        draw = ImageDraw.Draw(canvas)
        gap = float(spacing_model) / 4.0
        length = float(spacing_model) / 2.0
        width_px = 5

        def px_x(x_model: float) -> int:
            return int(round(margin_px + (x_model - min_x) * ppu))

        def px_y(y_model: float) -> int:
            return int(round(margin_px + (max_y - y_model) * ppu))

        if "front" in views:
            x0, y0, x1, y1 = rects["front"]
            xc = (x0 + x1) / 2.0

            # Upper center-axis tick.
            draw.line(
                [
                    (px_x(xc), px_y(y1 + gap)),
                    (px_x(xc), px_y(y1 + gap + length)),
                ],
                fill="black",
                width=width_px,
            )

            # Lower center-axis tick.
            draw.line(
                [
                    (px_x(xc), px_y(y0 - gap)),
                    (px_x(xc), px_y(y0 - gap - length)),
                ],
                fill="black",
                width=width_px,
            )

        if "top" in views:
            x0, y0, x1, y1 = rects["top"]
            yc = (y0 + y1) / 2.0

            # Left and right ticks mark the y-mid half-section plane.
            draw.line(
                [
                    (px_x(x0 - gap), px_y(yc)),
                    (px_x(x0 - gap - length), px_y(yc)),
                ],
                fill="black",
                width=width_px,
            )
            draw.line(
                [
                    (px_x(x1 + gap), px_y(yc)),
                    (px_x(x1 + gap + length), px_y(yc)),
                ],
                fill="black",
                width=width_px,
            )

    def _compose_mode(
        self,
        rendered: dict[str, np.ndarray],
        views: list[str],
        rects: dict[str, tuple[float, float, float, float]],
        ppu: float,
        out_path: Path,
        scale_bar_mm: float,
        spacing_model: float,
        outlines: dict[str, list[np.ndarray]] | None = None,
        outline_width_px: int = OUTLINE_PNG_WIDTH_PX,
        auxiliary_panels: dict[str, np.ndarray] | None = None,
        auxiliary_rects: dict[str, tuple[float, float, float, float]] | None = None,
    ) -> None:
        from PIL import Image

        auxiliary_panels = auxiliary_panels or {}
        auxiliary_rects = auxiliary_rects or {}

        all_rects = [rects[v] for v in views]
        all_rects.extend(
            auxiliary_rects[key]
            for key in auxiliary_panels
            if key in auxiliary_rects
        )
        min_x = min(r[0] for r in all_rects)
        min_y = min(r[1] for r in all_rects)
        max_x = max(r[2] for r in all_rects)
        max_y = max(r[3] for r in all_rects)

        # Reserve the full S/4 + S/2 extent used by layout ticks so they
        # are not clipped even when adjacent views are not selected.
        tick_extent = max(0.0, float(spacing_model) * 0.75)
        if "front" in views:
            min_y = min(min_y, rects["front"][1] - tick_extent)
            max_y = max(max_y, rects["front"][3] + tick_extent)
        if "top" in views:
            min_x = min(min_x, rects["top"][0] - tick_extent)
            max_x = max(max_x, rects["top"][2] + tick_extent)

        content_w = max(1, int(round((max_x - min_x) * ppu)))
        content_h = max(1, int(round((max_y - min_y) * ppu)))
        margin = 36
        scale_block_h = 120
        bar_px = int(round((scale_bar_mm / self.asset.unit_to_mm) * ppu))
        canvas_w = max(content_w + 2 * margin, bar_px + 2 * margin)
        canvas_h = content_h + 2 * margin + scale_block_h
        self._validate_png_dimensions(canvas_w, canvas_h, scale_bar_mm)
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))

        # Auxiliary panels are never targets of PNG+outline.
        for key, img in auxiliary_panels.items():
            x0, _y0, _x1, y1 = auxiliary_rects[key]
            px = margin + int(round((x0 - min_x) * ppu))
            py = margin + int(round((max_y - y1) * ppu))
            self._paste_rgba(canvas, img, (px, py))

        # Only ordinary orthographic panels receive the optional outline overlay.
        for view in views:
            img = rendered[view]
            x0, _y0, _x1, y1 = rects[view]
            px = margin + int(round((x0 - min_x) * ppu))
            py = margin + int(round((max_y - y1) * ppu))
            self._paste_rgba(canvas, img, (px, py))
            if outlines is not None:
                self._draw_outline_paths(
                    canvas,
                    outlines.get(view, []),
                    offset=(px, py),
                    width_px=outline_width_px,
                )

        self._draw_layout_ticks(
            canvas,
            rects,
            views,
            ppu,
            spacing_model,
            margin,
            min_x,
            max_y,
        )

        baseline = canvas_h - 34
        self._draw_scale_bar(canvas, ppu, scale_bar_mm, margin, baseline)
        canvas.convert("RGB").save(out_path, format="PNG")

    def _save_individual_view(
        self,
        rgba,
        ppu: float,
        path: Path,
        scale_bar_mm: float,
        outline_paths: list[np.ndarray] | None = None,
        outline_width_px: int = OUTLINE_PNG_WIDTH_PX,
    ):
        from PIL import Image
        arr = np.asarray(rgba, dtype=np.uint8)
        view_im = Image.fromarray(arr, mode="RGBA") if arr.shape[-1] == 4 else Image.fromarray(arr).convert("RGBA")
        margin = 30
        scale_block_h = 100
        bar_px = int(round((scale_bar_mm / self.asset.unit_to_mm) * ppu))
        width = max(view_im.width + 2 * margin, bar_px + 2 * margin)
        height = view_im.height + 2 * margin + scale_block_h
        self._validate_png_dimensions(width, height, scale_bar_mm)
        canvas = Image.new("RGBA", (width, height), (255, 255, 255, 255))
        canvas.alpha_composite(view_im, dest=(margin, margin))
        if outline_paths is not None:
            self._draw_outline_paths(
                canvas,
                outline_paths,
                offset=(margin, margin),
                width_px=outline_width_px,
            )
        self._draw_scale_bar(canvas, ppu, scale_bar_mm, margin, height - 30)
        canvas.convert("RGB").save(path, format="PNG")

    def export_orthos(
        self,
        out_dir: Path,
        views: list[str],
        modes: list[str],
        spacing_mm: float,
        scale_bar_mm: float,
        outline_width_px: int,
        individual: bool,
        export_png_plain: bool = True,
        export_svg: bool = False,
        export_png_outline: bool = False,
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
        base_modes = [m for m in modes if m in ("texture", "texture_normal", "shade")]
        section_selected = "section" in modes
        half_selected = "half_section" in modes
        quarter_selected = "quarter_half_section" in modes

        # Layout rule:
        #   front_outline - [selected ortho views]
        # with special raster panels inserted immediately after front:
        #   ... front - quarter - half - right ...
        # Example, six views + quarter + half + section:
        #   front_outline - left - front - quarter - half - right - back - section
        # and section is always at the far right.
        rects, aux_rects = self._layout_with_auxiliary_panels(
            bounds,
            spacing_model,
            views,
            include_quarter=quarter_selected,
            include_half=half_selected,
            include_section=section_selected,
        )

        all_layout_rects = [rects[v] for v in views] + list(aux_rects.values())
        sheet_w = max(r[2] for r in all_layout_rects) - min(r[0] for r in all_layout_rects)
        sheet_h = max(r[3] for r in all_layout_rects) - min(r[1] for r in all_layout_rects)
        ppu = ORTHO_COMPOSITE_LONG_EDGE_PX / max(float(sheet_w), float(sheet_h), 1e-9)

        stem = self.asset.source_path.stem
        written: list[Path] = []
        need_png = bool(export_png_plain or export_png_outline)

        # Front outline is always required as the leftmost composite panel.
        outline_views = ["front"]
        if export_svg or export_png_outline:
            for view in views:
                if view not in outline_views:
                    outline_views.append(view)

        total_renders = (
            len(outline_views)
            + (len(base_modes) * len(views) if need_png else 0)
        )
        total_renders = max(total_renders, 1)
        completed = 0

        # --------------------------------------------------------------
        # Orthographic silhouette outlines
        # --------------------------------------------------------------
        masks = self._render_views_for_mode(
            poly,
            bounds,
            outline_views,
            "outline_mask",
            ppu,
            progress_callback=progress_callback,
            progress_base=completed,
            progress_total=total_renders,
        )
        completed += len(outline_views)

        outlines: dict[str, list[np.ndarray]] = {}
        for view in outline_views:
            outlines[view] = self._outline_paths_from_rgba(masks[view])
            if not outlines[view]:
                raise RuntimeError(f"輪郭線を抽出できませんでした: {view}")
        del masks

        front_outline_panel = self._paths_to_rgba(
            outlines["front"], bounds, "front", ppu, outline_width_px
        )

        # --------------------------------------------------------------
        # Vertical section at post-pose AABB y-mid plane
        # --------------------------------------------------------------
        plane_y = (float(bounds[2]) + float(bounds[3])) / 2.0
        section_paths_3d = self._section_paths_3d(poly, plane_y)
        section_paths_px: list[np.ndarray] = []
        section_panel = None
        if section_selected:
            section_paths_px = self._project_world_paths_to_pixels(
                section_paths_3d, bounds, "front", ppu
            )
            if not section_paths_px:
                raise RuntimeError("縦断面を抽出できませんでした。")
            section_panel = self._paths_to_rgba(
                section_paths_px, bounds, "front", ppu, outline_width_px
            )

        # --------------------------------------------------------------
        # Composite SVG: outlines + section.  Quarter/half are raster
        # products and are intentionally not embedded in SVG.
        # --------------------------------------------------------------
        if export_svg:
            svg_paths: dict[str, list[np.ndarray]] = {}
            svg_rects: dict[str, tuple[float, float, float, float]] = {}
            svg_keys: list[str] = []

            svg_paths["front_outline_panel"] = outlines["front"]
            svg_rects["front_outline_panel"] = aux_rects["front_outline_panel"]
            svg_keys.append("front_outline_panel")

            for view in views:
                svg_paths[view] = outlines[view]
                svg_rects[view] = rects[view]
                svg_keys.append(view)

            if section_selected:
                svg_paths["section_panel"] = section_paths_px
                svg_rects["section_panel"] = aux_rects["section_panel"]
                svg_keys.append("section_panel")

            composite_svg = out_dir / f"{stem}_ortho_outline.svg"
            self._write_composite_outline_svg(
                composite_svg,
                svg_paths,
                svg_keys,
                svg_rects,
                ppu,
            )
            written.append(composite_svg)

            if individual:
                # Standalone outline/section SVG files are created only here.
                front_svg = out_dir / f"{stem}_front_outline.svg"
                self._write_individual_outline_svg(
                    front_svg, "front", outlines["front"], bounds, ppu
                )
                written.append(front_svg)

                for view in views:
                    path = out_dir / f"{stem}_{view}_outline.svg"
                    self._write_individual_outline_svg(
                        path, view, outlines[view], bounds, ppu
                    )
                    written.append(path)

                if section_selected:
                    section_svg = out_dir / f"{stem}_section.svg"
                    self._write_individual_outline_svg(
                        section_svg, "front", section_paths_px, bounds, ppu
                    )
                    written.append(section_svg)

        # --------------------------------------------------------------
        # Base orthographic PNG composites.
        # front outline is far left.
        # quarter and half are immediately after front (quarter first).
        # section is far right.
        # PNG+outline applies ONLY to the ordinary ortho panels.
        # --------------------------------------------------------------
        if need_png and base_modes:
            for mode in base_modes:
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

                auxiliary_panels = {
                    "front_outline_panel": front_outline_panel,
                }

                half_panel = None
                if half_selected or quarter_selected:
                    half_panel = self._half_panel_for_mode(
                        poly,
                        bounds,
                        ppu,
                        mode,
                        section_paths_3d,
                        outline_width_px,
                    )

                if quarter_selected:
                    auxiliary_panels["quarter_panel"] = self._quarter_panel_for_mode(
                        poly,
                        bounds,
                        ppu,
                        mode,
                        section_paths_3d,
                        outline_width_px,
                        half_panel=half_panel,
                    )

                if half_selected and half_panel is not None:
                    auxiliary_panels["half_panel"] = half_panel

                if section_selected and section_panel is not None:
                    auxiliary_panels["section_panel"] = section_panel

                if export_png_plain:
                    path = out_dir / f"{stem}_ortho_{mode}.png"
                    self._compose_mode(
                        rendered,
                        views,
                        rects,
                        ppu,
                        path,
                        scale_bar_mm,
                        spacing_model,
                        outlines=None,
                        outline_width_px=outline_width_px,
                        auxiliary_panels=auxiliary_panels,
                        auxiliary_rects=aux_rects,
                    )
                    written.append(path)

                if export_png_outline:
                    path = out_dir / f"{stem}_ortho_{mode}_outline.png"
                    self._compose_mode(
                        rendered,
                        views,
                        rects,
                        ppu,
                        path,
                        scale_bar_mm,
                        spacing_model,
                        outlines={v: outlines[v] for v in views},
                        outline_width_px=outline_width_px,
                        auxiliary_panels=auxiliary_panels,
                        auxiliary_rects=aux_rects,
                    )
                    written.append(path)

                if individual:
                    for view in views:
                        if export_png_plain:
                            path = out_dir / f"{stem}_{view}_{mode}.png"
                            self._save_individual_view(
                                rendered[view],
                                ppu,
                                path,
                                scale_bar_mm,
                                outline_paths=None,
                                outline_width_px=outline_width_px,
                            )
                            written.append(path)
                        if export_png_outline:
                            path = out_dir / f"{stem}_{view}_{mode}_outline.png"
                            self._save_individual_view(
                                rendered[view],
                                ppu,
                                path,
                                scale_bar_mm,
                                outline_paths=outlines.get(view),
                                outline_width_px=outline_width_px,
                            )
                            written.append(path)
                del rendered

        # Standalone outline and section PNGs only when individual output is ON.
        if need_png and individual:
            front_outline_png = out_dir / f"{stem}_front_outline.png"
            self._save_individual_view(
                front_outline_panel,
                ppu,
                front_outline_png,
                scale_bar_mm,
                outline_paths=None,
                outline_width_px=outline_width_px,
            )
            written.append(front_outline_png)

            if section_selected and section_panel is not None:
                section_png = out_dir / f"{stem}_section.png"
                self._save_individual_view(
                    section_panel,
                    ppu,
                    section_png,
                    scale_bar_mm,
                    outline_paths=None,
                    outline_width_px=outline_width_px,
                )
                written.append(section_png)


        if progress_callback is not None:
            progress_callback(1.0, "オルソ / 輪郭線 / 断面生成完了")
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
