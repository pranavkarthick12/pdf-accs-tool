"""
Finding Details Panel
Right sidebar panel showing exhaustive details for the currently selected CheckResult,
including technical evidence, standard citations, and actionable remediation steps.
"""

from typing import Optional, Dict, List, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser,
    QPushButton, QGroupBox, QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Signal, Qt
from ...core.models import CheckResult, CheckStatus, Severity
from ...engine.wcag.wcag_meta import WCAG_GUIDELINE_META
from .status_badge import StatusBadge, SeverityBadge


class MetaRowLabel(QLabel):
    """Custom label that automatically formats 'Key: Value' into a crisp two-column aligned layout."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setTextFormat(Qt.RichText)
        self.setProperty("class", "metaRowLabel")
        if text:
            self.setText(text)

    def setText(self, text: str):
        if ":" in text:
            key, val = text.split(":", 1)
            key_clean = key.strip().upper()
            val_clean = val.strip() if val.strip() != "-" else "—"
            html = (
                f"<table width='100%' cellpadding='0' cellspacing='0' style='border: none; margin: 0; padding: 0;'>"
                f"<tr>"
                f"<td style='color: #4a715b; font-weight: 700; font-size: 10px; letter-spacing: 0.5px; width: 76px; min-width: 76px; vertical-align: top; padding: 1px 10px 1px 0;'>{key_clean}</td>"
                f"<td style='color: #0b2c1c; font-weight: 600; font-size: 11px; vertical-align: top; padding: 1px 0; line-height: 1.3;'>{val_clean}</td>"
                f"</tr>"
                f"</table>"
            )
            super().setText(html)
        else:
            super().setText(text)


class AutoHeightTextBrowser(QTextBrowser):
    """Text browser that dynamically sizes its height to content without clipping."""

    def __init__(self, min_h: int = 50, max_h: int = 350, parent=None):
        super().__init__(parent)
        self.min_h = min_h
        self.max_h = max_h
        self.setOpenExternalLinks(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextBrowser.WidgetWidth)

    def update_height(self):
        txt = self.toPlainText()
        if not txt.strip():
            self.setFixedHeight(self.min_h)
            return
        vp_w = self.viewport().width()
        w = vp_w if vp_w > 50 else (self.width() - 16 if self.width() > 50 else 260)
        self.document().setTextWidth(w)
        ideal = int(self.document().size().height() + 16)
        self.setFixedHeight(max(self.min_h, min(ideal, self.max_h)))

    def setPlainText(self, text: str):
        super().setPlainText(text)
        self.update_height()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_height()


class FindingDetailsPanel(QWidget):
    """Inspector panel displaying rule evidence, explanation, and remediation."""

    highlight_requested = Signal(int, object)  # (page_num, bbox)
    finding_highlight_requested = Signal(object)  # (CheckResult)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("findingDetailsPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.current_finding: Optional[CheckResult] = None
        self._init_ui()

    def _init_ui(self):
        self.setMinimumWidth(290)
        self.setMaximumWidth(460)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header title
        self.title_label = QLabel("FINDING DETAILS")
        self.title_label.setObjectName("findingDetailsHeaderLabel")
        main_layout.addWidget(self.title_label)

        # Divider line below header
        divider = QFrame()
        divider.setObjectName("findingDetailsDivider")
        divider.setFrameShape(QFrame.HLine)
        main_layout.addWidget(divider)

        # Scroll Area for details
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content_widget = QWidget()
        content_widget.setObjectName("findingDetailsContent")
        content_widget.setStyleSheet("QWidget#findingDetailsContent { background-color: transparent; }")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 8, 10, 10)
        content_layout.setSpacing(10)

        # 1. Summary Card
        self.summary_box = QFrame()
        self.summary_box.setProperty("class", "detailCard")
        summary_layout = QVBoxLayout(self.summary_box)
        summary_layout.setContentsMargins(12, 10, 12, 10)
        summary_layout.setSpacing(6)

        lbl_c1_title = QLabel("CHECKPOINT")
        lbl_c1_title.setProperty("class", "cardSectionTitle")
        summary_layout.addWidget(lbl_c1_title)

        self.name_label = QLabel("No finding selected")
        self.name_label.setProperty("class", "cardTitle")
        self.name_label.setWordWrap(True)
        summary_layout.addWidget(self.name_label)

        badges_layout = QHBoxLayout()
        badges_layout.setSpacing(6)
        self.status_badge = StatusBadge(CheckStatus.NOT_APPLICABLE)
        self.severity_badge = SeverityBadge(Severity.INFO)
        badges_layout.addWidget(self.status_badge)
        badges_layout.addWidget(self.severity_badge)
        badges_layout.addStretch()
        summary_layout.addLayout(badges_layout)

        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("background-color: #e5eee8; max-height: 1px; border: none; margin-top: 2px; margin-bottom: 2px;")
        summary_layout.addWidget(div)

        self.id_label = MetaRowLabel("Rule ID: —")
        summary_layout.addWidget(self.id_label)

        self.standard_label = MetaRowLabel("Standard: —")
        summary_layout.addWidget(self.standard_label)

        self.page_label = MetaRowLabel("Page: —")
        summary_layout.addWidget(self.page_label)

        self.object_label = MetaRowLabel("Target: —")
        summary_layout.addWidget(self.object_label)

        content_layout.addWidget(self.summary_box)

        # 2. Highlight on Page Button
        self.btn_highlight = QPushButton("🎯  Highlight on Page")
        self.btn_highlight.setObjectName("btnHighlightOnPage")
        self.btn_highlight.setCursor(Qt.PointingHandCursor)
        self.btn_highlight.setEnabled(False)
        self.btn_highlight.setToolTip("Select a finding to highlight its location on page")
        self.btn_highlight.clicked.connect(self._on_highlight_clicked)
        content_layout.addWidget(self.btn_highlight)

        # 3. Message / Explanation Box
        self.explanation_box = QFrame()
        self.explanation_box.setProperty("class", "detailCard")
        exp_layout = QVBoxLayout(self.explanation_box)
        exp_layout.setContentsMargins(12, 10, 12, 10)
        exp_layout.setSpacing(4)

        lbl_c2 = QLabel("EXPLANATION")
        lbl_c2.setProperty("class", "cardSectionTitle")
        exp_layout.addWidget(lbl_c2)

        self.txt_explanation = AutoHeightTextBrowser(min_h=50, max_h=350)
        self.txt_explanation.setStyleSheet("font-size: 12px; color: #183626; line-height: 1.45; border: none; background: transparent;")
        exp_layout.addWidget(self.txt_explanation)
        content_layout.addWidget(self.explanation_box)

        # 4. Evidence Box
        self.evidence_box = QFrame()
        self.evidence_box.setProperty("class", "detailCard")
        ev_layout = QVBoxLayout(self.evidence_box)
        ev_layout.setContentsMargins(12, 10, 12, 10)
        ev_layout.setSpacing(4)

        lbl_c3 = QLabel("TECHNICAL EVIDENCE")
        lbl_c3.setProperty("class", "cardSectionTitle")
        ev_layout.addWidget(lbl_c3)

        self.txt_evidence = AutoHeightTextBrowser(min_h=45, max_h=250)
        self.txt_evidence.setStyleSheet("background-color: #f4f8f5; border: 1px solid #d2e3d8; border-radius: 5px; padding: 6px 8px; font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 11px; color: #153e28; line-height: 1.4;")
        ev_layout.addWidget(self.txt_evidence)
        content_layout.addWidget(self.evidence_box)

        # 5. Remediation Advice Box
        self.remediation_box = QFrame()
        self.remediation_box.setProperty("class", "remediationCard")
        rem_layout = QVBoxLayout(self.remediation_box)
        rem_layout.setContentsMargins(12, 10, 12, 10)
        rem_layout.setSpacing(4)

        lbl_c4 = QLabel("REMEDIATION ADVICE")
        lbl_c4.setProperty("class", "cardSectionTitle")
        lbl_c4.setStyleSheet("font-size: 10px; font-weight: 700; color: #166534; letter-spacing: 0.8px; background: transparent; border: none;")
        rem_layout.addWidget(lbl_c4)

        self.txt_remediation = AutoHeightTextBrowser(min_h=50, max_h=350)
        self.txt_remediation.setStyleSheet("font-size: 12px; color: #14532d; line-height: 1.45; border: none; background: transparent;")
        rem_layout.addWidget(self.txt_remediation)
        content_layout.addWidget(self.remediation_box)

        content_layout.addStretch()
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

    def display_category_summary(self, standard: str, category: str, counts: Dict[str, int], findings: List[CheckResult]):
        """Displays category-level summary and highlights primary failure or warning if present."""
        p = counts.get("passed", 0)
        w = counts.get("warned", 0)
        f = counts.get("failed", 0)

        # If there are active findings (failures or warnings), display the most critical finding directly
        active_findings = [res for res in findings if res.status in (CheckStatus.FAIL, CheckStatus.ERROR, CheckStatus.WARNING)]
        if active_findings:
            # Sort with FAIL first, then WARNING
            active_findings.sort(key=lambda x: 0 if x.status in (CheckStatus.FAIL, CheckStatus.ERROR) else 1)
            primary = active_findings[0]
            self.display_finding(primary)
            self.title_label.setText(f"{category} ({len(active_findings)} issue{'s' if len(active_findings) > 1 else ''})")
            return

        # If fully passed or no failures
        self.current_finding = None
        self.title_label.setText(f"Checkpoint: {category}")
        self.name_label.setText(f"{category}")
        if f > 0:
            self.status_badge.setStatus(CheckStatus.FAIL)
            self.severity_badge.setSeverity(Severity.HIGH)
        elif w > 0:
            self.status_badge.setStatus(CheckStatus.WARNING)
            self.severity_badge.setSeverity(Severity.MEDIUM)
        elif p > 0:
            self.status_badge.setStatus(CheckStatus.PASS)
            self.severity_badge.setSeverity(Severity.INFO)
        else:
            self.status_badge.setStatus(CheckStatus.NOT_APPLICABLE)
            self.severity_badge.setSeverity(Severity.INFO)

        wcag_meta = WCAG_GUIDELINE_META.get(category) if standard.upper() in ("WCAG", "WCAG2", "WCAG 2.1", "WCAG 2.2") else None

        if wcag_meta:
            self.id_label.setText(f"Criteria: {wcag_meta['criteria']}")
            self.standard_label.setText(f"Principle: {wcag_meta['principle']} ({wcag_meta['level']})")
        else:
            self.id_label.setText(f"Checkpoint: {category}")
            self.standard_label.setText(f"Standard: {standard}")

        if p == 0 and w == 0 and f == 0:
            self.page_label.setText("Status: Not Applicable (⊘)")
            self.object_label.setText("Total Evaluated: 0")
        else:
            self.page_label.setText(f"Passed: {p} | Warned: {w} | Failed: {f}")
            self.object_label.setText(f"Total Evaluated: {p + w + f}")

        if p == 0 and w == 0 and f == 0:
            if wcag_meta:
                self.txt_explanation.setPlainText(
                    f"{category} ({wcag_meta['criteria']}):\n{wcag_meta['summary']}\n\n"
                    f"Notice: {wcag_meta['not_applicable_guidance']}"
                )
                self.txt_evidence.setPlainText("No applicable objects found (⊘).")
                self.txt_remediation.setPlainText(wcag_meta['remediation'])
            else:
                self.txt_explanation.setPlainText(
                    f"Checkpoint '{category}' is not applicable to this document, or contains no machine-testable objects in this PDF."
                )
                self.txt_evidence.setPlainText("No applicable objects found (⊘).")
                self.txt_remediation.setPlainText("No action required. This checkpoint does not apply or contains no evaluable elements.")
        elif f == 0 and w == 0:
            if wcag_meta:
                self.txt_explanation.setPlainText(
                    f"{category} ({wcag_meta['criteria']}):\n{wcag_meta['summary']}\n\n"
                    f"Status: All {p} evaluated element(s) conform to {wcag_meta['level']} requirements."
                )
                self.txt_evidence.setPlainText(f"Compliance confirmed: {p} item(s) passed.")
                self.txt_remediation.setPlainText(f"Compliant: {wcag_meta['remediation']}")
            else:
                self.txt_explanation.setPlainText(
                    f"All checks for '{category}' passed successfully according to {standard} requirements."
                )
                self.txt_evidence.setPlainText(f"Compliance confirmed: {p} item(s) passed.")
                self.txt_remediation.setPlainText("No remediation necessary. This checkpoint conforms to accessibility requirements.")
        else:
            if wcag_meta:
                self.txt_explanation.setPlainText(
                    f"{category} ({wcag_meta['criteria']}):\n{wcag_meta['summary']}\n\n"
                    f"Identified {f} failure(s) and {w} warning(s) requiring remediation."
                )
                self.txt_evidence.setPlainText(f"Passed: {p}, Warned: {w}, Failed: {f}")
                self.txt_remediation.setPlainText(wcag_meta['remediation'])
            else:
                self.txt_explanation.setPlainText(
                    f"Evaluation of '{category}' identified {f} failure(s) and {w} warning(s)."
                )
                self.txt_evidence.setPlainText(f"Passed: {p}, Warned: {w}, Failed: {f}")
                self.txt_remediation.setPlainText("Double-click this row or navigate to 'Detailed Results' to inspect individual findings and page highlights.")

        findings_with_page = [r for r in findings if getattr(r, "page", None) is not None]
        if findings_with_page:
            self.current_finding = findings_with_page[0]
            self.btn_highlight.setEnabled(True)
        else:
            self.btn_highlight.setEnabled(False)

    def display_finding(self, finding: Optional[CheckResult]):
        """Populates panel with the selected finding's properties."""
        self.current_finding = finding
        if not finding:
            self.title_label.setText("Finding Details")
            self.name_label.setText("No finding selected")
            self.status_badge.setStatus(CheckStatus.NOT_APPLICABLE)
            self.severity_badge.setSeverity(Severity.INFO)
            self.id_label.setText("Rule ID: —")
            self.standard_label.setText("Standard: —")
            self.page_label.setText("Page: —")
            self.object_label.setText("Target: —")
            self.txt_explanation.setPlainText("Select any finding from the Checkpoints matrix or Detailed Results list to inspect its rule evidence, standard citations, and actionable remediation steps.")
            self.txt_evidence.setPlainText("No technical evidence available. Select an active finding to inspect its document elements.")
            self.txt_remediation.setPlainText("Remediation advice will appear here when an accessibility finding is selected.")
            self.btn_highlight.setEnabled(False)
            self.btn_highlight.setToolTip("Select a finding to highlight its location on page")
            return

        self.title_label.setText("Finding Details")
        self.name_label.setText(f"{finding.name}")
        self.status_badge.setStatus(finding.status)
        self.severity_badge.setSeverity(finding.severity)

        self.id_label.setText(f"Rule ID: {finding.check_id}")
        self.standard_label.setText(f"Standard: {finding.standard} ({finding.category})")
        if finding.page:
            self.page_label.setText(f"Page: {finding.page}")
            self.btn_highlight.setToolTip("Navigate to page and highlight issue in viewer")
        else:
            self.page_label.setText("Page: Document-level (No spatial coordinates)")
            self.btn_highlight.setToolTip("Document-level finding: Inspect on Page 1")

        self.object_label.setText(f"Target: {finding.object_reference or 'Document'}")

        # Rich, exhaustive explanation stating the exact issue
        explanation_text = f"Issue: {finding.message}\n\nStandard Requirement:\n{finding.description or 'Must conform to PDF/UA ISO 14289-1 and WCAG 2.1 accessibility guidelines.'}"
        if finding.page:
            explanation_text += f"\n\nLocation: Page {finding.page}"
        if finding.object_reference:
            explanation_text += f" (Element: {finding.object_reference})"

        self.txt_explanation.setPlainText(explanation_text)

        # Technical Evidence
        evidence_text = finding.evidence or "Document structural property or syntax validation."
        if finding.bounding_box:
            evidence_text += f"\nBounding Box: [{', '.join(f'{v:.1f}' for v in finding.bounding_box)}]"
        self.txt_evidence.setPlainText(evidence_text)

        # Remediation Advice
        remediation_text = finding.remediation or "Inspect tag properties in Adobe Acrobat Pro or source authoring application to resolve accessibility violation."
        self.txt_remediation.setPlainText(remediation_text)

        # Highlight on Page enabled for all findings
        self.btn_highlight.setEnabled(True)

    def _on_highlight_clicked(self):
        if self.current_finding:
            target_page = self.current_finding.page or 1
            self.highlight_requested.emit(target_page, self.current_finding.bounding_box)


