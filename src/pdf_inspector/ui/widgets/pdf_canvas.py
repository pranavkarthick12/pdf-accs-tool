"""
Interactive PDF Canvas & Viewer Widget
Integrates standard scrollable document inspection with a high-precision PAC Visual Issue Locator:
- PAC Split Callout View: Page overview with green projection lines and magnified red-framed issue crop
- Full Document View: High-fidelity scrollable page viewer with glowing bounding box overlays
"""

from typing import Optional, Tuple, List, Any, Dict
import pymupdf

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QPushButton, QComboBox, QLineEdit, QToolBar, QFrame, QSizePolicy,
    QStackedWidget, QButtonGroup
)
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QBrush, QFont, QIntValidator

from ...core.models import CheckResult, CheckStatus
from ...core.visual_locator import VisualLocatorResolver, ResolvedLocation
from .pac_visual_locator import PACVisualLocatorWidget


class PageDisplayWidget(QLabel):
    """Draws the rendered page pixmap and any active bounding box highlight overlays."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.current_pixmap: Optional[QPixmap] = None
        self.highlight_rects: List[Tuple[float, float, float, float]] = []
        self.active_bbox: Optional[Tuple[float, float, float, float]] = None
        self.page_rect: pymupdf.Rect = pymupdf.Rect(0, 0, 612, 792)
        self.scale_factor: float = 1.0
        self.rotation: int = 0
        self.status_message: Optional[str] = None

    def set_page_image(
        self,
        pixmap: QPixmap,
        page_rect: pymupdf.Rect,
        scale: float,
        rotation: int = 0,
        highlight_rects: Optional[List[Tuple[float, float, float, float]]] = None,
        status_message: Optional[str] = None
    ):
        self.current_pixmap = pixmap
        self.page_rect = page_rect
        self.scale_factor = scale
        self.rotation = rotation
        self.highlight_rects = highlight_rects or []
        self.active_bbox = self.highlight_rects[0] if self.highlight_rects else None
        self.status_message = status_message
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.current_pixmap:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Center pixmap
        px_x = (self.width() - self.current_pixmap.width()) // 2
        px_y = (self.height() - self.current_pixmap.height()) // 2
        painter.drawPixmap(px_x, px_y, self.current_pixmap)

        # Mathematical coordinate transformation from PyMuPDF page.rect to rendered pixmap pixel space
        mat = pymupdf.Matrix(self.scale_factor, self.scale_factor).prerotate(self.rotation)
        bounds = self.page_rect * mat

        # Draw highlight overlays if rectangles are provided
        if self.highlight_rects and self.scale_factor > 0:
            for b in self.highlight_rects:
                x0, y0, x1, y1 = b
                r_cand = pymupdf.Rect(x0, y0, x1, y1)
                tr = r_cand * mat
                pix_r = pymupdf.Rect(
                    tr.x0 - bounds.x0,
                    tr.y0 - bounds.y0,
                    tr.x1 - bounds.x0,
                    tr.y1 - bounds.y0
                )

                sx0 = px_x + pix_r.x0
                sy0 = px_y + pix_r.y0
                sw = max(8.0, pix_r.width)
                sh = max(8.0, pix_r.height)

                rect = QRectF(sx0, sy0, sw, sh)

                # Draw glowing highlight fill and border
                fill_color = QColor(239, 68, 68, 55)  # Red translucent
                border_color = QColor(220, 38, 38, 220)  # Solid red

                painter.setBrush(QBrush(fill_color))
                painter.setPen(QPen(border_color, 2.5, Qt.SolidLine))
                painter.drawRoundedRect(rect, 4, 4)

                # Corner pins
                pin_pen = QPen(QColor(185, 28, 28), 3)
                painter.setPen(pin_pen)
                pin_len = min(12.0, sw / 3, sh / 3)
                # Top-left
                painter.drawLine(sx0, sy0, sx0 + pin_len, sy0)
                painter.drawLine(sx0, sy0, sx0, sy0 + pin_len)
                # Top-right
                painter.drawLine(sx0 + sw, sy0, sx0 + sw - pin_len, sy0)
                painter.drawLine(sx0 + sw, sy0, sx0 + sw, sy0 + pin_len)
                # Bottom-left
                painter.drawLine(sx0, sy0 + sh, sx0 + pin_len, sy0 + sh)
                painter.drawLine(sx0, sy0 + sh, sx0, sy0 + sh - pin_len)
                # Bottom-right
                painter.drawLine(sx0 + sw, sy0 + sh, sx0 + sw - pin_len, sy0 + sh)
                painter.drawLine(sx0 + sw, sy0 + sh, sx0 + sw, sy0 + sh - pin_len)

        # Status badge if document-level or non-spatial finding
        elif self.status_message:
            badge_w = min(460, max(240, self.current_pixmap.width() - 40))
            badge_rect = QRectF(px_x + 20, px_y + 20, badge_w, 46)
            painter.setBrush(QBrush(QColor(241, 245, 249, 240)))
            painter.setPen(QPen(QColor(148, 163, 184), 1.2))
            painter.drawRoundedRect(badge_rect, 6, 6)

            painter.setPen(QColor(30, 41, 59))
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            painter.drawText(
                QRectF(badge_rect.left() + 12, badge_rect.top() + 6, badge_rect.width() - 24, 18),
                Qt.AlignLeft,
                "ℹ Document-Level / Non-Spatial Finding"
            )
            painter.setFont(QFont("Segoe UI", 8))
            painter.setPen(QColor(71, 85, 105))
            painter.drawText(
                QRectF(badge_rect.left() + 12, badge_rect.top() + 24, badge_rect.width() - 24, 18),
                Qt.AlignLeft,
                self.status_message[:70]
            )

        painter.end()


class PDFCanvas(QWidget):
    """Complete viewer widget containing PAC Visual Locator and Standard Page Canvas."""

    page_changed = Signal(int)
    finding_navigation_requested = Signal(int)  # offset -1 or +1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc: Optional[pymupdf.Document] = None
        self.doc_model: Optional[Any] = None
        self.current_filepath: Optional[str] = None
        self.current_page_idx: int = 0  # 0-indexed
        self.zoom: float = 1.25
        self.rotation: int = 0
        self.highlight_bbox: Optional[Tuple[float, float, float, float]] = None
        self.highlight_rects: List[Tuple[float, float, float, float]] = []
        self.highlight_message: Optional[str] = None
        self.current_finding: Optional[CheckResult] = None

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Main Viewer Toolbar
        self.toolbar = QToolBar()
        self.toolbar.setStyleSheet("background: #ffffff; border-bottom: 1px solid #e2e8f0; padding: 4px 8px;")

        # View Mode Toggle: [ 📑 PAC Split View ] / [ 📄 Document View ]
        self.btn_mode_pac = QPushButton("📑 PAC Split View")
        self.btn_mode_pac.setCheckable(True)
        self.btn_mode_pac.setChecked(True)
        self.btn_mode_pac.setStyleSheet("font-weight: 600; padding: 4px 10px;")
        self.toolbar.addWidget(self.btn_mode_pac)

        self.btn_mode_doc = QPushButton("📄 Document View")
        self.btn_mode_doc.setCheckable(True)
        self.btn_mode_doc.setStyleSheet("font-weight: 600; padding: 4px 10px;")
        self.toolbar.addWidget(self.btn_mode_doc)

        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.btn_mode_pac)
        self.mode_group.addButton(self.btn_mode_doc)
        self.btn_mode_pac.clicked.connect(lambda: self.set_view_mode("pac"))
        self.btn_mode_doc.clicked.connect(lambda: self.set_view_mode("doc"))

        self.toolbar.addSeparator()

        # Navigation controls with modern UI/UX styling
        nav_btn_style = """
            QPushButton {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                border-color: #94a3b8;
            }
            QPushButton:pressed {
                background-color: #e2e8f0;
            }
            QPushButton:disabled {
                background-color: #f8fafc;
                color: #94a3b8;
                border-color: #e2e8f0;
            }
        """

        self.btn_prev = QPushButton("◀ Prev Page")
        self.btn_prev.setStyleSheet(nav_btn_style)
        self.btn_prev.setToolTip("Previous Page (Left Arrow / Page Up)")
        self.btn_prev.setEnabled(False)
        self.btn_prev.clicked.connect(self.prev_page)
        self.toolbar.addWidget(self.btn_prev)

        self.page_input = QLineEdit("1")
        self.page_input.setFixedWidth(48)
        self.page_input.setFixedHeight(26)
        self.page_input.setAlignment(Qt.AlignCenter)
        self.page_input.setValidator(QIntValidator(1, 99999, self))
        self.page_input.setStyleSheet("""
            QLineEdit {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
                padding: 1px 4px;
            }
            QLineEdit:focus {
                border: 1.5px solid #2563eb;
            }
        """)
        self.page_input.setToolTip("Jump to page number (press Enter)")
        self.page_input.editingFinished.connect(self._on_page_jump)
        self.toolbar.addWidget(self.page_input)

        self.lbl_page_total = QLabel(" / 1 ")
        self.lbl_page_total.setStyleSheet("color: #64748b; font-weight: 600; font-size: 11px; padding: 0 4px;")
        self.toolbar.addWidget(self.lbl_page_total)

        self.btn_next = QPushButton("Next Page ▶")
        self.btn_next.setStyleSheet(nav_btn_style)
        self.btn_next.setToolTip("Next Page (Right Arrow / Page Down)")
        self.btn_next.setEnabled(False)
        self.btn_next.clicked.connect(self.next_page)
        self.toolbar.addWidget(self.btn_next)

        self.toolbar.addSeparator()

        # Zoom Controls
        self.btn_zoom_out = QPushButton("🔍 -")
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        self.toolbar.addWidget(self.btn_zoom_out)

        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["50%", "75%", "100%", "125%", "150%", "200%", "Fit Width", "Fit Page"])
        self.zoom_combo.setCurrentText("125%")
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_combo_changed)
        self.toolbar.addWidget(self.zoom_combo)

        self.btn_zoom_in = QPushButton("🔍 +")
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        self.toolbar.addWidget(self.btn_zoom_in)

        self.toolbar.addSeparator()

        # Rotate
        self.btn_rotate = QPushButton("🔄 Rotate")
        self.btn_rotate.clicked.connect(self.rotate_clockwise)
        self.toolbar.addWidget(self.btn_rotate)

        # Clear Highlight
        self.btn_clear_hl = QPushButton("✖ Clear Highlight")
        self.btn_clear_hl.clicked.connect(self.clear_highlight)
        self.toolbar.addWidget(self.btn_clear_hl)

        layout.addWidget(self.toolbar)

        # 2. Stacked Views (0: PAC Visual Locator, 1: Standard Scrollable Canvas)
        self.stack = QStackedWidget()

        # View 0: PAC Visual Locator
        self.pac_locator = PACVisualLocatorWidget()
        self.pac_locator.full_view_requested.connect(lambda: self.set_view_mode("doc"))
        self.pac_locator.finding_navigation_requested.connect(self.finding_navigation_requested.emit)
        self.pac_locator.canvas.zoom_changed.connect(self._on_pac_zoom_changed)
        self.stack.addWidget(self.pac_locator)

        # View 1: Standard Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setStyleSheet("background-color: #525659; border: none;")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignCenter)

        self.page_display = PageDisplayWidget()
        self.scroll_area.setWidget(self.page_display)
        self.stack.addWidget(self.scroll_area)

        layout.addWidget(self.stack, 1)

    def set_view_mode(self, mode: str):
        """Switches between 'pac' and 'doc' view modes."""
        if mode == "pac":
            self.btn_mode_pac.setChecked(True)
            self.stack.setCurrentIndex(0)
            if self.current_finding and (self.current_finding.page is None or self.current_finding.page == self.current_page_idx + 1):
                self.pac_locator.load_finding(
                    self.doc,
                    self.current_finding,
                    page_num=self.current_page_idx + 1,
                    bbox=self.highlight_bbox,
                    doc_model=self.doc_model,
                    rects=self.highlight_rects
                )
            elif self.doc:
                dummy_finding = CheckResult(
                    check_id="NAV",
                    name=f"Page {self.current_page_idx + 1} Inspection",
                    category="Visual Inspection",
                    standard="PDF/UA",
                    status=CheckStatus.PASS,
                    severity="INFO",
                    message=f"Page {self.current_page_idx + 1} of {len(self.doc)}",
                    page=self.current_page_idx + 1,
                    bounding_box=self.highlight_bbox
                )
                self.pac_locator.load_finding(
                    self.doc,
                    dummy_finding,
                    page_num=self.current_page_idx + 1,
                    bbox=self.highlight_bbox,
                    doc_model=self.doc_model,
                    rects=self.highlight_rects
                )
        else:
            self.btn_mode_doc.setChecked(True)
            self.stack.setCurrentIndex(1)
            self.render_current_page()
        self._update_nav_toolbar()

    def _update_nav_toolbar(self):
        """Synchronizes page input, total count label, and prev/next button enabled states."""
        if not self.doc or len(self.doc) == 0:
            self.page_input.blockSignals(True)
            self.page_input.setText("1")
            self.page_input.blockSignals(False)
            self.lbl_page_total.setText(" / 1 ")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            return

        total_pages = len(self.doc)
        curr_page = self.current_page_idx + 1
        self.page_input.blockSignals(True)
        self.page_input.setText(str(curr_page))
        self.page_input.blockSignals(False)
        self.lbl_page_total.setText(f" / {total_pages} ")
        self.btn_prev.setEnabled(self.current_page_idx > 0)
        self.btn_next.setEnabled(self.current_page_idx < total_pages - 1)
        self.page_changed.emit(curr_page)

    def load_document(self, filepath: str, password: Optional[str] = None, doc_model: Optional[Any] = None):
        """Loads a PDF document into the viewer."""
        if self.doc:
            try:
                self.doc.close()
            except Exception:
                pass

        self.current_filepath = filepath
        self.doc_model = doc_model
        self.doc = pymupdf.open(filepath)
        if self.doc.needs_pass and password:
            self.doc.authenticate(password)

        self.current_page_idx = 0
        self.rotation = 0
        self.highlight_bbox = None
        self.highlight_rects = []
        self.highlight_message = None
        self.current_finding = None
        self._update_nav_toolbar()
        self.render_current_page()

    def render_current_page(self):
        """Renders the current page at the current zoom and rotation."""
        if not self.doc or len(self.doc) == 0:
            return

        page = self.doc[self.current_page_idx]
        mat = pymupdf.Matrix(self.zoom, self.zoom).prerotate(self.rotation)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        # Convert PyMuPDF pixmap to QImage
        img_format = QImage.Format_RGB888
        qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, img_format)
        pixmap = QPixmap.fromImage(qimg)

        self.page_display.set_page_image(
            pixmap=pixmap,
            page_rect=page.rect,
            scale=self.zoom,
            rotation=self.rotation,
            highlight_rects=self.highlight_rects,
            status_message=self.highlight_message
        )

        self._update_nav_toolbar()

    def go_to_page(
        self,
        page_num_1based: int,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        finding: Optional[CheckResult] = None,
        doc_model: Optional[Any] = None
    ):
        target_idx = max(0, page_num_1based - 1)
        if self.doc and len(self.doc) > 0:
            target_idx = min(len(self.doc) - 1, target_idx)

        self.current_page_idx = target_idx
        if finding is not None:
            self.current_finding = finding

        if doc_model:
            self.doc_model = doc_model

        # Synchronize toolbar navigation controls immediately
        self._update_nav_toolbar()

        # Set default/initial highlight state before checking doc (supports headless/mock testing)
        if bbox and len(bbox) == 4:
            self.highlight_bbox = bbox
            self.highlight_rects = [bbox]
            self.highlight_message = None
        elif finding is not None and finding.bounding_box and len(finding.bounding_box) == 4:
            self.highlight_bbox = finding.bounding_box
            self.highlight_rects = [finding.bounding_box]
            self.highlight_message = None
        else:
            self.highlight_bbox = None
            self.highlight_rects = []
            self.highlight_message = None

        if not self.doc or len(self.doc) == 0:
            return

        # Central location resolution conforming to data contract
        if finding is not None:
            if bbox and len(bbox) == 4:
                self.highlight_bbox = bbox
                self.highlight_rects = [bbox]
                self.highlight_message = None
            else:
                resolved = VisualLocatorResolver.resolve_location(
                    self.doc, target_idx + 1, finding, self.doc_model
                )
                self.highlight_rects = resolved.rectangles
                self.highlight_bbox = resolved.primary_bbox
                self.highlight_message = resolved.message if not resolved.is_valid else None
        elif bbox and len(bbox) == 4:
            self.highlight_bbox = bbox
            self.highlight_rects = [bbox]
            self.highlight_message = None

        # Display in active view mode
        if finding:
            self.set_view_mode("pac")
            self.pac_locator.load_finding(
                self.doc,
                finding,
                page_num=target_idx + 1,
                bbox=self.highlight_bbox,
                doc_model=self.doc_model,
                rects=self.highlight_rects
            )
        else:
            if self.stack.currentIndex() == 0:
                # PAC Split View is active
                if self.current_finding and (self.current_finding.page is None or self.current_finding.page == target_idx + 1):
                    self.pac_locator.load_finding(
                        self.doc,
                        self.current_finding,
                        page_num=target_idx + 1,
                        bbox=self.highlight_bbox,
                        doc_model=self.doc_model,
                        rects=self.highlight_rects
                    )
                else:
                    dummy_finding = CheckResult(
                        check_id="NAV",
                        name=f"Page {target_idx + 1} Inspection",
                        category="Visual Inspection",
                        standard="PDF/UA",
                        status=CheckStatus.PASS,
                        severity="INFO",
                        message=f"Page {target_idx + 1} of {len(self.doc)}",
                        page=target_idx + 1,
                        bounding_box=self.highlight_bbox
                    )
                    self.pac_locator.load_finding(
                        self.doc,
                        dummy_finding,
                        page_num=target_idx + 1,
                        bbox=self.highlight_bbox,
                        doc_model=self.doc_model,
                        rects=self.highlight_rects
                    )
            else:
                self.render_current_page()

        # Scroll to highlighted element if in document view
        if self.highlight_rects and self.stack.currentIndex() == 1:
            page = self.doc[self.current_page_idx]
            mat = pymupdf.Matrix(self.zoom, self.zoom).prerotate(self.rotation)
            bounds = page.rect * mat
            tr = pymupdf.Rect(self.highlight_rects[0]) * mat
            pix_r = pymupdf.Rect(tr.x0 - bounds.x0, tr.y0 - bounds.y0, tr.x1 - bounds.x0, tr.y1 - bounds.y0)
            y_center = int((pix_r.y0 + pix_r.y1) / 2)
            self.scroll_area.verticalScrollBar().setValue(max(0, y_center - 150))

    def show_finding_visual_locator(self, finding: CheckResult, doc_model: Optional[Any] = None):
        """Directly activates PAC visual locator for a given CheckResult."""
        if doc_model:
            self.doc_model = doc_model
        target_page = finding.page or 1
        self.go_to_page(target_page, finding.bounding_box, finding=finding, doc_model=self.doc_model)

    def next_page(self):
        if self.doc and self.current_page_idx < len(self.doc) - 1:
            self.go_to_page(self.current_page_idx + 2)

    def prev_page(self):
        if self.doc and self.current_page_idx > 0:
            self.go_to_page(self.current_page_idx)

    def _on_page_jump(self):
        if not self.doc or len(self.doc) == 0:
            return
        text = self.page_input.text().strip()
        try:
            target = int(text)
            target = max(1, min(len(self.doc), target))
            if target != self.current_page_idx + 1:
                self.go_to_page(target)
            else:
                self._update_nav_toolbar()
        except ValueError:
            self._update_nav_toolbar()

    def keyPressEvent(self, event):
        if self.page_input.hasFocus():
            super().keyPressEvent(event)
            return
        if event.key() in (Qt.Key_PageUp, Qt.Key_Left):
            self.prev_page()
            event.accept()
        elif event.key() in (Qt.Key_PageDown, Qt.Key_Right):
            self.next_page()
            event.accept()
        elif event.key() == Qt.Key_Home:
            self.go_to_page(1)
            event.accept()
        elif event.key() == Qt.Key_End:
            if self.doc:
                self.go_to_page(len(self.doc))
            event.accept()
        else:
            super().keyPressEvent(event)

    def zoom_in(self):
        if self.btn_mode_pac.isChecked():
            self.pac_locator._zoom_in()
            pct = int(round(self.pac_locator.canvas._zoom_level * 100))
            self.zoom_combo.blockSignals(True)
            self.zoom_combo.setCurrentText(f"{pct}%")
            self.zoom_combo.blockSignals(False)
            return
        self.zoom = min(4.0, round(self.zoom + 0.25, 2))
        self.zoom_combo.setCurrentText(f"{int(self.zoom * 100)}%")
        self.render_current_page()

    def zoom_out(self):
        if self.btn_mode_pac.isChecked():
            self.pac_locator._zoom_out()
            pct = int(round(self.pac_locator.canvas._zoom_level * 100))
            self.zoom_combo.blockSignals(True)
            self.zoom_combo.setCurrentText(f"{pct}%")
            self.zoom_combo.blockSignals(False)
            return
        self.zoom = max(0.25, round(self.zoom - 0.25, 2))
        self.zoom_combo.setCurrentText(f"{int(self.zoom * 100)}%")
        self.render_current_page()

    def _on_pac_zoom_changed(self, zoom_level: float):
        if self.btn_mode_pac.isChecked():
            pct = int(round(zoom_level * 100))
            self.zoom_combo.blockSignals(True)
            self.zoom_combo.setCurrentText(f"{pct}%")
            self.zoom_combo.blockSignals(False)

    def _on_zoom_combo_changed(self, text: str):
        if self.btn_mode_pac.isChecked():
            if text in ("Fit Width", "Fit Page", "100%"):
                self.pac_locator._reset_zoom()
            elif text.endswith("%"):
                try:
                    val = float(text.replace("%", "")) / 100.0
                    self.pac_locator.canvas.set_zoom(val)
                except ValueError:
                    pass
            return
        if not self.doc:
            return
        if text.endswith("%"):
            try:
                self.zoom = float(text.replace("%", "")) / 100.0
                self.render_current_page()
            except ValueError:
                pass
        elif text == "Fit Width":
            viewport_w = self.scroll_area.viewport().width() - 40
            page_w = self.doc[self.current_page_idx].rect.width
            if page_w > 0:
                self.zoom = round(viewport_w / page_w, 2)
                self.render_current_page()
        elif text == "Fit Page":
            viewport_h = self.scroll_area.viewport().height() - 40
            page_h = self.doc[self.current_page_idx].rect.height
            if page_h > 0:
                self.zoom = round(viewport_h / page_h, 2)
                self.render_current_page()

    def rotate_clockwise(self):
        self.rotation = (self.rotation + 90) % 360
        self.render_current_page()

    def clear_highlight(self):
        self.highlight_bbox = None
        self.highlight_rects = []
        self.highlight_message = None
        self.current_finding = None
        self.render_current_page()

    def close_document(self):
        if self.doc:
            try:
                self.doc.close()
            except Exception:
                pass
            self.doc = None
        self.page_display.set_page_image(QPixmap(), pymupdf.Rect(0, 0, 100, 100), 1.0, 0, None)
