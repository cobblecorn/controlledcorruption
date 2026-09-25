"""Headless GUI smoke test.

Skipped automatically when PySide6 or an offscreen Qt platform is unavailable,
so it never blocks a core-only environment.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

try:  # a QApplication must be constructable (needs Qt platform libs)
    from PySide6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
except Exception as exc:  # pragma: no cover - environment dependent
    pytest.skip(f"Qt platform unavailable: {exc}", allow_module_level=True)

from controlled_corruptor.core.diff import changed_intervals  # noqa: E402
from controlled_corruptor.demo import build_demo_rom  # noqa: E402
from controlled_corruptor.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture
def window(tmp_path):
    path = tmp_path / "demo.z64"
    path.write_bytes(build_demo_rom())
    w = MainWindow()
    w.load_path(str(path))
    return w


def test_loads_and_identifies_profile(window):
    assert "Nintendo 64" in window.lbl_platform.text()
    assert "Demo ROM" in window.lbl_profile.text()
    assert "models" in window.category_checks


def test_generic_generate_matches_cli(window):
    for c, cb in window.category_checks.items():
        cb.setChecked(c == "models")
    window.edit_seed.setText("CODY-3491281")
    window.spin_density.setValue(0.01)
    window.spin_magnitude.setValue(0.35)
    window.on_generate()
    assert window.output_bytes is not None

    from controlled_corruptor.core.pipeline import corrupt
    from controlled_corruptor.core.settings import MutationSettings
    settings = MutationSettings(seed="CODY-3491281", density=0.01, magnitude=0.35)
    ref = corrupt(window.binary, settings, categories=["models"],
                  profile=window.profile)
    assert window.output_bytes == ref.output  # GUI == CLI/core


def test_hex_inspector(window):
    window._show_hex_at(0x20)
    text = window.hex_view.toPlainText()
    assert "CC DEMO ROM" in text
    assert "float32" in text


def test_semantic_mode_confined(window):
    for c, cb in window.category_checks.items():
        cb.setChecked(c == "models")
    window.sem_box.setChecked(True)
    window.combo_sem_op.setCurrentText("scale")
    window.spin_sx.setValue(0.0)
    window.spin_sy.setValue(2.0)
    window.spin_sz.setValue(0.0)
    window.on_generate()
    orig, out = window.binary.data, window.output_bytes
    changed = [i for i in range(len(orig)) if orig[i] != out[i]]
    # only the models region (0x40000..0x80000) plus the N64 checksum words
    assert changed
    assert all((0x40000 <= i < 0x80000) or (0x10 <= i < 0x18) for i in changed)
