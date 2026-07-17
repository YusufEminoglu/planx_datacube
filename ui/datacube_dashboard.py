# -*- coding: utf-8 -*-
"""
DataCube Dashboard — Professional QDialog following PlanX Suitability Lab pattern.

Production console for PlanX DataCube Lab with:
  - Hero header with gradient branding
  - Tabbed interface: Overview, Modules (card grid), Setup, Quick Actions
  - Processing algorithm cards with Run/Fav buttons
  - System health monitoring and dependency management
"""
from __future__ import annotations

import os
from datetime import datetime

import processing
from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListWidget,
    QMessageBox,
    QAbstractItemView,
    QScrollArea,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QSpinBox,
    QFormLayout,
)
from qgis.core import Qgis, QgsApplication, QgsProject


IS_QGIS4 = int(getattr(Qgis, "QGIS_VERSION_INT", 0)) >= 40000
DASHBOARD_SIZE = (1100, 760) if IS_QGIS4 else (1180, 800)
DEFAULT_CARD_COLUMNS = 2 if IS_QGIS4 else 3

# ── Algorithm catalogue ─────────────────────────────────────────────

ALGO_GROUPS = [
    (
        "Data Cube",
        "#2f7aa8",
        [
            ("Build Data Cube", "planx_datacube:create_data_cube",
             "Construct X×Y×T×V multi-dimensional cube from vector/raster time series, with optional netCDF4 export."),
            ("Space-Time Cube Aggregation", "planx_datacube:space_time_cube",
             "Bin point/feature events into a fishnet × time-step panel (count/sum/mean/max/min) — the front door to EHSA, Trend, Anomaly and Forecast."),
        ],
    ),
    (
        "Spatiotemporal Analysis",
        "#357a5f",
        [
            ("Emerging Hot Spot Analysis (EHSA)", "planx_datacube:emerging_hot_spot_analysis",
             "Getis-Ord Gi* (true distance-band / KNN neighbourhoods) + Mann-Kendall → classify each location into 17 spatiotemporal hot/cold spot patterns."),
            ("Local Outlier Analysis (Local Moran's I)", "planx_datacube:local_morans_i",
             "Anselin LISA: significant High-High / Low-Low clusters and High-Low / Low-High spatial outliers via conditional permutation."),
            ("Temporal Trend Analysis", "planx_datacube:temporal_trend",
             "Mann-Kendall + Theil-Sen per location → Increasing / Decreasing / No-trend classification with robust slope."),
            ("Temporal Anomaly Detection", "planx_datacube:temporal_anomaly",
             "Flag anomalous time steps per location with a robust median/MAD (or classic) z-score."),
        ],
    ),
    (
        "Forecasting",
        "#7a5f9e",
        [
            ("Time-Series Forecast", "planx_datacube:time_series_forecast",
             "Per-cell forecasting with ARIMA / Random Forest / Exponential Smoothing (auto-fallback chain)."),
            ("Forecast Backtest", "planx_datacube:forecast_backtest",
             "Hold-out accuracy (MAE / RMSE / MAPE) per method → pick the best forecaster before projecting forward."),
        ],
    ),
]

REQUIRED_IDS = [aid for _, _, items in ALGO_GROUPS for _, aid, _ in items]

CATEGORY_GROUPS = {
    "Cube Construction": [
        "planx_datacube:create_data_cube",
        "planx_datacube:space_time_cube",
    ],
    "Spatiotemporal Analysis": [
        "planx_datacube:emerging_hot_spot_analysis",
        "planx_datacube:local_morans_i",
        "planx_datacube:temporal_trend",
        "planx_datacube:temporal_anomaly",
    ],
    "Forecasting": [
        "planx_datacube:time_series_forecast",
        "planx_datacube:forecast_backtest",
    ],
}


class DataCubeDashboard(QDialog):
    """Production console for PlanX DataCube Lab."""

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.settings = QSettings()
        self.recent_runs: list[str] = []
        self.card_widgets: list[QFrame] = []
        self._current_card_columns = DEFAULT_CARD_COLUMNS
        self.favorites: set[str] = set(
            self.settings.value("planx_datacube/favorites", [], type=list) or []
        )

        self.setWindowTitle("PlanX DataCube Lab — Spatiotemporal Analysis Engine")
        self.resize(*DASHBOARD_SIZE)
        self._apply_style()
        self._build_ui()
        self._refresh()

    # ── Styling ──────────────────────────────────────────────────────

    def _apply_style(self) -> None:
        r = 10 if IS_QGIS4 else 13
        btn_r = 8 if IS_QGIS4 else 9
        title_sz = 22 if IS_QGIS4 else 24
        self.setStyleSheet(f"""
            QDialog {{ background: #ecf3f4; font-family: "Segoe UI", "Inter", sans-serif; }}
            QFrame#heroCard {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #0d1b2a, stop:0.45 #1b2838, stop:1 #1b3a4b);
                border-radius: {r}px; border: 1px solid #1a3a5c;
            }}
            QLabel#heroTitle {{ color: #64b5f6; font-weight: 700; font-size: {title_sz}px; }}
            QLabel#heroSub {{ color: #a0d2f0; font-size: 12px; }}
            QLabel#statusChip {{
                color: #0f2d3a; background: #f8d37a; border: 1px solid #e8bf58;
                border-radius: 8px; padding: 4px 10px; font-weight: 700;
            }}
            QTabWidget::pane {{ border: 1px solid #cfdee2; border-radius: {r}px; background: #ffffff; }}
            QTabBar::tab {{
                background: #dce9ec; color: #183844; border: 1px solid #c4d6dc;
                padding: 8px 14px; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 3px;
            }}
            QTabBar::tab:selected {{ background: #ffffff; font-weight: 700; border-color: #9bbac4; }}
            QTextBrowser {{
                background: #ffffff; border: 1px solid #d4e1e5; border-radius: {r}px;
                padding: 9px; color: #17313a;
            }}
            QPushButton {{
                background: #1565c0; color: #ffffff; border: 1px solid #0d47a1;
                border-radius: {btn_r}px; padding: 7px 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: #1976d2; }}
            QPushButton#ghost {{
                background: #ffffff; color: #1565c0; border: 1px solid #b4ccd3;
            }}
            QPushButton#ghost:hover {{ background: #e3f2fd; }}
            QPushButton#favBtn {{
                background: #ffffff; color: #1565c0; border: 1px solid #c0d8e8;
                border-radius: 8px; padding: 2px 8px; font-weight: 700;
            }}
            QPushButton#favBtn:checked {{
                background: #e3f2fd; color: #0d47a1; border: 1px solid #64b5f6;
            }}
            QLineEdit {{
                background: #ffffff; border: 1px solid #c9d9de; border-radius: 8px; padding: 6px; color: #17323a;
            }}
            QComboBox {{
                background: #ffffff; border: 1px solid #c9d9de; border-radius: 8px; padding: 6px; color: #17323a;
            }}
            QFrame[classCard="true"] {{
                background: #fbfefe; border: 1px solid #d3e3e7; border-radius: {r}px;
            }}
            QFrame[classCard="true"]:hover {{ background: #f2fafc; border: 1px solid #a8cfdb; }}
            QLabel[classTitle="true"] {{ color: #173741; font-weight: 700; font-size: 13px; }}
            QLabel[classMeta="true"] {{ color: #4a6871; font-size: 11px; }}
            QLabel[classChip="ok"] {{
                color: #0d4430; background: #b8e9cf; border: 1px solid #92d8b1;
                border-radius: 8px; padding: 1px 7px; font-size: 10px; font-weight: 700;
            }}
            QLabel[classChip="warn"] {{
                color: #734700; background: #ffe2ab; border: 1px solid #f0cb86;
                border-radius: 8px; padding: 1px 7px; font-size: 10px; font-weight: 700;
            }}
            QLabel#cardCount {{ color: #2b4d57; font-size: 11px; padding: 0 4px; }}
        """)

    # ── Build UI ─────────────────────────────────────────────────────

    def _make_group(self, title: str) -> QGroupBox:
        gb = QGroupBox(title)
        gb.setFont(QFont("Inter, Segoe UI", 9, QFont.Weight.Bold))
        gb.setStyleSheet(
            "QGroupBox { border: 1px solid #bbb; border-radius: 6px; "
            "margin-top: 8px; padding: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; "
            "padding: 0 4px; }"
        )
        return gb

    def _build_ui(self) -> None:
        m = 10 if IS_QGIS4 else 12
        root = QVBoxLayout(self)
        root.setContentsMargins(m, m, m, m)
        root.setSpacing(m)

        # ── Hero header ──
        hero = QFrame()
        hero.setObjectName("heroCard")
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(14, 12, 14, 12)
        ttl = QVBoxLayout()
        title = QLabel("PlanX DataCube Lab")
        title.setObjectName("heroTitle")
        sub = QLabel("Spatiotemporal analysis engine: data cubes, emerging hot spots, time-series forecasting | Mekan-zaman analizi: veri kupleri, EHSA, tahminleme")
        sub.setObjectName("heroSub")
        ttl.addWidget(title)
        ttl.addWidget(sub)
        hl.addLayout(ttl, 1)
        self.status_chip = QLabel("System Status: checking...")
        self.status_chip.setObjectName("statusChip")
        hl.addWidget(self.status_chip, 0, Qt.AlignmentFlag.AlignRight)
        root.addWidget(hero)

        # ── Tabs ──
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # Overview tab
        self.overview = QTextBrowser()
        self.tabs.addTab(self.overview, "Overview")

        # Forecasting Studio tab
        self.tabs.addTab(self._build_forecasting_studio_tab(), "Forecasting Studio")

        # Modules tab (card grid)
        mod_tab = QWidget()
        ml = QVBoxLayout(mod_tab)
        ml.setContentsMargins(8, 8, 8, 8)

        filter_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter modules...")
        self.search.textChanged.connect(self._filter_cards)
        filter_row.addWidget(self.search, 1)
        self.group_filter = QComboBox()
        self.group_filter.addItem("All Groups", "")
        for g, _, _ in ALGO_GROUPS:
            self.group_filter.addItem(g, g)
        self.group_filter.currentIndexChanged.connect(self._filter_cards)
        filter_row.addWidget(self.group_filter)
        self.fav_only = QPushButton("Favorites")
        self.fav_only.setObjectName("ghost")
        self.fav_only.setCheckable(True)
        self.fav_only.toggled.connect(self._filter_cards)
        filter_row.addWidget(self.fav_only)
        self.card_count = QLabel("0/0")
        self.card_count.setObjectName("cardCount")
        filter_row.addWidget(self.card_count, 0, Qt.AlignmentFlag.AlignRight)
        ml.addLayout(filter_row)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        cards_host = QWidget()
        self.cards_grid = QGridLayout(cards_host)
        self.cards_grid.setContentsMargins(4, 4, 4, 4)
        self.cards_grid.setHorizontalSpacing(8)
        self.cards_grid.setVerticalSpacing(8)
        self.cards_scroll.setWidget(cards_host)
        ml.addWidget(self.cards_scroll, 1)
        self.tabs.addTab(mod_tab, "Modules")

        self._build_cards()

        # Setup tab
        setup_tab = QWidget()
        sl = QVBoxLayout(setup_tab)
        sl.setContentsMargins(12, 12, 12, 12)
        sl.addWidget(QLabel(
            "DataCube Lab requires several Python data-science packages. "
            "Check what's missing and install with one click."))
        self.setup_status = QTextBrowser()
        sl.addWidget(self.setup_status, 1)
        sr = QHBoxLayout()
        btn_check = QPushButton("Check Dependencies")
        btn_check.clicked.connect(self._on_check_deps)
        sr.addWidget(btn_check)
        btn_install = QPushButton("Copy Install Command")
        btn_install.clicked.connect(self._on_install_deps)
        sr.addWidget(btn_install)
        sr.addStretch()
        sl.addLayout(sr)
        self.tabs.addTab(setup_tab, "Setup")

        # Quick Actions tab
        qa_tab = QWidget()
        ql = QVBoxLayout(qa_tab)
        ql.setContentsMargins(12, 12, 12, 12)
        quick = [
            ("Build Data Cube", lambda: self._run_algorithm("planx_datacube:create_data_cube", "Data Cube")),
            ("Aggregate Space-Time Cube", lambda: self._run_algorithm("planx_datacube:space_time_cube", "Space-Time Cube")),
            ("Run EHSA (Emerging Hot Spots)", lambda: self._run_algorithm("planx_datacube:emerging_hot_spot_analysis", "EHSA")),
            ("Run Local Outlier Analysis (LISA)", lambda: self._run_algorithm("planx_datacube:local_morans_i", "Local Moran's I")),
            ("Run Temporal Trend Analysis", lambda: self._run_algorithm("planx_datacube:temporal_trend", "Temporal Trend")),
            ("Run Temporal Anomaly Detection", lambda: self._run_algorithm("planx_datacube:temporal_anomaly", "Anomaly")),
            ("Run Time-Series Forecast", lambda: self._run_algorithm("planx_datacube:time_series_forecast", "Forecast")),
            ("Run Forecast Backtest", lambda: self._run_algorithm("planx_datacube:forecast_backtest", "Backtest")),
            ("Configure 3D Voxel Layer", self._on_voxel_config),
        ]
        for label, fn in quick:
            b = QPushButton(label)
            b.clicked.connect(fn)
            ql.addWidget(b)
        ql.addStretch()
        self.tabs.addTab(qa_tab, "Quick Actions")

        # Layout tab
        self._build_layout_tab()

        # Recent Runs tab
        rl_tab = QWidget()
        rl = QVBoxLayout(rl_tab)
        rl.setContentsMargins(8, 8, 8, 8)
        self.runlog = QTextBrowser()
        rl.addWidget(self.runlog, 1)
        clear = QPushButton("Clear Log")
        clear.setObjectName("ghost")
        clear.clicked.connect(self._clear_runlog)
        rl.addWidget(clear, 0, Qt.AlignmentFlag.AlignRight)
        self.tabs.addTab(rl_tab, "Recent Runs")

        # System Health tab
        self.readiness = QTextBrowser()
        self.tabs.addTab(self.readiness, "System Health")

        # Footer
        footer = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh)
        footer.addWidget(refresh)
        hint = QLabel("Tip: Build a Data Cube first, then run EHSA or Forecast on the panel data.")
        hint.setStyleSheet("color:#35545f; font-size:11px;")
        footer.addWidget(hint, 1)
        root.addLayout(footer)

        self._on_check_deps()

    # ── Module cards ─────────────────────────────────────────────────

    def _build_cards(self) -> None:
        for w in self.card_widgets:
            w.setParent(None)
        self.card_widgets = []
        columns = self._cards_column_count()
        self._current_card_columns = columns
        idx = 0
        for group, accent, items in ALGO_GROUPS:
            for title_txt, aid, desc in items:
                card = QFrame()
                card.setProperty("classCard", "true")
                card.setStyleSheet(f"border-left: 3px solid {accent};")
                v = QVBoxLayout(card)
                v.setContentsMargins(10, 10, 10, 10)

                hdr = QHBoxLayout()
                t = QLabel(title_txt)
                t.setProperty("classTitle", "true")
                hdr.addWidget(t, 1)
                status_lbl = QLabel("Checking")
                status_lbl.setProperty("classChip", "warn")
                hdr.addWidget(status_lbl, 0, Qt.AlignmentFlag.AlignRight)
                v.addLayout(hdr)

                m = QLabel(f"{group}  |  {aid}")
                m.setProperty("classMeta", "true")
                d = QLabel(desc)
                d.setWordWrap(True)
                d.setStyleSheet("color:#294e58; font-size:12px;")
                v.addWidget(m)
                v.addWidget(d, 1)

                fav = QPushButton("Fav")
                fav.setObjectName("favBtn")
                fav.setCheckable(True)
                fav.setChecked(aid in self.favorites)
                fav.clicked.connect(lambda checked, x=aid: self._toggle_favorite(x, checked))

                run = QPushButton("Run")
                run.clicked.connect(lambda _, x=aid, n=title_txt: self._run_algorithm(x, n))

                br = QHBoxLayout()
                br.addWidget(fav, 0, Qt.AlignmentFlag.AlignLeft)
                br.addStretch()
                br.addWidget(run, 0, Qt.AlignmentFlag.AlignRight)
                v.addLayout(br)

                card.meta = (group.lower(), title_txt.lower(), aid.lower(), desc.lower())
                card.algo_id = aid
                card.status_lbl = status_lbl
                r, c = divmod(idx, columns)
                self.cards_grid.addWidget(card, r, c)
                self.card_widgets.append(card)
                idx += 1

    def _cards_column_count(self) -> int:
        if not hasattr(self, "cards_scroll"):
            return DEFAULT_CARD_COLUMNS
        vp = self.cards_scroll.viewport()
        width = vp.width() if vp else self.width() - 120
        if width <= 0:
            width = 1
        target = 420 if IS_QGIS4 else 380
        max_cols = 2 if IS_QGIS4 else 3
        return max(1, min(max_cols, width // target))

    def _filter_cards(self) -> None:
        q = (self.search.text() or "").strip().lower()
        grp = (self.group_filter.currentData() or "").lower()
        fav_only = self.fav_only.isChecked()
        for card in self.card_widgets:
            mg, mt, ma, md = card.meta
            ok_q = (q in mg or q in mt or q in ma or q in md) if q else True
            ok_g = (mg == grp) if grp else True
            ok_f = (card.algo_id in self.favorites) if fav_only else True
            card.setVisible(ok_q and ok_g and ok_f)
        visible = sum(1 for c in self.card_widgets if c.isVisible())
        self.card_count.setText(f"Visible: {visible}/{len(self.card_widgets)}")

    def _toggle_favorite(self, algo_id: str, checked: bool) -> None:
        if checked:
            self.favorites.add(algo_id)
        else:
            self.favorites.discard(algo_id)
        self.settings.setValue("planx_datacube/favorites", sorted(self.favorites))
        self._filter_cards()

    # ── Algorithm execution ──────────────────────────────────────────

    def _run_algorithm(self, algo_id: str, label: str) -> None:
        reg = QgsApplication.processingRegistry()
        if reg.algorithmById(algo_id) is None:
            QMessageBox.warning(
                self, "Algorithm Not Found",
                f"The algorithm '{algo_id}' is not registered.\n\n"
                "The Processing provider may not have loaded correctly. "
                "Try restarting QGIS or reinstalling the plugin."
            )
            return
        try:
            processing.execAlgorithmDialog(algo_id)
        except Exception as exc:
            QMessageBox.critical(
                self, "Algorithm Error",
                f"Failed to open '{label}':\n{exc}"
            )
            return
        ts = datetime.now().strftime("%H:%M:%S")
        self.recent_runs.insert(0, f"[{ts}] {label} ({algo_id})")
        self.recent_runs = self.recent_runs[:30]
        self._refresh_runlog()

    def _refresh_runlog(self) -> None:
        if not self.recent_runs:
            self.runlog.setHtml("<h3>Recent Runs</h3><p>No runs yet.</p>")
            return
        html = "<h3>Recent Runs</h3><ul>" + "".join(f"<li>{r}</li>" for r in self.recent_runs) + "</ul>"
        self.runlog.setHtml(html)

    def _clear_runlog(self) -> None:
        self.recent_runs = []
        self._refresh_runlog()

    # ── Layout Tools ──────────────────────────────────────────────────

    def _build_layout_tab(self) -> None:
        w = QWidget()
        lyt = QVBoxLayout(w)
        lyt.setContentsMargins(12, 12, 12, 12)
        gb = self._make_group("Time-Slice Layout Stacker")
        gl = QVBoxLayout(gb)
        gl.addWidget(QLabel(
            "Stack temporal layers in a print layout to visualize\n"
            "spatial change over time. Select layers in order (oldest first)."))
        self.ts_layer_list = QListWidget()
        self.ts_layer_list.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )
        self.ts_layer_list.setMaximumHeight(120)
        gl.addWidget(self.ts_layer_list)
        btn_v = QPushButton("Stack Vertically")
        btn_v.clicked.connect(lambda: self._on_time_slice_stack("vertical"))
        gl.addWidget(btn_v)
        btn_d = QPushButton("Stack Diagonally")
        btn_d.clicked.connect(lambda: self._on_time_slice_stack("diagonal"))
        gl.addWidget(btn_d)
        lyt.addWidget(gb)
        lyt.addStretch()
        self.tabs.addTab(w, "Layout")

    def _on_time_slice_stack(self, direction: str) -> None:
        items = self.ts_layer_list.selectedItems()
        if len(items) < 2:
            QMessageBox.warning(self, "Time Slice Stack",
                                "Select at least 2 layers (in temporal order).")
            return
        names = [it.text() for it in items]
        all_layers = QgsProject.instance().mapLayers()
        layers = [lyr for name, lyr in all_layers.items() if lyr.name() in names]
        try:
            from ..layout.timeslice_stacker import create_time_slice_layout
            create_time_slice_layout(layers, stack_direction=direction,
                                     label_time_steps=names)
            self.iface.messageBar().pushSuccess(
                "DataCube Lab",
                "Time-slice layout created. Open Layout Manager to view.")
        except Exception as exc:
            QMessageBox.critical(self, "Layout Error", str(exc))

    def _on_voxel_config(self) -> None:
        """Open the 3D voxel layer configuration dialog."""
        try:
            from ..ui.voxel_config_dialog import VoxelConfigDialog
            dlg = VoxelConfigDialog(self)
            if dlg.exec():
                config = dlg.get_config()
                nc_path = config["nc_path"]

                # Check QGIS version to load native voxel layer
                if IS_QGIS4:
                    from qgis.core import QgsVoxelLayer, QgsProject
                    # Use netcdf provider for QgsVoxelLayer
                    layer = QgsVoxelLayer(nc_path, os.path.basename(nc_path), "netcdf")
                    if layer.isValid():
                        QgsProject.instance().addMapLayer(layer)
                        self.iface.messageBar().pushSuccess(
                            "DataCube Lab",
                            f"Voxel layer '{layer.name()}' added successfully to the project."
                        )
                    else:
                        QMessageBox.warning(
                            self, "Voxel Layer Error",
                            "Failed to load NetCDF file as a native QGIS 4 voxel layer.\n"
                            "Please check if the NetCDF file structure is valid."
                        )
                else:
                    self.iface.messageBar().pushInfo(
                        "DataCube Lab",
                        f"Voxel config saved. Voxel layers are supported in QGIS 4.x. "
                        f"(Selected variable: {config['variable']})"
                    )
        except Exception as exc:
            QMessageBox.critical(self, "Voxel Config Error", str(exc))

    def _on_copy_diagnostics(self) -> None:
        """Copy project diagnostics to clipboard."""
        from ..core.dependency_manager import check_packages, DATA_CUBE_DEPS
        avail, miss_req, miss_opt = check_packages(DATA_CUBE_DEPS)
        layers = list(QgsProject.instance().mapLayers().values())
        reg = QgsApplication.processingRegistry()
        missing = [aid for aid in REQUIRED_IDS if reg.algorithmById(aid) is None]
        txt = (
            "PlanX DataCube Lab — Project Diagnostics\n"
            "========================================\n"
            f"QGIS layers: {len(layers)}\n"
            f"Algorithms ready: {len(REQUIRED_IDS) - len(missing)}/{len(REQUIRED_IDS)}\n"
            f"Missing: {', '.join(missing) if missing else 'None'}\n"
            f"Packages OK: {', '.join(avail)}\n"
            f"Packages missing (required): {', '.join(miss_req) if miss_req else 'None'}\n"
            f"Packages missing (optional): {', '.join(miss_opt) if miss_opt else 'None'}\n"
        )
        QApplication.clipboard().setText(txt)
        self.iface.messageBar().pushSuccess("DataCube Lab", "Diagnostics copied to clipboard.")

    # ── System health / refresh ──────────────────────────────────────

    def _refresh(self) -> None:
        layers = list(QgsProject.instance().mapLayers().values())
        reg = QgsApplication.processingRegistry()
        missing = [aid for aid in REQUIRED_IDS if reg.algorithmById(aid) is None]

        if hasattr(self, "ts_layer_list"):
            self.ts_layer_list.clear()
            for layer in layers:
                self.ts_layer_list.addItem(layer.name())

        for card in self.card_widgets:
            is_ready = reg.algorithmById(card.algo_id) is not None
            card.status_lbl.setText("Ready" if is_ready else "Missing")
            card.status_lbl.setProperty("classChip", "ok" if is_ready else "warn")
            card.status_lbl.style().unpolish(card.status_lbl)
            card.status_lbl.style().polish(card.status_lbl)

        ready = len(missing) == 0
        status = "ALL READY" if ready else f"MISSING: {len(missing)}"
        self.status_chip.setText(f"System: {status}")
        if ready:
            self.status_chip.setStyleSheet(
                "color:#0f2d3a;background:#9fdfbf;border:1px solid #6fc995;border-radius:8px;padding:4px 10px;font-weight:700;"
            )
        else:
            self.status_chip.setStyleSheet(
                "color:#0f2d3a;background:#f8d37a;border:1px solid #e8bf58;border-radius:8px;padding:4px 10px;font-weight:700;"
            )

        cat_rows = []
        cat_ok_total = 0
        cat_total = 0
        for gname, ids in CATEGORY_GROUPS.items():
            found = sum(1 for aid in ids if reg.algorithmById(aid) is not None)
            total = len(ids)
            cat_ok_total += found
            cat_total += total
            pct = 100 * found / total if total else 0
            cat_rows.append((gname, found, total, pct))
        score = 100 * cat_ok_total / cat_total if cat_total else 0

        self.overview.setHtml(
            "<h2>PlanX DataCube Lab</h2>"
            "<p><b>Spatiotemporal analysis engine for QGIS.</b> Build multi-dimensional "
            "data cubes from vector/raster time series, run Emerging Hot Spot Analysis "
            "(17 pattern classes), and forecast future values with ARIMA / Random Forest.</p>"
            f"<p><b>Loaded layers:</b> {len(layers)}</p>"
            f"<p><b>System health:</b> {score:.0f}% ({cat_ok_total}/{cat_total} algorithms)</p>" +
            (f"<p><b>Missing:</b> {', '.join(missing)}</p>" if missing else "<p>All modules ready.</p>") +
            "<p><b>Get started:</b> Open <b>Modules</b>, pick an algorithm, and click <b>Run</b>.</p>"
        )

        cat_table = [
            "<table style='border-collapse:collapse;width:100%'>",
            "<tr><th style='text-align:left;border:1px solid #d7e3e6;padding:6px'>Category</th>"
            "<th style='text-align:right;border:1px solid #d7e3e6;padding:6px'>Coverage</th>"
            "<th style='text-align:right;border:1px solid #d7e3e6;padding:6px'>Score</th></tr>",
        ]
        for gname, found, total, pct in cat_rows:
            cat_table.append(
                f"<tr><td style='border:1px solid #d7e3e6;padding:6px'>{gname}</td>"
                f"<td style='text-align:right;border:1px solid #d7e3e6;padding:6px'>{found}/{total}</td>"
                f"<td style='text-align:right;border:1px solid #d7e3e6;padding:6px'>{pct:.0f}%</td></tr>"
            )
        cat_table.append("</table>")

        self.readiness.setHtml(
            "<h2>System Health</h2>"
            f"<p><b>Available algorithms:</b> {len(REQUIRED_IDS) - len(missing)}/{len(REQUIRED_IDS)}</p>"
            f"<p><b>Coverage score:</b> {score:.0f}%</p>"
            f"<p><b>Missing:</b> {', '.join(missing) if missing else 'None'}</p>"
            "<h3>Category Coverage</h3>" +
            "".join(cat_table)
        )

        self._refresh_runlog()
        self._filter_cards()
        self._populate_fc_layers()

    # ── Dependency management ────────────────────────────────────────

    def _on_check_deps(self) -> None:
        from ..core.dependency_manager import get_status_report, DATA_CUBE_DEPS
        report = get_status_report(DATA_CUBE_DEPS, "DataCube Lab Dependencies")
        self.setup_status.setPlainText(report)

    def _on_install_deps(self) -> None:
        from ..core.dependency_manager import check_packages, pip_install_command, DATA_CUBE_DEPS
        _, missing_req, missing_opt = check_packages(DATA_CUBE_DEPS)
        all_missing = missing_req + missing_opt
        if not all_missing:
            QMessageBox.information(self, "DataCube Setup", "All dependencies already installed.")
            return
        cmd = pip_install_command(all_missing)
        QApplication.clipboard().setText(cmd)
        self.setup_status.setPlainText(
            "Missing packages:\n"
            + "\n".join(f"  - {p}" for p in all_missing)
            + "\n\nThe plugin does not run pip itself. The exact install command has "
            "been copied to your clipboard — paste it into the OSGeo4W Shell "
            "(or your system terminal) and run it:\n\n"
            + cmd
            + "\n\nRestart QGIS afterwards, then click Check Dependencies again."
        )
        self.iface.messageBar().pushSuccess(
            "DataCube Lab", "pip install command copied to clipboard."
        )

    # ── Resize / keyboard ────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not hasattr(self, "cards_grid"):
            return
        desired = self._cards_column_count()
        if desired != self._current_card_columns:
            self._build_cards()
            self._refresh()

    def keyPressEvent(self, event) -> None:
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_R:
                self._refresh()
                return
            if event.key() == Qt.Key.Key_F:
                self.search.setFocus()
                return
        super().keyPressEvent(event)

    # ── Forecasting Studio ────────────────────────────────────────────

    def _build_forecasting_studio_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Left panel: parameters
        left_panel = QWidget()
        left_lyt = QVBoxLayout(left_panel)
        left_lyt.setContentsMargins(0, 0, 0, 0)
        left_lyt.setSpacing(10)

        gb = self._make_group("Forecast Settings")
        form = QFormLayout(gb)

        self.fc_layer_combo = QComboBox()
        self.fc_layer_combo.currentIndexChanged.connect(self._on_fc_layer_changed)
        form.addRow("Input Layer:", self.fc_layer_combo)

        self.fc_id_field_combo = QComboBox()
        self.fc_id_field_combo.currentIndexChanged.connect(self._on_fc_id_field_changed)
        form.addRow("Location ID Field:", self.fc_id_field_combo)

        self.fc_time_field_combo = QComboBox()
        form.addRow("Time Field:", self.fc_time_field_combo)

        self.fc_val_field_combo = QComboBox()
        form.addRow("Value Field:", self.fc_val_field_combo)

        self.fc_loc_combo = QComboBox()
        form.addRow("Target Location:", self.fc_loc_combo)

        self.fc_method_combo = QComboBox()
        self.fc_method_combo.addItem("Auto-select best", "auto")
        self.fc_method_combo.addItem("Exponential Smoothing", "exponential")
        self.fc_method_combo.addItem("ARIMA", "arima")
        self.fc_method_combo.addItem("Random Forest", "random_forest")
        form.addRow("Method:", self.fc_method_combo)

        self.fc_steps_spin = QSpinBox()
        self.fc_steps_spin.setRange(1, 50)
        self.fc_steps_spin.setValue(5)
        form.addRow("Steps Ahead:", self.fc_steps_spin)

        left_lyt.addWidget(gb)

        btn_run = QPushButton("Run Forecast & Plot")
        btn_run.clicked.connect(self._on_run_studio_forecast)
        left_lyt.addWidget(btn_run)

        self.btn_export_chart = QPushButton("Export Chart...")
        self.btn_export_chart.setObjectName("ghost")
        self.btn_export_chart.setEnabled(False)
        self.btn_export_chart.clicked.connect(self._on_export_forecast_chart)
        left_lyt.addWidget(self.btn_export_chart)

        left_lyt.addStretch()

        layout.addWidget(left_panel, 0)

        # Right panel: Plot canvas
        right_panel = QFrame()
        right_panel.setFrameShape(QFrame.Shape.StyledPanel)
        right_panel.setStyleSheet("background: #ffffff; border-radius: 8px; border: 1px solid #dcdcdc;")
        right_lyt = QVBoxLayout(right_panel)

        self.forecast_plot_lbl = QLabel("Run forecast to display preview chart.")
        self.forecast_plot_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.forecast_plot_lbl.setWordWrap(True)
        self.forecast_plot_lbl.setStyleSheet("color: #7f8c8d; font-style: italic; border: none;")
        right_lyt.addWidget(self.forecast_plot_lbl)

        layout.addWidget(right_panel, 1)

        # Populate layers
        self._populate_fc_layers()

        return tab

    def _populate_fc_layers(self) -> None:
        if not hasattr(self, "fc_layer_combo"):
            return
        self.fc_layer_combo.clear()
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if layer.type() == 0 or (hasattr(layer, 'type') and layer.type() == 0):
                self.fc_layer_combo.addItem(layer.name(), layer.id())

    def _on_fc_layer_changed(self) -> None:
        if not hasattr(self, "fc_layer_combo") or self.fc_layer_combo.currentIndex() == -1:
            return
        layer_id = self.fc_layer_combo.currentData()
        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            return

        self.fc_id_field_combo.clear()
        self.fc_time_field_combo.clear()
        self.fc_val_field_combo.clear()

        for field in layer.fields():
            name = field.name()
            self.fc_id_field_combo.addItem(name)
            self.fc_time_field_combo.addItem(name)
            self.fc_val_field_combo.addItem(name)

        # set some default selections if possible
        idx_t = self.fc_time_field_combo.findText("year")
        if idx_t == -1:
            idx_t = self.fc_time_field_combo.findText("time")
        if idx_t != -1:
            self.fc_time_field_combo.setCurrentIndex(idx_t)

    def _on_fc_id_field_changed(self) -> None:
        if not hasattr(self, "fc_id_field_combo") or self.fc_id_field_combo.currentIndex() == -1:
            return
        layer_id = self.fc_layer_combo.currentData()
        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            return
        id_field = self.fc_id_field_combo.currentText()

        self.fc_loc_combo.clear()
        # Collect unique values
        unique_vals = set()
        for feat in layer.getFeatures():
            val = feat[id_field]
            if val is not None:
                unique_vals.add(str(val))
        for val in sorted(unique_vals)[:200]:  # limit to 200 items for combobox sanity
            self.fc_loc_combo.addItem(val)

    def _on_run_studio_forecast(self) -> None:
        if self.fc_layer_combo.currentIndex() == -1:
            QMessageBox.warning(self, "No Layer", "Please select a data layer.")
            return
        layer_id = self.fc_layer_combo.currentData()
        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            QMessageBox.warning(self, "No Layer", "Selected layer not found.")
            return

        id_field = self.fc_id_field_combo.currentText()
        time_field = self.fc_time_field_combo.currentText()
        val_field = self.fc_val_field_combo.currentText()
        target_loc = self.fc_loc_combo.currentText()
        method = self.fc_method_combo.currentData()
        steps = self.fc_steps_spin.value()

        # Query features for target location
        data_points = []
        for feat in layer.getFeatures():
            if str(feat[id_field]) == target_loc:
                t = feat[time_field]
                v = feat[val_field]
                if t is not None and v is not None:
                    try:
                        data_points.append((float(t), float(v)))
                    except (ValueError, TypeError):
                        continue

        if not data_points:
            QMessageBox.warning(self, "No Data", f"No valid data points found for location: {target_loc}")
            return

        # Sort by time
        data_points.sort(key=lambda x: x[0])
        times = [pt[0] for pt in data_points]
        y_vals = [pt[1] for pt in data_points]

        # Call forecaster
        from ..core.forecasting_studio import forecast_cell_series
        try:
            forecast, method_used = forecast_cell_series(y_vals, method=method, steps_ahead=steps)
        except Exception as exc:
            QMessageBox.critical(self, "Forecast Error", f"Forecasting failed: {exc}")
            return

        # Generate plot
        try:
            import tempfile
            import matplotlib
            matplotlib.use('Agg')  # Thread-safe backend
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(6.2, 3.8), dpi=100)

            # Historical line
            ax.plot(times, y_vals, label="Historical", color="#1565c0", marker="o", linewidth=1.8, markersize=5)

            # Forecasted line
            last_t = times[-1]
            step_gap = times[1] - times[0] if len(times) > 1 else 1.0
            fc_times = [last_t + (i + 1) * step_gap for i in range(steps)]

            ax.plot([last_t] + fc_times, [y_vals[-1]] + forecast,
                    label=f"Forecast ({method_used})", color="#e94560", linestyle="--", marker="s", linewidth=1.8, markersize=5)

            # Style the plot
            ax.set_title(f"Forecasting: {target_loc}", fontsize=12, fontweight='bold', color='#2c3e50')
            ax.set_xlabel(f"Time ({time_field})", fontsize=10)
            ax.set_ylabel(val_field, fontsize=10)
            ax.grid(True, linestyle=":", alpha=0.5)
            ax.legend(frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0")

            # Remove top/right borders
            for spine in ('top', 'right'):
                ax.spines[spine].set_visible(False)

            fig.tight_layout()

            temp_dir = tempfile.gettempdir()
            img_path = os.path.join(temp_dir, "datacube_forecast_chart.png")
            fig.savefig(img_path)
            plt.close(fig)

            # Show image
            from qgis.PyQt.QtGui import QPixmap
            pixmap = QPixmap(img_path)
            self.forecast_plot_lbl.setPixmap(pixmap)
            self.forecast_plot_lbl.setStyleSheet("border: none;")
            self.btn_export_chart.setEnabled(True)
        except Exception as plot_exc:
            self.forecast_plot_lbl.setText(f"Forecast completed ({method_used}):\n{forecast}\n\nCould not render chart: {plot_exc}")
            self.forecast_plot_lbl.setStyleSheet("color: #e74c3c; font-style: normal; font-weight: 500;")
            self.btn_export_chart.setEnabled(False)

    def _on_export_forecast_chart(self) -> None:
        import shutil
        import tempfile
        from qgis.PyQt.QtWidgets import QFileDialog

        temp_dir = tempfile.gettempdir()
        src_path = os.path.join(temp_dir, "datacube_forecast_chart.png")
        if not os.path.exists(src_path):
            QMessageBox.warning(self, "No Chart", "Please generate a forecast chart first.")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Export Forecast Chart", "", "PNG Images (*.png)")
        if file_path:
            try:
                shutil.copy(src_path, file_path)
                self.iface.messageBar().pushSuccess("DataCube Lab", f"Chart exported successfully to {file_path}")
            except Exception as exc:
                QMessageBox.critical(self, "Export Error", f"Failed to export chart: {exc}")
