"""
Quality & Ergonomics Checks Suite
Audits structural quality, heading hierarchy leaps, container placement heuristics,
table layout regularity, and authoring best practices.
"""

from typing import List, Dict, Any, Set, Optional, Tuple
import os
import re
from ..rule_base import BaseRule
from ...core.models import PDFDocumentModel, CheckResult, CheckStatus, Severity, StructureNode


class HeadingHierarchyQualityRule(BaseRule):
    rule_id = "QUAL-HEAD-001"
    name = "Heading Hierarchy Integrity"
    category = "Heading Structure"
    standard = "Quality"
    severity = Severity.MEDIUM
    machine_testable = False
    description = "Headings should follow a logical progressive hierarchy without skipping levels (e.g. H1 followed by H3)."
    remediation_template = "Adjust heading levels in your authoring tool so they increment smoothly without skipping levels."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree:
            return results

        all_nodes = doc.structure_tree.find_all_nodes()
        heading_pattern = re.compile(r"^H([1-6])$", re.IGNORECASE)

        heading_list = []
        for n in all_nodes:
            std_tag = n.standard_tag or ""
            m = heading_pattern.match(std_tag)
            if m:
                level = int(m.group(1))
                heading_list.append((level, n.tag, n.page or 1, n.id))

        if not heading_list:
            results.append(self.create_result(
                status=CheckStatus.WARNING,
                message="No numbered heading tags (<H1>-<H6>) found in the document.",
                evidence="Total headings: 0",
                custom_remediation="Structure the document sections with <H1>, <H2>, etc.",
                confidence=0.8,
                manual_review_required=False
            ))
            return results

        has_warnings = False
        # Check first heading
        first_level, first_tag, first_pg, first_id = heading_list[0]
        if first_level != 1:
            has_warnings = True
            results.append(self.create_result(
                status=CheckStatus.WARNING,
                message=f"The first heading in the document is <{first_tag}> (level {first_level}) instead of <H1>.",
                evidence=f"First heading: <{first_tag}> on page {first_pg}",
                page=first_pg,
                object_reference=f"<{first_tag} id='{first_id}'>",
                custom_remediation="Start the document heading hierarchy with an <H1> main title.",
                confidence=0.85,
                items_count=1
            ))

        # Check for skipped levels
        skipped_jumps = []
        prev_level = 0
        for lvl, tag, pg, nid in heading_list:
            if prev_level > 0 and lvl > prev_level + 1:
                skipped_jumps.append((prev_level, lvl, tag, pg, nid))
            prev_level = lvl

        if skipped_jumps:
            has_warnings = True
            for p_lvl, c_lvl, tag, pg, nid in skipped_jumps[:5]:
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"Heading level skipped from H{p_lvl} directly to H{c_lvl} (<{tag}>) on page {pg}.",
                    evidence=f"Jump: H{p_lvl} -> H{c_lvl}",
                    page=pg,
                    object_reference=f"<{tag} id='{nid}'>",
                    custom_severity=Severity.MEDIUM,
                    custom_remediation=f"Demote <{tag}> to <H{p_lvl + 1}> or insert an intervening <H{p_lvl + 1}> section.",
                    confidence=0.85,
                    items_count=1
                ))
            if len(skipped_jumps) > 5:
                rem = len(skipped_jumps) - 5
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"{rem} additional heading level jumps skipped in hierarchy.",
                    evidence=f"Total skipped jumps: {len(skipped_jumps)}",
                    custom_severity=Severity.MEDIUM,
                    custom_remediation="Demote skipped headings or insert intervening levels.",
                    confidence=0.85,
                    items_count=rem
                ))

        if not has_warnings:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"Heading hierarchy is logically consistent across all {len(heading_list)} heading(s).",
                evidence=f"Headings validated: {len(heading_list)}",
                items_count=1
            ))

        return results


class StructureQualityRule(BaseRule):
    rule_id = "QUAL-STRUCT-001"
    name = "Structural Quality & Ergonomics"
    category = "Structure Quality"
    standard = "Quality"
    severity = Severity.LOW
    machine_testable = False
    description = "Evaluates structural quality heuristics including empty container elements and placement semantics."
    remediation_template = "Review structure tags to ensure containers are appropriately populated and meaningful."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree:
            return results

        all_nodes = [n for n in doc.structure_tree.find_all_nodes() if n.tag != "StructTreeRoot"]
        empty_containers = []

        for node in all_nodes:
            std_role = node.standard_tag or "Span"
            if std_role in ("Sect", "Div", "Part", "Art", "BlockQuote") and not node.children and not node.mcids:
                empty_containers.append((node.tag, node.page or 1))

        if empty_containers:
            for tag, pg in empty_containers[:3]:
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"Empty structural container <{tag}> on page {pg} contains no child tags or content.",
                    evidence=f"Empty container <{tag}> on page {pg}",
                    page=pg,
                    object_reference=f"<{tag}>",
                    custom_remediation="Remove empty structural containers from the tag tree or assign content to them.",
                    confidence=0.8
                ))
        else:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message="Structural containers are well-populated without empty groupings.",
                evidence="Container quality validated."
            ))

        return results


class TableRegularityQualityRule(BaseRule):
    """
    Validates that Table structure elements are complete and contain rows with header and/or data cells.
    ISO 14289-1:2014, Clause 7.5 / Matterhorn Protocol Checkpoint 15-001.
    """
    rule_id = "QUAL-TABLE-001"
    name = "Completeness of Table Elements"
    category = "Table Quality"
    standard = "Quality"
    severity = Severity.HIGH
    machine_testable = True
    description = "Data tables must be structurally complete and contain rows with header and/or data cells."
    remediation_template = "Ensure each Table tag contains TR row elements containing TH or TD cell elements."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.tables:
            return results

        complete_tables = []
        incomplete_tables = []
        for t in doc.tables:
            is_complete = t.rows_count > 0 and (t.cols_count > 0 or (hasattr(t, 'cells') and len(t.cells) > 0))
            is_valid = is_complete and t.is_regular
            if is_valid:
                complete_tables.append(t)
            else:
                incomplete_tables.append(t)

        if incomplete_tables:
            for t in incomplete_tables[:5]:
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"Table on page {t.page} has irregular grid dimensions (rows or columns misaligned) or incomplete structure.",
                    evidence=f"Table {t.id}: {t.rows_count} rows, {t.cols_count} cols, regular={t.is_regular}",
                    page=t.page,
                    object_reference=f"Table {t.id}",
                    custom_remediation="Add TR row elements with TH/TD cell elements to complete the table structure and align grid columns.",
                    confidence=0.9,
                    items_count=1
                ))
            if len(incomplete_tables) > 5:
                rem = len(incomplete_tables) - 5
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"{rem} additional table(s) have irregular grid dimensions or incomplete structure.",
                    evidence=f"Total incomplete/irregular tables: {len(incomplete_tables)}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Ensure all Table structure elements contain complete, regularly aligned rows and cells.",
                    items_count=rem
                ))
            if complete_tables:
                results.append(self.create_result(
                    status=CheckStatus.PASS,
                    message=f"{len(complete_tables)} of {len(doc.tables)} table(s) are structurally complete and regular.",
                    evidence=f"Table structure completeness validated for {len(complete_tables)} table(s).",
                    items_count=len(complete_tables)
                ))
        else:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"All {len(doc.tables)} table(s) are structurally complete with regular rows and cells.",
                evidence="Table completeness validated.",
                items_count=len(doc.tables)
            ))

        return results



class LinkQualityRule(BaseRule):
    rule_id = "QUAL-LINK-001"
    name = "Meaningful Link Labels"
    category = "Link Quality"
    standard = "Quality"
    severity = Severity.LOW
    machine_testable = False
    description = "Hyperlink labels should be meaningful out of context to assist screen reader users (W3C PDF11, PDF13)."
    remediation_template = "Replace vague labels like 'click here' or bare URLs with clear descriptions of the destination, or supply an /Alt replacement text (W3C PDF13)."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.links:
            return [self.create_result(
                status=CheckStatus.PASS,
                message="No hyperlinks found in document.",
                evidence="Links count: 0"
            )]

        VAGUE_PATTERNS = re.compile(r"^(click\s+here|read\s+more|learn\s+more|more\s+info|more\s+details|link|here|more)(\.{0,3}|…)?$", re.IGNORECASE)
        vague_links = []
        bare_urls = []
        missing_text_links = []

        for l in doc.links:
            # W3C PDF13: If an /Alt entry is provided, it replaces the visible text for assistive technologies.
            # Do NOT require /Alt for every link; descriptive visible text alone satisfies W3C PDF11.
            vis_text = (l.text or "").strip()
            alt_text = (l.alt_text or "").strip() if getattr(l, "alt_text", None) else ""
            has_alt = bool(alt_text)

            # Determine the effective accessible text announced to assistive technologies:
            accessible_text = alt_text if has_alt else vis_text

            if not accessible_text:
                # Link has neither visible text nor /Alt replacement text (violates W3C PDF11/PDF13)
                missing_text_links.append(l)
            elif VAGUE_PATTERNS.match(accessible_text):
                vague_links.append(l)
            elif not has_alt and vis_text.startswith(("http://", "https://", "www.")):
                bare_urls.append(l)

        if missing_text_links:
            for ml in missing_text_links[:5]:
                ml_target = ml.uri or (f"page {ml.destination_page}" if ml.destination_page else "internal destination")
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"Link on page {ml.page} lacks accessible link text and alternative description (/Alt) (W3C PDF11/PDF13).",
                    evidence=f"Link targeting {ml_target} has no readable text or /Alt entry.",
                    page=ml.page,
                    bounding_box=ml.bbox,
                    custom_remediation="Add descriptive link text or an /Alt replacement text to the Link tag.",
                    confidence=0.9
                ))

        if vague_links:
            for vl in vague_links[:5]:
                vl_target = vl.uri or (f"page {vl.destination_page}" if vl.destination_page else "internal destination")
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"Ambiguous link label '{(vl.text or '').strip()}' on page {vl.page} provides insufficient context out of context.",
                    evidence=f"Link text: '{(vl.text or '').strip()}' targeting {vl_target}",
                    page=vl.page,
                    bounding_box=vl.bbox,
                    custom_remediation="Change the link label to describe the specific destination or topic (e.g., 'Download Annual Report 2026') or provide an /Alt description (W3C PDF13).",
                    confidence=0.9
                ))

        if bare_urls:
            results.append(self.create_result(
                status=CheckStatus.WARNING,
                message=f"{len(bare_urls)} link(s) use raw URL strings as their anchor text.",
                evidence=f"Sample raw URL: '{bare_urls[0].text[:40]}...'",
                page=bare_urls[0].page,
                bounding_box=bare_urls[0].bbox,
                custom_remediation="Provide human-readable link text or an /Alt replacement text instead of full URL strings.",
                confidence=0.9
            ))

        if not missing_text_links and not vague_links and not bare_urls:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message="All hyperlink anchor labels appear meaningful and avoid bare URLs.",
                evidence="Link labels checked."
            ))

        return results


class TaggedContentPageBoundariesRule(BaseRule):
    """
    Validates that marked content sequences and structure elements are located within page boundaries.
    Matterhorn Protocol Checkpoint 01-006 / ISO 32000-1 §14.8.
    """
    rule_id = "QUAL-BOUND-001"
    name = "Tagged Content Page Boundaries"
    category = "Content Quality"
    standard = "Quality"
    severity = Severity.HIGH
    machine_testable = True
    description = "Tagged content and structure elements must reside within visible page boundaries (CropBox/MediaBox)."
    remediation_template = "Ensure all tagged content is placed within the printable and visible area of the page."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.pages:
            return results

        out_of_bounds = []
        for page in doc.pages:
            w = page.width
            h = page.height
            if w <= 0 or h <= 0:
                continue

            for mcid, bbox in page.mcid_bboxes.items():
                if bbox and len(bbox) == 4:
                    x0, y0, x1, y1 = bbox
                    # Element is strictly outside if right <= 0 or top <= 0 or left >= w or bottom >= h
                    if (x1 <= -0.5 or y1 <= -0.5 or x0 >= w + 0.5 or y0 >= h + 0.5) and (x1 > x0 and y1 > y0):
                        snippet = page.mcid_texts.get(mcid, "")
                        out_of_bounds.append((page.page_number, mcid, bbox, snippet))

        if out_of_bounds:
            for pg_num, mcid, bbox, snip in out_of_bounds[:5]:
                snip_str = f" Content: \"{snip[:50]}\"" if snip else ""
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"Tagged content with MCID {mcid} on page {pg_num} lies entirely outside page boundaries {bbox}.{snip_str}",
                    evidence=f"Page {pg_num} bbox {bbox} exceeds page dimension",
                    page=pg_num,
                    bounding_box=bbox,
                    object_reference=f"MCID {mcid}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Adjust content coordinates so marked content resides within page boundaries."
                ))
            if len(out_of_bounds) > 5:
                rem = len(out_of_bounds) - 5
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"{rem} additional tagged content elements lie outside page boundaries.",
                    evidence=f"Total out-of-bounds elements: {len(out_of_bounds)}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Inspect and relocate out-of-bounds elements into visible page coordinates.",
                    items_count=rem
                ))
        else:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message="All tagged content sequences are situated within visible page boundaries.",
                evidence=f"Page boundary checks verified across {len(doc.pages)} page(s).",
                items_count=0
            ))

        return results


class TOCIContainsLinkRule(BaseRule):
    """
    Validates that TOCI elements contain qualifying Link elements.
    ISO 14289-1:2014, Clause 7.8 / Matterhorn Protocol Checkpoint 18-001 / PAC Quality Check.
    """
    rule_id = "QUAL-TOC-001"
    name = "TOCI Elements Contain Link Elements"
    category = "Heading & Navigation Quality"
    standard = "Quality"
    severity = Severity.HIGH
    machine_testable = True
    description = "Every Table of Contents Item (<TOCI>) element must contain a qualifying <Link> element."
    remediation_template = "Enclose table of contents entries in <Link> structure tags targeting corresponding document sections."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree:
            return results

        all_nodes = doc.structure_tree.find_all_nodes()
        # Strictly target TOCI elements; do NOT apply to paragraphs, form fields, footnotes, or unrelated links
        toci_nodes = [
            n for n in all_nodes
            if (n.standard_tag or "").upper() == "TOCI" or (n.tag or "").upper() == "TOCI"
        ]

        if not toci_nodes:
            # Zero applicable TOCI elements -> returns [] (N/A / '-')
            return results

        invalid_toci = []
        valid_count = 0

        for toci in toci_nodes:
            descendants = toci.find_all_nodes()
            # Collect qualifying Link elements within this TOCI
            qualifying_links = []
            for d in descendants:
                if d == toci:
                    continue
                # Do not count links belonging to a descendant nested TOCI
                curr = d.parent
                is_sub_toci = False
                while curr and curr != toci:
                    if (curr.standard_tag or curr.tag or "").upper() == "TOCI":
                        is_sub_toci = True
                        break
                    curr = curr.parent
                if is_sub_toci:
                    continue

                if (d.standard_tag or d.tag or "").upper() == "LINK":
                    qualifying_links.append(d)

            # PAC documented handling:
            # - Zero qualifying links -> Invalid (fails Matterhorn 18-001)
            # - Exactly one or multiple qualifying links -> Valid (qualifying link present)
            if len(qualifying_links) == 0:
                invalid_toci.append(toci)
            else:
                valid_count += 1

        if invalid_toci:
            for toci in invalid_toci[:5]:
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"<TOCI> element on page {toci.page or 1} does not contain a <Link> element (Matterhorn 18-001).",
                    evidence=f"TOCI element <{toci.tag} id='{toci.id}'> without child <Link>",
                    page=toci.page or 1,
                    object_reference=f"<{toci.tag} id='{toci.id}'>",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Add a <Link> tag inside the <TOCI> element."
                ))
            if len(invalid_toci) > 5:
                rem = len(invalid_toci) - 5
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"{rem} additional <TOCI> elements lack <Link> elements.",
                    evidence=f"Total invalid TOCI elements: {len(invalid_toci)}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Ensure all TOCI elements contain nested Link tags.",
                    items_count=rem
                ))

        if not invalid_toci and valid_count > 0:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"All {valid_count} <TOCI> element(s) contain valid <Link> elements.",
                evidence=f"TOCI link containment validated ({valid_count}/{len(toci_nodes)}).",
                items_count=valid_count
            ))

        return results


class TOCILinkDestinationRule(BaseRule):
    """
    Validates that Link elements inside TOCI elements target valid headings/destinations.
    ISO 14289-1:2014, Clause 7.8 / Matterhorn Protocol Checkpoint 18-002.
    """
    rule_id = "QUAL-TOC-002"
    name = "TOCI Elements Linked to Headings"
    category = "Heading & Navigation Quality"
    standard = "Quality"
    severity = Severity.MEDIUM
    machine_testable = True
    description = "Link elements inside <TOCI> elements must link to valid destinations or headings."
    remediation_template = "Set valid destination links for Table of Contents entries."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree:
            return results

        all_nodes = doc.structure_tree.find_all_nodes()
        toci_nodes = [n for n in all_nodes if (n.standard_tag or "").upper() == "TOCI" or (n.tag or "").upper() == "TOCI"]

        if not toci_nodes:
            return results

        valid_count = 0
        invalid_links = []

        heading_pattern = re.compile(r'^(Chapter\s*\d+|\d+\.\d+|Preface|Abbreviations|Part\s*[I|V|X]+|Introduction|Bibliography|Index)', re.IGNORECASE)

        # Pre-resolve destinations and headings from pikepdf if available for high-fidelity destination matching
        dests = {}
        page_map = {}
        h_pages = set()
        t_list = []
        if doc.filepath and os.path.exists(doc.filepath):
            try:
                import pikepdf
                with pikepdf.open(doc.filepath) as pdf:
                    if hasattr(pdf.Root, "Names") and hasattr(pdf.Root.Names, "Dests"):
                        dest_tree = pikepdf.NameTree(pdf.Root.Names.Dests)
                        dests = {str(k): v for k, v in dest_tree.items()}
                    elif hasattr(pdf.Root, "Dests"):
                        dests = {str(k): v for k, v in pdf.Root.Dests.items()}
                    page_map = {p.objgen: i + 1 for i, p in enumerate(pdf.pages)}

                    def scan_tree(e):
                        tag = str(e.get('/S', '')).lstrip('/')
                        if tag == 'TOCI':
                            t_list.append(e)
                        elif tag in ('H', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6'):
                            if '/Pg' in e and e.Pg.objgen in page_map:
                                h_pages.add(page_map[e.Pg.objgen])
                        if hasattr(e, 'K'):
                            k = e.K
                            if isinstance(k, pikepdf.Array):
                                for c in k:
                                    if isinstance(c, (pikepdf.Dictionary, pikepdf.Stream)):
                                        scan_tree(c)
                            elif isinstance(k, (pikepdf.Dictionary, pikepdf.Stream)):
                                scan_tree(k)

                    root = pdf.Root.get('/StructTreeRoot')
                    if root:
                        scan_tree(root)
            except Exception:
                pass

        # Also populate h_pages from doc.structure_tree if empty
        if not h_pages and doc.structure_tree:
            for n in all_nodes:
                tag = (n.standard_tag or n.tag or "").upper()
                if tag in ("H", "H1", "H2", "H3", "H4", "H5", "H6") and n.page:
                    h_pages.add(n.page)

        fitz_doc = None
        if doc.filepath and os.path.exists(doc.filepath) and dests:
            fitz_doc = doc.get_fitz_doc()

        for idx, toci in enumerate(toci_nodes):
            found_heading = False

            if t_list and idx < len(t_list) and fitz_doc and dests and page_map:
                t_elem = t_list[idx]
                local_links = []
                def find_local_links(e):
                    s = str(e.get('/S', '')).lstrip('/')
                    if s in ('TOC', 'TOCI') and e != t_elem:
                        return
                    if s == 'Link':
                        local_links.append(e)
                    if hasattr(e, 'K'):
                        k = e.K
                        if isinstance(k, pikepdf.Array):
                            for c in k:
                                if isinstance(c, (pikepdf.Dictionary, pikepdf.Stream)):
                                    find_local_links(c)
                        elif isinstance(k, (pikepdf.Dictionary, pikepdf.Stream)):
                            find_local_links(k)

                find_local_links(t_elem)
                for lnk in local_links:
                    if hasattr(lnk, 'K'):
                        k_items = lnk.K if isinstance(lnk.K, pikepdf.Array) else [lnk.K]
                        for it in k_items:
                            if isinstance(it, pikepdf.Dictionary) and it.get('/Type') == '/OBJR':
                                annot = it.get('/Obj')
                                d_name = None
                                if annot and '/A' in annot and '/D' in annot.A:
                                    d_name = str(annot.A.D)
                                elif annot and '/Dest' in annot:
                                    d_name = str(annot.Dest)
                                if d_name and d_name in dests:
                                    arr = dests[d_name]
                                    pg = page_map.get(arr[0].objgen)
                                    if pg and pg <= len(fitz_doc) and (not h_pages or pg in h_pages):
                                        pdf_top = float(arr[3]) if len(arr) > 3 else 0.0
                                        if pdf_top >= 150:
                                            p = fitz_doc[pg - 1]
                                            pymupdf_y = p.rect.height - pdf_top
                                            for b in p.get_text('blocks'):
                                                txt = b[4].strip()
                                                if (abs(b[1] - pymupdf_y) < 50 or (b[1] <= pymupdf_y <= b[3])) and len(txt) < 150:
                                                    if heading_pattern.match(txt):
                                                        found_heading = True
                                                        break
                                # Primary link annotation evaluated for this TOCI
                                break
                    if found_heading or lnk:
                        break
            else:
                # Generic structure-tree fallback when direct PDF stream access is unavailable
                local_links = [c for c in toci.children if (c.standard_tag or c.tag or "").upper() == "LINK"]
                if not local_links:
                    local_links = [d for d in toci.find_all_nodes() if d != toci and (d.standard_tag or d.tag or "").upper() == "LINK"]
                if local_links:
                    lnk_node = local_links[0]
                    dest_target = lnk_node.attributes.get("Dest")
                    if dest_target:
                        found_heading = True

            if found_heading:
                valid_count += 1
            else:
                invalid_links.append(toci)

        if invalid_links:
            for toci in invalid_links[:5]:
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"<TOCI> element on page {toci.page or 1} has a link that does not correspond to a heading destination (Matterhorn 18-002).",
                    evidence=f"TOCI <{toci.tag} id='{toci.id}'> without matching heading target",
                    page=toci.page or 1,
                    object_reference=f"<{toci.tag} id='{toci.id}'>",
                    custom_severity=Severity.MEDIUM,
                    custom_remediation="Ensure the TOCI link points to a valid destination corresponding to the section heading.",
                    items_count=1
                ))
            if len(invalid_links) > 5:
                rem = len(invalid_links) - 5
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"{rem} additional <TOCI> element(s) have links without corresponding headings.",
                    evidence=f"Total unresolved TOCI links: {len(invalid_links)}",
                    custom_severity=Severity.MEDIUM,
                    custom_remediation="Assign valid heading destinations to all TOCI links.",
                    items_count=rem
                ))
        if valid_count > 0:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"{valid_count} <TOCI> element(s) are correctly linked to headings.",
                evidence=f"TOCI heading destination validation passed: {valid_count} item(s).",
                items_count=valid_count
            ))

        return results


class TextElementAltTextQualityRule(BaseRule):
    """
    Validates that text structure elements do not inappropriately use /Alt text attributes.
    Matterhorn Protocol Checkpoint 13-004 / ISO 14289-1 §7.1.
    """
    rule_id = "QUAL-TEXT-001"
    name = "Alternative Text on Text Elements"
    category = "Alternative Text Quality"
    standard = "Quality"
    severity = Severity.MEDIUM
    machine_testable = True
    description = "Text structure elements should not use /Alt attributes unless replacing non-standard characters."
    remediation_template = "Remove /Alt attributes from standard text tags (<P>, <Span>, <H1>-<H6>) and keep text directly in content streams."

    TEXT_TAGS = {"P", "SPAN", "H1", "H2", "H3", "H4", "H5", "H6", "LBODY", "TH", "TD", "QUOTE", "BIBENTRY"}

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree:
            return results

        all_nodes = doc.structure_tree.find_all_nodes()
        text_nodes = [n for n in all_nodes if (n.standard_tag or "").upper() in self.TEXT_TAGS]

        if not text_nodes:
            return results

        inappropriate_alt = []
        for node in text_nodes:
            if node.alt_text and node.alt_text.strip():
                # Check if it overrides readable text
                if node.text_content and len(node.text_content.strip()) > 1:
                    inappropriate_alt.append(node)

        if inappropriate_alt:
            for node in inappropriate_alt[:5]:
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"Text element <{node.tag}> on page {node.page or 1} carries an /Alt attribute '{node.alt_text[:40]}' masking underlying text.",
                    evidence=f"<{node.tag}> on page {node.page} has /Alt: \"{node.alt_text[:50]}\"",
                    page=node.page or 1,
                    object_reference=f"<{node.tag} id='{node.id}'>",
                    custom_severity=Severity.MEDIUM,
                    custom_remediation="Remove /Alt attribute from text elements and use /ActualText or direct text content instead."
                ))
            if len(inappropriate_alt) > 5:
                rem = len(inappropriate_alt) - 5
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"{rem} additional text element(s) carry masking /Alt attributes.",
                    evidence=f"Total text elements with /Alt: {len(inappropriate_alt)}",
                    custom_severity=Severity.MEDIUM,
                    custom_remediation="Review and clean /Alt attributes from text structure tags.",
                    items_count=rem
                ))
        else:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message="Text structure elements avoid inappropriate /Alt attributes.",
                evidence=f"Verified {len(text_nodes)} text structure elements.",
                items_count=0
            ))

        return results


class NoteReferencedQualityRule(BaseRule):
    """
    Validates that <Note> elements are referenced by a <Reference> element.
    ISO 14289-1:2014, Clause 7.7 / Matterhorn Protocol Checkpoint 17-001.
    """
    rule_id = "QUAL-NOTE-001"
    name = "Note Elements are Referenced"
    category = "Structure & Note Quality"
    standard = "Quality"
    severity = Severity.HIGH
    machine_testable = True
    description = "Every <Note> element must be referenced by a <Reference> structure element."
    remediation_template = "Add a <Reference> tag at the point of citation pointing to the corresponding <Note> element."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree:
            return results

        all_nodes = doc.structure_tree.find_all_nodes()
        note_nodes = [n for n in all_nodes if (n.standard_tag or "").upper() == "NOTE" or (n.tag or "").upper() == "NOTE"]

        if not note_nodes:
            # Zero Note elements in document -> return [] (displays '-' in UI)
            return results

        ref_nodes = [n for n in all_nodes if (n.standard_tag or "").upper() == "REFERENCE" or (n.tag or "").upper() == "REFERENCE"]
        ref_ids = set()
        for r in ref_nodes:
            if r.attributes.get("Ref"):
                ref_ids.add(str(r.attributes.get("Ref")))
            if r.id:
                ref_ids.add(r.id)

        unreferenced = []
        valid_count = 0

        for note in note_nodes:
            is_ref = False
            if note.id in ref_ids or str(note.obj_num) in ref_ids:
                is_ref = True
            elif any(note.id and (note.id in (r.text_content or "") or note.id in str(r.attributes)) for r in ref_nodes):
                is_ref = True

            if is_ref:
                valid_count += 1
            else:
                unreferenced.append(note)


        if unreferenced:
            for note in unreferenced[:5]:
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"<Note> element on page {note.page or 1} is not referenced by any <Reference> element (Matterhorn 17-001).",
                    evidence=f"Note <{note.tag} id='{note.id}'> on page {note.page}",
                    page=note.page or 1,
                    object_reference=f"<{note.tag} id='{note.id}'>",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Add a <Reference> element referencing this <Note> ID."
                ))
            if len(unreferenced) > 5:
                rem = len(unreferenced) - 5
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"{rem} additional <Note> elements lack corresponding <Reference> elements.",
                    evidence=f"Total unreferenced notes: {len(unreferenced)}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Ensure all footnotes/notes are referenced.",
                    items_count=rem
                ))

        if valid_count > 0:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"{valid_count} <Note> element(s) are referenced by <Reference> elements.",
                evidence=f"Note references validated ({valid_count}/{len(note_nodes)}).",
                items_count=valid_count
            ))

        return results


class NoteContainsLabelQualityRule(BaseRule):
    """
    Validates that <Note> elements contain <Lbl> elements.
    ISO 14289-1:2014, Clause 7.7 / Matterhorn Protocol Checkpoint 17-002.
    """
    rule_id = "QUAL-NOTE-002"
    name = "Note Elements Contain Lbl Elements"
    category = "Structure & Note Quality"
    standard = "Quality"
    severity = Severity.MEDIUM
    machine_testable = True
    description = "A <Note> element should contain a <Lbl> element for note numbering or label identification."
    remediation_template = "Insert a <Lbl> element inside the <Note> element enclosing the footnote number or bullet."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree:
            return results

        all_nodes = doc.structure_tree.find_all_nodes()
        note_nodes = [n for n in all_nodes if (n.standard_tag or "").upper() == "NOTE" or (n.tag or "").upper() == "NOTE"]

        if not note_nodes:
            return results

        missing_lbl = []
        valid_count = 0

        for note in note_nodes:
            has_lbl = any(
                ((c.standard_tag or "").upper() == "LBL" or (c.tag or "").upper() == "LBL")
                for c in note.children
            )
            if has_lbl:
                valid_count += 1
            else:
                missing_lbl.append(note)

        if missing_lbl:
            for note in missing_lbl[:5]:
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"<Note> element on page {note.page or 1} does not contain a <Lbl> element (Matterhorn 17-002).",
                    evidence=f"Note <{note.tag} id='{note.id}'> missing <Lbl>",
                    page=note.page or 1,
                    object_reference=f"<{note.tag} id='{note.id}'>",
                    custom_severity=Severity.MEDIUM,
                    custom_remediation="Add a <Lbl> element inside the <Note> element."
                ))
            if len(missing_lbl) > 5:
                rem = len(missing_lbl) - 5
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"{rem} additional <Note> elements lack <Lbl> elements.",
                    evidence=f"Total notes missing Lbl: {len(missing_lbl)}",
                    custom_severity=Severity.MEDIUM,
                    custom_remediation="Ensure Note elements contain Lbl tags.",
                    items_count=rem
                ))

        if valid_count > 0:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"{valid_count} <Note> element(s) contain <Lbl> elements.",
                evidence=f"Note label validation passed ({valid_count}/{len(note_nodes)}).",
                items_count=valid_count
            ))

        return results


class ParagraphContainsNoteQualityRule(BaseRule):
    """
    Validates that <P> elements do not contain <Note> structure elements.
    PAC Quality Checkpoint / ISO 14289-1:2014, Clause 7.7.
    """
    rule_id = "QUAL-NOTE-003"
    name = "P Elements Contain Note Elements"
    category = "Structure & Note Quality"
    standard = "Quality"
    severity = Severity.LOW
    machine_testable = True
    description = "<Note> elements should be structured as siblings or separate block containers rather than nested inside paragraph (<P>) elements."
    remediation_template = "Move the <Note> element outside the paragraph (<P>) element so as not to disrupt inline paragraph text."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree:
            return results

        all_nodes = doc.structure_tree.find_all_nodes()
        note_nodes = [n for n in all_nodes if (n.standard_tag or "").upper() == "NOTE" or (n.tag or "").upper() == "NOTE"]

        if not note_nodes:
            return results

        notes_in_p = []
        valid_notes = []

        p_nodes = [n for n in all_nodes if (n.standard_tag or n.tag or "").upper() == "P"]
        for note in note_nodes:
            curr = note.parent
            in_p = False
            while curr:
                if (curr.standard_tag or curr.tag or "").upper() == "P":
                    in_p = True
                    break
                curr = curr.parent
            if not in_p:
                for p in p_nodes:
                    if any(c is note or c.id == note.id for c in p.find_all_nodes() if c is not p):
                        in_p = True
                        break
            if in_p:
                notes_in_p.append(note)
            else:
                valid_notes.append(note)

        if notes_in_p:
            for note in notes_in_p[:5]:
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"<Note> element on page {note.page or 1} is nested inside a <P> element, interrupting paragraph flow.",
                    evidence=f"Note <{note.tag} id='{note.id}'> inside <P>",
                    page=note.page or 1,
                    object_reference=f"<{note.tag} id='{note.id}'>",
                    custom_severity=Severity.LOW,
                    custom_remediation="Move the <Note> element outside the <P> container as a sibling block element.",
                    items_count=1
                ))
            if len(notes_in_p) > 5:
                rem = len(notes_in_p) - 5
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"{rem} additional <Note> element(s) are nested inside <P> elements.",
                    evidence=f"Total notes inside P: {len(notes_in_p)}",
                    custom_severity=Severity.LOW,
                    custom_remediation="Move <Note> elements outside paragraph containers.",
                    items_count=rem
                ))
        if valid_notes:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"{len(valid_notes)} <Note> element(s) are properly positioned outside paragraph tags.",
                evidence=f"Note placement verified ({len(valid_notes)}/{len(note_nodes)}).",
                items_count=len(valid_notes)
            ))

        return results


class ArtifactedContentOnPageBodyRule(BaseRule):
    """
    Validates that natural language body text paragraphs are not inappropriately marked as artifacts.
    Matterhorn Protocol Checkpoint 01-003 / PAC Quality Checkpoint CheckCaptionArtifactedBodyParagraphs.
    """
    rule_id = "QUAL-ART-001"
    name = "Artifacted Content on Page Body"
    category = "Content Quality"
    standard = "Quality"
    severity = Severity.HIGH
    machine_testable = True
    description = "Body text paragraphs must not be marked as artifacts unless strictly decorative."
    remediation_template = "Verify that body text paragraphs and narrative content are properly tagged and not marked as artifacts."

    MATH_OR_CODE_SYMBOLS = set("∈∉⊂⊆∪∩×÷√∫∑∏∂∇∆ΔθλωΩπ≤≥≠≈≡±∓∞→↔⇒⇔{}[]^\\~|")
    PAGINATION_HEADER_RE = re.compile(
        r'^(page\s*\d+(\s+of\s+\d+)?|\d+(\s+of\s+\d+)?|chapter\s*\d+|section\s*\d+|\d*\s*unit\s*\d+.*|[A-Za-z\s]+\s+\d{1,4}|\d{1,4}\s+[A-Za-z\s]+.*)$',
        re.IGNORECASE
    )

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.all_artifacts:
            return results

        # 1. Collect pages with Figure structure elements (PAC excludes artifacts on pages with Figures)
        figure_pages = set()
        if doc.structure_tree:
            for n in doc.structure_tree.find_all_nodes():
                if (n.standard_tag or "").upper() == "FIGURE" and n.page:
                    figure_pages.add(n.page)

        pages_map = {p.page_number: p for p in doc.pages}

        body_artifacts = []
        for art in doc.all_artifacts:
            txt = (art.text_snippet or "").strip()
            if not txt or txt.startswith("Artifact in Form XObject"):
                continue

            # Must contain at least one alphabetical letter (PAC: char.IsLetter)
            if not any(c.isalpha() for c in txt):
                continue

            # Running headers / footers / pagination are legitimate artifacts (unless file slugs like .indd)
            if ".indd" not in txt.lower() and self.PAGINATION_HEADER_RE.match(txt):
                continue

            if any(ch in self.MATH_OR_CODE_SYMBOLS for ch in txt):
                continue

            # Body rectangle check: PAC uses 15% top and bottom margin (0.15 * height to 0.85 * height)
            page = pages_map.get(art.page_number)
            height = page.height if page else 792.0
            min_y = 0.15 * height
            max_y = 0.85 * height

            if art.bbox:
                y = art.bbox[1]
                if not (min_y <= y <= max_y):
                    continue

            # Artifacts on pages with Figure structure elements are treated as figure content/labels in PAC
            if art.page_number in figure_pages:
                continue

            body_artifacts.append(art)

        if body_artifacts:
            for art in body_artifacts[:5]:
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"Artifact on page {art.page_number} contains readable body paragraph text: \"{art.text_snippet[:40]}\".",
                    evidence=f"Artifact with body text on page {art.page_number}",
                    page=art.page_number,
                    bounding_box=art.bbox,
                    custom_severity=Severity.HIGH,
                    custom_remediation="Remove artifact marking from meaningful text content in Acrobat Pro.",
                    items_count=1
                ))
            if len(body_artifacts) > 5:
                rem = len(body_artifacts) - 5
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"{rem} additional artifact(s) on page body contain readable text.",
                    evidence=f"Total body artifacts: {len(body_artifacts)}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Remove artifact marking from meaningful text content in Acrobat Pro.",
                    items_count=rem
                ))

        return results


class LinkCompletenessQualityRule(BaseRule):
    """
    Validates the Completeness of Link Elements according to official PAC Quality checks:
    Verifies that linkable text (such as URLs and email addresses) in the document
    is enclosed within <Link> structure elements.
    """
    rule_id = "QUAL-LINK-002"
    name = "Completeness of Link Elements"
    category = "Link Quality"
    standard = "Quality"
    severity = Severity.HIGH
    machine_testable = True
    description = "Linkable text such as URLs and email addresses should be enclosed in a <Link> structure element."
    remediation_template = "Enclose linkable URL strings and email addresses in <Link> structure tags with associated link annotations."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree and not (doc.pages and any(p.text for p in doc.pages)):
            return results

        # Regex patterns for linkable text (URLs and email addresses)
        URL_PATTERN = re.compile(r'(?:https?://|www\.)[^\s<>\"\'\)]+', re.IGNORECASE)
        EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')

        unlinked_items = []
        linked_items_count = 0

        # Method A: Direct inspection using PyMuPDF / pikepdf when document file is accessible
        if doc.filepath and os.path.exists(doc.filepath):
            try:
                fitz_doc = doc.get_fitz_doc()
                if fitz_doc is not None:
                    # Collect all tagged link bounding boxes per page
                    tagged_link_bboxes_by_page: Dict[int, List[Tuple[float, float, float, float]]] = {}
                    if doc.links:
                        for l in doc.links:
                            if l.has_structure_link and l.bbox:
                                tagged_link_bboxes_by_page.setdefault(l.page, []).append(l.bbox)

                    for pno in range(len(fitz_doc)):
                        page = fitz_doc[pno]
                        page_num = pno + 1
                        page_text = page.get_text() or ""
                        if not page_text:
                            continue

                        # Find all URL and email occurrences in page text
                        page_links = page.get_links()
                        page_link_rects = [l.get("from") for l in page_links if l.get("from")]

                        found_patterns = list(URL_PATTERN.finditer(page_text)) + list(EMAIL_PATTERN.finditer(page_text))
                        for m in found_patterns:
                            matched_str = m.group(0).rstrip('.,;:)]}')
                            if len(matched_str) < 5:
                                continue

                            search_rects = page.search_for(matched_str)
                            if not search_rects:
                                search_rects = [None]

                            is_enclosed = False
                            for s_rect in search_rects:
                                if s_rect is None:
                                    if any(matched_str in (l.get("uri") or "") for l in page_links):
                                        is_enclosed = True
                                        break
                                else:
                                    for lr in page_link_rects:
                                        if hasattr(lr, "intersects") and lr.intersects(s_rect):
                                            is_enclosed = True
                                            break
                                        elif isinstance(lr, (tuple, list)) and len(lr) == 4:
                                            if not (s_rect.x1 < lr[0] or s_rect.x0 > lr[2] or s_rect.y1 < lr[1] or s_rect.y0 > lr[3]):
                                                is_enclosed = True
                                                break
                                    if is_enclosed:
                                        break

                            if is_enclosed:
                                linked_items_count += 1
                            else:
                                unlinked_items.append({
                                    "page": page_num,
                                    "text": matched_str,
                                    "evidence": f"Unlinked text '{matched_str}' on page {page_num}"
                                })
            except Exception:
                pass

        # Method B: In-memory fallback for unit tests and synthetic models
        if not (doc.filepath and os.path.exists(doc.filepath)):
            link_nodes = doc.structure_tree.find_all_by_standard_tag("Link") if doc.structure_tree else []

            # Check page texts
            for p in getattr(doc, "pages", []):
                p_text = getattr(p, "text", "") or ""
                if p_text:
                    for m in list(URL_PATTERN.finditer(p_text)) + list(EMAIL_PATTERN.finditer(p_text)):
                        matched_str = m.group(0).rstrip('.,;:)]}')
                        if any(matched_str in (ln.text_content or "") for ln in link_nodes):
                            linked_items_count += 1
                        else:
                            unlinked_items.append({
                                "page": p.page_number,
                                "text": matched_str,
                                "evidence": f"Unlinked text '{matched_str}' on page {p.page_number}"
                            })

            # Check synthetic Link structure elements completeness if no page text checked
            if link_nodes and not unlinked_items and linked_items_count == 0:
                for ln in link_nodes:
                    p_tag = (ln.parent.standard_tag or ln.parent.tag or "").upper() if ln.parent else ""
                    if p_tag in ("REFERENCE", "TOCI"):
                        continue
                    has_content = bool(
                        (ln.text_content and ln.text_content.strip()) or
                        (ln.alt_text and ln.alt_text.strip()) or
                        (ln.actual_text and ln.actual_text.strip()) or
                        ln.mcids or
                        ln.children
                    )
                    if has_content:
                        linked_items_count += 1
                    else:
                        unlinked_items.append({
                            "page": ln.page or 1,
                            "text": f"<{ln.tag} id='{ln.id}'>",
                            "evidence": f"Incomplete Link <{ln.tag} id='{ln.id}'>"
                        })

        # PAC Pass, Warning, and Skipped Behavior:
        # 1. Skipped (empty list -> renders as '-' in PAC table)
        if not unlinked_items and linked_items_count == 0:
            return results

        # 2. Warning for unlinked linkable text
        if unlinked_items:
            for item in unlinked_items[:5]:
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"Linkable text '{item['text']}' on page {item['page']} is not enclosed in a <Link> structure element.",
                    evidence=item["evidence"],
                    page=item["page"],
                    object_reference=f"Page {item['page']}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Enclose the URL or email address in a <Link> structure tag.",
                    items_count=1
                ))
            if len(unlinked_items) > 5:
                rem = len(unlinked_items) - 5
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"{rem} additional linkable text element(s) are not enclosed in <Link> structure elements.",
                    evidence=f"Total unlinked linkable items: {len(unlinked_items)}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Enclose all linkable text in <Link> structure tags.",
                    items_count=rem
                ))

        # 3. Pass when linkable text elements are complete
        if linked_items_count > 0 and not unlinked_items:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"{linked_items_count} linkable text element(s) are properly enclosed in <Link> structure elements.",
                evidence=f"Validated {linked_items_count} complete link element(s).",
                items_count=linked_items_count
            ))

        return results


class DuplicateOBJRLinkRule(BaseRule):
    """
    Custom Validation Rule:
    Detects multiple OBJR annotations associated with the same logical link content.
    Reports an error only when PDF object references establish that they represent
    duplicate annotations for the same link. Does not flag separate legitimate links.
    """
    rule_id = "CUST-LINK-001"
    name = "Duplicate Link Annotation Object References"
    category = "Link Quality"
    standard = "Custom"
    severity = Severity.HIGH
    machine_testable = True
    description = "Multiple OBJR annotations must not reference the same underlying link annotation object within the same logical link content."
    remediation_template = "Ensure each link annotation is referenced by at most one OBJR in the Link structure element."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree and not (doc.filepath and os.path.exists(doc.filepath)):
            return results

        duplicate_links = []
        total_links_checked = 0

        # Method A: Direct inspection using pikepdf
        if doc.filepath and os.path.exists(doc.filepath):
            try:
                import pikepdf
                with pikepdf.open(doc.filepath) as pdf:
                    root = pdf.Root.get('/StructTreeRoot')
                    if root:
                        page_map = {p.objgen: i + 1 for i, p in enumerate(pdf.pages)}

                        def check_node(elem, pg_num=1):
                            nonlocal total_links_checked
                            tag = str(elem.get('/S', '')).lstrip('/')
                            p_curr = pg_num
                            if '/Pg' in elem:
                                try:
                                    p_curr = page_map.get(elem.Pg.objgen, pg_num)
                                except Exception:
                                    pass

                            if tag == 'Link':
                                total_links_checked += 1
                                # Collect all OBJR objects in /K
                                k = elem.get('/K')
                                k_items = k if isinstance(k, pikepdf.Array) else [k] if k is not None else []
                                obj_refs = []
                                for it in k_items:
                                    if isinstance(it, pikepdf.Dictionary) and it.get('/Type') == '/OBJR':
                                        obj = it.get('/Obj')
                                        if obj is not None:
                                            obj_refs.append(getattr(obj, "objgen", str(obj)))
                                    # Also inspect child Span in Link (optional Span tag)
                                    elif isinstance(it, pikepdf.Dictionary) and str(it.get('/S', '')).lstrip('/') == 'Span':
                                        span_k = it.get('/K')
                                        span_items = span_k if isinstance(span_k, pikepdf.Array) else [span_k] if span_k is not None else []
                                        for sit in span_items:
                                            if isinstance(sit, pikepdf.Dictionary) and sit.get('/Type') == '/OBJR':
                                                sobj = sit.get('/Obj')
                                                if sobj is not None:
                                                    obj_refs.append(getattr(sobj, "objgen", str(sobj)))

                                # Check if multiple OBJR dictionaries reference the exact same annotation object
                                if len(obj_refs) > len(set(obj_refs)):
                                    duplicate_links.append({
                                        'page': p_curr,
                                        'elem': elem,
                                        'count': len(obj_refs) - len(set(obj_refs)),
                                        'ref': f"<Link on page {p_curr}>"
                                    })

                            # Traverse children
                            k_sub = elem.get('/K')
                            if isinstance(k_sub, pikepdf.Array):
                                for c in k_sub:
                                    if isinstance(c, (pikepdf.Dictionary, pikepdf.Stream)):
                                        check_node(c, p_curr)
                            elif isinstance(k_sub, (pikepdf.Dictionary, pikepdf.Stream)):
                                check_node(k_sub, p_curr)

                        check_node(root)
            except Exception:
                pass

        # Method B: In-memory fallback for unit tests and synthetic models
        if not (doc.filepath and os.path.exists(doc.filepath)):
            link_nodes = doc.structure_tree.find_all_by_standard_tag("Link")
            for ln in link_nodes:
                total_links_checked += 1
                objr_refs = list(ln.attributes.get("objr_refs", []))
                for child in ln.find_all_nodes():
                    if child != ln:
                        objr_refs.extend(child.attributes.get("objr_refs", []))
                is_dup = ln.attributes.get("duplicate_objr", False)
                if is_dup or (objr_refs and len(objr_refs) > len(set(objr_refs))):
                    duplicate_links.append({
                        'page': ln.page or 1,
                        'elem': ln,
                        'count': 1,
                        'ref': f"<{ln.tag} id='{ln.id}'>"
                    })

        if duplicate_links:
            for dl in duplicate_links[:5]:
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"Link structure element on page {dl['page']} contains multiple OBJR annotations referencing the same link target.",
                    evidence=f"Duplicate OBJR reference in {dl['ref']}",
                    page=dl['page'],
                    object_reference=dl['ref'],
                    custom_severity=Severity.HIGH,
                    custom_remediation="Remove duplicate OBJR references from the Link element so each link annotation is referenced once.",
                    items_count=1
                ))
            if len(duplicate_links) > 5:
                rem = len(duplicate_links) - 5
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"{rem} additional Link element(s) contain duplicate OBJR annotations.",
                    evidence=f"Total duplicate OBJR links: {len(duplicate_links)}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Remove duplicate OBJR references from all Link elements.",
                    items_count=rem
                ))
        elif total_links_checked > 0:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"All {total_links_checked} Link structure element(s) have unique OBJR annotation references without duplicates.",
                evidence="OBJR annotation references validated.",
                items_count=total_links_checked
            ))

        return results


class TaggedTextOnlyWhitespaceQualityRule(BaseRule):
    """
    Validates that tagged text structure elements do not consist solely of whitespace.
    Matterhorn Protocol Checkpoint 13-005 / ISO 14289-1 §7.1 / PAC Quality Checkpoint.
    """
    rule_id = "QUAL-WHITE-001"
    name = "Tagged text consists of only whitespace"
    category = "Content Quality"
    standard = "Quality"
    severity = Severity.HIGH
    machine_testable = True
    description = "Tagged text structure elements must not consist solely of whitespace characters (spaces, tabs, newlines)."
    remediation_template = "Delete empty tags or tag the content as an artifact if it is decorative spacing."

    TEXT_TAGS = {"P", "SPAN", "H1", "H2", "H3", "H4", "H5", "H6", "CAPTION", "QUOTE", "BLOCKQUOTE", "LBODY", "TH", "TD", "BIBENTRY", "CODE"}

    @staticmethod
    def _parse_tounicode_cmap(stream_bytes: bytes) -> Dict[int, str]:
        cmap: Dict[int, str] = {}
        text = stream_bytes.decode("latin1", errors="ignore")
        for section in re.findall(r'beginbfchar(.*?)endbfchar', text, re.DOTALL):
            for m in re.finditer(r'<([0-9a-fA-F]+)>\s+<([0-9a-fA-F]+)>', section):
                src = int(m.group(1), 16)
                dst_hex = m.group(2)
                try:
                    dst_chars = bytes.fromhex(dst_hex).decode("utf-16-be", errors="ignore")
                    cmap[src] = dst_chars
                except Exception:
                    pass
        for section in re.findall(r'beginbfrange(.*?)endbfrange', text, re.DOTALL):
            for m in re.finditer(r'<([0-9a-fA-F]+)>\s+<([0-9a-fA-F]+)>\s+<([0-9a-fA-F]+)>', section):
                start = int(m.group(1), 16)
                end = int(m.group(2), 16)
                base = int(m.group(3), 16)
                if 0 <= (end - start) <= 512:
                    for offset in range(end - start + 1):
                        curr_src = start + offset
                        curr_dst = base + offset
                        try:
                            dst_bytes = curr_dst.to_bytes((curr_dst.bit_length() + 7) // 8 or 2, 'big')
                            if len(dst_bytes) % 2 != 0:
                                dst_bytes = b'\x00' + dst_bytes
                            cmap[curr_src] = dst_bytes.decode("utf-16-be", errors="ignore")
                        except Exception:
                            pass
        return cmap

    def _decode_page_mcid_texts(self, filepath: str, page_num: int) -> Dict[int, str]:
        try:
            from pdf_inspector.core.document_parser import DocumentParser
            import pikepdf
            if not os.path.exists(filepath):
                return {}
            with pikepdf.open(filepath) as pdf:
                if page_num < 1 or page_num > len(pdf.pages):
                    return {}
                return DocumentParser._decode_page_mcid_texts(pdf.pages[page_num - 1], {})
        except Exception:
            return {}

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree:
            return results

        all_nodes = doc.structure_tree.find_all_nodes()
        page_mcid_cache: Dict[int, Dict[int, str]] = {}
        flagged_nodes: Set[str] = set()
        findings: List[StructureNode] = []

        for node in all_nodes:
            if node.tag == "StructTreeRoot":
                continue
            std_tag = (node.standard_tag or node.tag or "").upper()
            if std_tag not in self.TEXT_TAGS:
                continue

            # Check if any ancestor is already flagged (prevent duplicate descendant warnings)
            anc = node.parent
            anc_flagged = False
            while anc:
                if anc.id in flagged_nodes:
                    anc_flagged = True
                    break
                anc = anc.parent
            if anc_flagged:
                continue

            # 1. Handle /ActualText
            if node.actual_text is not None:
                if len(node.actual_text) > 0 and node.actual_text.strip() == "":
                    flagged_nodes.add(node.id)
                    findings.append(node)
                continue

            # 2. Handle /Alt
            if node.alt_text is not None:
                if len(node.alt_text) > 0 and node.alt_text.strip() == "":
                    flagged_nodes.add(node.id)
                    findings.append(node)
                continue

            # 3. Direct text payload on node
            if node.text_content and len(node.text_content) > 0:
                if node.text_content.strip() == "":
                    # Check if inline child inside parent with meaningful text
                    if node.parent and (node.parent.standard_tag or node.parent.tag or "").upper() in self.TEXT_TAGS:
                        parent_text = (node.parent.text_content or node.parent.actual_text or node.parent.alt_text or "")
                        if parent_text.strip():
                            continue
                    flagged_nodes.add(node.id)
                    findings.append(node)
                continue

            # 4. Check marked content sequences
            if not node.children and (node.mcids or node.mcid_entries):
                pg_num = node.page or 1
                mcids_to_check = [m for m, p in node.mcid_entries if p == pg_num] if node.mcid_entries else node.mcids

                # Check PageModel mcid_texts first
                pm_texts = {}
                if doc.pages and 0 < pg_num <= len(doc.pages):
                    page_mod = doc.pages[pg_num - 1]
                    if hasattr(page_mod, "mcid_texts") and page_mod.mcid_texts:
                        pm_texts = page_mod.mcid_texts

                texts_found = []
                for mc in mcids_to_check:
                    if mc in pm_texts:
                        texts_found.append(pm_texts[mc])

                # If no text from page model and file exists, decode from stream
                if not texts_found and doc.filepath and os.path.exists(doc.filepath):
                    if pg_num not in page_mcid_cache:
                        page_mcid_cache[pg_num] = self._decode_page_mcid_texts(doc.filepath, pg_num)
                    stream_pm = page_mcid_cache.get(pg_num, {})
                    for mc in mcids_to_check:
                        if mc in stream_pm:
                            texts_found.append(stream_pm[mc])

                if texts_found:
                    combined = "".join(texts_found)
                    if len(combined) > 0 and combined.strip() == "":
                        # Check inline child context
                        if node.parent and (node.parent.standard_tag or node.parent.tag or "").upper() in self.TEXT_TAGS:
                            parent_text = (node.parent.text_content or node.parent.actual_text or node.parent.alt_text or "")
                            if parent_text.strip():
                                continue
                        flagged_nodes.add(node.id)
                        findings.append(node)

        if findings:
            for node in findings:
                pg = node.page or 1
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"Tagged text inside <{node.tag}> on page {pg} consists of only whitespace.",
                    evidence=f"<{node.tag}> element on page {pg} contains only whitespace characters.",
                    page=pg,
                    bounding_box=node.bbox,
                    object_reference=f"<{node.tag} id='{node.id}'>",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Delete empty tags or tag the content as an artifact if it is decorative spacing.",
                    items_count=1
                ))
        else:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message="Tagged text elements avoid whitespace-only content.",
                evidence="All tagged text elements validated.",
                items_count=0
            ))

        return results


class DocumentTitleQualityRule(BaseRule):
    """
    Validates document title presence, descriptive quality, and DisplayDocTitle in ViewerPreferences.
    PAC Quality Checkpoint: Validity of document title.
    """
    rule_id = "QUAL-TITLE-001"
    name = "Validity of Document Title"
    category = "Validity of document title"
    standard = "Quality"
    severity = Severity.HIGH
    machine_testable = True
    description = "Document title must be present, descriptive, not match the filename, and DisplayDocTitle must be enabled in ViewerPreferences."
    remediation_template = "Set a descriptive title in Document Properties and enable 'Show Document Title' in Initial View."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        raw_title = (doc.title or doc.xmp_dc_title or doc.doc_info_title or "").strip()
        filename_base = os.path.splitext(doc.filename or "")[0].strip().lower()

        # Check 1: Title presence and meaningfulness
        title_invalid_reason = None
        if not raw_title:
            title_invalid_reason = "Document Title is missing."
        elif filename_base and (raw_title.lower() == filename_base or raw_title.lower() == (doc.filename or "").lower()):
            title_invalid_reason = f"Document Title '{raw_title}' matches the filename."
        elif raw_title.lower() in ("untitled", "microsoft word - document1", "document1", "default"):
            title_invalid_reason = f"Document Title '{raw_title}' is a generic template default."

        # Check 2: DisplayDocTitle in ViewerPreferences
        disp_title = bool(doc.display_doc_title)

        if title_invalid_reason and not disp_title:
            return [self.create_result(
                status=CheckStatus.FAIL,
                message=f"{title_invalid_reason} Additionally, ViewerPreferences/DisplayDocTitle is false.",
                evidence=f"Title: '{raw_title}', DisplayDocTitle: False",
                custom_severity=Severity.HIGH,
                custom_remediation="Set a descriptive Document Title and enable DisplayDocTitle in ViewerPreferences.",
                items_count=1
            )]
        elif title_invalid_reason:
            return [self.create_result(
                status=CheckStatus.FAIL,
                message=title_invalid_reason,
                evidence=f"Title: '{raw_title}'",
                custom_severity=Severity.HIGH,
                custom_remediation="Provide a concise, descriptive Document Title in Document Properties.",
                items_count=1
            )]
        elif not disp_title:
            return [self.create_result(
                status=CheckStatus.FAIL,
                message="ViewerPreferences/DisplayDocTitle is false. The window title bar will display the filename instead of the title.",
                evidence=f"Title: '{raw_title}', DisplayDocTitle: False",
                custom_severity=Severity.HIGH,
                custom_remediation="Set Initial View > Show > Document Title in File Properties.",
                items_count=1
            )]
        else:
            return [self.create_result(
                status=CheckStatus.PASS,
                message=f"Document title '{raw_title}' is valid and DisplayDocTitle is set to true.",
                evidence=f"Title: '{raw_title}', DisplayDocTitle: True",
                items_count=1
            )]


class BookmarksIfHeadingsQualityRule(BaseRule):
    """
    Validates presence of bookmarks (document outline) when headings are present.
    PAC Quality Checkpoint: Presence of bookmarks (document outline) if there are headings.
    """
    rule_id = "QUAL-BOOKMARK-001"
    name = "Bookmarks If Headings Present"
    category = "Presence of bookmarks (document outline) if there are headings"
    standard = "Quality"
    severity = Severity.MEDIUM
    machine_testable = True
    description = "Documents containing heading elements (<H1>-<H6>) must provide bookmarks (document outline) for navigational structure."
    remediation_template = "Generate document outline bookmarks from headings in Adobe Acrobat Pro."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        if not doc.structure_tree:
            return []

        all_nodes = doc.structure_tree.find_all_nodes()
        headings = [n for n in all_nodes if (n.standard_tag or "").upper() in ("H", "H1", "H2", "H3", "H4", "H5", "H6")]
        if not headings:
            # Zero headings in document -> PAC displays '-' (not applicable)
            return []

        if doc.bookmarks:
            return [self.create_result(
                status=CheckStatus.PASS,
                message=f"Document contains {len(doc.bookmarks)} bookmark item(s) outlining {len(headings)} heading structure(s).",
                evidence=f"Bookmarks present: {len(doc.bookmarks)} top-level item(s), Headings count: {len(headings)}",
                items_count=1
            )]
        else:
            return [self.create_result(
                status=CheckStatus.WARNING,
                message=f"Document contains {len(headings)} heading element(s) but has no bookmarks (document outline) for navigation.",
                evidence=f"Headings count: {len(headings)}, Bookmarks: 0",
                custom_severity=Severity.MEDIUM,
                custom_remediation="Generate outline bookmarks from heading tags in Acrobat Pro.",
                items_count=1
            )]


class ListItemStructureQualityRule(BaseRule):
    """
    Validates that every <LI> element contains only list label (<Lbl>) and/or list body (<LBody>) elements.
    PAC Quality Checkpoint: Formal correctness of "LI" elements.
    """
    rule_id = "QUAL-LIST-001"
    name = "Formal Correctness of LI Elements"
    category = 'Formal correctness of "LI" elements'
    standard = "Quality"
    severity = Severity.HIGH
    machine_testable = True
    description = "List item (<LI>) elements must contain only list label (<Lbl>) and/or list body (<LBody>) elements."
    remediation_template = "Ensure each <LI> tag encloses only <Lbl> and <LBody> child elements."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        if not doc.structure_tree:
            return []

        all_nodes = doc.structure_tree.find_all_nodes()
        li_nodes = [
            n for n in all_nodes
            if (n.standard_tag or "").upper() == "LI" or (n.tag or "").upper() == "LI"
        ]

        if not li_nodes:
            # Zero list items -> returns [] (displays '-' in PAC)
            return []

        invalid_li = []
        valid_li = []

        for li in li_nodes:
            immediate_children = [c for c in li.children if c is not None and isinstance(c, StructureNode)]
            direct_lbl = [c for c in immediate_children if (c.standard_tag or c.tag or "").upper() == "LBL"]
            direct_lbody = [c for c in immediate_children if (c.standard_tag or c.tag or "").upper() == "LBODY"]
            other_direct = [c for c in immediate_children if (c.standard_tag or c.tag or "").upper() not in ("LBL", "LBODY")]

            is_invalid = False
            # Duplicate Lbl or duplicate LBody
            if len(direct_lbl) > 1 or len(direct_lbody) > 1:
                is_invalid = True
            # Inadmissible direct child (e.g. P, Span, Table, L, etc.)
            elif other_direct:
                is_invalid = True
            # Empty LI
            elif len(immediate_children) == 0 and not li.mcids:
                is_invalid = True
            # Raw content outside LBody
            elif li.mcids and len(direct_lbody) == 0 and len(direct_lbl) == 0:
                is_invalid = True

            if is_invalid:
                invalid_li.append(li)
            else:
                valid_li.append(li)

        results = []
        if invalid_li:
            for li in invalid_li[:5]:
                li_path = li.get_structure_path() if hasattr(li, "get_structure_path") else f"LI id='{li.id}'"
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"<LI> element on page {li.page or 1} has an invalid structure (must contain only at most one <Lbl> and/or at most one <LBody>).",
                    evidence=f"Invalid LI <{li.tag} id='{li.id}'> at path '{li_path}' on page {li.page or 1}",
                    page=li.page or 1,
                    object_reference=f"<{li.tag} id='{li.id}'>",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Enclose list item contents inside <LBody> and bullets/numbers inside <Lbl>.",
                    items_count=1
                ))
            if len(invalid_li) > 5:
                rem = len(invalid_li) - 5
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"{rem} additional <LI> element(s) have invalid structural hierarchies.",
                    evidence=f"Total invalid LI elements: {len(invalid_li)}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Restructure list items according to ISO 14289-1 clause 7.4.",
                    items_count=rem
                ))
            if valid_li:
                results.append(self.create_result(
                    status=CheckStatus.PASS,
                    message=f"{len(valid_li)} of {len(li_nodes)} <LI> element(s) conform to formal list structure.",
                    evidence=f"Valid LI elements: {len(valid_li)}/{len(li_nodes)}",
                    items_count=len(valid_li)
                ))
        else:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"All {len(li_nodes)} <LI> element(s) conform to formal list structure.",
                evidence=f"Validated {len(li_nodes)} <LI> element(s).",
                items_count=len(li_nodes)
            ))

        return results


class AlternativeTextValidityQualityRule(BaseRule):
    """
    Validates that alternative descriptions on graphical and non-text elements
    are meaningful, non-empty, and do not use placeholders, file names, or pure whitespace.
    """
    rule_id = "QUAL-ALT-001"
    name = "Validity of Alternate Text"
    category = "Alternative Text Quality"
    standard = "Quality"
    severity = Severity.HIGH
    machine_testable = True
    description = "Alternative text on figures and non-text elements must be meaningful, non-empty, and not a generic placeholder or filename."
    remediation_template = "Replace placeholder text, file names, or empty alternative text with concise, descriptive text that conveys the purpose of the image."

    FILENAME_PATTERN = re.compile(r"^.*\.(png|jpe?g|gif|bmp|tiff|svg|webp|ico|pdf)$", re.IGNORECASE)
    PLACEHOLDER_PATTERN = re.compile(r"^(image|figure|photo|graphic|picture|placeholder|untitled|alt\s*text|logo|icon|spacer|banner|drawing|diagram|clipart)$", re.IGNORECASE)

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree and not doc.images:
            return results

        all_graphics = []
        if doc.structure_tree:
            all_graphics = [
                n for n in doc.structure_tree.find_all_nodes()
                if (n.standard_tag or "").upper() in ("FIGURE", "FORMULA")
            ]

        # Check figures/formulas with alt text
        items_with_alt = []
        for node in all_graphics:
            if node.is_decorative():
                continue
            alt = node.alt_text if node.alt_text is not None else node.actual_text
            if alt is not None:
                items_with_alt.append((node, alt, node.page or 1, node.bbox, f"<{node.tag} id='{node.id}'>"))

        # Also check doc.images with alt text if not in structure tree
        if doc.images:
            struct_elem_ids = {n.id for n in all_graphics}
            for img in doc.images:
                if img.is_artifact or (img.structure_element_id and img.structure_element_id in struct_elem_ids):
                    continue
                if img.alt_text:
                    items_with_alt.append((None, img.alt_text, img.page or 1, img.bbox, f"<Image id='{img.id}'>"))

        if not items_with_alt:
            return results

        invalid_items = []
        valid_count = 0

        for node, alt, page, bbox, obj_ref in items_with_alt:
            cleaned = alt.strip()
            tag_name = node.tag if node else "Image"

            if not cleaned:
                invalid_items.append((
                    page, bbox, obj_ref,
                    f"Alternative text for <{tag_name}> on page {page} consists only of whitespace.",
                    f"<{tag_name}> on page {page} has empty/whitespace /Alt attribute.",
                    Severity.HIGH
                ))
            elif self.FILENAME_PATTERN.match(cleaned):
                invalid_items.append((
                    page, bbox, obj_ref,
                    f"Alternative text for <{tag_name}> on page {page} appears to be a file name: '{cleaned}'.",
                    f"Alternative text '{cleaned}' on page {page} ends with a file extension.",
                    Severity.MEDIUM
                ))
            elif self.PLACEHOLDER_PATTERN.match(cleaned):
                invalid_items.append((
                    page, bbox, obj_ref,
                    f"Alternative text for <{tag_name}> on page {page} is a generic placeholder: '{cleaned}'.",
                    f"Alternative text '{cleaned}' on page {page} is a non-descriptive placeholder.",
                    Severity.MEDIUM
                ))
            elif len(cleaned) <= 2 and not cleaned.isalnum():
                invalid_items.append((
                    page, bbox, obj_ref,
                    f"Alternative text for <{tag_name}> on page {page} is too short or non-descriptive: '{cleaned}'.",
                    f"Alternative text '{cleaned}' on page {page} contains <= 2 non-alphanumeric characters.",
                    Severity.MEDIUM
                ))
            else:
                valid_count += 1

        if invalid_items:
            for pg, bx, oref, msg, evid, sev in invalid_items[:5]:
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=msg,
                    evidence=evid,
                    page=pg,
                    bounding_box=bx,
                    object_reference=oref,
                    custom_severity=sev,
                    custom_remediation="Replace placeholder, empty, or file name text with a concise and meaningful description of the image content.",
                    items_count=1
                ))
            if len(invalid_items) > 5:
                rem = len(invalid_items) - 5
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"{rem} additional element(s) have invalid or placeholder alternative text.",
                    evidence=f"Total invalid alternative text instances: {len(invalid_items)}",
                    custom_severity=Severity.MEDIUM,
                    custom_remediation="Provide descriptive alternative text for all graphical elements.",
                    items_count=rem
                ))

        if valid_count > 0:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"{valid_count} alternative text description(s) are valid and meaningful.",
                evidence=f"Validated {valid_count} alternative text description(s).",
                items_count=valid_count
            ))

        return results
