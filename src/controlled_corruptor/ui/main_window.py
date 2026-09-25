"""Main application window.

Deliberately functional rather than elaborate. Every action routes through the
same core APIs the CLI uses (:mod:`controlled_corruptor.core.pipeline`), so the
GUI can never drift from the command line behaviour.
"""

from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter, QVBoxLayout,
    QWidget,
)

from ..core import binary as binmod
from ..core import hexview, semantic
from ..core.diff import changed_intervals
from ..core.pipeline import corrupt as run_corrupt, gather_regions
from ..core.project import CorruptionProject
from ..core.regions import subtract_intervals
from ..core.settings import ALL_TYPES, DEFAULT_TYPES, MutationSettings
from ..profiles import ProfileLibrary
from .. import platforms
from .rommap import RomMapWidget, category_color


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Controlled ROM Corruptor")
        self.resize(1024, 640)

        self.library = ProfileLibrary()
        self.binary: Optional[binmod.BinaryFile] = None
        self.platform = None
        self.profile = None
        self.targets: List = []
        self.protected: List = []
        self.output_bytes: Optional[bytes] = None
        self.category_checks = {}

        self._build_ui()
        self._build_menu()
        self._set_enabled(False)

    @staticmethod
    def _axis_spin(default: float) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setDecimals(2)
        s.setRange(0.0, 8.0)
        s.setSingleStep(0.1)
        s.setValue(default)
        return s

    # -- construction -------------------------------------------------------
    def _build_ui(self):
        central = QSplitter(Qt.Horizontal)

        # ---- left control panel ----
        left = QWidget()
        left_layout = QVBoxLayout(left)

        info_box = QGroupBox("File")
        info_form = QFormLayout(info_box)
        self.lbl_name = QLabel("-")
        self.lbl_size = QLabel("-")
        self.lbl_sha = QLabel("-")
        self.lbl_sha.setWordWrap(True)
        self.lbl_platform = QLabel("-")
        self.lbl_profile = QLabel("-")
        info_form.addRow("Name:", self.lbl_name)
        info_form.addRow("Size:", self.lbl_size)
        info_form.addRow("SHA-256:", self.lbl_sha)
        info_form.addRow("Platform:", self.lbl_platform)
        info_form.addRow("Profile:", self.lbl_profile)
        left_layout.addWidget(info_box)

        self.cat_box = QGroupBox("Corrupt categories")
        self.cat_layout = QVBoxLayout(self.cat_box)
        left_layout.addWidget(self.cat_box)

        settings_box = QGroupBox("Settings")
        settings_form = QFormLayout(settings_box)
        self.spin_density = QDoubleSpinBox()
        self.spin_density.setDecimals(5)
        self.spin_density.setRange(0.0, 1.0)
        self.spin_density.setSingleStep(0.001)
        self.spin_density.setValue(0.002)
        self.spin_magnitude = QDoubleSpinBox()
        self.spin_magnitude.setDecimals(3)
        self.spin_magnitude.setRange(0.0, 1.0)
        self.spin_magnitude.setSingleStep(0.05)
        self.spin_magnitude.setValue(0.35)
        self.edit_seed = QLineEdit("CODY-3491281")
        self.combo_platform = QComboBox()
        self.combo_platform.addItem("(auto)")
        for pid in platforms.available():
            self.combo_platform.addItem(pid)
        self.chk_repair = QCheckBox("Repair platform checksum")
        self.chk_repair.setChecked(True)
        settings_form.addRow("Density:", self.spin_density)
        settings_form.addRow("Magnitude:", self.spin_magnitude)
        settings_form.addRow("Seed:", self.edit_seed)
        settings_form.addRow("Platform:", self.combo_platform)
        settings_form.addRow("", self.chk_repair)
        left_layout.addWidget(settings_box)

        types_box = QGroupBox("Mutation types")
        types_layout = QVBoxLayout(types_box)
        self.type_checks = {}
        for t in ALL_TYPES:
            cb = QCheckBox(t)
            cb.setChecked(t in DEFAULT_TYPES)
            self.type_checks[t] = cb
            types_layout.addWidget(cb)
        left_layout.addWidget(types_box)

        # Semantic (Level-3) model corruption controls.
        self.sem_box = QGroupBox("Semantic model mode (float regions)")
        self.sem_box.setCheckable(True)
        self.sem_box.setChecked(False)
        sem_form = QFormLayout(self.sem_box)
        self.combo_sem_op = QComboBox()
        for op in semantic.OPS:
            self.combo_sem_op.addItem(op)
        self.spin_stride = QSpinBox()
        self.spin_stride.setRange(4, 256)
        self.spin_stride.setValue(12)
        self.spin_sx = self._axis_spin(0.4)
        self.spin_sy = self._axis_spin(0.4)
        self.spin_sz = self._axis_spin(0.4)
        sem_form.addRow("Op:", self.combo_sem_op)
        sem_form.addRow("Stride:", self.spin_stride)
        sem_form.addRow("X strength:", self.spin_sx)
        sem_form.addRow("Y strength:", self.spin_sy)
        sem_form.addRow("Z strength:", self.spin_sz)
        left_layout.addWidget(self.sem_box)

        btn_row = QHBoxLayout()
        self.btn_generate = QPushButton("Generate")
        self.btn_generate.clicked.connect(self.on_generate)
        self.btn_save = QPushButton("Save Corrupted As...")
        self.btn_save.clicked.connect(self.on_save_output)
        btn_row.addWidget(self.btn_generate)
        btn_row.addWidget(self.btn_save)
        left_layout.addLayout(btn_row)
        left_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left)
        scroll.setMinimumWidth(340)

        # ---- right side: ROM map + history ----
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("ROM map (regions tinted by category; "
                                      "white = changed bytes)"))
        self.rom_map = RomMapWidget()
        self.rom_map.offset_hovered.connect(self._on_hover)
        self.rom_map.offset_clicked.connect(self._show_hex_at)
        right_layout.addWidget(self.rom_map)
        self.lbl_hover = QLabel("offset: - (click the map to inspect bytes)")
        right_layout.addWidget(self.lbl_hover)

        right_layout.addWidget(QLabel("Mutation history"))
        self.history = QListWidget()
        right_layout.addWidget(self.history, 1)
        self.lbl_summary = QLabel("-")
        right_layout.addWidget(self.lbl_summary)

        right_layout.addWidget(QLabel("Hex / value inspector (click the ROM map)"))
        self.hex_view = QPlainTextEdit()
        self.hex_view.setReadOnly(True)
        self.hex_view.setFont(QFont("monospace"))
        self.hex_view.setMaximumHeight(180)
        right_layout.addWidget(self.hex_view)

        central.addWidget(scroll)
        central.addWidget(right)
        central.setStretchFactor(1, 1)
        self.setCentralWidget(central)

    def _build_menu(self):
        m = self.menuBar()
        file_menu = m.addMenu("&File")
        file_menu.addAction("Open ROM...", self.on_open)
        file_menu.addAction("Save Corrupted As...", self.on_save_output)
        file_menu.addSeparator()
        file_menu.addAction("Save Project...", self.on_save_project)
        file_menu.addAction("Load Project...", self.on_load_project)
        file_menu.addSeparator()
        file_menu.addAction("Quit", self.close)

        prof_menu = m.addMenu("&Profiles")
        prof_menu.addAction("Reload profiles", self._reload_profiles)

        help_menu = m.addMenu("&Help")
        help_menu.addAction("About", self._about)

    # -- state --------------------------------------------------------------
    def _set_enabled(self, on: bool):
        self.btn_generate.setEnabled(on)
        self.btn_save.setEnabled(on and self.output_bytes is not None)

    def _reload_profiles(self):
        self.library.reload()
        if self.binary:
            self._refresh_for_binary()

    def _about(self):
        QMessageBox.information(self, "About",
                                "Controlled ROM Corruptor\n\n"
                                "Deterministic, region-aware ROM/binary corruption.\n"
                                "GUI and CLI share the same core engine.")

    # -- actions ------------------------------------------------------------
    def on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open ROM / binary", "",
            "ROMs/binaries (*.z64 *.n64 *.v64 *.nds *.gba *.iso *.bin *.rom *.dat);;All files (*)")
        if not path:
            return
        self.load_path(path)

    def load_path(self, path: str):
        self.binary = binmod.load_binary(path)
        self.output_bytes = None
        self._refresh_for_binary()

    def _refresh_for_binary(self):
        bf = self.binary
        self.platform = platforms.detect(bf.data)
        self.profile = self.library.identify(bf.sha256)
        self.targets, self.protected = gather_regions(bf, self.platform, self.profile)

        self.lbl_name.setText(bf.filename or "-")
        self.lbl_size.setText(f"{bf.size:,} bytes (0x{bf.size:08X})")
        self.lbl_sha.setText(bf.sha256)
        self.lbl_platform.setText(f"{self.platform.name} ({self.platform.id})")
        self.lbl_profile.setText(self.profile.name if self.profile else "(none matched)")

        # Category checkboxes.
        for i in reversed(range(self.cat_layout.count())):
            w = self.cat_layout.itemAt(i).widget()
            if w:
                w.setParent(None)
        self.category_checks = {}
        cats = self.profile.categories() if self.profile else []
        if not cats:
            cats = sorted({r.category for r in self.targets}) or ["(whole file)"]
        for c in cats:
            cb = QCheckBox(c)
            cb.setChecked(c in ("models", "animations") or len(cats) == 1)
            self.category_checks[c] = cb
            self.cat_layout.addWidget(cb)

        self.rom_map.set_file(bf.size, self.targets, self.protected)
        self.history.clear()
        self.lbl_summary.setText("-")
        self._set_enabled(True)

    def _selected_categories(self) -> Optional[List[str]]:
        cats = [c for c, cb in self.category_checks.items()
                if cb.isChecked() and c != "(whole file)"]
        return cats or None

    def _build_settings(self) -> MutationSettings:
        types = [t for t, cb in self.type_checks.items() if cb.isChecked()] or list(DEFAULT_TYPES)
        return MutationSettings(
            seed=self.edit_seed.text().strip() or "0",
            density=self.spin_density.value(),
            magnitude=self.spin_magnitude.value(),
            types=types,
        )

    def _selected_platform(self):
        pid = self.combo_platform.currentText()
        if pid == "(auto)":
            return None
        return platforms.get(pid)

    def on_generate(self):
        if not self.binary:
            return
        try:
            if self.sem_box.isChecked():
                output, log = self._run_semantic()
                summary = log.summary() if log else {"applied": 0, "skipped": 0}
                records = log.records if log else []
                mutable = None
                repaired = False
            else:
                settings = self._build_settings()
                result = run_corrupt(
                    self.binary, settings,
                    categories=self._selected_categories(),
                    profile=self.profile,
                    platform=self._selected_platform(),
                    repair_checksum=self.chk_repair.isChecked(),
                )
                output = result.output
                summary = result.engine_result.log.summary()
                records = result.engine_result.log.records
                mutable = result.engine_result.mutable_bytes
                repaired = result.checksum_repaired
        except Exception as exc:  # pragma: no cover - GUI guard
            QMessageBox.critical(self, "Corruption failed", str(exc))
            return

        self.output_bytes = output
        changed = changed_intervals(self.binary.data, output, merge_gap=64)
        self.rom_map.set_changed(changed)

        self.history.clear()
        for rec in records[:2000]:
            self.history.addItem(rec.describe())
        extra = f"mutable {mutable:,} bytes" if mutable is not None else "semantic mode"
        self.lbl_summary.setText(
            f"{summary['applied']} applied, {summary.get('skipped', 0)} skipped; "
            f"{extra}" + ("; checksum repaired" if repaired else ""))
        self._set_enabled(True)

    def on_save_output(self):
        if not self.output_bytes:
            QMessageBox.information(self, "Nothing to save", "Generate a corruption first.")
            return
        default = binmod.suggest_output_name(self.binary.path, self.edit_seed.text().strip())
        path, _ = QFileDialog.getSaveFileName(self, "Save corrupted ROM",
                                              os.path.basename(default))
        if not path:
            return
        binmod.write_output(path, self.output_bytes, overwrite=True)
        QMessageBox.information(self, "Saved", f"Wrote {path}")

    def on_save_project(self):
        if not self.binary:
            return
        settings = self._build_settings()
        project = CorruptionProject.single(
            self.binary, settings,
            categories=self._selected_categories(),
            profile_id=(self.profile.id if self.profile else None),
            platform=(self.platform.id if self.platform else None),
            repair_checksum=self.chk_repair.isChecked(),
        )
        path, _ = QFileDialog.getSaveFileName(self, "Save project", "corruption.ccproject",
                                              "Corruption project (*.ccproject)")
        if not path:
            return
        project.save(path)
        QMessageBox.information(self, "Saved", f"Wrote {path}")

    def on_load_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load project", "",
                                              "Corruption project (*.ccproject)")
        if not path:
            return
        project = CorruptionProject.load(path)
        if not self.binary:
            QMessageBox.information(self, "Open a ROM first",
                                   "Load the source ROM before applying a project.")
            return
        ok, msg = project.verify_source(self.binary)
        if not ok and QMessageBox.question(self, "Hash mismatch",
                                           msg + "\n\nApply anyway?") != QMessageBox.Yes:
            return
        layer = project.layers[0] if project.layers else None
        if layer:
            self.spin_density.setValue(layer.settings.density)
            self.spin_magnitude.setValue(layer.settings.magnitude)
            self.edit_seed.setText(str(layer.settings.seed))
            for c, cb in self.category_checks.items():
                cb.setChecked(bool(layer.categories) and c in layer.categories)
        self.on_generate()

    def _show_hex_at(self, offset: int):
        if not self.binary:
            return
        start = max(0, offset - (offset % 16) - 32)
        dump = hexview.hex_dump(self.binary.data, start, 128, width=16)
        interp = hexview.format_interpret(self.binary.data, offset,
                                          endian=self.platform.endianness(self.binary.data)
                                          if self.platform else "little")
        self.hex_view.setPlainText(dump + "\n\n" + interp)

    def _run_semantic(self):
        """Apply semantic model corruption to selected float regions."""
        cats = self._selected_categories()
        regions = [r for r in self.targets
                   if r.mutable and (cats is None or r.matches(cats))]
        protected = [r.interval for r in self.protected]
        endian = self.platform.endianness(self.binary.data) if self.platform else "little"
        layout = semantic.build_layout(stride=self.spin_stride.value(), endian=endian)
        settings = semantic.SemanticSettings(
            op=self.combo_sem_op.currentText(),
            strengths=[self.spin_sx.value(), self.spin_sy.value(), self.spin_sz.value()],
            seed=self.edit_seed.text().strip() or "0",
        )
        out = bytearray(self.binary.data)
        log = None
        for r in regions:
            for s, e in subtract_intervals([r.interval], protected):
                log = semantic.corrupt_region(out, s, e, layout, settings,
                                              region_name=r.name, log=log)
        output = bytes(out)
        if self.chk_repair.isChecked() and self.platform:
            output = self.platform.repair_checksum(output)
        return output, log

    def _on_hover(self, offset: int):
        region = None
        for r in self.targets + self.protected:
            if r.start <= offset < r.end:
                region = r
                break
        label = f"offset: 0x{offset:08X}"
        if region:
            label += f"  [{region.name} / {region.category}]"
        self.lbl_hover.setText(label)
