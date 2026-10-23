"""Views for PDF Accessibility Inspector."""

from .dashboard_view import DashboardView
from .checkpoints_view import CheckpointsView
from .detailed_results_view import DetailedResultsView
from .tag_tree_view import TagTreeView
from .screen_reader_view import ScreenReaderView, SemanticReaderView
from .metadata_view import MetadataView
from .statistics_view import StatisticsView
from .elements_view import ElementsView
from .batch_view import BatchScanView
from .loading_view import LoadingView

__all__ = [
    "DashboardView",
    "CheckpointsView",
    "DetailedResultsView",
    "TagTreeView",
    "ScreenReaderView",
    "SemanticReaderView",
    "MetadataView",
    "StatisticsView",
    "ElementsView",
    "BatchScanView",
    "LoadingView",
]
