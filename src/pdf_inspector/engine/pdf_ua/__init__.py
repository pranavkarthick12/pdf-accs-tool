"""PDF/UA ISO 14289-1 rule implementations."""

from .syntax_rules import PDFSyntaxBasicRule
from .font_rules import FontEmbeddingRule, FontToUnicodeRule
from .content_rules import (
    TaggedPDFRule, ContentTaggedRule, TaggedInsideArtifactRule, MCIDStructureReferenceRule,
    StructureMCIDExistenceRule, NestedMarkedContentRule
)
from .embedded_files_rules import EmbeddedFilesAccessibilityRule
from .language_rules import DocumentLanguageRule, StructureLanguageRule
from .structure_rules import (
    StructureTreeIntegrityRule, StructureNestingRule, EmptyStructureElementsRule, FigureBoundingBoxRule
)
from .role_map_rules import RoleMappingValidityRule
from .alt_text_rules import FigureAlternativeTextRule
from .metadata_rules import (
    MetadataCompletenessRule, XMPMetadataStreamRule, XMPDocumentTitleRule, PDFUAIdentifierRule
)
from .document_settings_rules import DisplayDocTitleRule, BookmarkStructureRule
from .parent_tree_rules import ParentTreeIntegrityRule
from .artifact_rules import ArtifactInStructureTreeRule, ArtifactInsideTaggedContentRule
from .list_rules import ListStructureHierarchyRule
from .table_rules import TableStructureHeadersRule
from .annotation_rules import AnnotationTaggedRule, PageTabOrderRule
from .form_rules import FormFieldAccessibilityRule
from .unicode_rules import UnicodePUARule, ReplacementCharacterRule

PDF_UA_RULES = [
    PDFSyntaxBasicRule(),
    FontEmbeddingRule(),
    FontToUnicodeRule(),
    UnicodePUARule(),
    ReplacementCharacterRule(),
    TaggedPDFRule(),
    ContentTaggedRule(),
    TaggedInsideArtifactRule(),
    MCIDStructureReferenceRule(),
    StructureMCIDExistenceRule(),
    NestedMarkedContentRule(),
    ArtifactInStructureTreeRule(),
    ArtifactInsideTaggedContentRule(),
    AnnotationTaggedRule(),
    PageTabOrderRule(),
    EmbeddedFilesAccessibilityRule(),
    DocumentLanguageRule(),
    StructureLanguageRule(),
    StructureTreeIntegrityRule(),
    ParentTreeIntegrityRule(),
    StructureNestingRule(),
    FigureBoundingBoxRule(),
    ListStructureHierarchyRule(),
    TableStructureHeadersRule(),
    EmptyStructureElementsRule(),
    RoleMappingValidityRule(),
    FigureAlternativeTextRule(),
    MetadataCompletenessRule(),
    DisplayDocTitleRule(),
    BookmarkStructureRule(),
]

__all__ = [
    "PDF_UA_RULES",
    "PDFSyntaxBasicRule",
    "FontEmbeddingRule",
    "FontToUnicodeRule",
    "UnicodePUARule",
    "ReplacementCharacterRule",
    "TaggedPDFRule",
    "ContentTaggedRule",
    "TaggedInsideArtifactRule",
    "MCIDStructureReferenceRule",
    "StructureMCIDExistenceRule",
    "NestedMarkedContentRule",
    "ArtifactInStructureTreeRule",
    "ArtifactInsideTaggedContentRule",
    "AnnotationTaggedRule",
    "PageTabOrderRule",
    "FormFieldAccessibilityRule",
    "EmbeddedFilesAccessibilityRule",
    "DocumentLanguageRule",
    "StructureLanguageRule",
    "StructureTreeIntegrityRule",
    "ParentTreeIntegrityRule",
    "StructureNestingRule",
    "FigureBoundingBoxRule",
    "ListStructureHierarchyRule",
    "TableStructureHeadersRule",
    "EmptyStructureElementsRule",
    "RoleMappingValidityRule",
    "FigureAlternativeTextRule",
    "MetadataCompletenessRule",
    "XMPMetadataStreamRule",
    "XMPDocumentTitleRule",
    "PDFUAIdentifierRule",
    "DisplayDocTitleRule",
    "BookmarkStructureRule",
]
