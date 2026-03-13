import math
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import (
    QWidget, QMainWindow, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QPushButton, QLabel, QComboBox, QDoubleSpinBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QSplitter, QFrame, QSlider,
    QCheckBox, QTextBrowser, QGraphicsView, QScrollArea
)
from PySide6.QtWidgets import QGraphicsSimpleTextItem

from gear_math import GearSpec, gear_geom, center_distance, contact_ratio, rpm_chain, ang_vel_from_rpm
from gear_scene import GearTrainScene, GearItem


def _rot_label(rpm: float) -> str:
    return "CW" if rpm < 0 else "CCW"


def _fmt(x: float, d: int = 4) -> str:
    return f"{x:.{d}f}"


def _pd_from_module(m_mm: float) -> float:
    if m_mm <= 1e-12:
        return 0.0
    return 25.4 / m_mm


def _module_from_pd(pd_inv_in: float) -> float:
    if pd_inv_in <= 1e-12:
        return 0.0
    return 25.4 / pd_inv_in


def _pitch_line_velocity(d: float, rpm: float) -> float:
    return math.pi * d * rpm / 60.0


def _pair_ratio_text(z1: int, z2: int) -> str:
    g = math.gcd(int(z1), int(z2))
    a = int(z1) // g
    b = int(z2) // g
    return f"{a}:{b}"


def _overall_ratio_text(z_in: int, z_out: int) -> str:
    g = math.gcd(int(z_in), int(z_out))
    a = int(z_in) // g
    b = int(z_out) // g
    return f"{a}:{b}"


def _chain_k_explicit(teeth: list[int]) -> float:
    if not teeth:
        return 0.0
    sign = (-1) ** (len(teeth) - 1)
    z1 = float(teeth[0])
    zn = float(teeth[-1])
    if abs(zn) < 1e-12:
        return 0.0
    return sign * (z1 / zn)


def _solve_motor_rpm_for_target(teeth: list[int], rpm_out_target: float) -> float:
    k = _chain_k_explicit(teeth)
    if abs(k) < 1e-12:
        return 0.0
    return rpm_out_target / k


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gear Studio — Definitive Gear Train Simulator")
        self.resize(1480, 860)

        self.scene = GearTrainScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.view.setFrameShape(QFrame.NoFrame)
        self.view.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

        self._overlay_items = []

        self.fx_open = False
        self.fx_panel_size = (560, 600)

        self.fx_panel = QWidget(self.view.viewport())
        self.fx_panel.setStyleSheet("""
            QWidget{
                background: rgba(10,14,20,0.88);
                border: 1px solid rgba(255,255,255,0.16);
                border-radius: 14px;
            }
            QLabel{ color: rgba(255,255,255,0.92); }
            QTextBrowser{
                background: transparent;
                border: 0px;
                color: rgba(255,255,255,0.90);
                font-family: Menlo, Monaco, Consolas, "SF Mono", monospace;
                font-size: 12px;
            }
            QTextBrowser QScrollBar:vertical{
                background: rgba(255,255,255,0.06);
                width: 10px;
                margin: 6px 3px 6px 3px;
                border-radius: 6px;
            }
            QTextBrowser QScrollBar::handle:vertical{
                background: rgba(255,255,255,0.22);
                min-height: 24px;
                border-radius: 6px;
            }
            QTextBrowser QScrollBar::add-line:vertical,
            QTextBrowser QScrollBar::sub-line:vertical{
                height: 0px;
            }
            QPushButton{
                background: rgba(255,255,255,0.08);
                color: white;
                border: 1px solid rgba(255,255,255,0.14);
                padding: 4px 10px;
                border-radius: 10px;
            }
            QPushButton:hover{ background: rgba(255,255,255,0.12); }
        """)
        self.fx_panel.resize(*self.fx_panel_size)
        self.fx_panel.hide()

        fx_layout = QVBoxLayout(self.fx_panel)
        fx_layout.setContentsMargins(12, 10, 12, 10)
        fx_layout.setSpacing(10)

        fx_header = QHBoxLayout()
        fx_header.setContentsMargins(0, 0, 0, 0)
        fx_header.setSpacing(10)

        self.fx_title = QLabel("Quick Formulas + Summary")
        ft = QFont()
        ft.setPointSize(12)
        ft.setBold(True)
        self.fx_title.setFont(ft)

        self.fx_btn_close = QPushButton("Close")
        self.fx_btn_close.setFixedWidth(90)
        self.fx_btn_close.clicked.connect(self._toggle_fx)

        fx_header.addWidget(self.fx_title, 1)
        fx_header.addWidget(self.fx_btn_close, 0)

        self.fx_summary = QTextBrowser()
        self.fx_summary.setReadOnly(True)
        self.fx_summary.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.fx_summary.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.fx_summary.setFixedHeight(170)

        self.fx_body = QTextBrowser()
        self.fx_body.setReadOnly(True)
        self.fx_body.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.fx_body.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        fx_layout.addLayout(fx_header)
        fx_layout.addWidget(self.fx_summary)
        fx_layout.addWidget(self.fx_body, 1)

        self.fx_button = QPushButton("ƒx", self.view.viewport())
        self.fx_button.setFixedSize(52, 52)
        self.fx_button.clicked.connect(self._toggle_fx)
        self.fx_button.setStyleSheet("""
            QPushButton{
                background: rgba(255,255,255,0.10);
                color: rgba(255,255,255,0.95);
                border: 1px solid rgba(255,255,255,0.18);
                border-radius: 26px;
                font-size: 16px;
                font-weight: 700;
            }
            QPushButton:hover{ background: rgba(255,255,255,0.14); }
            QPushButton:pressed{ background: rgba(255,255,255,0.18); }
        """)
        self.fx_button.show()
        self.view.viewport().installEventFilter(self)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self._omega = []
        self._angles = []
        self._running = False

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)

        title = QLabel("Gear Studio")
        f = QFont()
        f.setPointSize(20)
        f.setBold(True)
        title.setFont(f)

        subtitle = QLabel("Simulate + compute: geometry, ratios, RPM propagation, torque/power, solved formulas.")
        subtitle.setStyleSheet("color: rgba(255,255,255,0.70);")

        left_layout.addWidget(title)
        left_layout.addWidget(subtitle)

        self.gb_add = QGroupBox("Add gear")
        add_layout = QFormLayout(self.gb_add)
        add_layout.setVerticalSpacing(8)

        self.unit_mode = QComboBox()
        self.unit_mode.addItems(["Metric (module mm)", "Imperial (Pd 1/in)"])
        self.unit_mode.currentIndexChanged.connect(self._sync_unit_fields)

        self.teeth = QSpinBox()
        self.teeth.setRange(6, 500)
        self.teeth.setValue(23)

        self.module_mm = QDoubleSpinBox()
        self.module_mm.setRange(0.1, 1000.0)
        self.module_mm.setDecimals(3)
        self.module_mm.setSingleStep(0.5)
        self.module_mm.setValue(6.0)

        self.pd = QDoubleSpinBox()
        self.pd.setRange(0.1, 200.0)
        self.pd.setDecimals(3)
        self.pd.setSingleStep(0.5)
        self.pd.setValue(6.0)

        self.phi = QDoubleSpinBox()
        self.phi.setRange(5.0, 40.0)
        self.phi.setDecimals(2)
        self.phi.setSingleStep(0.5)
        self.phi.setValue(25.0)

        self.add_factor = QDoubleSpinBox()
        self.add_factor.setRange(0.5, 2.0)
        self.add_factor.setDecimals(3)
        self.add_factor.setValue(1.0)

        self.ded_factor = QDoubleSpinBox()
        self.ded_factor.setRange(0.5, 2.5)
        self.ded_factor.setDecimals(3)
        self.ded_factor.setValue(1.25)

        add_layout.addRow("Units", self.unit_mode)
        add_layout.addRow("Teeth (Z)", self.teeth)
        add_layout.addRow("Module (mm)", self.module_mm)
        add_layout.addRow("Pd (1/in)", self.pd)
        add_layout.addRow("Pressure angle (deg)", self.phi)
        add_layout.addRow("Addendum factor", self.add_factor)
        add_layout.addRow("Dedendum factor", self.ded_factor)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Add to train")
        self.btn_add.clicked.connect(self._add_gear)
        self.btn_remove = QPushButton("Remove selected")
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_clear = QPushButton("Clear train")
        self.btn_clear.clicked.connect(self._clear_train)
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_remove)
        btn_row.addWidget(self.btn_clear)
        add_layout.addRow(btn_row)

        left_layout.addWidget(self.gb_add)

        self.gb_order = QGroupBox("Train order")
        order_layout = QHBoxLayout(self.gb_order)
        order_layout.setContentsMargins(10, 10, 10, 10)
        order_layout.setSpacing(8)

        self.btn_up = QPushButton("Move up")
        self.btn_up.clicked.connect(self._move_up)
        self.btn_down = QPushButton("Move down")
        self.btn_down.clicked.connect(self._move_down)
        self.btn_reverse = QPushButton("Reverse train")
        self.btn_reverse.clicked.connect(self._reverse_train)

        order_layout.addWidget(self.btn_up)
        order_layout.addWidget(self.btn_down)
        order_layout.addWidget(self.btn_reverse)
        left_layout.addWidget(self.gb_order)

        self.gb_drive = QGroupBox("Motor + target + torque (required for simulation)")
        drive_layout = QFormLayout(self.gb_drive)
        drive_layout.setVerticalSpacing(8)

        self.rpm_in = QDoubleSpinBox()
        self.rpm_in.setRange(-200000.0, 200000.0)
        self.rpm_in.setDecimals(2)
        self.rpm_in.setValue(120.0)
        self.rpm_in.valueChanged.connect(self._recompute)

        self.rpm_out_target = QDoubleSpinBox()
        self.rpm_out_target.setRange(-200000.0, 200000.0)
        self.rpm_out_target.setDecimals(2)
        self.rpm_out_target.setValue(-120.0)
        self.rpm_out_target.valueChanged.connect(self._target_changed)

        self.lock_output = QCheckBox("Lock output RPM (auto-solve motor RPM)")
        self.lock_output.stateChanged.connect(self._recompute)

        self.btn_solve_motor = QPushButton("Solve motor RPM from target")
        self.btn_solve_motor.clicked.connect(self._solve_motor_once)

        self.torque_in = QDoubleSpinBox()
        self.torque_in.setRange(0.0, 1e9)
        self.torque_in.setDecimals(4)
        self.torque_in.setValue(1.0000)
        self.torque_in.valueChanged.connect(self._recompute)

        self.eff_per_mesh = QDoubleSpinBox()
        self.eff_per_mesh.setRange(0.50, 1.00)
        self.eff_per_mesh.setDecimals(4)
        self.eff_per_mesh.setValue(0.9700)
        self.eff_per_mesh.valueChanged.connect(self._recompute)

        self.use_losses = QCheckBox("Include efficiency losses")
        self.use_losses.setChecked(True)
        self.use_losses.stateChanged.connect(self._recompute)

        self.speed_scale = QSlider(Qt.Horizontal)
        self.speed_scale.setRange(10, 400)
        self.speed_scale.setValue(100)
        self.speed_scale.valueChanged.connect(self._recompute)

        self.motor_status = QLabel("Motor: set non-zero input RPM to run.")
        self.motor_status.setStyleSheet("color: rgba(255,255,255,0.70);")

        self.btn_play = QPushButton("Play")
        self.btn_play.clicked.connect(self._toggle_play)

        drive_layout.addRow("Motor RPM (gear 1)", self.rpm_in)
        drive_layout.addRow("Target RPM (output gear)", self.rpm_out_target)
        drive_layout.addRow(self.lock_output)
        drive_layout.addRow(self.btn_solve_motor)
        drive_layout.addRow("Input torque (N·m)", self.torque_in)
        drive_layout.addRow("Efficiency per mesh (0-1)", self.eff_per_mesh)
        drive_layout.addRow(self.use_losses)
        drive_layout.addRow("Animation scale (%)", self.speed_scale)
        drive_layout.addRow(self.motor_status)
        drive_layout.addRow(self.btn_play)

        left_layout.addWidget(self.gb_drive)

        self.gb_table = QGroupBox("Train results + ratios + torque/power")
        table_layout = QVBoxLayout(self.gb_table)
        table_layout.setContentsMargins(10, 10, 10, 10)

        self.table = QTableWidget(0, 16)
        self.table.setHorizontalHeaderLabels([
            "#", "Z", "Pitch d", "Outside d", "Root d", "Base d",
            "p_c", "RPM", "Rot", "Pair ratio", "a (center)", "ε", "V_pitch",
            "Torque (N·m)", "Power (W)", "η_to_here"
        ])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("background: rgba(255,255,255,0.04); color: white;")
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        table_layout.addWidget(self.table)
        left_layout.addWidget(self.gb_table, stretch=1)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setWidget(left)

        left_scroll.setStyleSheet("""
        QScrollArea{background:transparent;}
        QScrollBar:vertical{
            background: rgba(255,255,255,0.06);
            width: 10px;
            margin: 10px 4px 10px 4px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical{
            background: rgba(255,255,255,0.22);
            min-height: 28px;
            border-radius: 6px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical{
            height: 0px;
        }
        """)

        splitter = QSplitter()
        splitter.addWidget(left_scroll)
        splitter.addWidget(self.view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([560, 920])

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(splitter)
        self.setCentralWidget(root)

        self._gear_specs = []
        self._geoms = []
        self._rpms = []
        self._torques = []
        self._powers = []
        self._etas = []

        self._sync_unit_fields()
        self._recompute()

        self.setStyleSheet("""
        QMainWindow{background:#0b0f14;}
        QLabel{color:white;}
        QPushButton{
            background:rgba(255,255,255,0.08);
            color:white;
            border:1px solid rgba(255,255,255,0.14);
            padding:8px 10px;
            border-radius:10px;
        }
        QPushButton:hover{background:rgba(255,255,255,0.12);}
        QPushButton:pressed{background:rgba(255,255,255,0.16);}
        QPushButton:disabled{
            background:rgba(255,255,255,0.04);
            color:rgba(255,255,255,0.35);
            border:1px solid rgba(255,255,255,0.08);
        }
        QGroupBox{
            border:1px solid rgba(255,255,255,0.12);
            border-radius:14px;
            margin-top:12px;
        }
        QGroupBox::title{
            subcontrol-origin:margin;
            left:12px;
            padding:0 6px;
            color:rgba(255,255,255,0.88);
        }
        QSpinBox,QDoubleSpinBox,QComboBox{
            background:rgba(255,255,255,0.06);
            color:white;
            border:1px solid rgba(255,255,255,0.12);
            border-radius:10px;
            padding:6px 8px;
        }
        QHeaderView::section{
            background:rgba(255,255,255,0.06);
            color:rgba(255,255,255,0.90);
            border:1px solid rgba(255,255,255,0.10);
            padding:6px 6px;
        }
        """)

    def eventFilter(self, obj, event):
        if obj is self.view.viewport():
            if event.type() in (QEvent.Resize, QEvent.Show, QEvent.Paint):
                self._position_fx()
        return super().eventFilter(obj, event)

    def _toggle_fx(self):
        self.fx_open = not self.fx_open
        if self.fx_open:
            self.fx_panel.show()
            self.fx_panel.raise_()
        else:
            self.fx_panel.hide()
        self._position_fx()
        self._update_fx_panel(self.table.currentRow())

    def _position_fx(self):
        m = 14
        vw = self.view.viewport().width()
        vh = self.view.viewport().height()

        bx = vw - self.fx_button.width() - m
        by = vh - self.fx_button.height() - m
        self.fx_button.move(bx, by)
        self.fx_button.raise_()

        if self.fx_open and self.fx_panel.isVisible():
            pw, ph = self.fx_panel_size
            px = vw - pw - m
            py = vh - ph - self.fx_button.height() - (m * 2)
            py = max(m, py)
            self.fx_panel.move(px, py)
            self.fx_panel.raise_()

    def _sync_unit_fields(self):
        metric = self.unit_mode.currentIndex() == 0
        self.module_mm.setEnabled(metric)
        self.pd.setEnabled(not metric)
        self._recompute()

    def _spec_from_fields(self) -> GearSpec:
        metric = self.unit_mode.currentIndex() == 0
        Z = int(self.teeth.value())
        phi = float(self.phi.value())
        af = float(self.add_factor.value())
        df = float(self.ded_factor.value())
        if metric:
            m = float(self.module_mm.value())
            return GearSpec(teeth=Z, module_mm=m, pd_inv_in=None, pressure_angle_deg=phi, addendum_factor=af, dedendum_factor=df)
        Pd = float(self.pd.value())
        return GearSpec(teeth=Z, module_mm=None, pd_inv_in=Pd, pressure_angle_deg=phi, addendum_factor=af, dedendum_factor=df)

    def _add_gear(self):
        try:
            spec = self._spec_from_fields()
            spec.validate()
        except Exception:
            return
        self._gear_specs.append(spec)
        self._recompute(select_index=len(self._gear_specs) - 1)

    def _remove_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._gear_specs):
            return
        self._gear_specs.pop(row)
        self._recompute(select_index=min(row, len(self._gear_specs) - 1))

    def _clear_train(self):
        self._gear_specs.clear()
        self._geoms = []
        self._rpms = []
        self._torques = []
        self._powers = []
        self._etas = []
        self._omega = []
        self._angles = []
        self.scene.clear_all()
        self._clear_overlays()
        self.table.setRowCount(0)
        self._update_fx_panel(None)
        self._position_fx()

    def _move_up(self):
        row = self.table.currentRow()
        if row <= 0 or row >= len(self._gear_specs):
            return
        self._gear_specs[row - 1], self._gear_specs[row] = self._gear_specs[row], self._gear_specs[row - 1]
        self._recompute(select_index=row - 1)

    def _move_down(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._gear_specs) - 1:
            return
        self._gear_specs[row + 1], self._gear_specs[row] = self._gear_specs[row], self._gear_specs[row + 1]
        self._recompute(select_index=row + 1)

    def _reverse_train(self):
        self._gear_specs.reverse()
        self._recompute(select_index=0)

    def _target_changed(self):
        if self.lock_output.isChecked():
            self._solve_motor_once()
            self._recompute()

    def _solve_motor_once(self):
        if not self._gear_specs:
            return
        try:
            teeth = [int(s.teeth) for s in self._gear_specs]
        except Exception:
            return
        rpm_out_t = float(self.rpm_out_target.value())
        rpm_in_needed = _solve_motor_rpm_for_target(teeth, rpm_out_t)
        self.rpm_in.blockSignals(True)
        self.rpm_in.setValue(rpm_in_needed)
        self.rpm_in.blockSignals(False)

    def _can_run(self) -> bool:
        return len(self._gear_specs) > 0 and abs(float(self.rpm_in.value())) > 1e-9

    def _toggle_play(self):
        if not self._running:
            if not self._can_run():
                self._running = False
                self.btn_play.setText("Play")
                return
        self._running = not self._running
        self.btn_play.setText("Pause" if self._running else "Play")
        if self._running:
            self.timer.start(16)
        else:
            self.timer.stop()

    def _recompute(self, select_index: int | None = None):
        self._position_fx()

        if not self._gear_specs:
            self.scene.clear_all()
            self._clear_overlays()
            self.table.setRowCount(0)
            self._omega = []
            self._angles = []
            self._geoms = []
            self._rpms = []
            self._torques = []
            self._powers = []
            self._etas = []
            self.motor_status.setText("Motor: set non-zero input RPM to run.")
            self.btn_play.setEnabled(False)
            self._update_fx_panel(None)
            return

        if self.lock_output.isChecked():
            self._solve_motor_once()

        self._geoms = []
        for spec in self._gear_specs:
            try:
                self._geoms.append(gear_geom(spec))
            except Exception:
                self._geoms.append(None)

        if any(g is None for g in self._geoms):
            self.scene.clear_all()
            self._clear_overlays()
            self.table.setRowCount(0)
            self._omega = []
            self._angles = []
            self._rpms = []
            self._torques = []
            self._powers = []
            self._etas = []
            self.btn_play.setEnabled(False)
            self._update_fx_panel(None)
            return

        teeth_list = [g.teeth for g in self._geoms]

        if self._can_run():
            rpm_in = float(self.rpm_in.value())
            self._rpms = rpm_chain(teeth_list, rpm_in)
            scale = float(self.speed_scale.value()) / 100.0
            self._omega = [ang_vel_from_rpm(r) * scale for r in self._rpms]
            self.motor_status.setText("Motor: OK (RPM applied to gear 1).")
            self.btn_play.setEnabled(True)
        else:
            self._rpms = [0.0 for _ in teeth_list]
            self._omega = [0.0 for _ in teeth_list]
            if self._running:
                self._running = False
                self.timer.stop()
                self.btn_play.setText("Play")
            self.motor_status.setText("Motor: set non-zero input RPM to run.")
            self.btn_play.setEnabled(False)

        if len(self._angles) != len(self._omega):
            self._angles = [0.0 for _ in self._omega]

        self._compute_torque_power()
        self._render_scene()
        self._render_table()

        if select_index is not None and 0 <= select_index < self.table.rowCount():
            self.table.selectRow(select_index)
        elif self.table.rowCount() > 0 and self.table.currentRow() < 0:
            self.table.selectRow(0)

        self._sync_order_buttons()
        self._on_selection_changed()
        self._update_fx_panel(self.table.currentRow())

    def _compute_torque_power(self):
        n = len(self._geoms)
        if n == 0:
            self._torques, self._powers, self._etas = [], [], []
            return

        Tin = float(self.torque_in.value())
        eff = float(self.eff_per_mesh.value())
        use_losses = self.use_losses.isChecked()

        self._etas = []
        for i in range(n):
            eta = (eff ** i) if use_losses else 1.0
            self._etas.append(eta)

        self._torques = [0.0] * n
        self._powers = [0.0] * n

        self._torques[0] = Tin
        w0 = ang_vel_from_rpm(self._rpms[0]) if self._rpms else 0.0
        self._powers[0] = abs(Tin * w0)

        for i in range(1, n):
            z_prev = float(self._geoms[i - 1].teeth)
            z_cur = float(self._geoms[i].teeth)
            stage_gain = (z_cur / z_prev) if z_prev > 0 else 0.0
            stage_eta = eff if use_losses else 1.0
            self._torques[i] = self._torques[i - 1] * stage_gain * stage_eta
            wi = ang_vel_from_rpm(self._rpms[i]) if i < len(self._rpms) else 0.0
            self._powers[i] = abs(self._torques[i] * wi)

    def _sync_order_buttons(self):
        row = self.table.currentRow()
        n = len(self._gear_specs)
        self.btn_up.setEnabled(0 < row < n)
        self.btn_down.setEnabled(0 <= row < n - 1)

    def _clear_overlays(self):
        for it in self._overlay_items:
            try:
                self.scene.removeItem(it)
            except Exception:
                pass
        self._overlay_items.clear()

    def _render_scene(self):
        self.scene.clear_all()
        self._clear_overlays()

        g0 = self._geoms[0]
        unit_scale = self.scene.scale_px_per_unit / max(1e-6, g0.pitch_rad)

        pitch_r_px = []
        for i, g in enumerate(self._geoms, start=1):
            pitch_r = g.pitch_rad * unit_scale
            base_r = g.base_rad * unit_scale
            add_r = g.addendum_rad * unit_scale
            root_r = g.root_rad * unit_scale
            label = f"G{i}\nZ={g.teeth}"
            item = GearItem(g.teeth, pitch_r, base_r, add_r, root_r, label)
            self.scene.add_gear(item)
            pitch_r_px.append(pitch_r)

        self.scene.layout_chain(pitch_r_px)

        for i, gear_item in enumerate(self.scene.gears):
            rpm = self._rpms[i] if i < len(self._rpms) else 0.0
            t = QGraphicsSimpleTextItem(f"{_rot_label(rpm)}")
            t.setBrush(Qt.white)
            t.setFlag(QGraphicsSimpleTextItem.ItemIgnoresTransformations, True)
            pos = gear_item.pos()
            t.setPos(pos.x() - 18, pos.y() - (pitch_r_px[i] + 26))
            self.scene.addItem(t)
            self._overlay_items.append(t)

        for i in range(1, len(self.scene.gears)):
            z_prev = self._geoms[i - 1].teeth
            z_cur = self._geoms[i].teeth
            rt = _pair_ratio_text(z_prev, z_cur)
            midx = (self.scene.gears[i - 1].pos().x() + self.scene.gears[i].pos().x()) / 2.0
            t = QGraphicsSimpleTextItem(rt)
            t.setBrush(Qt.white)
            t.setFlag(QGraphicsSimpleTextItem.ItemIgnoresTransformations, True)
            t.setPos(midx - 18, 26)
            self.scene.addItem(t)
            self._overlay_items.append(t)

        if self._geoms:
            z_in = self._geoms[0].teeth
            z_out = self._geoms[-1].teeth
            ratio = _overall_ratio_text(z_in, z_out)
            t = QGraphicsSimpleTextItem(f"{z_in}:{z_out} ({ratio})")
            t.setBrush(Qt.white)
            t.setFlag(QGraphicsSimpleTextItem.ItemIgnoresTransformations, True)
            br = self.scene.itemsBoundingRect()
            t.setPos(br.right() - 130, br.bottom() - 26)
            self.scene.addItem(t)
            self._overlay_items.append(t)

        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def _render_table(self):
        geoms = self._geoms
        rpms = self._rpms
        self.table.setRowCount(len(geoms))
        unit_label = "mm" if self._gear_specs[0].is_metric() else "in"

        for i, g in enumerate(geoms):
            pitch_d = g.pitch_diam
            out_d = 2.0 * g.addendum_rad
            root_d = 2.0 * g.root_rad
            base_d = 2.0 * g.base_rad

            v = _pitch_line_velocity(pitch_d, rpms[i])
            torque = self._torques[i] if i < len(self._torques) else 0.0
            power = self._powers[i] if i < len(self._powers) else 0.0
            eta = self._etas[i] if i < len(self._etas) else 1.0

            self._set_cell(i, 0, str(i + 1))
            self._set_cell(i, 1, str(g.teeth))
            self._set_cell(i, 2, f"{_fmt(pitch_d)} {unit_label}")
            self._set_cell(i, 3, f"{_fmt(out_d)} {unit_label}")
            self._set_cell(i, 4, f"{_fmt(root_d)} {unit_label}")
            self._set_cell(i, 5, f"{_fmt(base_d)} {unit_label}")
            self._set_cell(i, 6, f"{_fmt(g.circular_pitch)} {unit_label}")
            self._set_cell(i, 7, f"{rpms[i]:.2f}")
            self._set_cell(i, 8, _rot_label(rpms[i]))

            if i == 0:
                self._set_cell(i, 9, "—")
                self._set_cell(i, 10, "—")
                self._set_cell(i, 11, "—")
            else:
                self._set_cell(i, 9, _pair_ratio_text(geoms[i - 1].teeth, geoms[i].teeth))
                cd = center_distance(geoms[i - 1], geoms[i])
                eps = contact_ratio(geoms[i - 1], geoms[i])
                self._set_cell(i, 10, f"{_fmt(cd)} {unit_label}")
                self._set_cell(i, 11, f"{_fmt(eps)}")

            self._set_cell(i, 12, f"{_fmt(v)} {unit_label}/s")
            self._set_cell(i, 13, f"{torque:.4f}")
            self._set_cell(i, 14, f"{power:.4f}")
            self._set_cell(i, 15, f"{eta:.4f}")

        self.table.resizeColumnsToContents()

    def _set_cell(self, r, c, text):
        it = QTableWidgetItem(text)
        it.setForeground(Qt.white)
        self.table.setItem(r, c, it)

    def _on_selection_changed(self):
        if not self._gear_specs or not self._geoms:
            self._update_fx_panel(None)
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self._geoms):
            self._update_fx_panel(None)
            return
        self._update_fx_panel(row)
        self._sync_order_buttons()
        for i, it in enumerate(self.scene.gears):
            it.setSelected(i == row)

    def _update_fx_panel(self, row: int | None):
        if not self._gear_specs or not self._geoms:
            self.fx_summary.setHtml("<b>No train yet.</b> Add gears to start.")
            self.fx_body.setHtml("Use the ƒx button to open solved formulas.")
            return

        unit_metric = self._gear_specs[0].is_metric()
        unit_len = "mm" if unit_metric else "in"

        rpm_in = float(self.rpm_in.value())
        rpm_out_target = float(self.rpm_out_target.value())
        rpm_out = self._rpms[-1] if self._rpms else 0.0

        teeth = [g.teeth for g in self._geoms]
        z_in = teeth[0]
        z_out = teeth[-1]

        ratio_txt = f"{z_in}:{z_out} ({_overall_ratio_text(z_in, z_out)})"
        k = _chain_k_explicit(teeth)
        motor_needed = _solve_motor_rpm_for_target(teeth, rpm_out_target)

        Tout = self._torques[-1] if self._torques else 0.0
        Pout = self._powers[-1] if self._powers else 0.0
        eta_total = self._etas[-1] if self._etas else 1.0

        rot_out = _rot_label(rpm_out)

        rpm_out_from_in = rpm_in * k
        rpm_in_from_target = (rpm_out_target / k) if abs(k) > 1e-12 else 0.0

        summary = (
            f"<b>Train:</b> gears={len(self._geoms)} &nbsp; <b>Overall ratio (Zin:Zout):</b> {ratio_txt}<br>"
            f"<b>RPM in:</b> {rpm_in:.2f} &nbsp; <b>RPM out:</b> {rpm_out:.2f} ({rot_out})<br>"
            f"<b>Target out:</b> {rpm_out_target:.2f} &nbsp; <b>Motor for target:</b> {motor_needed:.2f}<br>"
            f"<b>k=rpm_out/rpm_in:</b> {k:.6f}<br>"
            f"<b>RPM_out(from in):</b> {rpm_out_from_in:.2f} &nbsp; <b>RPM_in(for target):</b> {rpm_in_from_target:.2f}<br>"
            f"<b>T_out:</b> {Tout:.4f} N·m &nbsp; <b>P_out:</b> {Pout:.4f} W &nbsp; <b>η_total:</b> {eta_total:.4f}"
        )
        self.fx_summary.setHtml(summary)

        if row is None or row < 0 or row >= len(self._geoms) or row >= len(self._gear_specs):
            self.fx_body.setHtml("Select a gear row to show solved formulas.")
            return

        g = self._geoms[row]
        spec = self._gear_specs[row]
        rpm = self._rpms[row] if row < len(self._rpms) else 0.0
        torque = self._torques[row] if row < len(self._torques) else 0.0
        power = self._powers[row] if row < len(self._powers) else 0.0
        rot = _rot_label(rpm)

        phi_deg = float(spec.pressure_angle_deg)
        phi_rad = g.phi_rad

        pitch_d = g.pitch_diam
        r_calc = pitch_d / 2.0
        rb = g.base_rad
        out_d = 2.0 * g.addendum_rad
        root_d = 2.0 * g.root_rad

        v_pitch = _pitch_line_velocity(pitch_d, rpm)
        tooth_thickness = 0.5 * g.circular_pitch
        omega = ang_vel_from_rpm(rpm)

        if spec.is_metric():
            m = float(spec.module_mm)
            Pd = _pd_from_module(m)
            unit_line = f"Metric: m={m:.6f} {unit_len}, Pd={Pd:.6f} 1/in"
            d_expr = f"d = m·Z = {m:.6f}·{g.teeth} = {pitch_d:.6f} {unit_len}"
            pc_expr = f"p_c = π·m = π·{m:.6f} = {math.pi*m:.6f} {unit_len}"
            a_lin = float(spec.addendum_factor) * m
            b_lin = float(spec.dedendum_factor) * m
        else:
            Pd = float(spec.pd_inv_in)
            m = _module_from_pd(Pd)
            unit_line = f"Imperial: Pd={Pd:.6f} 1/in, m={m:.6f} mm"
            d_expr = f"d = Z/Pd = {g.teeth}/{Pd:.6f} = {pitch_d:.6f} {unit_len}"
            pc_expr = f"p_c = π/Pd = π/{Pd:.6f} = {math.pi/Pd:.6f} {unit_len}"
            a_lin = float(spec.addendum_factor) / Pd
            b_lin = float(spec.dedendum_factor) / Pd

        rb_expr = f"r_b = r·cos(φ) = {r_calc:.6f}·cos({phi_deg:.2f}°) = {rb:.6f} {unit_len}"
        do_expr = f"d_o = 2·(r+a) = {out_d:.6f} {unit_len}"
        df_expr = f"d_f = 2·(r-b) = {root_d:.6f} {unit_len}"
        t_expr = f"t = p_c/2 = {g.circular_pitch:.6f}/2 = {tooth_thickness:.6f} {unit_len}"
        pb_expr = f"p_b = p_c·cos(φ) = {g.base_pitch:.6f} {unit_len}"
        v_expr = f"V = π·d·RPM/60 = π·{pitch_d:.6f}·{rpm:.6f}/60 = {v_pitch:.6f} {unit_len}/s"
        w_expr = f"ω = RPM·2π/60 = {rpm:.6f}·2π/60 = {omega:.6f} rad/s"
        p_expr = f"P = T·|ω| = {torque:.6f}·|{omega:.6f}| = {abs(torque * omega):.6f} W"

        pair_block = ""
        if row > 0:
            z_prev = self._geoms[row - 1].teeth
            z_cur = g.teeth
            cd = center_distance(self._geoms[row - 1], g)
            eps = contact_ratio(self._geoms[row - 1], g)
            rpm_prev = self._rpms[row - 1]
            rpm_pred = -rpm_prev * (z_prev / z_cur)
            pair_block = (
                f"<br><b>Pair with previous (resolved):</b><br>"
                f"Ratio: {_pair_ratio_text(z_prev, z_cur)}<br>"
                f"a = r1+r2 = {_fmt(cd)} {unit_len}<br>"
                f"ε (contact ratio) = {_fmt(eps)}<br>"
                f"RPM_cur = -RPM_prev·(Z_prev/Z_cur) = -({rpm_prev:.6f})·({z_prev}/{z_cur}) = {rpm_pred:.6f}<br>"
            )

        chain_block = (
            f"<br><b>Chain solver (resolved):</b><br>"
            f"k = (-1)^(n-1)·(Z1/Zn) = {k:.6f}<br>"
            f"RPM_out = RPM_in·k = {rpm_in:.6f}·{k:.6f} = {rpm_out_from_in:.6f}<br>"
            f"RPM_in(for target) = RPM_out_target/k = {rpm_out_target:.6f}/{k:.6f} = {rpm_in_from_target:.6f}<br>"
        )

        body = (
            f"<b>Selected gear:</b> G{row+1} &nbsp; Z={g.teeth} &nbsp; RPM={rpm:.2f} ({rot}) &nbsp; "
            f"T={torque:.4f} N·m &nbsp; P={power:.4f} W<br>"
            f"<b>{unit_line}</b><br><br>"
            f"<b>Solved geometry:</b><br>"
            f"{d_expr}<br>"
            f"r = d/2 = {pitch_d:.6f}/2 = {r_calc:.6f} {unit_len}<br>"
            f"φ = {phi_deg:.2f}° = {phi_rad:.6f} rad<br>"
            f"{rb_expr}<br>"
            f"a = add_factor·m OR add_factor/Pd = {a_lin:.6f} {unit_len}<br>"
            f"b = ded_factor·m OR ded_factor/Pd = {b_lin:.6f} {unit_len}<br>"
            f"{do_expr}<br>"
            f"{df_expr}<br>"
            f"{pc_expr}<br>"
            f"{t_expr}<br>"
            f"{pb_expr}<br>"
            f"{v_expr}<br><br>"
            f"<b>Solved power:</b><br>"
            f"{w_expr}<br>"
            f"{p_expr}<br>"
            f"{pair_block}"
            f"{chain_block}"
        )
        self.fx_body.setHtml(body)

    def _tick(self):
        if not self._running:
            return
        dt = 1.0 / 60.0
        for i, item in enumerate(self.scene.gears):
            if i >= len(self._omega):
                continue
            self._angles[i] = (self._angles[i] + self._omega[i] * dt) % (2.0 * math.pi)
            item.setRotation(math.degrees(self._angles[i]))