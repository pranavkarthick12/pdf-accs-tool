"""
Content Rules (ISO 14289-1:2014, Clause 7.1 & Matterhorn Protocol Checkpoint 01)
Verifies that all real content is tagged within the structure tree or marked as an artifact,
and verifies marked content sequence integrity and ParentTree/MCID associations.
"""

from typing import List, Set, Dict
from ..rule_base import BaseRule
from ...core.models import PDFDocumentModel, CheckResult, CheckStatus, Severity


class TaggedPDFRule(BaseRule):
    rule_id = "PDFUA-CONTENT-001"
    name = "Tagged PDF"
    category = "Content"
    standard = "PDF/UA"
    severity = Severity.CRITICAL
    description = "The document must be marked as a Tagged PDF in the document Catalog dictionary (ISO 14289-1, Clause 7.1 / Matterhorn 01-001)."
    remediation_template = "In Acrobat Pro, open Accessibility tool and select 'Add Tags to Document', or check 'Document is tagged PDF' in authoring tool export settings."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        if doc.is_tagged and doc.structure_tree is not None:
            return [self.create_result(
                status=CheckStatus.PASS,
                message="Document is explicitly marked as a Tagged PDF with a structure tree.",
                evidence="Catalog /MarkInfo /Marked is true and /StructTreeRoot exists."
            )]

        has_content = bool(doc.images or any(p.text.strip() for p in doc.pages))
        return [self.create_result(
            status=CheckStatus.FAIL,
            message="Document is NOT a Tagged PDF. Assistive technologies cannot determine reading order or semantics.",
            evidence=f"is_tagged: {doc.is_tagged}, StructTreeRoot present: {doc.structure_tree is not None}",
            custom_severity=Severity.CRITICAL,
            custom_remediation="Tag the document using an accessible PDF authoring tool or Adobe Acrobat Pro's 'Autotag Document' feature.",
            items_count=0 if has_content else 1
        )]


class ContentTaggedRule(BaseRule):
    rule_id = "PDFUA-CONTENT-002"
    name = "Real Content Tagged"
    category = "Content"
    standard = "PDF/UA"
    severity = Severity.HIGH
    description = "All real content on each page must be tagged in the structure tree or marked as an Artifact (ISO 14289-1, Clause 7.1 / Matterhorn 01-002, 01-005)."
    remediation_template = "Inspect untagged elements in the PDF structure pane and tag them or mark them as background artifacts."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        total_unmarked = sum(p.unmarked_real_content_count for p in doc.pages) if doc.pages else 0
        if not doc.is_tagged and doc.structure_tree is None:
            total_untagged = len(doc.images) + sum(len(p.text.splitlines()) for p in doc.pages if p.text.strip())
            if total_untagged > 0:
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"Document is untagged: {total_untagged} real content element(s) are not tagged in the structure tree (Matterhorn 01-001).",
                    evidence=f"Total untagged content elements: {total_untagged} ({len(doc.images)} image(s)) across {doc.page_count} page(s).",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Tag the document using an accessible PDF creator or Acrobat Pro Autotag Document.",
                    items_count=total_untagged
                ))
            return results

        total_chars = sum(len(p.text) for p in doc.pages if p.text)
        total_mcids = sum(len(p.mcids) for p in doc.pages)
        total_images = len(doc.images)
        total_links = len(doc.links)
        total_elements = total_chars + total_mcids + total_images + total_links
        if total_elements == 0:
            total_elements = sum(p.tagged_operations_count for p in doc.pages) + total_images

        passed_items = max(0, total_elements - total_unmarked)

        # 1. Check pages with unmarked real content operations on tagged documents
        unmarked_pages: Dict[int, List[str]] = {}
        for p in doc.pages:
            unmarked_occs = [occ for occ in p.content_occurrences if occ.is_unmarked_real_content]
            if unmarked_occs or p.unmarked_real_content_count > 0:
                snippets = [occ.snippet for occ in unmarked_occs if occ.snippet]
                unmarked_pages[p.page_number] = snippets

        if unmarked_pages:
            for pg_num, snippets in list(unmarked_pages.items())[:10]:
                snip_str = f" Content: \"{snippets[0]}\"" if snippets else ""
                # Find page bounding box if available
                p_model = next((p for p in doc.pages if p.page_number == pg_num), None)
                unmarked_bbox = None
                items_on_pg = p_model.unmarked_real_content_count if p_model and p_model.unmarked_real_content_count > 0 else 1
                if p_model and p_model.content_occurrences:
                    for occ in p_model.content_occurrences:
                        if occ.is_unmarked_real_content and occ.bbox:
                            unmarked_bbox = occ.bbox
                            break

                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"Page {pg_num} contains real content that is neither enclosed in marked content (/MCID) nor marked as an Artifact.",
                    evidence=f"Unmarked real content on page {pg_num}.{snip_str}",
                    page=pg_num,
                    bounding_box=unmarked_bbox,
                    object_reference=f"Untagged Content on Page {pg_num}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Tag the unmarked content in the logical structure tree or mark it as an Artifact.",
                    items_count=items_on_pg
                ))
            if len(unmarked_pages) > 10:
                rem_pages = list(unmarked_pages.keys())[10:]
                rem_items = sum(
                    next((p.unmarked_real_content_count for p in doc.pages if p.page_number == pg), 1)
                    for pg in rem_pages
                )
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"{len(rem_pages)} additional page(s) contain unmarked real content.",
                    evidence=f"Total pages with unmarked content: {len(unmarked_pages)}",
                    page=rem_pages[0],
                    custom_severity=Severity.HIGH,
                    custom_remediation="Review and tag untagged content across pages.",
                    items_count=rem_items
                ))

            if passed_items > 0:
                results.append(self.create_result(
                    status=CheckStatus.PASS,
                    message=f"{passed_items} real content element(s) are properly enclosed in marked content tags or marked as Artifacts.",
                    evidence=f"Validated content streams across {doc.page_count} page(s).",
                    items_count=passed_items
                ))

        else:
            items_to_report = passed_items if passed_items > 0 else 1
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message="All real content is enclosed in marked content tags or marked as Artifacts.",
                evidence=f"Validated content streams across all {doc.page_count} page(s).",
                items_count=items_to_report
            ))

        return results


class TaggedInsideArtifactRule(BaseRule):
    rule_id = "PDFUA-CONTENT-004"
    name = "Tagged Content inside Artifact"
    category = "Content"
    standard = "PDF/UA"
    severity = Severity.HIGH
    description = "Tagged content (marked content sequences) must not be present inside an artifact (ISO 14289-1, Clause 7.1 / Matterhorn 01-004)."
    remediation_template = "Remove enclosing artifact tags around tagged content sequences in the page content stream."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.is_tagged and doc.structure_tree is None:
            return results

        invalid_pages = []
        for p in doc.pages:
            if p.tagged_in_artifact_count > 0:
                invalid_pages.append((p.page_number, p.tagged_in_artifact_count))

        if invalid_pages:
            for pg_num, cnt in invalid_pages:
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"Page {pg_num} has tagged content sequence(s) incorrectly nested inside an Artifact sequence.",
                    evidence=f"{cnt} tagged sequence(s) inside Artifact on page {pg_num}.",
                    page=pg_num,
                    custom_severity=Severity.HIGH,
                    custom_remediation="Move tagged content outside artifact blocks in page content stream."
                ))
        else:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message="No tagged content sequences are enclosed within artifact blocks.",
                evidence="Nesting of tagged content outside artifacts validated."
            ))

        return results


class MCIDStructureReferenceRule(BaseRule):
    rule_id = "PDFUA-CONTENT-005"
    name = "MCID Reference Integrity"
    category = "Content"
    standard = "PDF/UA"
    severity = Severity.HIGH
    description = "Every marked-content identifier (/MCID) in page content streams must be referenced by a structure element in the structure tree (ISO 14289-1, Clause 7.1 / Matterhorn 01-005)."
    remediation_template = "Associate orphan MCID marked content sequences with matching structure elements or mark them as Artifacts."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree and not any(p.mcids for p in doc.pages):
            return results

        # Collect all MCIDs referenced in the structure tree, indexed by page
        tree_mcids_by_page: Dict[int, Set[int]] = {}
        global_unassigned_mcids: Set[int] = set()

        all_nodes = doc.structure_tree.find_all_nodes() if doc.structure_tree else []
        for node in all_nodes:
            entries = getattr(node, "mcid_entries", [])
            if entries:
                for mcid, explicit_pg in entries:
                    pg_num = explicit_pg or node.page
                    if pg_num is not None:
                        tree_mcids_by_page.setdefault(pg_num, set()).add(mcid)
                    elif len(doc.pages) == 1:
                        tree_mcids_by_page.setdefault(doc.pages[0].page_number, set()).add(mcid)
                    else:
                        global_unassigned_mcids.add(mcid)
            elif node.mcids:
                pg_num = node.page
                if pg_num is not None:
                    for mcid in node.mcids:
                        tree_mcids_by_page.setdefault(pg_num, set()).add(mcid)
                elif len(doc.pages) == 1:
                    for mcid in node.mcids:
                        tree_mcids_by_page.setdefault(doc.pages[0].page_number, set()).add(mcid)
                elif node.pages_spanned:
                    for pg_spanned in node.pages_spanned:
                        for mcid in node.mcids:
                            tree_mcids_by_page.setdefault(pg_spanned, set()).add(mcid)
                else:
                    for mcid in node.mcids:
                        global_unassigned_mcids.add(mcid)

        # Check for orphan page MCIDs
        orphan_pages = []
        pt_map = doc.parent_tree_map
        for p in doc.pages:
            referenced = tree_mcids_by_page.get(p.page_number, set())
            sp_id = p.struct_parents_id
            pt_entry = pt_map.get(sp_id, []) if sp_id is not None else []
            empty_mcids = getattr(p, "empty_mcids", set())
            orphans = []
            art_mcids = getattr(p, "artifact_mcids", set())
            for mcid in p.mcids:
                if mcid in empty_mcids:
                    continue
                if mcid in referenced or mcid in global_unassigned_mcids:
                    continue
                # Artifact MCIDs (marked as /Artifact in content stream or /S /Artifact in ParentTree)
                # are by definition excluded from the structure tree (ISO 32000-1 14.8.2.2 / ISO 14289-1 7.1)
                if mcid in art_mcids:
                    continue
                is_artifact_pt = False
                has_pt_struct = False
                if isinstance(pt_entry, list) and mcid < len(pt_entry):
                    target = pt_entry[mcid]
                    if isinstance(target, dict):
                        t_tag = target.get("tag", "").lower()
                        t_type = target.get("type", "").lower()
                        if t_tag == "artifact" or t_type == "artifact":
                            is_artifact_pt = True
                        elif target.get("tag") or target.get("obj_num"):
                            has_pt_struct = True
                if not is_artifact_pt and not has_pt_struct:
                    # In PDF ISO 32000-1 §14.7.4.2, marked content within Form XObjects
                    # is indexed in /ParentTree under the Form XObject's StructParents.
                    for other_sp, other_entry in pt_map.items():
                        if other_sp != sp_id and isinstance(other_entry, list) and mcid < len(other_entry):
                            t = other_entry[mcid]
                            if isinstance(t, dict):
                                t_tag = t.get("tag", "").lower()
                                t_type = t.get("type", "").lower()
                                if t_tag == "artifact" or t_type == "artifact":
                                    is_artifact_pt = True
                                    break
                                elif t.get("tag") or t.get("obj_num"):
                                    has_pt_struct = True
                                    break
                if is_artifact_pt or has_pt_struct:
                    continue
                orphans.append(mcid)
            if orphans:
                orphan_pages.append((p.page_number, orphans))

        if orphan_pages:
            for pg_num, orphans in orphan_pages:
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"Page {pg_num} contains marked content MCID(s) {orphans[:10]} not referenced by any structure element (Matterhorn 01-005).",
                    evidence=f"Orphan MCIDs on page {pg_num}: {orphans}",
                    page=pg_num,
                    custom_severity=Severity.HIGH,
                    custom_remediation="Associate orphan MCID marked content sequences with matching structure elements or mark them as Artifacts.",
                    items_count=len(orphans)
                ))
        else:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message="All marked-content identifiers (MCIDs) are properly referenced in the structure tree.",
                evidence="MCID structure tree mapping verified.",
                items_count=0
            ))

        return results


class StructureMCIDExistenceRule(BaseRule):
    rule_id = "PDFUA-CONTENT-006"
    name = "Structure Element MCID Existence"
    category = "Content"
    standard = "PDF/UA"
    severity = Severity.HIGH
    description = "Every marked-content identifier (MCID) referenced by a structure element must exist on the associated page."
    remediation_template = "Ensure structure tree elements only reference MCIDs that actually exist in the page content stream."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree:
            return results

        invalid_refs = []
        for node in doc.structure_tree.find_all_nodes():
            if not node.mcids:
                continue

            entries = getattr(node, "mcid_entries", [])
            if entries:
                for mcid, explicit_pg in entries:
                    pg_num = explicit_pg or node.page
                    if not pg_num:
                        invalid_refs.append((node, mcid, "missing page"))
                        continue
                    page = next((p for p in doc.pages if p.page_number == pg_num), None)
                    if not page:
                        invalid_refs.append((node, mcid, pg_num))
                        continue
                    if mcid not in page.mcids:
                        invalid_refs.append((node, mcid, pg_num))
            else:
                pg_num = node.page
                if not pg_num:
                    for mcid in node.mcids:
                        invalid_refs.append((node, mcid, "missing page"))
                    continue
                page = next((p for p in doc.pages if p.page_number == pg_num), None)
                for mcid in node.mcids:
                    if not page or mcid not in page.mcids:
                        invalid_refs.append((node, mcid, pg_num))
                    
        if invalid_refs:
            for node, mcid, pg_num in invalid_refs[:10]:
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"Structure element <{node.tag}> references MCID {mcid} which does not exist on page {pg_num} (Matterhorn 01-007).",
                    evidence=f"Invalid MCID reference: {mcid} on page {pg_num}",
                    page=pg_num if isinstance(pg_num, int) else None,
                    object_reference=f"<{node.tag}>",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Recreate tags or repair structure tree references.",
                    items_count=1
                ))
            if len(invalid_refs) > 10:
                rem = len(invalid_refs) - 10
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"{rem} additional invalid MCID references found.",
                    evidence=f"Total invalid MCID refs: {len(invalid_refs)}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Rebuild document structure tree.",
                    items_count=rem
                ))
        else:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message="All MCIDs referenced by the structure tree exist on their respective pages.",
                evidence="Structure MCID references verified.",
                items_count=0
            ))

        return results


class NestedMarkedContentRule(BaseRule):
    rule_id = "PDFUA-CONTENT-007"
    name = "Nested Marked Content"
    category = "Content"
    standard = "PDF/UA"
    severity = Severity.HIGH
    description = "Marked content sequences must not be nested inside other marked content sequences."
    remediation_template = "Flatten nested marked content tags in the page content stream."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.is_tagged and doc.structure_tree is None:
            return results

        nested_pages = []
        for p in doc.pages:
            nested_occs = [occ for occ in p.content_occurrences if occ.is_inside_tagged and occ.mcid is not None]
            if nested_occs:
                nested_pages.append((p.page_number, len(nested_occs)))

        if nested_pages:
            for pg_num, cnt in nested_pages[:5]:
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"Page {pg_num} contains {cnt} nested marked content sequence(s).",
                    evidence=f"Nested marked content found on page {pg_num}.",
                    page=pg_num,
                    custom_severity=Severity.HIGH,
                    custom_remediation="Flatten marked content sequences."
                ))
            if len(nested_pages) > 5:
                rem = len(nested_pages) - 5
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"{rem} additional page(s) contain nested marked content sequences.",
                    evidence=f"Total pages with nested sequences: {len(nested_pages)}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Review and fix nested content across pages."
                ))
        else:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message="No nested marked content sequences detected.",
                evidence="Marked content hierarchy validated."
            ))

        return results
