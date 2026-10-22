"""
Test PDF Viewer & PAC Split View Navigation Controls
Verifies:
1. When loading a document, toolbar navigation is initialized (Page 1, Prev disabled, Next enabled).
2. When 'Highlight on Page' or go_to_page is invoked with a finding (e.g. Page 5),
   the page input reflects '5' and 'Prev Page' is enabled (previously remained stuck on 1 and disabled).
3. 'Prev Page' and 'Next Page' buttons update the current page and input text synchronously.
4. Entering a page number in page_input jumps to the target page and updates button states.
5. Out-of-bounds page entries clamp safely to [1, total_pages].
6. Keyboard navigation (PageUp/PageDown/Home/End) operates correctly.
"""

import os
import tempfile
import pytest
import pymupdf
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from src.pdf_inspector.ui.widgets.pdf_canvas import PDFCanvas
from src.pdf_inspector.core.models import CheckResult, CheckStatus, Severity


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def sample_multipage_pdf(tmp_path):
    """Creates a temporary 10-page PDF for viewer navigation tests."""
    doc = pymupdf.open()
    for i in range(10):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), f"This is Page {i + 1} content.", fontsize=14)
    pdf_path = str(tmp_path / "test_10pages.pdf")
    doc.save(pdf_path)
    doc.close()
    return pdf_path


def test_pdf_canvas_initial_navigation_state(qapp, sample_multipage_pdf):
    canvas = PDFCanvas()
    canvas.load_document(sample_multipage_pdf)

    assert canvas.current_page_idx == 0
    assert canvas.page_input.text() == "1"
    assert canvas.lbl_page_total.text().strip() == "/ 10"
    assert canvas.btn_prev.isEnabled() is False
    assert canvas.btn_next.isEnabled() is True


def test_pdf_canvas_highlight_on_page_enables_prev_and_updates_page_number(qapp, sample_multipage_pdf):
    canvas = PDFCanvas()
    canvas.load_document(sample_multipage_pdf)

    # Initial state on Page 1
    assert canvas.btn_prev.isEnabled() is False
    assert canvas.page_input.text() == "1"

    # Simulate user clicking [Highlight on Page] for a finding on Page 5
    finding = CheckResult(
        check_id="PDFUA-SYNTAX-001",
        name="Document is not encrypted",
        category="PDF Syntax",
        standard="PDF/UA",
        status=CheckStatus.PASS,
        severity=Severity.INFO,
        message="Document is not encrypted; accessibility content extraction is unrestricted.",
        page=5,
        bounding_box=(72.0, 72.0, 300.0, 100.0)
    )

    canvas.go_to_page(5, finding.bounding_box, finding=finding)

    # Verify that page_input updated to 5 and Prev Page is now enabled
    assert canvas.current_page_idx == 4
    assert canvas.page_input.text() == "5"
    assert canvas.btn_prev.isEnabled() is True
    assert canvas.btn_next.isEnabled() is True
    assert canvas.lbl_page_total.text().strip() == "/ 10"


def test_pdf_canvas_prev_and_next_navigation(qapp, sample_multipage_pdf):
    canvas = PDFCanvas()
    canvas.load_document(sample_multipage_pdf)

    # Jump to Page 5
    canvas.go_to_page(5)
    assert canvas.current_page_idx == 4
    assert canvas.page_input.text() == "5"

    # Click Prev Page
    canvas.prev_page()
    assert canvas.current_page_idx == 3
    assert canvas.page_input.text() == "4"
    assert canvas.btn_prev.isEnabled() is True
    assert canvas.btn_next.isEnabled() is True

    # Click Next Page
    canvas.next_page()
    assert canvas.current_page_idx == 4
    assert canvas.page_input.text() == "5"


def test_pdf_canvas_page_input_jump(qapp, sample_multipage_pdf):
    canvas = PDFCanvas()
    canvas.load_document(sample_multipage_pdf)

    # Jump via text input to Page 8
    canvas.page_input.setText("8")
    canvas._on_page_jump()

    assert canvas.current_page_idx == 7
    assert canvas.page_input.text() == "8"
    assert canvas.btn_prev.isEnabled() is True
    assert canvas.btn_next.isEnabled() is True

    # Jump to Page 1
    canvas.page_input.setText("1")
    canvas._on_page_jump()

    assert canvas.current_page_idx == 0
    assert canvas.page_input.text() == "1"
    assert canvas.btn_prev.isEnabled() is False
    assert canvas.btn_next.isEnabled() is True


def test_pdf_canvas_clamping_out_of_bounds(qapp, sample_multipage_pdf):
    canvas = PDFCanvas()
    canvas.load_document(sample_multipage_pdf)

    # Enter page beyond total (e.g. 999) -> clamp to 10
    canvas.page_input.setText("999")
    canvas._on_page_jump()

    assert canvas.current_page_idx == 9
    assert canvas.page_input.text() == "10"
    assert canvas.btn_prev.isEnabled() is True
    assert canvas.btn_next.isEnabled() is False

    # Enter page 0 -> clamp to 1
    canvas.page_input.setText("0")
    canvas._on_page_jump()

    assert canvas.current_page_idx == 0
    assert canvas.page_input.text() == "1"
    assert canvas.btn_prev.isEnabled() is False
    assert canvas.btn_next.isEnabled() is True


def test_pdf_canvas_keyboard_shortcuts(qapp, sample_multipage_pdf):
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent

    canvas = PDFCanvas()
    canvas.load_document(sample_multipage_pdf)

    # PageDown advances to Page 2
    event_down = QKeyEvent(QEvent.KeyPress, Qt.Key_PageDown, Qt.NoModifier)
    canvas.keyPressEvent(event_down)
    assert canvas.current_page_idx == 1
    assert canvas.page_input.text() == "2"

    # End jumps to last page (10)
    event_end = QKeyEvent(QEvent.KeyPress, Qt.Key_End, Qt.NoModifier)
    canvas.keyPressEvent(event_end)
    assert canvas.current_page_idx == 9
    assert canvas.page_input.text() == "10"

    # PageUp goes to Page 9
    event_up = QKeyEvent(QEvent.KeyPress, Qt.Key_PageUp, Qt.NoModifier)
    canvas.keyPressEvent(event_up)
    assert canvas.current_page_idx == 8
    assert canvas.page_input.text() == "9"

    # Home jumps to first page (1)
    event_home = QKeyEvent(QEvent.KeyPress, Qt.Key_Home, Qt.NoModifier)
    canvas.keyPressEvent(event_home)
    assert canvas.current_page_idx == 0
    assert canvas.page_input.text() == "1"

