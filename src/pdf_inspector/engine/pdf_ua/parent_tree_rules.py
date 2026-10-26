"""
ParentTree Rules (ISO 14289-1, Clause 7.1 & Matterhorn Protocol Checkpoint 01-002, 01-003)
Verifies integrity of the /ParentTree number tree mapping pages and annotations to structure elements.
"""

from typing import List
from ..rule_base import BaseRule
from ...core.models import PDFDocumentModel, CheckResult, CheckStatus, Severity


class ParentTreeIntegrityRule(BaseRule):
    rule_id = "PDFUA-TREE-002"
    name = "ParentTree Integrity"
    category = "Structure tree"
    standard = "PDF/UA"
    severity = Severity.HIGH
    description = "The structure tree must include a valid /ParentTree number tree that accurately maps page content and annotations to structural elements."
    remediation_template = "Regenerate tags and the ParentTree in Acrobat Pro or re-export using a PDF/UA compliant authoring tool."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree and not doc.has_parent_tree and not any(p.mcids for p in doc.pages):
            return results

        if not doc.has_parent_tree:
            results.append(self.create_result(
                status=CheckStatus.FAIL,
                message="/StructTreeRoot is missing the mandatory /ParentTree number tree (Matterhorn 01-003).",
                evidence="StructTreeRoot has no /ParentTree entry.",
                custom_severity=Severity.HIGH,
                custom_remediation="Add or reconstruct the ParentTree using an accessible PDF tool."
            ))
            return results

        if not doc.parent_tree_valid:
            results.append(self.create_result(
                status=CheckStatus.WARNING,
                message="/ParentTree number tree exists but contains no valid entry mappings.",
                evidence=f"ParentTree entries count: {doc.parent_tree_entries_count}",
                custom_severity=Severity.MEDIUM,
                custom_remediation="Verify that structural elements and marked content references are indexed in the ParentTree."
            ))
        else:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"/ParentTree number tree is present and valid with {doc.parent_tree_entries_count} mapped entries.",
                evidence=f"ParentTree entries: {doc.parent_tree_entries_count}",
                items_count=0
            ))

        pt_map = getattr(doc, "parent_tree_map", {})

        # 1. Check page /StructParents presence (Matterhorn 01-004)
        pages_missing_struct_parents = []
        for p in doc.pages:
            non_art_mcids = [m for m in p.mcids if m not in getattr(p, "artifact_mcids", set())]
            if non_art_mcids and p.struct_parents_id is None:
                pages_missing_struct_parents.append(p.page_number)

        if pages_missing_struct_parents:
            results.append(self.create_result(
                status=CheckStatus.FAIL,
                message=f"Page(s) {pages_missing_struct_parents[:5]} contain marked content (MCIDs) but lack /StructParents page dictionary entry (Matterhorn 01-004).",
                evidence=f"Pages missing /StructParents: {pages_missing_struct_parents}",
                page=pages_missing_struct_parents[0],
                custom_severity=Severity.HIGH,
                custom_remediation="Ensure every page with marked content defines a /StructParents index pointing into the ParentTree.",
                items_count=len(pages_missing_struct_parents)
            ))
        else:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message="All pages with marked content possess valid /StructParents attributes.",
                evidence="Page StructParents validated.",
                items_count=0
            ))

        # 2. Check /StructParents index exists in ParentTree (Matterhorn 01-006)
        pages_sp_not_in_pt = []
        for p in doc.pages:
            if p.struct_parents_id is not None and p.struct_parents_id not in pt_map:
                pages_sp_not_in_pt.append((p.page_number, p.struct_parents_id))

        if pages_sp_not_in_pt:
            for pg, sp_id in pages_sp_not_in_pt[:5]:
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"Page {pg} /StructParents index {sp_id} is missing from the /ParentTree number tree (Matterhorn 01-006).",
                    evidence=f"Missing ParentTree key: {sp_id} for page {pg}",
                    page=pg,
                    custom_severity=Severity.HIGH,
                    custom_remediation="Ensure the ParentTree contains entries corresponding to all page /StructParents indices.",
                    items_count=1
                ))

        # 3. Check every page MCID is present and non-null in ParentTree (Matterhorn 01-006)
        pt_missing_mcids = []
        for p in doc.pages:
            art_mcids = getattr(p, "artifact_mcids", set())
            if p.struct_parents_id is not None and p.struct_parents_id in pt_map:
                pt_entry = pt_map[p.struct_parents_id]
                if isinstance(pt_entry, list):
                    for mcid in p.mcids:
                        # In PDF/UA (Matterhorn 01-006), only content items that are part of a structure
                        # element are required to have a structure element entry in /ParentTree.
                        # Marked content sequences that are artifacts are excluded from the structure tree
                        # (ISO 32000-1 §14.8.2.2) and may validly correspond to null or omitted entries (ISO 32000-1 §14.7.4.4).
                        if mcid in art_mcids:
                            continue
                        if mcid < len(pt_entry):
                            target = pt_entry[mcid]
                            if isinstance(target, dict):
                                t_tag = target.get("tag", "").lower()
                                t_type = target.get("type", "").lower()
                                if t_tag == "artifact" or t_type == "artifact":
                                    continue
                            elif target is None:
                                pt_missing_mcids.append((p.page_number, mcid, "null entry in ParentTree"))
                        else:
                            # If mcid exceeds array length, check if it's mapped in another ParentTree key
                            # (e.g. within a Form XObject with its own StructParents, ISO 32000-1 §14.7.4.2)
                            is_mapped_elsewhere = False
                            for sp_k, arr in pt_map.items():
                                if sp_k != p.struct_parents_id and isinstance(arr, list) and mcid < len(arr):
                                    t = arr[mcid]
                                    if t is not None:
                                        is_mapped_elsewhere = True
                                        break
                            if not is_mapped_elsewhere:
                                pt_missing_mcids.append((p.page_number, mcid, f"exceeds array length {len(pt_entry)}"))

        if pt_missing_mcids:
            for pg, mcid, reason in pt_missing_mcids[:10]:
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"Page {pg} marked content MCID {mcid} has no valid entry in /ParentTree ({reason}) (Matterhorn 01-006).",
                    evidence=f"ParentTree entry missing for page {pg}, MCID {mcid}: {reason}",
                    page=pg,
                    custom_severity=Severity.HIGH,
                    custom_remediation="Ensure ParentTree contains valid structure element entries for every MCID.",
                    items_count=1
                ))

        # 4. Check bidirectional consistency between StructTree and ParentTree (Matterhorn 01-008)
        all_tree_nodes = doc.structure_tree.find_all_nodes() if doc.structure_tree else []
        all_tree_objs = {n.obj_num: n for n in all_tree_nodes if n.obj_num is not None and n.obj_num != 0}

        mismatches = []
        for node in all_tree_nodes:
            entries = getattr(node, "mcid_entries", [])
            mcid_list = entries if entries else [(m, node.page) for m in node.mcids]
            for mcid, explicit_pg in mcid_list:
                pg_num = explicit_pg or node.page
                p = next((page for page in doc.pages if page.page_number == pg_num), None)
                if p and p.struct_parents_id is not None and p.struct_parents_id in pt_map:
                    pt_entry = pt_map[p.struct_parents_id]
                    if isinstance(pt_entry, list) and mcid < len(pt_entry):
                        target = pt_entry[mcid]
                        if isinstance(target, dict):
                            og = target.get("obj_num")
                            if og and node.obj_num and og != 0 and node.obj_num != 0 and og != node.obj_num:
                                # In PDF ISO 32000-1 Clause 14.7.4.2, marked content within a Form XObject
                                # (/Stm) is indexed in /ParentTree under the Form XObject's own /StructParents,
                                # rather than the page's /StructParents.
                                # Verify if node.obj_num is validly mapped in ParentTree under any key for this MCID:
                                is_matched_in_pt = False
                                for sp_key, pt_entry_arr in pt_map.items():
                                    if isinstance(pt_entry_arr, list) and mcid < len(pt_entry_arr):
                                        t = pt_entry_arr[mcid]
                                        if isinstance(t, dict) and t.get("obj_num") == node.obj_num:
                                            is_matched_in_pt = True
                                            break
                                if not is_matched_in_pt:
                                    mismatches.append((node.tag, node.obj_num, og, mcid, pg_num))

        if mismatches:
            for tag, n_obj, pt_obj, mcid, pg_num in mismatches[:10]:
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"Structure element <{tag}> (obj {n_obj}) on page {pg_num} refers to MCID {mcid}, but /ParentTree points to obj {pt_obj} (Matterhorn 01-008).",
                    evidence=f"Inconsistent ParentTree entry: struct obj {n_obj} != ParentTree obj {pt_obj} for MCID {mcid} on page {pg_num}",
                    page=pg_num,
                    object_reference=f"<{tag}>",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Ensure structure tree elements and ParentTree entries point to the same objects.",
                    items_count=1
                ))

        # 5. Check for invalid/corrupt ParentTree entries referenced by page MCIDs (Matterhorn 01-008)
        invalid_pt_entries = []
        for p in doc.pages:
            art_mcids = getattr(p, "artifact_mcids", set())
            if p.struct_parents_id is not None and p.struct_parents_id in pt_map:
                pt_entry = pt_map[p.struct_parents_id]
                if isinstance(pt_entry, list):
                    for mcid in p.mcids:
                        if mcid < len(pt_entry):
                            target = pt_entry[mcid]
                            if isinstance(target, dict):
                                og = target.get("obj_num")
                                s_tag = target.get("tag", "")
                                s_type = target.get("type", "")
                                is_artifact = (
                                    s_tag.lower() == "artifact"
                                    or s_type.lower() == "artifact"
                                    or mcid in art_mcids
                                )
                                has_parent = target.get("has_parent", True)
                                is_in_tree = (og and og in all_tree_objs) or any(
                                    mcid in n.mcids and (n.standard_tag or n.tag) == s_tag
                                    for n in all_tree_nodes
                                )
                                is_detached = not is_in_tree and not has_parent and s_tag != "StructTreeRoot"
                                if is_artifact:
                                    # An Artifact entry in ParentTree is only invalid if it claims
                                    # to be a structural element inside StructTreeRoot (Matterhorn 01-001/01-008).
                                    # When outside StructTreeRoot, it is a valid artifact entry (ISO 32000-1 §14.8.2.2).
                                    if is_in_tree:
                                        invalid_pt_entries.append((p.page_number, mcid, og, s_tag or "Artifact"))
                                elif is_detached or (not s_tag and not is_in_tree):
                                    invalid_pt_entries.append((p.page_number, mcid, og, s_tag))

        if invalid_pt_entries:
            for pg_num, mcid, og, s_tag in invalid_pt_entries[:10]:
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"Page {pg_num} /ParentTree entry for MCID {mcid} (obj {og}) is not a valid structure element (tag: '{s_tag}') (Matterhorn 01-008).",
                    evidence=f"Invalid ParentTree entry for page {pg_num}, MCID {mcid}: obj {og}, tag '{s_tag}'",
                    page=pg_num,
                    custom_severity=Severity.HIGH,
                    custom_remediation="Ensure ParentTree entries point to valid structure elements in StructTreeRoot.",
                    items_count=1
                ))

        return results
