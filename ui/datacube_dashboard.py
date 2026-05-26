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
from qgis.PyQt.QtCore import QSettings, Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListWidget,
    QMessageBox,
    QScrollArea,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
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
        ],
    ),
    (
        "Spatiotemporal Analysis",
        "#357a5f",
        [
            ("Emerging Hot Spot Analysis (EHSA)", "planx_datacube:emerging_hot_spot_analysis",
             "Getis-Ord Gi* + Mann-Kendall → classify each location into 17 spatiotemporal hot/cold spot patterns."),
            ("Time-Series Forecast", "planx_datacube:time_series_forecast",
             "Per-cell forecasting with ARIMA / Random Forest / Exponential Smoothing (auto-fallback chain)."),
        ],
    ),
]

REQUIRED_IDS = [aid for _, _, items in ALGO_GROUPS for _, aid, _ in items]

CATEGORY_GROUPS = {
    "Cube Construction": [
        "planx_datacube:create_data_cube",
    ],
    "Spatiotemporal Analysis": [
        "planx_datacube:emerging_hot_spot_analysis",
        "planx_datacube:time_series_forecast",
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
        btn_install = QPushButton("Install Missing (pip)")
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
            ("Run EHSA (Emerging Hot Spots)", lambda: self._run_algorithm("planx_datacube:emerging_hot_spot_analysis", "EHSA")),
            ("Run Time-Series Forecast", lambda: self._run_algorithm("planx_datacube:time_series_forecast", "Forecast")),
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
        self.ts_layer_list.setSelectionMode(QListWidget.MultiSelection)
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
            self.iface.messageBar().pushSuccess("DataCube Lab",
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
                self.iface.messageBar().pushInfo(
                    "DataCube Lab",
                    f"Voxel config: {config['variable']} @ {config['nc_path']}"
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
            f"<p><b>System health:</b> {score:.0f}% ({cat_ok_total}/{cat_total} algorithms)</p>"
            + (f"<p><b>Missing:</b> {', '.join(missing)}</p>" if missing else "<p>All modules ready.</p>")
            + "<p><b>Get started:</b> Open <b>Modules</b>, pick an algorithm, and click <b>Run</b>.</p>"
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
            "<h3>Category Coverage</h3>"
            + "".join(cat_table)
        )

        self._refresh_runlog()
        self._filter_cards()

    # ── Dependency management ────────────────────────────────────────

    def _on_check_deps(self) -> None:
        from ..core.dependency_manager import check_packages, get_status_report, DATA_CUBE_DEPS
        report = get_status_report(DATA_CUBE_DEPS, "DataCube Lab Dependencies")
        self.setup_status.setPlainText(report)

    def _on_install_deps(self) -> None:
        from ..core.dependency_manager import check_packages, install_packages, DATA_CUBE_DEPS
        _, missing_req, missing_opt = check_packages(DATA_CUBE_DEPS)
        all_missing = missing_req + missing_opt
        if not all_missing:
            QMessageBox.information(self, "DataCube Setup", "All dependencies already installed.")
            return
        msg = (
            "The following packages will be installed via pip:\n\n"
            + "\n".join(f"  - {p}" for p in all_missing)
            + "\n\nThis may take several minutes (scikit-learn, statsmodels are large).\n"
            "QGIS restart recommended afterwards.\n\nContinue?"
        )
        if QMessageBox.question(self, "Install Dependencies", msg,
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.setup_status.setPlainText("Installing... this may take a few minutes.\n")
        ok, output = install_packages(all_missing)
        self.setup_status.append(output)
        if ok:
            self.setup_status.append("\nDone. Restart QGIS for changes to take effect.")
            self.iface.messageBar().pushSuccess("DataCube Lab", "Dependencies installed. Restart QGIS recommended.")
        else:
            self.setup_status.append("\nErrors occurred. See output above.")
            self.iface.messageBar().pushCritical("DataCube Lab", "Installation failed.")

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
