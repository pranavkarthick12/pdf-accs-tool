"""
PAC-Style Visual Issue Locator Widget and Canvas
Provides a high-precision, dual-view visual inspector matching PDF Accessibility Checker (PAC):
- Left: Complete page overview thumbnail with page label and highlight outline
- Middle: Dynamic green callout projection lines linking page bbox to magnified detail
- Right: High-resolution zoomed-in callout crop centered on the problem element with a crisp red bounding box
"""

from typing import Optional, Tuple, List, Dict, Any
import math
import pymupdf
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QToolBar, QFrame, QSizePolicy, QSlider, QDialog, QSplitter
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QPen, QBrush,
    QFont, QPainterPath, QLinearGradient
)

from ...core.models import CheckResult, CheckStatus, Severity, PDFDocumentModel
from ...core.visual_locator import VisualLocatorResolver


class PACVisualCanvas(QWidget):
    """
    Dual-view custom canvas rendering:
    1. Scaled full-page overview on the left
    2. Green projection / callout connector lines across the split
    3. Crystal-clear magnified callout crop on the right with a red bounding box
    """

    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Small minimum size so canvas dynamically fits without overflowing or clipping
        self.setMinimumSize(180, 80)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.doc: Optional[pymupdf.Document] = None
        self.doc_model: Optional[PDFDocumentModel] = None
        self.page_num: int = 1  # 1-indexed
        self.bbox: Optional[Tuple[float, float, float, float]] = None  # (x0, y0, x1, y1) in PDF pts (top-left origin)
        self.finding: Optional[CheckResult] = None

        # Cached renders
        self._cached_page_pixmap: Optional[QPixmap] = None
        self._cached_crop_pixmap: Optional[QPixmap] = None
        self._cached_page_size: Tuple[float, float] = (612.0, 792.0)
        self._cached_crop_rect: Optional[Tuple[float, float, float, float]] = None

        # Zoom & Navigation
        self._zoom_level: float = 1.0  # 1.0 = 100% Fit to viewport
        self._context_margin: float = 65.0  # Extra PDF points of surrounding context
        self._split_ratio: float = 0.38  # Left overview gets ~38% width
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0
        self._is_dragging: bool = False
        self._drag_start: QPointF = QPointF()

        # Visual theme
        self.setStyleSheet("background-color: #f8fafc;")
        self.setMouseTracking(True)

    def set_data(
        self,
        doc: Optional[pymupdf.Document],
        page_num: int,
        bbox: Optional[Tuple[float, float, float, float]],
        finding: Optional[CheckResult] = None,
        doc_model: Optional[PDFDocumentModel] = None,
        zoom: float = 1.0
    ):
        """Sets the document and finding details, then prepares high-res renders."""
        self.doc = doc
        self.doc_model = doc_model
        self.page_num = max(1, page_num)
        self.finding = finding
        self._zoom_level = zoom
        self._pan_x = 0.0
        self._pan_y = 0.0

        # Pinpoint precise bounding box using explicit bbox or VisualLocatorResolver
        if bbox and len(bbox) == 4:
            self.bbox = bbox
        else:
            self.bbox = VisualLocatorResolver.resolve_bbox(self.doc, self.page_num, self.finding, self.doc_model)
        self._render_elements()
        self.update()
        self.zoom_changed.emit(self._zoom_level)

    def set_zoom(self, zoom: float):
        """Sets the interactive zoom level (1.0 = 100% Fit)."""
        new_zoom = max(0.4, min(4.0, round(zoom, 2)))
        if abs(new_zoom - 1.0) < 0.01:
            self._pan_x = 0.0
            self._pan_y = 0.0
        self._zoom_level = new_zoom
        self._render_elements()
        self.update()
        self.zoom_changed.emit(self._zoom_level)

    def set_context_margin(self, margin: float):
        self._context_margin = max(20.0, min(180.0, margin))
        self._render_elements()
        self.update()

    def _render_elements(self):
        """Pre-renders the page overview and high-res cropped callout."""
        if not self.doc or len(self.doc) < self.page_num:
            self._cached_page_pixmap = None
            self._cached_crop_pixmap = None
            return

        page = self.doc[self.page_num - 1]
        p_rect = page.rect
        self._cached_page_size = (p_rect.width, p_rect.height)

        # 1. Page Overview Pixmap (rendered at 1.5x for crisp thumbnail display)
        try:
            overview_mat = pymupdf.Matrix(1.5, 1.5)
            ov_pix = page.get_pixmap(matrix=overview_mat, alpha=False)
            qimg_ov = QImage(ov_pix.samples, ov_pix.width, ov_pix.height, ov_pix.stride, QImage.Format_RGB888)
            self._cached_page_pixmap = QPixmap.fromImage(qimg_ov)
        except Exception:
            self._cached_page_pixmap = None

        # 2. Magnified Callout Crop
        try:
            bx0, by0, bx1, by1 = self.bbox or (0, 0, p_rect.width, 100)
            margin = self._context_margin

            crop_x0 = max(0.0, bx0 - margin)
            crop_y0 = max(0.0, by0 - (margin * 0.7))
            crop_x1 = min(p_rect.width, bx1 + margin)
            crop_y1 = min(p_rect.height, by1 + (margin * 0.7))

            crop_rect = pymupdf.Rect(crop_x0, crop_y0, crop_x1, crop_y1)
            render_scale = max(2.5, min(5.0, 2.5 * max(1.0, self._zoom_level)))
            crop_mat = pymupdf.Matrix(render_scale, render_scale)

            # High-res crop render
            crop_pix = page.get_pixmap(matrix=crop_mat, clip=crop_rect, alpha=False)
            qimg_crop = QImage(crop_pix.samples, crop_pix.width, crop_pix.height, crop_pix.stride, QImage.Format_RGB888)
            self._cached_crop_pixmap = QPixmap.fromImage(qimg_crop)
            self._cached_crop_rect = (crop_x0, crop_y0, crop_x1, crop_y1)
        except Exception:
            self._cached_crop_pixmap = None
            self._cached_crop_rect = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if event.position().x() > self.width() * self._split_ratio:
                self._is_dragging = True
                self._drag_start = event.position()
                self.setCursor(Qt.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            delta = event.position() - self._drag_start
            self._drag_start = event.position()
            self._pan_x += delta.x()
            self._pan_y += delta.y()
            self.update()
            event.accept()
            return
        elif event.position().x() > self.width() * self._split_ratio and self._zoom_level > 1.0:
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._is_dragging:
            self._is_dragging = False
            self.setCursor(Qt.OpenHandCursor if self._zoom_level > 1.0 else Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if event.position().x() > self.width() * self._split_ratio:
            delta = event.angleDelta().y()
            if delta > 0:
                self.set_zoom(self._zoom_level + 0.15)
            elif delta < 0:
                self.set_zoom(self._zoom_level - 0.15)
            event.accept()
            return
        super().wheelEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)

        # Canvas background
        w = self.width()
        h = self.height()
        painter.fillRect(0, 0, w, h, QColor("#f1f5f9"))

        if not self._cached_page_pixmap or not self.bbox:
            painter.setPen(QColor("#94a3b8"))
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(self.rect(), Qt.AlignCenter, "No page preview available.")
            painter.end()
            return

        # Split geometry
        left_width = int(w * self._split_ratio)
        pad = 12

        # -------------------------------------------------------------
        # 1. LEFT PANEL: Full Page Overview (fits completely, never clipped)
        # -------------------------------------------------------------
        page_w, page_h = self._cached_page_size
        avail_pw = max(40, left_width - (pad * 2))
        avail_ph = max(40, h - (pad * 2) - 22)  # 22px reserved for "Page X" label below

        scale_ov = min(avail_pw / page_w, avail_ph / page_h)
        disp_pw = page_w * scale_ov
        disp_ph = page_h * scale_ov

        ov_x = pad + (avail_pw - disp_pw) / 2
        ov_y = pad + (avail_ph - disp_ph) / 2

        # Page shadow
        shadow_rect = QRectF(ov_x + 2, ov_y + 3, disp_pw, disp_ph)
        painter.fillRect(shadow_rect, QColor(0, 0, 0, 30))

        # Page white sheet
        page_rect = QRectF(ov_x, ov_y, disp_pw, disp_ph)
        painter.fillRect(page_rect, QColor("#ffffff"))
        painter.drawPixmap(
            int(ov_x), int(ov_y), int(disp_pw), int(disp_ph),
            self._cached_page_pixmap
        )

        # Page outline border
        painter.setPen(QPen(QColor("#cbd5e1"), 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(page_rect)

        # Bounding box on Left Page
        bx0, by0, bx1, by1 = self.bbox
        ov_bx0 = ov_x + (bx0 * scale_ov)
        ov_by0 = ov_y + (by0 * scale_ov)
        ov_bw = max(4.0, (bx1 - bx0) * scale_ov)
        ov_bh = max(4.0, (by1 - by0) * scale_ov)
        ov_bbox_rect = QRectF(ov_bx0, ov_by0, ov_bw, ov_bh)

        # Highlight fill and stroke on full page
        painter.setBrush(QBrush(QColor(34, 197, 94, 45)))  # Subtle green glow
        painter.setPen(QPen(QColor("#16a34a"), 1.8, Qt.SolidLine))
        painter.drawRoundedRect(ov_bbox_rect, 2, 2)

        # "Page X" Caption below the page
        painter.setPen(QColor("#334155"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        label_y = ov_y + disp_ph + 3
        painter.drawText(
            QRectF(ov_x, label_y, disp_pw, 20),
            Qt.AlignCenter,
            f"Page {self.page_num}"
        )

        # -------------------------------------------------------------
        # 2. RIGHT PANEL: Magnified Callout Crop
        # -------------------------------------------------------------
        rx_start = left_width + pad
        avail_rw = max(40, w - rx_start - pad)
        avail_rh = max(40, h - (pad * 2))

        crop_x0, crop_y0, crop_x1, crop_y1 = self._cached_crop_rect or (bx0, by0, bx1, by1)
        crop_w = max(1.0, crop_x1 - crop_x0)
        crop_h = max(1.0, crop_y1 - crop_y0)

        # Base scale that fits perfectly inside avail_rw x avail_rh
        base_fit_scale = min(avail_rw / crop_w, avail_rh / crop_h)
        effective_scale = base_fit_scale * self._zoom_level

        disp_cw = crop_w * effective_scale
        disp_ch = crop_h * effective_scale

        # Container viewport rect for right panel
        container_rect = QRectF(rx_start, pad, avail_rw, avail_rh)

        # Container drop shadow & background
        painter.fillRect(QRectF(rx_start + 3, pad + 3, avail_rw, avail_rh), QColor(0, 0, 0, 30))
        painter.fillRect(container_rect, QColor("#ffffff"))

        # Target BBox center in crop coordinates
        target_crop_cx = ((bx0 + bx1) / 2.0 - crop_x0) * effective_scale
        target_crop_cy = ((by0 + by1) / 2.0 - crop_y0) * effective_scale

        container_cx = rx_start + avail_rw / 2.0
        container_cy = pad + avail_rh / 2.0

        if self._zoom_level <= 1.0:
            cx = rx_start + (avail_rw - disp_cw) / 2.0
            cy = pad + (avail_rh - disp_ch) / 2.0
        else:
            cx = container_cx - target_crop_cx + self._pan_x
            cy = container_cy - target_crop_cy + self._pan_y

        # Draw cropped pixmap and red bbox inside clipped container
        painter.save()
        painter.setClipRect(container_rect)

        if self._cached_crop_pixmap:
            painter.drawPixmap(
                int(cx), int(cy), int(disp_cw), int(disp_ch),
                self._cached_crop_pixmap
            )

        # Target Bounding Box inside Magnified Crop
        mag_bx0 = cx + ((bx0 - crop_x0) * effective_scale)
        mag_by0 = cy + ((by0 - crop_y0) * effective_scale)
        mag_bw = max(6.0, (bx1 - bx0) * effective_scale)
        mag_bh = max(6.0, (by1 - by0) * effective_scale)
        mag_bbox_rect = QRectF(mag_bx0, mag_by0, mag_bw, mag_bh)

        # Prominent Red Bounding Box framing the element (matching PAC reference)
        painter.setBrush(QBrush(QColor(239, 68, 68, 25)))  # Very soft red translucent
        painter.setPen(QPen(QColor("#dc2626"), 2.2, Qt.SolidLine))
        painter.drawRoundedRect(mag_bbox_rect, 3, 3)

        painter.restore()

        # Container border
        painter.setPen(QPen(QColor("#cbd5e1"), 1.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(container_rect)

        # -------------------------------------------------------------
        # 3. MIDDLE: Green Projection / Callout Connecting Lines
        # -------------------------------------------------------------
        proj_pen = QPen(QColor(22, 163, 74, 210), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(proj_pen)

        # Connect left page highlight corners to right magnified box corners
        # Clamp right points to container_rect so projection lines cleanly meet container
        def clamp_pt(px, py):
            return QPointF(
                max(container_rect.left(), min(container_rect.right(), px)),
                max(container_rect.top(), min(container_rect.bottom(), py))
            )

        p_tl = clamp_pt(mag_bx0, mag_by0)
        p_bl = clamp_pt(mag_bx0, mag_by0 + mag_bh)
        p_tr = clamp_pt(mag_bx0 + mag_bw, mag_by0)
        p_br = clamp_pt(mag_bx0 + mag_bw, mag_by0 + mag_bh)

        painter.drawLine(QPointF(ov_bx0, ov_by0), p_tl)
        painter.drawLine(QPointF(ov_bx0, ov_by0 + ov_bh), p_bl)
        painter.drawLine(QPointF(ov_bx0 + ov_bw, ov_by0), p_tr)
        painter.drawLine(QPointF(ov_bx0 + ov_bw, ov_by0 + ov_bh), p_br)

        painter.end()


class PACVisualLocatorWidget(QWidget):
    """
    Complete PAC-style Visual Issue Inspector widget with:
    - Finding Title & Info Banner
    - High-Precision PAC Dual Canvas
    - Interactive Toolbar (Zoom, Context Padding, Finding Navigation)
    """

    finding_navigation_requested = Signal(int)  # offset: -1 for prev, +1 for next
    full_view_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_finding: Optional[CheckResult] = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Top Header Banner (PAC Title Bar)
        self.banner = QFrame()
        self.banner.setStyleSheet("background: #ffffff; border-bottom: 1px solid #e2e8f0; padding: 4px 10px;")
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(10, 5, 10, 5)
        banner_layout.setSpacing(10)

        # Finding title
        self.lbl_title = QLabel("Visual Issue Locator")
        self.lbl_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #0f172a;")
        self.lbl_title.setWordWrap(True)
        banner_layout.addWidget(self.lbl_title, 1)

        # Badges
        self.lbl_badge_status = QLabel("FAIL")
        self.lbl_badge_status.setStyleSheet("background: #fee2e2; color: #991b1b; font-weight: 700; padding: 3px 8px; border-radius: 4px; font-size: 11px;")
        banner_layout.addWidget(self.lbl_badge_status)

        self.lbl_badge_rule = QLabel("PDF/UA")
        self.lbl_badge_rule.setStyleSheet("background: #f1f5f9; color: #475569; font-weight: 600; padding: 3px 8px; border-radius: 4px; font-size: 11px;")
        banner_layout.addWidget(self.lbl_badge_rule)

        # Action Buttons
        self.btn_full_view = QPushButton("📄 Document View")
        self.btn_full_view.setStyleSheet("background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px 10px; font-size: 11px;")
        self.btn_full_view.clicked.connect(self.full_view_requested.emit)
        banner_layout.addWidget(self.btn_full_view)

        layout.addWidget(self.banner)

        # 2. Main PAC Visual Canvas
        self.canvas = PACVisualCanvas(self)
        self.canvas.zoom_changed.connect(self._on_zoom_changed)
        layout.addWidget(self.canvas, 1)

        # 3. Bottom Toolbar
        self.toolbar = QToolBar()
        self.toolbar.setStyleSheet("background: #ffffff; border-top: 1px solid #e2e8f0; padding: 4px 8px;")

        self.btn_prev = QPushButton("◀ Prev Issue")
        self.btn_prev.clicked.connect(lambda: self.finding_navigation_requested.emit(-1))
        self.toolbar.addWidget(self.btn_prev)

        self.btn_next = QPushButton("Next Issue ▶")
        self.btn_next.clicked.connect(lambda: self.finding_navigation_requested.emit(1))
        self.toolbar.addWidget(self.btn_next)

        self.toolbar.addSeparator()

        lbl_zoom = QLabel(" Zoom: ")
        lbl_zoom.setStyleSheet("color: #64748b; font-size: 11px;")
        self.toolbar.addWidget(lbl_zoom)

        self.btn_zoom_out = QPushButton("🔍 -")
        self.btn_zoom_out.setToolTip("Zoom Out callout")
        self.btn_zoom_out.clicked.connect(self._zoom_out)
        self.toolbar.addWidget(self.btn_zoom_out)

        self.btn_zoom_in = QPushButton("🔍 +")
        self.btn_zoom_in.setToolTip("Zoom In callout")
        self.btn_zoom_in.clicked.connect(self._zoom_in)
        self.toolbar.addWidget(self.btn_zoom_in)

        self.btn_reset_zoom = QPushButton("100% Fit")
        self.btn_reset_zoom.setToolTip("Reset Zoom to 100% Fit")
        self.btn_reset_zoom.clicked.connect(self._reset_zoom)
        self.toolbar.addWidget(self.btn_reset_zoom)

        self.toolbar.addSeparator()

        lbl_ctx = QLabel(" Surrounding Context: ")
        lbl_ctx.setStyleSheet("color: #64748b; font-size: 11px;")
        self.toolbar.addWidget(lbl_ctx)

        self.slider_margin = QSlider(Qt.Horizontal)
        self.slider_margin.setRange(30, 160)
        self.slider_margin.setValue(65)
        self.slider_margin.setFixedWidth(110)
        self.slider_margin.valueChanged.connect(self.canvas.set_context_margin)
        self.toolbar.addWidget(self.slider_margin)

        layout.addWidget(self.toolbar)

    def load_finding(
        self,
        doc: Optional[pymupdf.Document],
        finding: CheckResult,
        page_num: Optional[int] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        doc_model: Optional[PDFDocumentModel] = None
    ):
        """Loads a CheckResult and immediately renders PAC visual locator."""
        self.current_finding = finding
        target_page = page_num or finding.page or 1
        if bbox is not None:
            target_bbox = bbox
        elif finding.page is None or finding.page == target_page:
            target_bbox = finding.bounding_box
        else:
            target_bbox = None

        # Format header title matching PAC
        title_text = finding.message or finding.name
        self.lbl_title.setText(f"{title_text}")

        # Update badges
        status_val = finding.status.value if hasattr(finding.status, "value") else str(finding.status)
        self.lbl_badge_status.setText(status_val)
        if status_val in ("FAIL", "ERROR"):
            self.lbl_badge_status.setStyleSheet("background: #fee2e2; color: #991b1b; font-weight: 700; padding: 3px 8px; border-radius: 4px; font-size: 11px;")
        elif status_val == "WARNING":
            self.lbl_badge_status.setStyleSheet("background: #fef3c7; color: #92400e; font-weight: 700; padding: 3px 8px; border-radius: 4px; font-size: 11px;")
        else:
            self.lbl_badge_status.setStyleSheet("background: #dcfce7; color: #166534; font-weight: 700; padding: 3px 8px; border-radius: 4px; font-size: 11px;")

        self.lbl_badge_rule.setText(f"{finding.standard} • {finding.check_id}")

        self.canvas.set_data(doc, target_page, target_bbox, finding, doc_model=doc_model)

    def _zoom_in(self):
        self.canvas.set_zoom(self.canvas._zoom_level + 0.25)

    def _zoom_out(self):
        self.canvas.set_zoom(self.canvas._zoom_level - 0.25)

    def _reset_zoom(self):
        self.canvas.set_zoom(1.0)

    def _on_zoom_changed(self, zoom_level: float):
        pct = int(round(zoom_level * 100))
        self.btn_reset_zoom.setText("100% Fit" if pct == 100 else f"{pct}% Fit")
        self.btn_reset_zoom.setToolTip(f"Current zoom: {pct}%. Click to reset to 100% Fit")


class PACVisualLocatorDialog(QDialog):
    """Standalone / modal inspection window for examining issues in full PAC visual locator format."""

    def __init__(
        self,
        doc: Optional[pymupdf.Document],
        finding: CheckResult,
        page_num: Optional[int] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        doc_model: Optional[PDFDocumentModel] = None,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle(f"PAC Visual Locator — {finding.name}")
        self.resize(1000, 680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.locator = PACVisualLocatorWidget(self)
        self.locator.load_finding(doc, finding, page_num, bbox, doc_model=doc_model)
        self.locator.full_view_requested.connect(self.accept)

        layout.addWidget(self.locator)

