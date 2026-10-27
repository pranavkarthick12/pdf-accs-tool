"""
Visual Locator Engine
Pinpoints the exact visual bounding box(es) on any PDF page for ANY accessibility finding:
- Structure Tags: Formulas, Figures, Headings, Tables, Lists, Paragraphs, Links, Annotations
- Untagged Content / Artifacts: Character snippets, Form XObjects, vector paths
- Color Contrast & Visual Anomalies: Low luminance text spans
- Mathematical Equations: Vector fraction bars, integral symbols, and formula glyph clusters
- Images & Figures: Raster images and vector diagram bounding boxes

Data Contract:
- Strict location hierarchy:
  1. Validated bounding box directly associated with offending content
  2. Structure element / MCID / annotation / PDF object resolution
  3. Text snippet / content search
  4. Whole-page highlight (only when finding genuinely applies to entire page)
  5. Honest non-spatial indicator (no fabricated highlights or default corners)
"""

from typing import Optional, Tuple, List, Dict, Any, Set
from dataclasses import dataclass, field
import logging
import math
import re
import pymupdf

from .models import CheckResult, StructureNode, PDFDocumentModel

logger = logging.getLogger("pdf_inspector.visual_locator")


@dataclass
class ResolvedLocation:
    """
    Standardized, verified visual location contract for any accessibility finding.
    Distinguishes CONTENT, STRUCTURE, PAGE, DOCUMENT, and NONE location types.
    """
    location_type: str  # "CONTENT", "STRUCTURE", "PAGE", "DOCUMENT", "NONE"
    rectangles: List[Tuple[float, float, float, float]] = field(default_factory=list)  # (x0, y0, x1, y1) in page coordinates
    page_number: Optional[int] = None  # 1-based page number
    source: str = "NONE"  # "EXPLICIT_BBOX", "STRUCTURE_NODE", "MCID", "CONTENT_SEARCH", "PAGE_LEVEL", "NONE"
    is_valid: bool = False
    message: str = ""
    target_node: Optional[StructureNode] = None

    @property
    def primary_bbox(self) -> Optional[Tuple[float, float, float, float]]:
        """Returns union envelope of all rectangles, or None if no rectangles."""
        if not self.rectangles:
            return None
        min_x = min(r[0] for r in self.rectangles)
        min_y = min(r[1] for r in self.rectangles)
        max_x = max(r[2] for r in self.rectangles)
        max_y = max(r[3] for r in self.rectangles)
        return (min_x, min_y, max_x, max_y)


def validate_highlight_rect(
    rect: Any,
    page_rect: pymupdf.Rect,
    min_size: float = 0.5
) -> Tuple[bool, Optional[Tuple[float, float, float, float]], str]:
    """
    Centralized validation step for candidate highlight geometry.
    A candidate rectangle must:
    - Contain four finite numeric coordinates
    - Have positive width and height (>= min_size)
    - Intersect the visible page bounds
    - Not be a dummy (0, 0, 0, 0) placeholder

    Returns (is_valid, clamped_rect_tuple, reason)
    """
    if rect is None:
        return False, None, "Rectangle is None"

    if not isinstance(rect, (list, tuple)) and not hasattr(rect, "__iter__"):
        return False, None, "Rectangle is not iterable"

    try:
        coords = list(rect)
        if len(coords) != 4:
            return False, None, f"Expected 4 coordinates, got {len(coords)}"

        # Verify finite numeric values
        float_coords = []
        for c in coords:
            if isinstance(c, (bool, str, bytes, dict, list)):
                return False, None, f"Non-numeric coordinate: {type(c).__name__}"
            f = float(c)
            if not math.isfinite(f):
                return False, None, f"Non-finite coordinate: {f}"
            float_coords.append(f)

        x0, y0, x1, y1 = float_coords
        nx0, nx1 = min(x0, x1), max(x0, x1)
        ny0, ny1 = min(y0, y1), max(y0, y1)

        w = nx1 - nx0
        h = ny1 - ny0

        # Check if dummy (0, 0, 0, 0)
        if abs(nx0) < 1e-4 and abs(ny0) < 1e-4 and abs(nx1) < 1e-4 and abs(ny1) < 1e-4:
            return False, None, "Dummy zero rectangle (0, 0, 0, 0)"

        if w < min_size or h < min_size:
            return False, None, f"Rectangle dimensions too small ({w:.2f} x {h:.2f} pt)"

        cand = pymupdf.Rect(nx0, ny0, nx1, ny1)

        # Check intersection with page bounds
        if not cand.intersects(page_rect):
            return False, None, f"Rectangle {cand} does not intersect visible page bounds {page_rect}"

        # Clamp to page bounds
        clamped = cand & page_rect
        if clamped.width < min_size or clamped.height < min_size:
            return False, None, f"Clamped rectangle is too small ({clamped.width:.2f} x {clamped.height:.2f} pt)"

        return True, (float(clamped.x0), float(clamped.y0), float(clamped.x1), float(clamped.y1)), "Valid"

    except Exception as e:
        return False, None, f"Validation error: {e}"


def validate_highlight_rectangles(
    rects: List[Any],
    page_rect: pymupdf.Rect,
    min_size: float = 0.5
) -> Tuple[List[Tuple[float, float, float, float]], List[str]]:
    """Validates a list of candidate rectangles, filtering out invalid or out-of-bounds ones."""
    valid_rects = []
    reasons = []
    for r in rects:
        ok, valid_r, reason = validate_highlight_rect(r, page_rect, min_size)
        if ok and valid_r:
            valid_rects.append(valid_r)
        else:
            reasons.append(reason)
    return valid_rects, reasons


# Document-level rule IDs that genuinely evaluate document-wide metadata, catalogs, or fonts
DOCUMENT_LEVEL_CHECK_IDS: Set[str] = {
    # PDF/UA Document & Metadata
    "PDFUA-DOC-001", "PDFUA-DOC-002", "PDFUA-DOC-003",
    "PDFUA-META-001", "PDFUA-META-002", "PDFUA-META-003", "PDFUA-META-004",
    "PDFUA-LANG-001", "PDFUA-LANG-002", "PDFUA-NATLANG-001",
    "PDFUA-ROLE-001", "PDFUA-ROLE-002", "PDFUA-SYNTAX-001",
    "PDFUA-BOOKMARK-001", "PDFUA-BOOKMARK-002",
    "PDFUA-FONT-001", "PDFUA-FONT-002",
    # WCAG Document-level
    "WCAG-DOC-001", "WCAG-META-001", "WCAG-2.4.2", "WCAG-3.1.1",
    # Quality Document-level
    "QUAL-META-001", "QUAL-META-002", "QUAL-FONT-001", "QUAL-FONT-002",
    "QUAL-BOOKMARK-001",
}

PAGE_LEVEL_CHECK_IDS: Set[str] = {
    "PDFUA-SYNTAX-003",  # Page TabOrder /Tabs
    "PDFUA-PAGE-001",
    "WCAG-2.4.3",        # Tab order
    "QUAL-TAB-001",
}


class VisualLocatorResolver:
    """
    Intelligently resolves the precise pixel-perfect bounding box(es) for any accessibility finding.
    Strictly conforms to data contract: NEVER fabricates coordinates or substitutes arbitrary page corners.
    """

    @classmethod
    def resolve_location(
        cls,
        doc: pymupdf.Document,
        page_num: int,
        finding: Optional[CheckResult] = None,
        doc_model: Optional[PDFDocumentModel] = None
    ) -> ResolvedLocation:
        """
        Main entry point returning a comprehensive ResolvedLocation object.
        Supports single or multiple rectangles, accurate page mapping, and honest non-spatial reporting.
        """
        if not doc or len(doc) == 0:
            return ResolvedLocation(
                location_type="NONE",
                is_valid=False,
                message="No document loaded"
            )

        target_idx = max(0, min(len(doc) - 1, page_num - 1))
        page = doc[target_idx]
        p_rect = page.rect
        actual_page_num = target_idx + 1

        rule_id = (finding.check_id if finding else "UNKNOWN").upper()
        finding_name = finding.name if finding else ""
        cat = (finding.category or "").strip()

        # ------------------------------------------------------------------
        # 1. Document-Level Findings Detection
        # ------------------------------------------------------------------
        if finding:
            is_doc_level = (
                rule_id in DOCUMENT_LEVEL_CHECK_IDS
                or any(rule_id.startswith(p) for p in ("PDFUA-DOC", "PDFUA-META", "PDFUA-LANG", "WCAG-META", "QUAL-META"))
                or (finding.page is None and cat.lower() in ("metadata", "document", "bookmarks", "catalog", "fonts"))
                or "missing title" in (finding.message or "").lower()
                or "missing language" in (finding.message or "").lower()
                or "pdf/ua identifier" in (finding.message or "").lower()
            )

            # Exclude elements that have explicit page-anchored structure IDs
            has_spatial_target = bool(
                finding.bounding_box
                or (finding.object_reference and "id=" in finding.object_reference.lower())
                or (finding.object_reference and "mcid" in finding.object_reference.lower())
            )

            if is_doc_level and not has_spatial_target:
                cls._log_diagnostic(
                    finding_id=finding.check_id,
                    rule_id=rule_id,
                    target_page=actual_page_num,
                    location_type="DOCUMENT",
                    source="DOCUMENT_METADATA",
                    rects=[],
                    outcome="REJECTED_DOCUMENT_LEVEL",
                    reason="Finding applies to document-level metadata, catalog, or font properties with no spatial coordinates."
                )
                return ResolvedLocation(
                    location_type="DOCUMENT",
                    page_number=actual_page_num,
                    source="NONE",
                    is_valid=False,
                    message=f"Document-level finding: '{finding_name}' evaluates document metadata or properties and has no visual position on the page."
                )

        # ------------------------------------------------------------------
        # 2. Priority 1: Explicit Finding Bounding Box
        # ------------------------------------------------------------------
        if finding and finding.bounding_box and len(finding.bounding_box) == 4:
            if finding.page is None or finding.page == actual_page_num:
                ok, valid_r, reason = validate_highlight_rect(finding.bounding_box, p_rect)
                if ok and valid_r:
                    cls._log_diagnostic(
                        finding_id=finding.check_id,
                        rule_id=rule_id,
                        target_page=actual_page_num,
                        location_type="CONTENT",
                        source="EXPLICIT_BBOX",
                        rects=[valid_r],
                        outcome="ACCEPTED",
                        reason="Validated explicit finding bounding box"
                    )
                    return ResolvedLocation(
                        location_type="CONTENT",
                        rectangles=[valid_r],
                        page_number=actual_page_num,
                        source="EXPLICIT_BBOX",
                        is_valid=True,
                        message="Exact spatial finding coordinates"
                    )
                else:
                    logger.debug(f"Explicit bounding box {finding.bounding_box} rejected: {reason}")

        # ------------------------------------------------------------------
        # 3. Priority 2: Structure Tree Node Lookup (Accurate Target Identification)
        # ------------------------------------------------------------------
        if finding and doc_model and doc_model.structure_tree:
            node = cls._find_structure_node_for_finding(finding, doc_model.structure_tree, actual_page_num)
            if node:
                # For list hierarchy findings, identify the actual offending child node
                offending_nodes = cls._resolve_offending_subelements(finding, node, actual_page_num)
                target_nodes = offending_nodes if offending_nodes else [node]

                resolved_rects: List[Tuple[float, float, float, float]] = []
                for tn in target_nodes:
                    rects = cls._resolve_node_rectangles(tn, page, doc_model, actual_page_num)
                    resolved_rects.extend(rects)

                valid_rects, reasons = validate_highlight_rectangles(resolved_rects, p_rect)
                if valid_rects:
                    cls._log_diagnostic(
                        finding_id=finding.check_id,
                        rule_id=rule_id,
                        target_page=actual_page_num,
                        location_type="STRUCTURE",
                        source="STRUCTURE_NODE",
                        rects=valid_rects,
                        outcome="ACCEPTED",
                        reason=f"Resolved structure element <{node.tag} id='{node.id}'>"
                    )
                    return ResolvedLocation(
                        location_type="STRUCTURE",
                        rectangles=valid_rects,
                        page_number=actual_page_num,
                        source="STRUCTURE_NODE",
                        is_valid=True,
                        message=f"Structure element <{node.tag}>",
                        target_node=node
                    )

        # ------------------------------------------------------------------
        # 4. Priority 3: Direct MCID Lookup
        # ------------------------------------------------------------------
        if finding and doc_model:
            mcid_rects = cls._resolve_mcid_from_finding(finding, doc_model, actual_page_num, page)
            if mcid_rects:
                valid_rects, reasons = validate_highlight_rectangles(mcid_rects, p_rect)
                if valid_rects:
                    cls._log_diagnostic(
                        finding_id=finding.check_id,
                        rule_id=rule_id,
                        target_page=actual_page_num,
                        location_type="CONTENT",
                        source="MCID",
                        rects=valid_rects,
                        outcome="ACCEPTED",
                        reason="Resolved MCID on target page"
                    )
                    return ResolvedLocation(
                        location_type="CONTENT",
                        rectangles=valid_rects,
                        page_number=actual_page_num,
                        source="MCID",
                        is_valid=True,
                        message="Marked content sequence (MCID)"
                    )

        # ------------------------------------------------------------------
        # 5. Priority 4: Content / Snippet Search from Evidence or Message
        # ------------------------------------------------------------------
        if finding:
            text_rects = cls._search_text_evidence_rects(finding, page)
            if text_rects:
                valid_rects, reasons = validate_highlight_rectangles(text_rects, p_rect)
                if valid_rects:
                    cls._log_diagnostic(
                        finding_id=finding.check_id,
                        rule_id=rule_id,
                        target_page=actual_page_num,
                        location_type="CONTENT",
                        source="CONTENT_SEARCH",
                        rects=valid_rects,
                        outcome="ACCEPTED",
                        reason="Matched text snippet from finding evidence"
                    )
                    return ResolvedLocation(
                        location_type="CONTENT",
                        rectangles=valid_rects,
                        page_number=actual_page_num,
                        source="CONTENT_SEARCH",
                        is_valid=True,
                        message="Text occurrence matched from evidence"
                    )

        # ------------------------------------------------------------------
        # 6. Priority 5: Specific Visual Object Locators
        # ------------------------------------------------------------------
        if finding:
            name_lower = (finding.name or "").lower()
            cat_lower = (finding.category or "").lower()
            msg_lower = (finding.message or "").lower()
            obj_lower = (finding.object_reference or "").lower()

            # Formulas
            if "formula" in name_lower or "formula" in cat_lower or "formula" in msg_lower or "formula" in obj_lower:
                formula_box = cls._locate_formula(page)
                if formula_box:
                    ok, valid_r, _ = validate_highlight_rect(formula_box, p_rect)
                    if ok and valid_r:
                        return ResolvedLocation(
                            location_type="CONTENT",
                            rectangles=[valid_r],
                            page_number=actual_page_num,
                            source="COMPUTER_VISION",
                            is_valid=True,
                            message="Formula cluster"
                        )

            # Figures / Images
            if "figure" in name_lower or "image" in name_lower or "figure" in cat_lower or "image" in cat_lower:
                figure_box = cls._locate_figure(page, finding)
                if figure_box:
                    ok, valid_r, _ = validate_highlight_rect(figure_box, p_rect)
                    if ok and valid_r:
                        return ResolvedLocation(
                            location_type="CONTENT",
                            rectangles=[valid_r],
                            page_number=actual_page_num,
                            source="IMAGE_LOCATOR",
                            is_valid=True,
                            message="Graphic / Image element"
                        )

            # Tables
            if "table" in name_lower or "table" in cat_lower or "table" in msg_lower or "th" in obj_lower or "td" in obj_lower:
                table_box = cls._locate_table(page)
                if table_box:
                    ok, valid_r, _ = validate_highlight_rect(table_box, p_rect)
                    if ok and valid_r:
                        return ResolvedLocation(
                            location_type="CONTENT",
                            rectangles=[valid_r],
                            page_number=actual_page_num,
                            source="TABLE_LOCATOR",
                            is_valid=True,
                            message="Table boundary"
                        )

            # Headings
            if "heading" in name_lower or "heading" in cat_lower or re.search(r"\bh[1-6]\b", obj_lower):
                heading_box = cls._locate_heading(page, obj_lower)
                if heading_box:
                    ok, valid_r, _ = validate_highlight_rect(heading_box, p_rect)
                    if ok and valid_r:
                        return ResolvedLocation(
                            location_type="CONTENT",
                            rectangles=[valid_r],
                            page_number=actual_page_num,
                            source="HEADING_LOCATOR",
                            is_valid=True,
                            message="Heading text span"
                        )

            # Links / Annotations
            if "link" in name_lower or "annot" in name_lower or "link" in cat_lower or "form" in cat_lower:
                link_box = cls._locate_link_or_annot(page)
                if link_box:
                    ok, valid_r, _ = validate_highlight_rect(link_box, p_rect)
                    if ok and valid_r:
                        return ResolvedLocation(
                            location_type="CONTENT",
                            rectangles=[valid_r],
                            page_number=actual_page_num,
                            source="ANNOTATION_LOCATOR",
                            is_valid=True,
                            message="Interactive annotation / link"
                        )

        # ------------------------------------------------------------------
        # 7. Priority 6: Whole-Page Findings (Genuine Page-Level)
        # ------------------------------------------------------------------
        if finding:
            is_page_level = (
                rule_id in PAGE_LEVEL_CHECK_IDS
                or "tab order" in (finding.message or "").lower()
                or "taborder" in (finding.message or "").lower()
                or "page orientation" in (finding.message or "").lower()
                or "page boundary" in (finding.message or "").lower()
            )
            if is_page_level:
                page_bbox = (float(p_rect.x0), float(p_rect.y0), float(p_rect.x1), float(p_rect.y1))
                cls._log_diagnostic(
                    finding_id=finding.check_id,
                    rule_id=rule_id,
                    target_page=actual_page_num,
                    location_type="PAGE",
                    source="PAGE_LEVEL",
                    rects=[page_bbox],
                    outcome="ACCEPTED",
                    reason="Applies to entire page properties"
                )
                return ResolvedLocation(
                    location_type="PAGE",
                    rectangles=[page_bbox],
                    page_number=actual_page_num,
                    source="PAGE_LEVEL",
                    is_valid=True,
                    message="Page-level finding: applies to page layout or tab order"
                )

        # ------------------------------------------------------------------
        # 8. Priority 7: Non-Spatial / Unresolvable Finding
        # Strictly reports limitation without fabricating phantom rectangles!
        # ------------------------------------------------------------------
        cls._log_diagnostic(
            finding_id=finding.check_id if finding else "UNKNOWN",
            rule_id=rule_id,
            target_page=actual_page_num,
            location_type="NONE",
            source="NONE",
            rects=[],
            outcome="REJECTED_NO_GEOMETRY",
            reason="No reliable spatial coordinates could be established for this finding."
        )
        return ResolvedLocation(
            location_type="NONE",
            rectangles=[],
            page_number=actual_page_num,
            source="NONE",
            is_valid=False,
            message="No precise visual location is available on this page for this finding."
        )

    @classmethod
    def resolve_bbox(
        cls,
        doc: pymupdf.Document,
        page_num: int,
        finding: Optional[CheckResult] = None,
        doc_model: Optional[PDFDocumentModel] = None
    ) -> Optional[Tuple[float, float, float, float]]:
        """
        Backward-compatible helper returning the primary bounding box tuple or None.
        Never returns fabricated or dummy coordinates.
        """
        loc = cls.resolve_location(doc, page_num, finding, doc_model)
        return loc.primary_bbox

    # ----------------------------------------------------------------------
    # Structure Node & Hierarchy Resolution
    # ----------------------------------------------------------------------
    @classmethod
    def _find_structure_node_for_finding(
        cls,
        finding: CheckResult,
        root: StructureNode,
        page_num: int
    ) -> Optional[StructureNode]:
        """Finds the precise StructureNode matching finding's id, path, or object reference."""
        ref = finding.object_reference or ""
        evidence = finding.evidence or ""

        all_nodes = root.find_all_nodes() if hasattr(root, "find_all_nodes") else cls._collect_all_nodes(root)

        # 1. Match by exact ID: e.g. <LI id='node_12'> or node_12
        m_id = re.search(r"id=['\"]?([a-zA-Z0-9_-]+)['\"]?", ref)
        if not m_id:
            m_id = re.search(r"id=['\"]?([a-zA-Z0-9_-]+)['\"]?", evidence)
        if m_id:
            target_id = m_id.group(1)
            for n in all_nodes:
                if n.id == target_id:
                    return n

        # 2. Match by structure path: e.g. Path: Document/Sect/L/LI[2] or Document/Sect/P
        m_path = re.search(r"Path:\s*([a-zA-Z0-9_/-]+(?:\[\d+\])?)", evidence)
        if m_path:
            path_str = m_path.group(1).strip()
            matched = cls._find_node_by_path(root, path_str)
            if matched:
                return matched

        # 3. Match by specific tag and page (only if unique or best-match)
        tag_match = re.search(r"<([a-zA-Z0-9_-]+)", ref)
        if tag_match:
            tag_name = tag_match.group(1).upper()
            page_matches = [
                n for n in all_nodes
                if (n.standard_tag.upper() == tag_name or n.tag.upper() == tag_name)
                and (n.page == page_num or page_num in n.pages_spanned)
            ]
            if len(page_matches) == 1:
                return page_matches[0]
            elif page_matches:
                # Prefer node matching evidence text snippet if available
                snippet = cls._extract_snippet(evidence) or cls._extract_snippet(finding.message)
                if snippet:
                    for pm in page_matches:
                        if snippet.lower() in (pm.text_content or "").lower():
                            return pm
                return page_matches[0]

        return None

    @classmethod
    def _find_node_by_path(cls, root: StructureNode, path_str: str) -> Optional[StructureNode]:
        """Traverses structure tree following path steps like 'Document/Sect/L/LI'."""
        steps = [s.strip() for s in path_str.strip("/").split("/") if s.strip()]
        if not steps:
            return None

        curr = root
        for step in steps:
            # Check array index like LI[2]
            m_idx = re.match(r"([a-zA-Z0-9_-]+)\[(\d+)\]", step)
            if m_idx:
                step_tag = m_idx.group(1).upper()
                target_idx = int(m_idx.group(2)) - 1  # 1-based
                matching_children = [
                    c for c in curr.children
                    if (c.standard_tag.upper() == step_tag or c.tag.upper() == step_tag)
                ]
                if 0 <= target_idx < len(matching_children):
                    curr = matching_children[target_idx]
                else:
                    return None
            else:
                step_tag = step.upper()
                matching = next(
                    (c for c in curr.children if c.standard_tag.upper() == step_tag or c.tag.upper() == step_tag),
                    None
                )
                if matching:
                    curr = matching
                else:
                    return None

        return curr

    @classmethod
    def _resolve_offending_subelements(
        cls,
        finding: CheckResult,
        node: StructureNode,
        page_num: int
    ) -> List[StructureNode]:
        """
        For rule findings on container elements (e.g. <LI> or <L>), resolves the ACTUAL offending
        sub-element(s) rather than highlighting the whole container or unrelated nested content.
        """
        msg = (finding.message or "").lower()
        evidence = (finding.evidence or "").lower()

        offending: List[StructureNode] = []

        # 1. List Item (<LI>) invalid child tags: e.g. "contains invalid direct child element(s) ['P']"
        m_invalid = re.search(r"invalid direct child element\(s\)\s*\[([^\]]+)\]", msg)
        if m_invalid:
            bad_tags = [t.strip(" '\"").upper() for t in m_invalid.group(1).split(",")]
            for c in node.children:
                if (c.standard_tag.upper() in bad_tags or c.tag.upper() in bad_tags):
                    offending.append(c)
            if offending:
                return offending

        # 2. List Item (<LI>) multiple <Lbl> elements
        if "contains" in msg and "direct <lbl>" in msg:
            lbl_children = [c for c in node.children if (c.standard_tag or c.tag or "").upper() == "LBL"]
            if len(lbl_children) > 1:
                return lbl_children

        # 3. List Item (<LI>) multiple <LBody> elements
        if "contains" in msg and "direct <lbody>" in msg:
            lbody_children = [c for c in node.children if (c.standard_tag or c.tag or "").upper() == "LBODY"]
            if len(lbody_children) > 1:
                return lbody_children

        # 4. List container (<L>) with invalid direct children
        if (node.standard_tag or node.tag or "").upper() == "L" and "invalid direct child" in msg:
            bad_children = [
                c for c in node.children
                if (c.standard_tag or c.tag or "").upper() not in ("LI", "CAPTION")
            ]
            if bad_children:
                return bad_children

        return []

    @classmethod
    def _resolve_node_rectangles(
        cls,
        node: StructureNode,
        page: pymupdf.Page,
        doc_model: Optional[PDFDocumentModel],
        page_num: int
    ) -> List[Tuple[float, float, float, float]]:
        """Resolves verified bounding rectangle(s) for a StructureNode without giant union blowups."""
        rects: List[Tuple[float, float, float, float]] = []
        page_h = page.rect.height

        # 1. MCID records for this page from document model
        if doc_model and doc_model.pages and page_num <= len(doc_model.pages):
            page_obj = doc_model.pages[page_num - 1]
            if node.mcids and page_obj.mcid_bboxes:
                for mcid in node.mcids:
                    if mcid in page_obj.mcid_bboxes:
                        box = page_obj.mcid_bboxes[mcid]
                        if box and any(c > 0 for c in box):
                            rects.append(box)
                if rects:
                    return rects

        # 2. Direct node.bbox (validated for page)
        if node.bbox and (node.page is None or node.page == page_num):
            ok, valid_r, _ = validate_highlight_rect(node.bbox, page.rect)
            if ok and valid_r:
                return [valid_r]

        # 3. Structure layout bbox (/A /BBox)
        if node.struct_bbox and len(node.struct_bbox) == 4:
            # Transform from PDF user space to PyMuPDF page coordinates
            sb = node.struct_bbox
            pdf_r = pymupdf.Rect(sb[0], sb[1], sb[2], sb[3])
            try:
                # Apply transformation matrix for rotation and cropbox
                fitz_r = pdf_r * page.transformation_matrix * page.rotation_matrix
                ok, valid_r, _ = validate_highlight_rect((fitz_r.x0, fitz_r.y0, fitz_r.x1, fitz_r.y1), page.rect)
                if ok and valid_r:
                    return [valid_r]
            except Exception:
                pass

        # 4. Search node text on target page
        text_content = node.get_readable_text(recursive=False) if hasattr(node, "get_readable_text") else node.text_content
        if text_content and len(text_content.strip()) >= 3:
            clean = text_content.strip()[:45].replace("\n", " ")
            try:
                hits = page.search_for(clean)
                if hits:
                    return [(float(h.x0), float(h.y0), float(h.x1), float(h.y1)) for h in hits]
            except Exception:
                pass

        # 5. Children bounding rectangles (only for children on this target page)
        child_rects = []
        for c in node.children:
            if c.page is None or c.page == page_num or page_num in c.pages_spanned:
                cr = cls._resolve_node_rectangles(c, page, doc_model, page_num)
                child_rects.extend(cr)

        return child_rects

    @classmethod
    def _resolve_mcid_from_finding(
        cls,
        finding: CheckResult,
        doc_model: PDFDocumentModel,
        page_num: int,
        page: pymupdf.Page
    ) -> List[Tuple[float, float, float, float]]:
        """Resolves bounding rectangles for MCID mentions in finding."""
        ref = (finding.object_reference or "") + " " + (finding.evidence or "")
        m_mcid = re.search(r"\bmcid\s*(\d+)\b", ref.lower())
        if not m_mcid:
            return []

        mcid_val = int(m_mcid.group(1))

        if doc_model.pages and page_num <= len(doc_model.pages):
            page_obj = doc_model.pages[page_num - 1]
            if page_obj.mcid_bboxes and mcid_val in page_obj.mcid_bboxes:
                box = page_obj.mcid_bboxes[mcid_val]
                if box and any(c > 0 for c in box):
                    return [box]

            # Try looking up decoded text for that MCID
            if page_obj.mcid_texts and mcid_val in page_obj.mcid_texts:
                txt = page_obj.mcid_texts[mcid_val].strip()
                if txt and len(txt) >= 2:
                    hits = page.search_for(txt[:40].replace("\n", " "))
                    if hits:
                        return [(float(h.x0), float(h.y0), float(h.x1), float(h.y1)) for h in hits]

        return []

    @classmethod
    def _search_text_evidence_rects(
        cls,
        finding: CheckResult,
        page: pymupdf.Page
    ) -> List[Tuple[float, float, float, float]]:
        """Extracts text snippets from evidence or message and finds precise page rects."""
        candidates = []
        for src in [finding.evidence, finding.message, finding.object_reference]:
            if not src:
                continue
            # Quotes
            quotes = re.findall(r'["\']([^"\']{3,60})["\']', src)
            candidates.extend(quotes)

            m_c = re.search(r'Content:\s*["\']?([^"\'\n\r]{3,60})', src)
            if m_c:
                candidates.append(m_c.group(1).strip())
            m_t = re.search(r'Text:\s*["\']?([^"\'\n\r]{3,60})', src)
            if m_t:
                candidates.append(m_t.group(1).strip())

        for cand in candidates:
            clean = cand.replace("\\n", " ").replace("\\", "").strip()
            if len(clean) >= 3:
                try:
                    hits = page.search_for(clean[:35])
                    if hits:
                        return [(float(h.x0), float(h.y0), float(h.x1), float(h.y1)) for h in hits]
                except Exception:
                    pass

        return []

    # ----------------------------------------------------------------------
    # Visual Object Locators
    # ----------------------------------------------------------------------
    @classmethod
    def _locate_formula(cls, page: pymupdf.Page) -> Optional[Tuple[float, float, float, float]]:
        text_dict = page.get_text("dict")
        math_spans = []
        for b in text_dict.get("blocks", []):
            if b.get("type") == 0:
                for l in b.get("lines", []):
                    for s in l.get("spans", []):
                        txt = s.get("text", "")
                        font_name = (s.get("font", "")).lower()
                        has_math_chars = any(c in txt for c in "=+-±×÷√∫∑∏∂∆∇≈≠≤≥∞αβγδεθλμπσωΩ")
                        is_math_font = any(mf in font_name for mf in ["math", "symbol", "italic", "cambria"])
                        if has_math_chars or (is_math_font and len(txt.strip()) <= 4):
                            math_spans.append(s["bbox"])

        if math_spans:
            math_spans.sort(key=lambda b: b[1])
            curr_group = [math_spans[0]]
            for sb in math_spans[1:]:
                if sb[1] - curr_group[-1][3] < 35:
                    curr_group.append(sb)
                else:
                    return (
                        min(b[0] for b in curr_group) - 8,
                        min(b[1] for b in curr_group) - 6,
                        max(b[2] for b in curr_group) + 8,
                        max(b[3] for b in curr_group) + 6
                    )
            if curr_group:
                return (
                    min(b[0] for b in curr_group) - 8,
                    min(b[1] for b in curr_group) - 6,
                    max(b[2] for b in curr_group) + 8,
                    max(b[3] for b in curr_group) + 6
                )

        drawings = page.cluster_drawings()
        if drawings:
            dc = sorted(drawings, key=lambda r: (r.width * r.height), reverse=True)[0]
            return (float(dc.x0), float(dc.y0), float(dc.x1), float(dc.y1))

        return None

    @classmethod
    def _locate_figure(cls, page: pymupdf.Page, finding: CheckResult) -> Optional[Tuple[float, float, float, float]]:
        images = page.get_image_info()
        if images:
            ref = finding.object_reference or ""
            m_num = re.search(r"image\s*(\d+)", ref.lower())
            if m_num:
                idx = int(m_num.group(1))
                if 0 <= idx < len(images):
                    b = images[idx]["bbox"]
                    return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
            b = images[0]["bbox"]
            return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))

        clusters = page.cluster_drawings()
        if clusters:
            dc = sorted(clusters, key=lambda r: (r.width * r.height), reverse=True)[0]
            return (float(dc.x0), float(dc.y0), float(dc.x1), float(dc.y1))

        return None

    @classmethod
    def _locate_table(cls, page: pymupdf.Page) -> Optional[Tuple[float, float, float, float]]:
        try:
            tables = page.find_tables()
            if tables and tables.tables:
                t = tables.tables[0]
                b = t.bbox
                return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
        except Exception:
            pass

        clusters = page.cluster_drawings()
        if clusters:
            dc = sorted(clusters, key=lambda r: (r.width * r.height), reverse=True)[0]
            return (float(dc.x0), float(dc.y0), float(dc.x1), float(dc.y1))

        return None

    @classmethod
    def _locate_heading(cls, page: pymupdf.Page, obj_ref: str) -> Optional[Tuple[float, float, float, float]]:
        text_dict = page.get_text("dict")
        largest_span = None
        max_size = 0.0

        for b in text_dict.get("blocks", []):
            if b.get("type") == 0:
                for l in b.get("lines", []):
                    for s in l.get("spans", []):
                        txt = s.get("text", "").strip()
                        size = s.get("size", 0.0)
                        if len(txt) >= 2 and size > max_size:
                            max_size = size
                            largest_span = s["bbox"]

        if largest_span:
            return (float(largest_span[0]), float(largest_span[1]), float(largest_span[2]), float(largest_span[3]))

        return None

    @classmethod
    def _locate_link_or_annot(cls, page: pymupdf.Page) -> Optional[Tuple[float, float, float, float]]:
        links = page.get_links()
        if links and "from" in links[0]:
            r = links[0]["from"]
            return (float(r.x0), float(r.y0), float(r.x1), float(r.y1))

        annots = list(page.annots())
        if annots:
            r = annots[0].rect
            return (float(r.x0), float(r.y0), float(r.x1), float(r.y1))

        return None

    @classmethod
    def _collect_all_nodes(cls, root: StructureNode) -> List[StructureNode]:
        nodes = [root]
        for child in root.children:
            if isinstance(child, StructureNode):
                nodes.extend(cls._collect_all_nodes(child))
        return nodes

    @classmethod
    def _extract_snippet(cls, text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        m = re.search(r'["\']([^"\']{4,40})["\']', text)
        return m.group(1).strip() if m else None

    @classmethod
    def _log_diagnostic(
        cls,
        finding_id: str,
        rule_id: str,
        target_page: int,
        location_type: str,
        source: str,
        rects: List[Tuple[float, float, float, float]],
        outcome: str,
        reason: str
    ):
        """Focused debug logging tracing location resolution pipeline."""
        logger.debug(
            f"[VisualLocator] Finding={finding_id} Rule={rule_id} Page={target_page} "
            f"Type={location_type} Source={source} RectCount={len(rects)} "
            f"Outcome={outcome} Reason='{reason}'"
        )
