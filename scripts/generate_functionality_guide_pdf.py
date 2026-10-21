"""
Generates a comprehensive, publication-grade PDF User & Functionality Guide
for PDF Accessibility Inspector.
"""

import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and draw total page count and running headers/footers."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages):
        self.saveState()
        page_num = self._pageNumber
        w, h = letter

        # Running header (pages 2+)
        if page_num > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(colors.HexColor("#0284c7"))
            self.drawString(36, h - 25, "PDF ACCESSIBILITY INSPECTOR")
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#64748b"))
            self.drawRightString(w - 36, h - 25, "Comprehensive Functionality & User Guide")
            self.setStrokeColor(colors.HexColor("#e2e8f0"))
            self.setLineWidth(0.75)
            self.line(36, h - 28, w - 36, h - 28)

        # Running footer (all pages)
        self.setStrokeColor(colors.HexColor("#e2e8f0"))
        self.setLineWidth(0.75)
        self.line(36, 32, w - 36, 32)

        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        self.drawString(36, 20, "ISO 14289-1 (PDF/UA-1) • WCAG 2.1/2.2 AA • Matterhorn Protocol 1.1")
        page_str = f"Page {page_num} of {total_pages}"
        self.drawRightString(w - 36, 20, page_str)
        self.restoreState()


def create_functionality_guide_pdf(output_path: str):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=38,
        bottomMargin=38
    )

    styles = getSampleStyleSheet()

    # Color Palette
    PRIMARY = colors.HexColor("#0f172a")      # Dark Slate
    SECONDARY = colors.HexColor("#0284c7")    # Accent Cyan/Blue
    TEXT_MAIN = colors.HexColor("#1e293b")    # Slate 800
    TEXT_MUTED = colors.HexColor("#64748b")   # Slate 500
    BG_LIGHT = colors.HexColor("#f8fafc")     # Light background
    BORDER_COLOR = colors.HexColor("#cbd5e1") # Border
    SUCCESS = colors.HexColor("#16a34a")
    FAIL = colors.HexColor("#dc2626")
    WARNING = colors.HexColor("#d97706")

    # Typography Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=PRIMARY,
        spaceAfter=6
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=16,
        textColor=SECONDARY,
        spaceAfter=14
    )

    h1_style = ParagraphStyle(
        'SectionH1',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=19,
        textColor=PRIMARY,
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11.5,
        leading=15,
        textColor=SECONDARY,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'BodyMain',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=TEXT_MAIN,
        spaceAfter=6
    )

    bullet_style = ParagraphStyle(
        'BulletMain',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=TEXT_MAIN,
        leftIndent=14,
        firstLineIndent=-10,
        spaceAfter=3
    )

    callout_style = ParagraphStyle(
        'CalloutText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12.5,
        textColor=TEXT_MAIN
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white
    )

    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=TEXT_MAIN
    )

    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11,
        textColor=TEXT_MAIN
    )

    story = []

    # =========================================================================
    # HEADER BANNER & COVER
    # =========================================================================
    banner_data = [
        [
            Paragraph("<b>PDF ACCESSIBILITY INSPECTOR</b>", ParagraphStyle('B1', fontName='Helvetica-Bold', fontSize=18, leading=22, textColor=colors.white)),
            Paragraph("<b>v1.0.0 Enterprise Edition</b>", ParagraphStyle('B2', fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=colors.HexColor("#bae6fd"), alignment=2))
        ],
        [
            Paragraph("Complete Functionality & User Guide • Architecture, Standards & Visual Remediation", ParagraphStyle('B3', fontName='Helvetica', fontSize=10, leading=14, textColor=colors.HexColor("#f1f5f9"))),
            Paragraph("Standards: ISO 14289-1 • WCAG 2.2 • Matterhorn 1.1", ParagraphStyle('B4', fontName='Helvetica', fontSize=8.5, leading=12, textColor=colors.HexColor("#e2e8f0"), alignment=2))
        ]
    ]
    banner_table = Table(banner_data, colWidths=[360, 180])
    banner_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PRIMARY),
        ('PADDING', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
        ('TOPPADDING', (0, 1), (-1, 1), 2),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 12))

    # =========================================================================
    # 1. EXECUTIVE SUMMARY & TOOL PURPOSE
    # =========================================================================
    story.append(Paragraph("1. Executive Overview & Purpose", h1_style))
    story.append(Paragraph(
        "<b>PDF Accessibility Inspector</b> is a professional Windows desktop application engineered for deep compliance "
        "auditing, interactive structural inspection, and actionable remediation of PDF documents. Built as an advanced "
        "alternative and companion to tools like PAC (PDF Accessibility Checker) and Adobe Acrobat Pro Accessibility Checker, "
        "it validates electronic documents against international accessibility mandates including <b>PDF/UA-1 (ISO 14289-1:2014)</b>, "
        "<b>WCAG 2.1 & 2.2 (Level A & AA)</b>, and the complete <b>Matterhorn Protocol 1.1</b> checkpoint catalog.",
        body_style
    ))
    story.append(Paragraph(
        "Unlike black-box checkers that merely list error codes, PDF Accessibility Inspector couples deterministic "
        "low-level PDF stream parsing with an <b>Integrated Visual PDF Viewer and Locator</b> that visually highlights "
        "the exact bounding boxes of accessibility violations directly on the rendered document page. It empowers document authors, "
        "accessibility remediators, and compliance auditors to inspect logical tag trees, verify ToUnicode font mappings, "
        "validate complex data tables, and generate publication-grade audit reports in seconds.",
        body_style
    ))

    # Highlights box
    hl_data = [[
        Paragraph(
            "<b>Key Highlights:</b><br/>"
            "• <b>Full Standard Coverage:</b> 100% deterministic validation for PDF/UA-1, Matterhorn Protocol 1.1, and WCAG 2.1/2.2 AA.<br/>"
            "• <b>Dual-Engine PDF Parsing:</b> Combines <i>pikepdf</i> (C++ QPDF) for raw structural dictionary analysis and <i>PyMuPDF</i> (C MuPDF) for rendering and text geometry.<br/>"
            "• <b>Interactive Visual Locator:</b> Automatically computes and overlays bounding boxes for untagged elements, missing alt text, headings, and tables.<br/>"
            "• <b>Screen Reader Semantic Preview:</b> Linearized accessible reading stream showing the exact text and tag order presented to assistive technology.<br/>"
            "• <b>Comprehensive Reporting:</b> Export formal PDF audit reports, interactive standalone HTML reports, and machine-readable JSON/CSV data.",
            callout_style
        )
    ]]
    hl_table = Table(hl_data, colWidths=[540])
    hl_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f0fdf4")),
        ('BORDER', (0, 0), (-1, -1), 1, colors.HexColor("#86efac")),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(hl_table)
    story.append(Spacer(1, 10))

    # =========================================================================
    # 2. CORE ARCHITECTURE & SYSTEM PIPELINE
    # =========================================================================
    story.append(Paragraph("2. Core Architecture & Inspection Pipeline", h1_style))
    story.append(Paragraph(
        "The application is organized into a modular pipeline separating low-level document extraction, the rules engine, "
        "the unified in-memory document model, and the PySide6 user interface:",
        body_style
    ))

    arch_data = [
        [
            Paragraph("<b>Stage</b>", table_header_style),
            Paragraph("<b>Component</b>", table_header_style),
            Paragraph("<b>Description & Responsibilities</b>", table_header_style)
        ],
        [
            Paragraph("<b>1. Parsing</b>", table_cell_bold),
            Paragraph("DocumentParser<br/>(pikepdf + pymupdf)", table_cell_style),
            Paragraph("Extracts low-level PDF Catalog, MarkInfo, Pages, StructTreeRoot, ParentTree, RoleMap, fonts, XObjects, Form fields, annotations, and MCID content streams.", table_cell_style)
        ],
        [
            Paragraph("<b>2. Model</b>", table_cell_bold),
            Paragraph("PDFDocumentModel", table_cell_style),
            Paragraph("Normalized, thread-safe, in-memory representation containing StructureNode trees, PageModels, font dictionaries, image models, and table grids.", table_cell_style)
        ],
        [
            Paragraph("<b>3. Engine</b>", table_cell_bold),
            Paragraph("AuditRunner & Rule Suites", table_cell_style),
            Paragraph("Executes 4 comprehensive test suites: PDF/UA (ISO 14289-1), WCAG 2.1/2.2 AA, Quality/Ergonomics, and AI Heuristics. Aggregates results into CheckResult models.", table_cell_style)
        ],
        [
            Paragraph("<b>4. Analysis</b>", table_cell_bold),
            Paragraph("AuditReport", table_cell_style),
            Paragraph("Computes overall accessibility scores (0-100%), failure tallies, category scorecards, Matterhorn checkpoint matrices, and remediation templates.", table_cell_style)
        ],
        [
            Paragraph("<b>5. Visuals</b>", table_cell_bold),
            Paragraph("VisualLocator & Canvas", table_cell_style),
            Paragraph("Computes page-relative bounding boxes and highlights issues with zoom, split-screen PAC view, and page thumbnail navigation.", table_cell_style)
        ],
        [
            Paragraph("<b>6. Export</b>", table_cell_bold),
            Paragraph("Report Generators", table_cell_style),
            Paragraph("Outputs publication-quality PDF audit reports (via ReportLab), self-contained interactive HTML reports, and structured CSV/JSON exports.", table_cell_style)
        ]
    ]
    arch_table = Table(arch_data, colWidths=[65, 125, 350])
    arch_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(arch_table)
    story.append(Spacer(1, 10))

    # =========================================================================
    # 3. USER INTERFACE & NAVIGATION PANELS
    # =========================================================================
    story.append(Paragraph("3. Detailed User Interface & Core Views", h1_style))
    story.append(Paragraph(
        "The interface is designed with a modern dark/light responsive layout divided into a <b>Top Action Bar</b>, "
        "a <b>Left Navigation Sidebar</b>, a <b>Central Visual Workspace</b>, and a <b>Right Inspector Panel</b>:",
        body_style
    ))

    views_data = [
        [
            Paragraph("<b>View / Module</b>", table_header_style),
            Paragraph("<b>Core Capabilities & User Features</b>", table_header_style)
        ],
        [
            Paragraph("<b>Dashboard</b>", table_cell_bold),
            Paragraph("Executive overview displaying overall document compliance score (0-100%), summary cards for Passed, Warnings, and Failures, and category-level health progress bars across PDF/UA, WCAG, and Quality standards.", table_cell_style)
        ],
        [
            Paragraph("<b>Checkpoints<br/>(PAC Matrix)</b>", table_cell_bold),
            Paragraph("PAC-parity checkpoint grid mapping findings to standard clauses (ISO 14289-1 and WCAG). Features tabs for All, Failures, Warnings, and Passed, displaying exact Rule ID, Standard, Category, and Affected Page counts.", table_cell_style)
        ],
        [
            Paragraph("<b>Detailed Results</b>", table_cell_bold),
            Paragraph("High-density interactive findings table. Allows instant filtering by status (Fail/Warn/Pass), category, and free-text search. Clicking any finding immediately reveals technical evidence, standard clause, and remediation steps in the Right Inspector.", table_cell_style)
        ],
        [
            Paragraph("<b>Integrated PDF Viewer<br/>& Visual Locator</b>", table_cell_bold),
            Paragraph("High-fidelity PDF page renderer featuring PAC Split View, thumbnail sidebar, zoom controls, and active bounding box highlights. Clicking 'Highlight on Page' automatically scrolls and boxes the offending element in red with contextual lines.", table_cell_style)
        ],
        [
            Paragraph("<b>Logical Structure Tree</b>", table_cell_bold),
            Paragraph("Interactive hierarchy tree displaying the document's tag tree (StructTreeRoot down to leaf Spans/MCRs). Displays standard resolved tags, RoleMap aliases, attributes (/A), MCID references, /ParentTree mapping, and language tags (/Lang).", table_cell_style)
        ],
        [
            Paragraph("<b>Semantic Reading Order<br/>(Screen Reader View)</b>", table_cell_bold),
            Paragraph("Linearized view displaying document content in the exact logical order assistive technologies (e.g., NVDA, JAWS) read it, highlighting skipped headings, out-of-order text blocks, or misplaced figures.", table_cell_style)
        ],
        [
            Paragraph("<b>Document & Metadata</b>", table_cell_bold),
            Paragraph("Audits document catalog dictionary and XMP metadata stream: validates Dublin Core title (&lt;dc:title&gt;), document language (/Lang), DisplayDocTitle setting, and PDF/UA-1 identification conformance markings.", table_cell_style)
        ],
        [
            Paragraph("<b>Statistics & Health</b>", table_cell_bold),
            Paragraph("Document metrics scorecard: page count, file size, font counts, image tallies, table dimensions, link destinations, tagged vs untagged operations ratio, and artifact sequence percentages.", table_cell_style)
        ]
    ]
    views_table = Table(views_data, colWidths=[120, 420])
    views_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(views_table)
    story.append(Spacer(1, 10))

    # =========================================================================
    # 4. SPECIALIZED ASSET & ELEMENT INSPECTORS
    # =========================================================================
    story.append(Paragraph("4. Specialized Asset & Element Inspectors", h1_style))
    story.append(Paragraph(
        "PDF Accessibility Inspector includes dedicated element-specific inspectors in the left sidebar, allowing "
        "granular investigation of every document asset type:",
        body_style
    ))

    elements_data = [
        [
            Paragraph("<b>Asset Type</b>", table_header_style),
            Paragraph("<b>Inspection & Verification Capabilities</b>", table_header_style)
        ],
        [
            Paragraph("<b>Font Assets</b>", table_cell_bold),
            Paragraph("Inspects every font resource across all pages. Validates font embedding (fully embedded or valid subset), font format (Type 1, TrueType, OpenType, Type 0 CID), and verifies presence of a valid <b>/ToUnicode CMap</b> mapping character codes to Unicode glyphs (ISO 14289-1 Clause 7.2).", table_cell_style)
        ],
        [
            Paragraph("<b>Images & Figures</b>", table_cell_bold),
            Paragraph("Catalog of all raster images and vector diagrams. Checks whether figures are enclosed in &lt;Figure&gt; tags, verifies presence and descriptive quality of alternative text (<b>/Alt</b>), checks bounding box attributes (<b>/BBox</b>), and identifies decorative graphics marked as background <b>/Artifact</b>.", table_cell_style)
        ],
        [
            Paragraph("<b>Table Structures</b>", table_cell_bold),
            Paragraph("Visualizes table structural hierarchy: verifies strict containment (&lt;Table&gt; → &lt;TR&gt; → &lt;TH&gt;/&lt;TD&gt;), detects presence of header cells (&lt;TH&gt;), audits row/column span attributes (/RowSpan, /ColSpan), checks table summaries/captions, and detects empty or malformed cells.", table_cell_style)
        ],
        [
            Paragraph("<b>Hyperlinks & Annots</b>", table_cell_bold),
            Paragraph("Extracts all interactive links and annotations. Validates that &lt;Link&gt; tags contain valid Link-OBJR object references, verifies descriptive link text (flagging generic 'click here' labels), and ensures pages with annotations define tab order as Structure (<b>/Tabs /S</b>).", table_cell_style)
        ],
        [
            Paragraph("<b>Form Fields</b>", table_cell_bold),
            Paragraph("Audits interactive AcroForm fields (text boxes, checkboxes, radio buttons, dropdowns). Checks mandatory accessible tooltips (<b>/TU</b> attribute), unique field names (<b>/T</b>), tab order navigation, and widget annotation structure tree links.", table_cell_style)
        ]
    ]
    elem_table = Table(elements_data, colWidths=[110, 430])
    elem_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(elem_table)
    story.append(Spacer(1, 10))

    # =========================================================================
    # 5. STANDARDS COMPLIANCE & CHECKPOINT RULES
    # =========================================================================
    story.append(Paragraph("5. Standards & Checkpoint Rules Catalog", h1_style))
    story.append(Paragraph(
        "The automated audit engine evaluates over 40 discrete rules categorized by standard and Matterhorn checkpoint:",
        body_style
    ))

    rules_summary_data = [
        [
            Paragraph("<b>Rule ID</b>", table_header_style),
            Paragraph("<b>Category</b>", table_header_style),
            Paragraph("<b>Standard</b>", table_header_style),
            Paragraph("<b>Requirement & Evaluation Logic</b>", table_header_style)
        ],
        [
            Paragraph("PDFUA-SYNTAX-001", table_cell_bold),
            Paragraph("PDF Syntax", table_cell_style),
            Paragraph("PDF/UA", table_cell_style),
            Paragraph("Validates ISO 32000-1 header version and unhindered accessibility text extraction permissions under document security.", table_cell_style)
        ],
        [
            Paragraph("PDFUA-CONTENT-001", table_cell_bold),
            Paragraph("Content", table_cell_style),
            Paragraph("PDF/UA", table_cell_style),
            Paragraph("Catalog /MarkInfo /Marked must be true and /StructTreeRoot must exist in document catalog.", table_cell_style)
        ],
        [
            Paragraph("PDFUA-CONTENT-002", table_cell_bold),
            Paragraph("Content", table_cell_style),
            Paragraph("PDF/UA", table_cell_style),
            Paragraph("All real content (text Tj/TJ, path painting, real XObjects) must be enclosed in marked content (/MCID) or marked as /Artifact.", table_cell_style)
        ],
        [
            Paragraph("PDFUA-TREE-002", table_cell_bold),
            Paragraph("Structure tree", table_cell_style),
            Paragraph("PDF/UA", table_cell_style),
            Paragraph("/ParentTree number tree must exist and maintain bidirectional consistency with all structure element MCIDs (including Form XObject stream /StructParents per ISO 32000-1 Clause 14.7.4.2).", table_cell_style)
        ],
        [
            Paragraph("PDFUA-FONT-001/002", table_cell_bold),
            Paragraph("Fonts", table_cell_style),
            Paragraph("PDF/UA", table_cell_style),
            Paragraph("All rendering fonts must be embedded (fully or subset) and must contain a /ToUnicode mapping dictionary.", table_cell_style)
        ],
        [
            Paragraph("PDFUA-LANG-001/002", table_cell_bold),
            Paragraph("Natural language", table_cell_style),
            Paragraph("PDF/UA", table_cell_style),
            Paragraph("Document catalog must specify a primary language (/Lang) conforming to a valid IETF BCP 47 language tag.", table_cell_style)
        ],
        [
            Paragraph("PDFUA-META-001/002", table_cell_bold),
            Paragraph("Metadata", table_cell_style),
            Paragraph("PDF/UA", table_cell_style),
            Paragraph("XMP metadata stream must contain Dublin Core title (&lt;dc:title&gt;) and declare PDF/UA-1 conformance identifier.", table_cell_style)
        ],
        [
            Paragraph("PDFUA-SETTINGS-001", table_cell_bold),
            Paragraph("Document settings", table_cell_style),
            Paragraph("PDF/UA", table_cell_style),
            Paragraph("/ViewerPreferences dictionary must declare /DisplayDocTitle true so the window title bar displays the document title.", table_cell_style)
        ],
        [
            Paragraph("PDFUA-ALT-001", table_cell_bold),
            Paragraph("Alternative Descr.", table_cell_style),
            Paragraph("PDF/UA", table_cell_style),
            Paragraph("All non-decorative &lt;Figure&gt; elements must define non-empty alternative text (/Alt).", table_cell_style)
        ],
        [
            Paragraph("PDFUA-TABLE-001", table_cell_bold),
            Paragraph("Tables", table_cell_style),
            Paragraph("PDF/UA", table_cell_style),
            Paragraph("Data tables must contain header cells (&lt;TH&gt;) and maintain proper row/cell containment hierarchy.", table_cell_style)
        ],
        [
            Paragraph("PDFUA-LIST-001", table_cell_bold),
            Paragraph("Lists", table_cell_style),
            Paragraph("PDF/UA", table_cell_style),
            Paragraph("List container (&lt;L&gt;) must only contain List Items (&lt;LI&gt;), and &lt;LI&gt; must contain Label (&lt;Lbl&gt;) and/or Body (&lt;LBody&gt;).", table_cell_style)
        ],
        [
            Paragraph("WCAG-1.4.3", table_cell_bold),
            Paragraph("Contrast", table_cell_style),
            Paragraph("WCAG 2.1 AA", table_cell_style),
            Paragraph("Computes color contrast ratio between text glyphs and background pixels (minimum 4.5:1 for regular text, 3.0:1 for large text).", table_cell_style)
        ]
    ]
    rules_table = Table(rules_summary_data, colWidths=[95, 80, 65, 300])
    rules_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(rules_table)
    story.append(Spacer(1, 10))

    # =========================================================================
    # 6. ACTIONABLE REMEDIATION & EXPORT SYSTEM
    # =========================================================================
    story.append(Paragraph("6. Actionable Remediation Guidance & Export Formats", h1_style))
    story.append(Paragraph(
        "A standout capability of the tool is contextual remediation guidance. Selecting any failure or warning "
        "provides clear, step-by-step instructions on how to correct the issue using primary authoring tools:",
        body_style
    ))
    story.append(Paragraph("• <b>Adobe Acrobat Pro:</b> Exact path through Tools → Accessibility → Reading Order or Tags Tree.", bullet_style))
    story.append(Paragraph("• <b>Microsoft Word:</b> File → Info → Check for Issues → Check Accessibility, Heading Styles, Table Headers, and Alt Text.", bullet_style))
    story.append(Paragraph("• <b>Adobe InDesign:</b> Articles Panel, Export Tagging dialog, Anchored Objects, and Object Export Options.", bullet_style))
    story.append(Spacer(1, 4))

    story.append(Paragraph("<b>Export Options:</b>", h2_style))
    story.append(Paragraph("• <b>Formal PDF Audit Report:</b> Publication-grade executive report featuring compliance badges, scorecards, failure tables, and remediation instructions.", bullet_style))
    story.append(Paragraph("• <b>Interactive Standalone HTML Report:</b> Self-contained interactive report with embedded CSS/JS, live search, filtering, and collapsible findings.", bullet_style))
    story.append(Paragraph("• <b>Structured JSON & CSV:</b> Complete machine-readable data dumps for CI/CD automated regression pipelines and enterprise reporting.", bullet_style))
    story.append(Spacer(1, 8))

    # =========================================================================
    # 7. STEP-BY-STEP USER WORKFLOW
    # =========================================================================
    story.append(Paragraph("7. Standard User Workflow", h1_style))
    wf_data = [
        [
            Paragraph("<b>Step 1: Open Document</b>", table_cell_bold),
            Paragraph("Click <b>Open PDF</b> on the top toolbar or drag and drop any PDF into the application. Password-protected files will prompt for decryption.", table_cell_style)
        ],
        [
            Paragraph("<b>Step 2: Review Dashboard</b>", table_cell_bold),
            Paragraph("Inspect the overall score (e.g., 99.7%) and check the category breakdown (PDF/UA, WCAG, Quality). Identify whether failures are critical.", table_cell_style)
        ],
        [
            Paragraph("<b>Step 3: Checkpoints & Details</b>", table_cell_bold),
            Paragraph("Navigate to <b>Checkpoints</b> or <b>Detailed Results</b>. Filter by <b>Failures</b> to examine specific standard violations.", table_cell_style)
        ],
        [
            Paragraph("<b>Step 4: Visual Localization</b>", table_cell_bold),
            Paragraph("Select a failure and click <b>Highlight on Page</b>. The Integrated Viewer jumps to the target page and boxes the exact offending element.", table_cell_style)
        ],
        [
            Paragraph("<b>Step 5: Apply Remediation</b>", table_cell_bold),
            Paragraph("Read the step-by-step instructions in the Right Inspector to fix the issue in Word, InDesign, or Acrobat Pro.", table_cell_style)
        ],
        [
            Paragraph("<b>Step 6: Rescan & Export</b>", table_cell_bold),
            Paragraph("Save the remediated PDF, click <b>Rescan</b> to verify 100% compliance, and export a formal <b>PDF Audit Report</b>.", table_cell_style)
        ]
    ]
    wf_table = Table(wf_data, colWidths=[130, 410])
    wf_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(wf_table)

    # Build document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated PDF Guide at: {output_path}")


if __name__ == "__main__":
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs"))
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, "PDF_Accessibility_Inspector_Functionality_Guide.pdf")
    create_functionality_guide_pdf(target)
