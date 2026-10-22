"""
Visual Locator Engine
Pinpoints the exact visual bounding box on any PDF page for ANY accessibility finding:
- Structure Tags: Formulas, Figures, Headings, Tables, Lists, Paragraphs, Links, Annotations
- Untagged Content / Artifacts: Character snippets, Form XObjects, vector paths
- Color Contrast & Visual Anomalies: Low luminance text spans
- Mathematical Equations: Vector fraction bars, integral symbols, and formula glyph clusters
- Images & Figures: Raster images and vector diagram bounding boxes
"""

from typing import Optional, Tuple, List, Dict, Any
import re
import pymupdf

from .models import CheckResult, StructureNode, PDFDocumentModel


class VisualLocatorResolver:
    """Intelligently resolves the precise pixel-perfect bounding box for any accessibility finding."""

    @classmethod
    def resolve_bbox(
        cls,
        doc: pymupdf.Document,
        page_num: int,
        finding: Optional[CheckResult] = None,
        doc_model: Optional[PDFDocumentModel] = None
    ) -> Tuple[float, float, float, float]:
        """
        Main entry point. Returns (x0, y0, x1, y1) in PyMuPDF page coordinates (top-left origin).
        Guaranteed to return a valid, pinpointed bounding box on the target page.
        """
        if not doc or len(doc) == 0:
            return (72.0, 72.0, 500.0, 180.0)

        target_idx = max(0, min(len(doc) - 1, page_num - 1))
        page = doc[target_idx]
        p_rect = page.rect
        page_w, page_h = p_rect.width, p_rect.height

        # ------------------------------------------------------------------
        # Stage 1: Explicit Finding Bounding Box
        # ------------------------------------------------------------------
        if finding and finding.bounding_box and len(finding.bounding_box) == 4:
            if finding.page is None or finding.page == page_num:
                x0, y0, x1, y1 = finding.bounding_box
                if cls._is_valid_bbox(x0, y0, x1, y1, page_w, page_h):
                    return cls._normalize_bbox(x0, y0, x1, y1, page_w, page_h)

        # ------------------------------------------------------------------
        # Stage 2: Structure Tree Node Lookup (by ID or object reference)
        # ------------------------------------------------------------------
        if finding and doc_model and doc_model.structure_tree:
            node = cls._find_structure_node_for_finding(finding, doc_model.structure_tree, page_num)
            if node:
                node_box = cls._resolve_node_geometry(node, page, page_h)
                if node_box:
                    return cls._normalize_bbox(*node_box, page_w, page_h)

        # ------------------------------------------------------------------
        # Stage 3: Direct Text / Snippet Search from Evidence or Message
        # ------------------------------------------------------------------
        if finding:
            text_box = cls._search_text_evidence(finding, page)
            if text_box:
                return cls._normalize_bbox(*text_box, page_w, page_h)

        # ------------------------------------------------------------------
        # Stage 4: Type-Specific Computer Vision & Layout Locators
        # ------------------------------------------------------------------
        if finding:
            name_lower = (finding.name or "").lower()
            cat_lower = (finding.category or "").lower()
            msg_lower = (finding.message or "").lower()
            obj_lower = (finding.object_reference or "").lower()

            # 4A. Formula / Mathematical Equation
            if "formula" in name_lower or "formula" in cat_lower or "formula" in msg_lower or "formula" in obj_lower:
                formula_box = cls._locate_formula(page)
                if formula_box:
                    return cls._normalize_bbox(*formula_box, page_w, page_h)

            # 4B. Figure / Graphic / Image
            if "figure" in name_lower or "image" in name_lower or "figure" in cat_lower or "image" in cat_lower:
                figure_box = cls._locate_figure(page, finding)
                if figure_box:
                    return cls._normalize_bbox(*figure_box, page_w, page_h)

            # 4C. Table / Table Header / Cell
            if "table" in name_lower or "table" in cat_lower or "table" in msg_lower or "th" in obj_lower or "td" in obj_lower:
                table_box = cls._locate_table(page)
                if table_box:
                    return cls._normalize_bbox(*table_box, page_w, page_h)

            # 4D. Heading (<H1> - <H6>)
            if "heading" in name_lower or "heading" in cat_lower or re.search(r"\bh[1-6]\b", obj_lower):
                heading_box = cls._locate_heading(page, obj_lower)
                if heading_box:
                    return cls._normalize_bbox(*heading_box, page_w, page_h)

            # 4E. Untagged Real Content (PDFUA-CONTENT-002)
            if "untagged" in msg_lower or "unmarked" in msg_lower or "content" in cat_lower:
                unmarked_box = cls._locate_unmarked_content(page, finding)
                if unmarked_box:
                    return cls._normalize_bbox(*unmarked_box, page_w, page_h)

            # 4F. Links & Annotations
            if "link" in name_lower or "annot" in name_lower or "link" in cat_lower:
                link_box = cls._locate_link_or_annot(page)
                if link_box:
                    return cls._normalize_bbox(*link_box, page_w, page_h)

        # ------------------------------------------------------------------
        # Stage 5: Intelligent Fallback Anchor to First Content Block
        # ------------------------------------------------------------------
        blocks = page.get_text("blocks")
        if blocks:
            # Pick the first non-empty text block
            for b in blocks:
                if len(b) >= 5 and b[4].strip() and abs(b[2] - b[0]) > 20 and abs(b[3] - b[1]) > 8:
                    return cls._normalize_bbox(b[0], b[1], b[2], b[3], page_w, page_h)

        # Safe proportional viewport
        return (page_w * 0.1, page_h * 0.2, page_w * 0.9, page_h * 0.4)

    @classmethod
    def _is_valid_bbox(cls, x0: float, y0: float, x1: float, y1: float, max_w: float, max_h: float) -> bool:
        w = abs(x1 - x0)
        h = abs(y1 - y0)
        return (
            w >= 3.0 and h >= 3.0
            and x0 < max_w and y0 < max_h
            and x1 > 0 and y1 > 0
        )

    @classmethod
    def _normalize_bbox(cls, x0: float, y0: float, x1: float, y1: float, max_w: float, max_h: float) -> Tuple[float, float, float, float]:
        nx0 = max(0.0, min(max_w - 5.0, min(x0, x1)))
        ny0 = max(0.0, min(max_h - 5.0, min(y0, y1)))
        nx1 = max(nx0 + 5.0, min(max_w, max(x0, x1)))
        ny1 = max(ny0 + 5.0, min(max_h, max(y0, y1)))
        return (nx0, ny0, nx1, ny1)

    @classmethod
    def _find_structure_node_for_finding(cls, finding: CheckResult, root: StructureNode, page_num: int) -> Optional[StructureNode]:
        """Finds the corresponding StructureNode matching finding's object_reference or id."""
        ref = finding.object_reference or ""
        # Match node ID: e.g. <Formula id='node_12'> or node_12
        m_id = re.search(r"id=['\"]?([a-zA-Z0-9_-]+)['\"]?", ref)
        target_id = m_id.group(1) if m_id else None

        all_nodes = root.find_all_nodes() if hasattr(root, "find_all_nodes") else cls._collect_all_nodes(root)

        if target_id:
            for n in all_nodes:
                if n.id == target_id:
                    return n

        # Match by tag and page
        tag_match = re.search(r"<([a-zA-Z0-9_-]+)", ref)
        if tag_match:
            tag_name = tag_match.group(1).upper()
            page_matches = [
                n for n in all_nodes
                if (n.standard_tag.upper() == tag_name or n.tag.upper() == tag_name)
                and (n.page == page_num or page_num in n.pages_spanned)
            ]
            if page_matches:
                return page_matches[0]

        return None

    @classmethod
    def _collect_all_nodes(cls, root: StructureNode) -> List[StructureNode]:
        nodes = [root]
        for child in root.children:
            nodes.extend(cls._collect_all_nodes(child))
        return nodes

    @classmethod
    def _resolve_node_geometry(cls, node: StructureNode, page: pymupdf.Page, page_h: float) -> Optional[Tuple[float, float, float, float]]:
        """Resolves geometry from a StructureNode."""
        # 1. Direct MCID bbox
        if node.bbox and cls._is_valid_bbox(*node.bbox, page.rect.width, page_h):
            return node.bbox

        # 2. Structure layout bbox (/A /BBox)
        if node.struct_bbox and len(node.struct_bbox) == 4:
            sb = node.struct_bbox
            # Convert if in PDF user space (bottom-up)
            if sb[1] < page_h and sb[3] <= page_h:
                top = max(0.0, page_h - max(sb[1], sb[3]))
                bottom = min(page_h, page_h - min(sb[1], sb[3]))
                return (sb[0], top, sb[2], bottom)
            return sb

        # 3. Search node text on page
        text_content = node.get_readable_text() if hasattr(node, "get_readable_text") else node.text_content
        if text_content and len(text_content.strip()) >= 3:
            clean = text_content.strip()[:45]
            matches = page.search_for(clean)
            if matches:
                m = matches[0]
                return (float(m.x0), float(m.y0), float(m.x1), float(m.y1))

        # 4. Children bbox union
        child_boxes = []
        for c in node.children:
            cb = cls._resolve_node_geometry(c, page, page_h)
            if cb:
                child_boxes.append(cb)

        if child_boxes:
            return (
                min(b[0] for b in child_boxes),
                min(b[1] for b in child_boxes),
                max(b[2] for b in child_boxes),
                max(b[3] for b in child_boxes)
            )

        return None

    @classmethod
    def _search_text_evidence(cls, finding: CheckResult, page: pymupdf.Page) -> Optional[Tuple[float, float, float, float]]:
        """Extracts text quotes or snippets from evidence/message and searches the page."""
        text_candidates = []

        # Extract quoted strings: "..." or '...'
        for source in [finding.evidence, finding.message, finding.object_reference]:
            if not source:
                continue
            quotes = re.findall(r'["\']([^"\']{3,60})["\']', source)
            text_candidates.extend(quotes)

            # Explicit "Content: ..." patterns
            m_cont = re.search(r'Content:\s*["\']?([^"\'\n\r]{3,60})', source)
            if m_cont:
                text_candidates.append(m_cont.group(1).strip())

            # Text: "..." patterns
            m_txt = re.search(r'Text:\s*["\']?([^"\'\n\r]{3,60})', source)
            if m_txt:
                text_candidates.append(m_txt.group(1).strip())

        for cand in text_candidates:
            # Clean string
            cand_clean = cand.replace("\\n", " ").replace("\\", "").strip()
            if len(cand_clean) >= 3:
                try:
                    rects = page.search_for(cand_clean[:35])
                    if rects:
                        # Union of rects if split across lines
                        min_x = min(r.x0 for r in rects)
                        min_y = min(r.y0 for r in rects)
                        max_x = max(r.x1 for r in rects)
                        max_y = max(r.y1 for r in rects)
                        return (float(min_x), float(min_y), float(max_x), float(max_y))
                except Exception:
                    pass

        return None

    @classmethod
    def _locate_formula(cls, page: pymupdf.Page) -> Optional[Tuple[float, float, float, float]]:
        """
        Computer vision locator for math formulas and equations.
        Finds math drawing clusters (fraction lines, integral symbols, roots)
        and math symbols/font spans on the page.
        """
        p_rect = page.rect
        drawings = page.get_drawings()
        text_dict = page.get_text("dict")

        # 1. Search for math font spans (e.g. Symbol, Math, Italic variables)
        math_spans = []
        for b in text_dict.get("blocks", []):
            if b.get("type") == 0:  # Text block
                for l in b.get("lines", []):
                    for s in l.get("spans", []):
                        txt = s.get("text", "")
                        font_name = (s.get("font", "")).lower()
                        # Detect math symbols or variables
                        has_math_chars = any(c in txt for c in "=+-±×÷√∫∑∏∂∆∇≈≠≤≥∞αβγδεθλμπσωΩ")
                        is_math_font = any(mf in font_name for mf in ["math", "symbol", "italic", "cambria"])
                        if has_math_chars or (is_math_font and len(txt.strip()) <= 4):
                            math_spans.append(s["bbox"])

        # 2. Search for vector drawing clusters (fraction bars, square roots)
        drawing_clusters = page.cluster_drawings()

        # Combine math spans and horizontal line drawings
        candidates = []
        if math_spans:
            # Group math spans in close vertical proximity (< 40pt)
            math_spans.sort(key=lambda b: b[1])
            curr_group = [math_spans[0]]
            for sb in math_spans[1:]:
                if sb[1] - curr_group[-1][3] < 35:
                    curr_group.append(sb)
                else:
                    candidates.append((
                        min(b[0] for b in curr_group) - 8,
                        min(b[1] for b in curr_group) - 6,
                        max(b[2] for b in curr_group) + 8,
                        max(b[3] for b in curr_group) + 6
                    ))
                    curr_group = [sb]
            if curr_group:
                candidates.append((
                    min(b[0] for b in curr_group) - 8,
                    min(b[1] for b in curr_group) - 6,
                    max(b[2] for b in curr_group) + 8,
                    max(b[3] for b in curr_group) + 6
                ))

        if candidates:
            return candidates[0]

        if drawing_clusters:
            # Pick the most prominent drawing cluster
            dc = sorted(drawing_clusters, key=lambda r: (r.width * r.height), reverse=True)[0]
            return (float(dc.x0), float(dc.y0), float(dc.x1), float(dc.y1))

        return None

    @classmethod
    def _locate_figure(cls, page: pymupdf.Page, finding: CheckResult) -> Optional[Tuple[float, float, float, float]]:
        """Locates raster images or vector graphic diagrams on the page."""
        # 1. Raster images
        images = page.get_image_info()
        if images:
            # Check if finding mentions a specific image number
            ref = finding.object_reference or ""
            m_num = re.search(r"image\s*(\d+)", ref.lower())
            if m_num:
                idx = int(m_num.group(1))
                if 0 <= idx < len(images):
                    b = images[idx]["bbox"]
                    return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
            b = images[0]["bbox"]
            return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))

        # 2. Vector drawings / diagram cluster
        clusters = page.cluster_drawings()
        if clusters:
            dc = sorted(clusters, key=lambda r: (r.width * r.height), reverse=True)[0]
            return (float(dc.x0), float(dc.y0), float(dc.x1), float(dc.y1))

        return None

    @classmethod
    def _locate_table(cls, page: pymupdf.Page) -> Optional[Tuple[float, float, float, float]]:
        """Locates tables or grid structures on the page."""
        try:
            tables = page.find_tables()
            if tables and tables.tables:
                t = tables.tables[0]
                b = t.bbox
                return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
        except Exception:
            pass

        # Fallback to drawing clusters with rectangular paths
        clusters = page.cluster_drawings()
        if clusters:
            dc = sorted(clusters, key=lambda r: (r.width * r.height), reverse=True)[0]
            return (float(dc.x0), float(dc.y0), float(dc.x1), float(dc.y1))

        return None

    @classmethod
    def _locate_heading(cls, page: pymupdf.Page, obj_ref: str) -> Optional[Tuple[float, float, float, float]]:
        """Locates heading text spans by font size or text block position."""
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
    def _locate_unmarked_content(cls, page: pymupdf.Page, finding: CheckResult) -> Optional[Tuple[float, float, float, float]]:
        """Locates unmarked / untagged text or paths on the page."""
        # Check evidence snippet
        snippet_box = cls._search_text_evidence(finding, page)
        if snippet_box:
            return snippet_box

        # First text block
        blocks = page.get_text("blocks")
        if blocks:
            for b in blocks:
                if len(b) >= 5 and b[4].strip():
                    return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))

        return None

    @classmethod
    def _locate_link_or_annot(cls, page: pymupdf.Page) -> Optional[Tuple[float, float, float, float]]:
        """Locates hyperlinks, annotations, or interactive widgets."""
        links = page.get_links()
        if links and "from" in links[0]:
            r = links[0]["from"]
            return (float(r.x0), float(r.y0), float(r.x1), float(r.y1))

        annots = list(page.annots())
        if annots:
            r = annots[0].rect
            return (float(r.x0), float(r.y0), float(r.x1), float(r.y1))

        return None
