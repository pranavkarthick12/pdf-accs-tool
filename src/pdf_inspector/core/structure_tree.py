"""
PDF Structure Tree Parser
Parses the Logical Structure Tree (/StructTreeRoot), /ParentTree number tree,
and resolves custom role mappings to ISO 32000-1 standard structure types.
Links real page MCID text and geometry to structural nodes.
"""

from typing import Dict, List, Optional, Tuple, Set, Any
import logging
import pikepdf
from .models import StructureNode, validate_bbox_coordinates

logger = logging.getLogger(__name__)

# Standard structure types defined in ISO 32000-1:2008, Clause 14.8.4 (exact case-sensitive PDF names)
STANDARD_STRUCTURE_TYPES_EXACT: Set[str] = {
    # Document level & Grouping
    "Document", "Part", "Art", "Sect", "Div", "BlockQuote", "Caption",
    "TOC", "TOCI", "Index", "NonStruct", "Private",
    # Paragraph-like & Headings
    "P", "H", "H1", "H2", "H3", "H4", "H5", "H6",
    # Lists
    "L", "LI", "Lbl", "LBody",
    # Tables
    "Table", "TR", "TH", "TD",
    # Inline
    "Span", "Quote", "Note", "Reference", "BibEntry", "Code", "Link", "Annot",
    # Illustration & Forms
    "Figure", "Formula", "Form",
    # Ruby & Warichu
    "Ruby", "RB", "RT", "RP", "Warichu", "WT", "WP"
}

STANDARD_STRUCTURE_TYPES: Set[str] = {s.upper() for s in STANDARD_STRUCTURE_TYPES_EXACT}


# Standard structure role classification groups defined in ISO 32000-1:2008
GROUPING_ROLES: Set[str] = {
    "Document", "Part", "Art", "Sect", "Div", "BlockQuote", "Caption",
    "TOC", "TOCI", "Index", "NonStruct", "Private"
}
BLOCK_ROLES: Set[str] = {
    "P", "H", "H1", "H2", "H3", "H4", "H5", "H6"
}
LIST_ROLES: Set[str] = {
    "L", "LI", "Lbl", "LBody"
}
TABLE_ROLES: Set[str] = {
    "Table", "TR", "TH", "TD", "THEAD", "TBODY", "TFOOT"
}
INLINE_ROLES: Set[str] = {
    "Span", "Quote", "Note", "Reference", "BibEntry", "Code", "Link", "Annot",
    "Ruby", "RB", "RT", "RP", "Warichu", "WT", "WP"
}
ILLUSTRATION_ROLES: Set[str] = {
    "Figure", "Formula", "Form"
}


def resolve_role(tag: str, role_map: Dict[str, str]) -> Tuple[str, bool, bool]:
    """
    Resolves a structure type to its standard role via /RoleMap according to ISO 32000-1.
    Standard PDF structure types are case-sensitive.
    Returns: (standard_role, is_mapped, is_circular)
    """
    clean_tag = tag.strip("/ ")
    curr = clean_tag
    visited = set()

    while True:
        # Check exact case match first
        if curr in STANDARD_STRUCTURE_TYPES_EXACT:
            return curr, curr != clean_tag, False

        visited.add(curr)
        next_tag = role_map.get(curr) or role_map.get("/" + curr)
        if not next_tag:
            # Unmapped custom role
            return clean_tag, False, False

        clean_next = str(next_tag).strip("/ ")
        if clean_next in visited:
            # Circular mapping detected
            return clean_next, True, True

        curr = clean_next


def parse_number_tree(tree_obj: Any) -> Dict[int, Any]:
    """
    Recursively parses a PDF Number Tree dictionary into a Python dict {int_key: object}.
    Number trees can contain either /Nums or /Kids arrays.
    """
    results: Dict[int, Any] = {}
    if not isinstance(tree_obj, (pikepdf.Dictionary, pikepdf.Object)):
        return results

    try:
        if "/Nums" in tree_obj:
            nums = tree_obj["/Nums"]
            for i in range(0, len(nums), 2):
                if i + 1 < len(nums):
                    key = int(nums[i])
                    val = nums[i + 1]
                    results[key] = val

        elif "/Kids" in tree_obj:
            kids = tree_obj["/Kids"]
            for kid in kids:
                results.update(parse_number_tree(kid))
    except Exception as e:
        logger.debug(f"Error parsing number tree node: {e}")

    return results


class StructureTreeParser:
    """Extracts and builds the hierarchical StructureNode tree from a pikepdf document."""

    def __init__(
        self,
        pdf: pikepdf.Pdf,
        role_map: Dict[str, str],
        page_map: Dict[Any, int],
        page_mcid_data: Optional[Dict[int, Dict[int, Tuple[str, Tuple[float, float, float, float]]]]] = None
    ):
        self.pdf = pdf
        self.role_map = role_map
        self.page_map = page_map  # Map pikepdf page object ref -> 1-based page number
        self.page_mcid_data = page_mcid_data or {}  # page -> {mcid: (text, bbox)}
        self.node_counter = 0
        self.parent_tree_entries: Dict[int, Any] = {}
        self.has_parent_tree: bool = False
        self.parent_tree_valid: bool = False
        self._role_cache: Dict[str, Tuple[str, bool, bool]] = {}

    def _resolve_role_cached(self, tag: str) -> Tuple[str, bool, bool]:
        if tag not in self._role_cache:
            self._role_cache[tag] = resolve_role(tag, self.role_map)
        return self._role_cache[tag]

    def parse(self) -> Optional[StructureNode]:
        """Parses the root StructTreeRoot and /ParentTree if present."""
        try:
            if "/StructTreeRoot" not in self.pdf.Root:
                return None

            root_obj = self.pdf.Root.StructTreeRoot

            # Parse ParentTree
            if "/ParentTree" in root_obj:
                self.has_parent_tree = True
                try:
                    self.parent_tree_entries = parse_number_tree(root_obj["/ParentTree"])
                    self.parent_tree_valid = len(self.parent_tree_entries) > 0
                except Exception as e:
                    logger.debug(f"Failed parsing ParentTree: {e}")
                    self.parent_tree_valid = False

            root_node = StructureNode(
                id="root",
                tag="StructTreeRoot",
                standard_tag="StructTreeRoot",
                title="Root",
            )

            if "/K" in root_obj:
                k_val = root_obj["/K"]
                self._parse_k(k_val, root_node)

            # Link MCIDs from ParentTree to matching or ancestor StructureNodes
            if self.has_parent_tree and self.parent_tree_entries:
                self._link_parent_tree_mcids(root_node)

            # Compute root pages spanned
            root_spanned = set()
            for c in root_node.children:
                root_spanned.update(c.pages_spanned)
            root_node.pages_spanned = sorted(list(root_spanned))

            # Ensure nodes with spanned pages have their primary page assigned and inherit from parent
            for n in root_node.find_all_nodes():
                if n.page is None and n.pages_spanned:
                    n.page = n.pages_spanned[0]
                elif n.page is None and n.parent and n.parent.page:
                    n.page = n.parent.page

            # Post-pass: link MCID text and geometry for any nodes that received MCIDs from ParentTree or /K
            for n in root_node.find_all_nodes():
                if n.mcids and not n.bbox:
                    self._link_mcid_data(n)

            return root_node
        except Exception as e:
            logger.warning(f"Error parsing Structure Tree: {e}")
            return None

    def _parse_k(self, k_val: Any, parent_node: StructureNode):
        """Recursively parses the /K entry."""
        if k_val is None:
            return
        if isinstance(k_val, (pikepdf.Array, list, tuple)):
            for item in k_val:
                self._parse_k_item(item, parent_node)
        else:
            self._parse_k_item(k_val, parent_node)

    def _parse_k_item(self, item: Any, parent_node: StructureNode):
        if item is None:
            return
        if isinstance(item, (pikepdf.Array, list, tuple)):
            for sub_item in item:
                self._parse_k_item(sub_item, parent_node)
            return

        if isinstance(item, pikepdf.Dictionary):
            elem_type = str(item.get("/Type", ""))
            if elem_type == "/MCR":
                # Marked Content Reference
                mcid = int(item.get("/MCID", -1))
                pg_ref = item.get("/Pg")
                target_page = self._resolve_page_number(pg_ref) if pg_ref else parent_node.page
                if mcid >= 0:
                    parent_node.mcids.append(mcid)
                    parent_node.mcid_entries.append((mcid, target_page))
                if target_page and parent_node.page is None:
                    parent_node.page = target_page
                return

            if elem_type == "/OBJR":
                # Object reference
                pg_ref = item.get("/Pg")
                target_page = self._resolve_page_number(pg_ref) if pg_ref else parent_node.page
                if target_page and parent_node.page is None:
                    parent_node.page = target_page
                return

            # Structural element /StructElem
            self.node_counter += 1
            node_id = f"node_{self.node_counter}"

            raw_tag = str(item.get("/S", "Span")).strip("/ ")
            standard_tag, _, _ = self._resolve_role_cached(raw_tag)

            title = str(item.get("/T")).replace("\x00", "").strip() if "/T" in item else None
            alt_raw = item.get("/Alt")
            alt_text = str(alt_raw).replace("\x00", "") if alt_raw is not None else None
            actual_raw = item.get("/ActualText")
            actual_text = str(actual_raw).replace("\x00", "") if actual_raw is not None else None
            exp_raw = item.get("/E")
            expanded_text = str(exp_raw).replace("\x00", "").strip() if exp_raw is not None else None
            lang = str(item.get("/Lang")).replace("\x00", "").strip() if "/Lang" in item else None

            page_num = None
            if "/Pg" in item:
                page_num = self._resolve_page_number(item["/Pg"])

            # Attributes dictionary /A
            attrs: Dict[str, Any] = {}
            has_explicit_bbox = False
            struct_bbox: Optional[Tuple[float, float, float, float]] = None
            placement: Optional[str] = None

            def _extract_from_attr_dict(ad: pikepdf.Dictionary):
                nonlocal has_explicit_bbox, struct_bbox, placement
                for k, v in ad.items():
                    k_str = str(k).strip("/")
                    if k_str.lower() == "bbox":
                        if isinstance(v, (pikepdf.Array, list, tuple)):
                            if len(v) == 0:
                                # Empty array represents unspecified BBox; do not record as explicit/malformed
                                pass
                            else:
                                is_valid, parsed_bbox = validate_bbox_coordinates(v)
                                if is_valid and parsed_bbox is not None:
                                    attrs[k_str] = list(parsed_bbox)
                                    struct_bbox = parsed_bbox
                                    has_explicit_bbox = True
                                else:
                                    try:
                                        attrs[k_str] = [float(x) for x in v]
                                    except Exception:
                                        attrs[k_str] = [str(x) for x in v]
                                    has_explicit_bbox = True
                        else:
                            attrs[k_str] = str(v)
                            has_explicit_bbox = True
                    else:
                        attrs[k_str] = str(v)
                        if k_str.lower() == "placement":
                            placement = str(v).strip("/ ")

            if "/A" in item:
                a_val = item["/A"]
                if isinstance(a_val, pikepdf.Dictionary):
                    _extract_from_attr_dict(a_val)
                elif isinstance(a_val, (pikepdf.Array, list)):
                    for a_elem in a_val:
                        if isinstance(a_elem, pikepdf.Dictionary):
                            _extract_from_attr_dict(a_elem)

            has_pg = "/Pg" in item
            pg_val = page_num if has_pg else None

            is_artifact = (
                elem_type == "/Artifact"
                or raw_tag.lower() == "artifact"
                or standard_tag.lower() == "artifact"
                or attrs.get("O") == "/Artifact"
                or attrs.get("Type") == "/Pagination"
            )

            child_node = StructureNode(
                id=node_id,
                tag=raw_tag,
                standard_tag=standard_tag,
                title=title,
                alt_text=alt_text,
                actual_text=actual_text,
                expanded_text=expanded_text,
                is_artifact=is_artifact,
                lang=lang,
                page=page_num or parent_node.page,
                attributes=attrs,
                struct_bbox=struct_bbox,
                has_explicit_bbox=has_explicit_bbox,
                placement=placement,
                obj_num=getattr(item, "objgen", (None, None))[0] if hasattr(item, "objgen") else None,
                has_pg_attr=has_pg,
                pg_attr_val=pg_val,
                parent=parent_node
            )

            # Traverse /K of this element
            if "/K" in item:
                self._parse_k(item["/K"], child_node)

            # Attach actual page text and bounding box from MCID data
            self._link_mcid_data(child_node)

            # If figure/formula, distinguish extracted graphic text from alt text
            if standard_tag.upper() in ("FIGURE", "FORMULA"):
                if child_node.text_content and child_node.text_content.strip():
                    child_node.extracted_graphic_text = child_node.text_content.strip().replace("\x00", "")

            # Detect character decoding anomalies (unmapped glyphs / PUA without ActualText)
            sample_text = (actual_text or "") + (child_node.text_content or "")
            pua_present = any("\ue000" <= c <= "\uf8ff" for c in (child_node.text_content or ""))
            is_exempt = child_node.is_in_formula() or bool(actual_text) or child_node.has_actual_text_ancestor() or child_node.is_artifact_ancestor()
            if "\ufffd" in sample_text or (pua_present and not is_exempt):
                child_node.has_decoding_error = True
                child_node.decoding_error_msg = "Contains unmapped glyphs, replacement characters (), or undecodable font encoding."

            # Fast bottom-up post-order collection of pages spanned (O(1) per node)
            spanned = set([child_node.page] if child_node.page else [])
            for mcid, pg in child_node.mcid_entries:
                if pg:
                    spanned.add(pg)
            for c in child_node.children:
                spanned.update(c.pages_spanned)
            child_node.pages_spanned = sorted(list(spanned))

            parent_node.children.append(child_node)

        elif isinstance(item, (int, pikepdf.Integer)):
            # Direct MCID on parent
            mcid = int(item)
            parent_node.mcids.append(mcid)
            parent_node.mcid_entries.append((mcid, parent_node.page))
            self._link_mcid_data(parent_node)

    def _link_mcid_data(self, node: StructureNode):
        """Populates node.text_content and node.bbox from real page MCID records."""
        if not node.mcids:
            return

        texts: List[str] = []
        bboxes: List[Tuple[float, float, float, float]] = []

        if node.mcid_entries:
            for mcid, pg in node.mcid_entries:
                pg_num = pg or node.page
                if not pg_num:
                    continue
                page_data = self.page_mcid_data.get(pg_num)
                if not page_data or mcid not in page_data:
                    continue
                txt, box = page_data[mcid]
                if txt:
                    texts.append(txt)
                if box and any(c > 0 for c in box):
                    bboxes.append(box)
        elif node.page:
            page_data = self.page_mcid_data.get(node.page)
            if page_data:
                for mcid in node.mcids:
                    if mcid in page_data:
                        txt, box = page_data[mcid]
                        if txt:
                            texts.append(txt)
                        if box and any(c > 0 for c in box):
                            bboxes.append(box)

        if texts and not node.text_content:
            node.text_content = " ".join(texts)

        if bboxes and not node.bbox:
            # Union of bounding boxes
            min_x = min(b[0] for b in bboxes)
            min_y = min(b[1] for b in bboxes)
            max_x = max(b[2] for b in bboxes)
            max_y = max(b[3] for b in bboxes)
            node.bbox = (min_x, min_y, max_x, max_y)

    def _link_parent_tree_mcids(self, root_node: StructureNode):
        """Associates MCIDs from ParentTree with corresponding structure elements or nearest ancestor."""
        all_nodes = root_node.find_all_nodes()
        nodes_by_obj: Dict[int, StructureNode] = {n.obj_num: n for n in all_nodes if n.obj_num is not None}

        # Build map of struct_parents_id -> page_num
        sp_to_page: Dict[int, int] = {}
        for page_idx, pike_page in enumerate(self.pdf.pages, start=1):
            if "/StructParents" in pike_page:
                try:
                    sp_to_page[int(pike_page["/StructParents"])] = page_idx
                except Exception:
                    pass

        for sp_id, items in self.parent_tree_entries.items():
            if sp_id not in sp_to_page:
                continue
            page_num = sp_to_page[sp_id]
            if not isinstance(items, (pikepdf.Array, list)):
                continue

            for mcid_int, target in enumerate(items):
                if target is None:
                    continue

                target_obj_num = getattr(target, "objgen", (None, None))[0] if hasattr(target, "objgen") else None
                node = nodes_by_obj.get(target_obj_num)

                if node:
                    if mcid_int not in node.mcids:
                        node.mcids.append(mcid_int)
                        node.mcid_entries.append((mcid_int, node.page or page_num))
                    if node.page is None:
                        node.page = page_num

    def _resolve_page_number(self, pg_obj: Any) -> Optional[int]:
        """Resolves a pikepdf page dictionary or indirect object to a 1-based page number."""
        try:
            if hasattr(pg_obj, "objgen") and pg_obj.objgen in self.page_map:
                return self.page_map[pg_obj.objgen]
            if hasattr(pg_obj, "objgen") and pg_obj.objgen[0] in self.page_map:
                return self.page_map[pg_obj.objgen[0]]
            if isinstance(pg_obj, (pikepdf.Array, list, tuple)) and len(pg_obj) >= 2:
                try:
                    gen_pair = (int(pg_obj[0]), int(pg_obj[1]))
                    if gen_pair in self.page_map:
                        return self.page_map[gen_pair]
                    if gen_pair[0] in self.page_map:
                        return self.page_map[gen_pair[0]]
                except Exception:
                    pass
            # Also try direct object ref id
            if id(pg_obj) in self.page_map:
                return self.page_map[id(pg_obj)]
        except Exception:
            pass
        return None
