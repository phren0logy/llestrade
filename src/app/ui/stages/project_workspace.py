"""Dashboard workspace for the new UI."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, List, Sequence, Set, Tuple

from PySide6.QtCore import Qt, QUrl, Signal
from shiboken6 import isValid
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QDialog,
    QComboBox,
    QGroupBox,
    QLineEdit,
    QProgressBar,
    QSpinBox,
    QTextEdit,
)
from PySide6.QtWidgets import QHeaderView

from src.app.core.conversion_manager import (
    ConversionJob,
    DuplicateSource,
    build_conversion_jobs,
)
from src.app.core.feature_flags import FeatureFlags
from src.app.core.file_tracker import WorkspaceMetrics, WorkspaceGroupMetrics
from src.app.core.project_manager import ProjectManager, ProjectMetadata
from src.app.core.summary_groups import SummaryGroup
from src.app.core.bulk_paths import iter_map_outputs
from src.app.core.report_inputs import (
    REPORT_CATEGORY_BULK_COMBINED,
    REPORT_CATEGORY_BULK_MAP,
    REPORT_CATEGORY_CONVERTED,
    REPORT_CATEGORY_HIGHLIGHT_COLOR,
    REPORT_CATEGORY_HIGHLIGHT_DOCUMENT,
    ReportInputDescriptor,
    category_display_name,
)
from src.app.core.refinement_prompt import (
    read_generation_prompt,
    read_refinement_prompt,
    validate_generation_prompt,
    validate_refinement_prompt,
)
from src.app.core.report_template_sections import load_template_sections
from src.app.ui.dialogs.project_metadata_dialog import ProjectMetadataDialog
from src.app.ui.dialogs.summary_group_dialog import SummaryGroupDialog
from src.app.ui.dialogs.prompt_preview_dialog import PromptPreviewDialog
from src.app.workers import (
    BulkAnalysisWorker,
    BulkReduceWorker,
    ConversionWorker,
    HighlightWorker,
    ReportWorker,
    WorkerCoordinator,
    get_worker_pool,
)
from src.config.prompt_store import (
    get_template_custom_dir,
    get_bundled_dir,
    get_custom_dir,
    get_repo_prompts_dir,
)
from src.app.core.prompt_preview import generate_prompt_preview, PromptPreviewError

LOGGER = logging.getLogger(__name__)

def _qt_flag(*names: str):
    """Return the first matching Qt ItemFlag for backwards compatibility."""

    item_flag_container = getattr(Qt, "ItemFlag", None)
    for name in names:
        if item_flag_container is not None and hasattr(item_flag_container, name):
            return getattr(item_flag_container, name)
        if hasattr(Qt, name):
            return getattr(Qt, name)
    # Fallback to zero-value flag
    if item_flag_container is not None:
        return item_flag_container(0)
    return 0


_ITEM_IS_USER_CHECKABLE = _qt_flag("ItemIsUserCheckable")
_ITEM_IS_TRISTATE = _qt_flag("ItemIsTristate", "ItemIsAutoTristate")
_ITEM_IS_ENABLED = _qt_flag("ItemIsEnabled")


class ProjectWorkspace(QWidget):
    """Dashboard workspace showing documents and bulk analysis groups."""

    home_requested = Signal()

    def __init__(
        self,
        project_manager: Optional[ProjectManager] = None,
        parent: Optional[QWidget] = None,
        *,
        feature_flags: Optional[FeatureFlags] = None,
    ) -> None:
        super().__init__(parent)
        self._feature_flags = feature_flags or FeatureFlags()
        self._project_manager: Optional[ProjectManager] = None
        self._project_path_label = QLabel()
        self._metadata_label: QLabel | None = None
        self._edit_metadata_button: QPushButton | None = None
        self._home_button: QPushButton | None = None
        self._workspace_metrics: WorkspaceMetrics | None = None
        self._current_warnings: List[str] = []
        self._thread_pool = get_worker_pool()
        self._workers = WorkerCoordinator(self._thread_pool)
        self._inflight_sources: set[Path] = set()
        self._conversion_running = False
        self._conversion_total = 0
        self._missing_root_prompted = False
        self._running_groups: set[str] = set()
        self._bulk_progress: Dict[str, tuple[int, int]] = {}
        self._bulk_failures: Dict[str, List[str]] = {}
        self._cancelling_groups: set[str] = set()
        self._summary_tab: QWidget | None = None
        self._summary_table: QTableWidget | None = None
        self._summary_empty_label: QLabel | None = None
        self._summary_info_label: QLabel | None = None
        self._missing_bulk_label: QLabel | None = None
        self._group_source_tree: QTreeWidget | None = None
        self._extract_highlights_button: QPushButton | None = None
        self._highlight_running = False
        self._highlight_total = 0
        self._highlight_errors: List[str] = []
        self._missing_highlights_label: QLabel | None = None
        self._highlights_tab: QWidget | None = None
        self._highlight_counts_label: QLabel | None = None
        self._highlight_last_run_label: QLabel | None = None
        self._highlight_status_label: QLabel | None = None
        self._highlight_tree: QTreeWidget | None = None
        self._open_highlights_button: QPushButton | None = None
        self._reports_tab: QWidget | None = None
        self._report_inputs_tree: QTreeWidget | None = None
        self._report_selected_inputs: Set[str] = set()
        self._report_model_combo: QComboBox | None = None
        self._report_custom_model_edit: QLineEdit | None = None
        self._report_custom_model_label: QLabel | None = None
        self._report_custom_context_spin: QSpinBox | None = None
        self._report_custom_context_label: QLabel | None = None
        self._report_generation_user_prompt_edit: QLineEdit | None = None
        self._report_refinement_prompt_edit: QLineEdit | None = None
        self._report_generate_button: QPushButton | None = None
        self._report_progress_bar: QProgressBar | None = None
        self._report_log: QTextEdit | None = None
        self._report_template_edit: QLineEdit | None = None
        self._report_transcript_edit: QLineEdit | None = None
        self._report_generation_system_prompt_edit: QLineEdit | None = None
        self._report_refinement_system_prompt_edit: QLineEdit | None = None
        self._report_history_list: QTreeWidget | None = None
        self._report_open_draft_button: QPushButton | None = None
        self._report_open_refined_button: QPushButton | None = None
        self._report_open_reasoning_button: QPushButton | None = None
        self._report_open_manifest_button: QPushButton | None = None
        self._report_open_inputs_button: QPushButton | None = None
        self._report_last_result: Optional[Dict[str, str]] = None
        self._report_running = False

        self._build_ui()
        if project_manager:
            self.set_project(project_manager)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(8)

        self._home_button = QPushButton("home")
        self._home_button.setCursor(Qt.PointingHandCursor)
        self._home_button.setFlat(True)
        self._home_button.clicked.connect(self.home_requested.emit)
        top_bar.addWidget(self._home_button)

        self._project_path_label.setStyleSheet("font-weight: 600;")
        top_bar.addWidget(self._project_path_label)
        top_bar.addStretch()

        layout.addLayout(top_bar)

        self._tabs = QTabWidget()
        self._documents_tab = self._build_documents_tab()
        self._tabs.addTab(self._documents_tab, "Documents")
        self._highlights_tab = self._build_highlights_tab()
        self._tabs.addTab(self._highlights_tab, "Highlights")
        if self._feature_flags.summary_groups_enabled:
            self._summary_tab = self._build_summary_groups_tab()
            self._tabs.addTab(self._summary_tab, "Bulk Analysis")
        self._reports_tab = self._build_reports_tab()
        self._tabs.addTab(self._reports_tab, "Reports")
        metadata_row = QHBoxLayout()
        metadata_row.setContentsMargins(0, 0, 0, 0)
        self._metadata_label = QLabel("Subject: — | DOB: —")
        self._metadata_label.setStyleSheet("color: #555;")
        metadata_row.addWidget(self._metadata_label)
        metadata_row.addStretch()
        self._edit_metadata_button = QPushButton("Edit Project Info…")
        self._edit_metadata_button.setEnabled(False)
        self._edit_metadata_button.clicked.connect(self._edit_project_metadata)
        metadata_row.addWidget(self._edit_metadata_button)
        layout.addLayout(metadata_row)
        layout.addWidget(self._tabs)

    def _build_documents_tab(self) -> QWidget:
        widget = QWidget()
        tab_layout = QVBoxLayout(widget)
        tab_layout.setSpacing(8)

        # Source root selector
        root_layout = QHBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        self._source_root_label = QLabel("Source root: not set")
        self._source_root_label.setStyleSheet("font-weight: bold;")
        root_layout.addWidget(self._source_root_label)
        root_layout.addStretch()
        tab_layout.addLayout(root_layout)

        # Counts + scan controls
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        self._counts_label = QLabel("Re-scan pending…")
        header_layout.addWidget(self._counts_label)
        header_layout.addStretch()
        self._last_scan_label = QLabel("")
        self._last_scan_label.setStyleSheet("color: #666;")
        header_layout.addWidget(self._last_scan_label)
        self._rescan_button = QPushButton("Re-scan")
        self._rescan_button.clicked.connect(lambda: self._trigger_conversion(auto_run=False))
        header_layout.addWidget(self._rescan_button)
        tab_layout.addLayout(header_layout)

        # Tree view for folder selection
        self._source_tree = QTreeWidget()
        self._source_tree.setHeaderHidden(True)
        self._source_tree.setSelectionMode(QAbstractItemView.NoSelection)
        tab_layout.addWidget(self._source_tree)

        self._root_warning_label = QLabel("")
        self._root_warning_label.setWordWrap(True)
        self._root_warning_label.setStyleSheet("color: #b26a00;")
        tab_layout.addWidget(self._root_warning_label)
        self._root_warning_label.hide()

        self._missing_highlights_label = QLabel("Highlights missing: —")
        self._missing_highlights_label.setWordWrap(True)
        tab_layout.addWidget(self._missing_highlights_label)

        self._missing_bulk_label = QLabel("Bulk analysis missing: —")

        self._missing_bulk_label.setWordWrap(True)
        tab_layout.addWidget(self._missing_bulk_label)

        tab_layout.addStretch()
        return widget

    def _wrap_line_edit_with_button(self, line_edit: QLineEdit, button: QPushButton) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit)
        layout.addWidget(button)
        return container

    def _build_highlights_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        self._highlight_counts_label = QLabel("Highlights extracted: 0 | Pending: 0")
        header_layout.addWidget(self._highlight_counts_label)
        header_layout.addStretch()
        self._highlight_last_run_label = QLabel("Last run: —")
        self._highlight_last_run_label.setStyleSheet("color: #666;")
        header_layout.addWidget(self._highlight_last_run_label)
        layout.addLayout(header_layout)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        self._extract_highlights_button = QPushButton("Extract Highlights")
        self._extract_highlights_button.setEnabled(False)
        self._extract_highlights_button.clicked.connect(self._trigger_highlight_extraction)
        button_row.addWidget(self._extract_highlights_button)

        self._open_highlights_button = QPushButton("Open Highlights Folder")
        self._open_highlights_button.setEnabled(False)
        self._open_highlights_button.clicked.connect(self._open_highlights_folder)
        button_row.addWidget(self._open_highlights_button)

        button_row.addStretch()
        layout.addLayout(button_row)

        self._highlight_status_label = QLabel("Highlights have not been extracted yet.")
        self._highlight_status_label.setWordWrap(True)
        self._highlight_status_label.setStyleSheet("color: #555;")
        layout.addWidget(self._highlight_status_label)

        self._highlight_tree = QTreeWidget()
        self._highlight_tree.setColumnCount(2)
        self._highlight_tree.setHeaderLabels(["Category", "Relative Path"])
        self._highlight_tree.setHeaderHidden(False)
        self._highlight_tree.setIndentation(18)
        self._highlight_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self._highlight_tree.itemDoubleClicked.connect(self._open_highlight_item)
        layout.addWidget(self._highlight_tree)

        return widget

    def _build_reports_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)

        inputs_group = QGroupBox("Select Inputs")
        inputs_layout = QVBoxLayout(inputs_group)
        self._report_inputs_tree = QTreeWidget()
        self._report_inputs_tree.setColumnCount(2)
        self._report_inputs_tree.setHeaderLabels(["Input", "Project Path"])
        self._report_inputs_tree.setUniformRowHeights(True)
        self._report_inputs_tree.setSelectionMode(QAbstractItemView.NoSelection)
        self._report_inputs_tree.itemChanged.connect(self._on_report_input_changed)
        inputs_layout.addWidget(self._report_inputs_tree)
        top_layout.addWidget(inputs_group, 1)

        config_group = QGroupBox("Configuration")
        config_layout = QVBoxLayout(config_group)
        config_layout.setSpacing(6)

        model_row = QHBoxLayout()
        model_row.setContentsMargins(0, 0, 0, 0)
        model_row.addWidget(QLabel("Model:"))
        self._report_model_combo = self._build_report_model_combo()
        self._report_model_combo.currentIndexChanged.connect(self._on_report_model_changed)
        model_row.addWidget(self._report_model_combo)
        config_layout.addLayout(model_row)

        self._report_custom_model_label = QLabel("Custom model id:")
        self._report_custom_model_edit = QLineEdit()
        custom_model_row = QHBoxLayout()
        custom_model_row.setContentsMargins(0, 0, 0, 0)
        custom_model_row.addWidget(self._report_custom_model_label)
        custom_model_row.addWidget(self._report_custom_model_edit)
        config_layout.addLayout(custom_model_row)

        self._report_custom_context_label = QLabel("Context window:")
        self._report_custom_context_spin = QSpinBox()
        self._report_custom_context_spin.setRange(10_000, 400_000)
        self._report_custom_context_spin.setSingleStep(1_000)
        context_row = QHBoxLayout()
        context_row.setContentsMargins(0, 0, 0, 0)
        context_row.addWidget(self._report_custom_context_label)
        context_row.addWidget(self._report_custom_context_spin)
        context_row.addWidget(QLabel("tokens"))
        config_layout.addLayout(context_row)

        template_label = QLabel("Template (required):")
        config_layout.addWidget(template_label)
        self._report_template_edit = QLineEdit()
        template_browse = QPushButton("Browse…")
        template_browse.clicked.connect(self._browse_report_template)
        config_layout.addWidget(
            self._wrap_line_edit_with_button(self._report_template_edit, template_browse)
        )

        transcript_label = QLabel("Transcript (optional):")
        config_layout.addWidget(transcript_label)
        self._report_transcript_edit = QLineEdit()
        transcript_browse = QPushButton("Browse…")
        transcript_browse.clicked.connect(self._browse_report_transcript)
        config_layout.addWidget(
            self._wrap_line_edit_with_button(self._report_transcript_edit, transcript_browse)
        )

        generation_user_label = QLabel("Generation user prompt:")
        config_layout.addWidget(generation_user_label)
        self._report_generation_user_prompt_edit = QLineEdit()
        self._report_generation_user_prompt_edit.textChanged.connect(self._update_report_controls)
        generation_user_browse = QPushButton("Browse…")
        generation_user_browse.clicked.connect(self._browse_generation_user_prompt)
        config_layout.addWidget(
            self._wrap_line_edit_with_button(
                self._report_generation_user_prompt_edit,
                generation_user_browse,
            )
        )
        generation_preview_button = QPushButton("Preview generation prompt")
        generation_preview_button.clicked.connect(self._preview_generation_prompt)
        config_layout.addWidget(generation_preview_button)

        generation_system_label = QLabel("Generation system prompt:")
        config_layout.addWidget(generation_system_label)
        self._report_generation_system_prompt_edit = QLineEdit()
        self._report_generation_system_prompt_edit.textChanged.connect(self._update_report_controls)
        gen_system_browse = QPushButton("Browse…")
        gen_system_browse.clicked.connect(self._browse_generation_system_prompt)
        config_layout.addWidget(
            self._wrap_line_edit_with_button(
                self._report_generation_system_prompt_edit,
                gen_system_browse,
            )
        )

        refinement_user_label = QLabel("Refinement user prompt:")
        config_layout.addWidget(refinement_user_label)
        self._report_refinement_prompt_edit = QLineEdit()
        self._report_refinement_prompt_edit.textChanged.connect(self._update_report_controls)
        refinement_browse = QPushButton("Browse…")
        refinement_browse.clicked.connect(self._browse_refinement_prompt)
        config_layout.addWidget(
            self._wrap_line_edit_with_button(self._report_refinement_prompt_edit, refinement_browse)
        )
        refinement_preview_button = QPushButton("Preview refinement prompt")
        refinement_preview_button.clicked.connect(self._preview_refinement_prompt)
        config_layout.addWidget(refinement_preview_button)

        refinement_system_label = QLabel("Refinement system prompt:")
        config_layout.addWidget(refinement_system_label)
        self._report_refinement_system_prompt_edit = QLineEdit()
        self._report_refinement_system_prompt_edit.textChanged.connect(self._update_report_controls)
        ref_system_browse = QPushButton("Browse…")
        ref_system_browse.clicked.connect(self._browse_refinement_system_prompt)
        config_layout.addWidget(
            self._wrap_line_edit_with_button(
                self._report_refinement_system_prompt_edit,
                ref_system_browse,
            )
        )

        if self._report_generation_user_prompt_edit and not self._report_generation_user_prompt_edit.text().strip():
            default_generation_user = self._default_generation_user_prompt_path()
            if default_generation_user:
                self._report_generation_user_prompt_edit.setText(default_generation_user)
        if self._report_generation_system_prompt_edit and not self._report_generation_system_prompt_edit.text().strip():
            default_generation_system = self._default_generation_system_prompt_path()
            if default_generation_system:
                self._report_generation_system_prompt_edit.setText(default_generation_system)
        if self._report_refinement_prompt_edit and not self._report_refinement_prompt_edit.text().strip():
            default_refinement = self._default_refinement_user_prompt_path()
            if default_refinement:
                self._report_refinement_prompt_edit.setText(default_refinement)
        if self._report_refinement_system_prompt_edit and not self._report_refinement_system_prompt_edit.text().strip():
            default_refinement_system = self._default_refinement_system_prompt_path()
            if default_refinement_system:
                self._report_refinement_system_prompt_edit.setText(default_refinement_system)


        top_layout.addWidget(config_group, 1)
        layout.addLayout(top_layout)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        self._report_generate_button = QPushButton("Generate & Refine Report")
        self._report_generate_button.clicked.connect(self._start_report_job)
        button_row.addWidget(self._report_generate_button)
        open_reports = QPushButton("Open Reports Folder")
        open_reports.clicked.connect(self._open_reports_folder)
        button_row.addWidget(open_reports)
        button_row.addStretch()
        layout.addLayout(button_row)

        self._report_progress_bar = QProgressBar()
        self._report_progress_bar.setRange(0, 100)
        self._report_progress_bar.setValue(0)
        layout.addWidget(self._report_progress_bar)

        self._report_log = QTextEdit()
        self._report_log.setReadOnly(True)
        self._report_log.setMinimumHeight(140)
        layout.addWidget(self._report_log)

        history_group = QGroupBox("Recent Reports")
        history_layout = QVBoxLayout(history_group)
        self._report_history_list = QTreeWidget()
        self._report_history_list.setColumnCount(3)
        self._report_history_list.setHeaderLabels(["Generated", "Model", "Outputs"])
        self._report_history_list.itemSelectionChanged.connect(self._on_report_history_selected)
        history_layout.addWidget(self._report_history_list)

        history_buttons = QHBoxLayout()
        self._report_open_draft_button = QPushButton("Open Draft")
        self._report_open_draft_button.clicked.connect(lambda: self._open_report_history_file("draft"))
        history_buttons.addWidget(self._report_open_draft_button)
        self._report_open_refined_button = QPushButton("Open Refined")
        self._report_open_refined_button.clicked.connect(lambda: self._open_report_history_file("refined"))
        history_buttons.addWidget(self._report_open_refined_button)
        self._report_open_reasoning_button = QPushButton("Open Reasoning")
        self._report_open_reasoning_button.clicked.connect(lambda: self._open_report_history_file("reasoning"))
        history_buttons.addWidget(self._report_open_reasoning_button)
        self._report_open_manifest_button = QPushButton("Open Manifest")
        self._report_open_manifest_button.clicked.connect(lambda: self._open_report_history_file("manifest"))
        history_buttons.addWidget(self._report_open_manifest_button)
        self._report_open_inputs_button = QPushButton("Open Inputs")
        self._report_open_inputs_button.clicked.connect(lambda: self._open_report_history_file("inputs"))
        history_buttons.addWidget(self._report_open_inputs_button)
        history_buttons.addStretch()
        history_layout.addLayout(history_buttons)

        layout.addWidget(history_group)

        self._on_report_model_changed()
        self._update_report_history_buttons()
        return widget

    def _build_summary_groups_tab(self) -> QWidget:
        self._summary_tab = QWidget()
        layout = QVBoxLayout(self._summary_tab)
        layout.setSpacing(8)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(QLabel("Manage bulk analysis groups to organise processed documents."))
        header_layout.addStretch()
        create_button = QPushButton("New Bulk Analysis…")
        create_button.clicked.connect(self._show_create_group_dialog)
        header_layout.addWidget(create_button)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)
        header_layout.addWidget(refresh_button)
        layout.addLayout(header_layout)

        self._summary_info_label = QLabel("No bulk analysis groups yet.")
        layout.addWidget(self._summary_info_label)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)

        table_container = QVBoxLayout()
        table_container.setSpacing(6)

        self._summary_table = QTableWidget(0, 5)
        self._summary_table.setHorizontalHeaderLabels(["Group", "Coverage", "Updated", "Status", "Actions"])
        self._summary_table.verticalHeader().setVisible(False)
        self._summary_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._summary_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._summary_table.setSelectionMode(QAbstractItemView.NoSelection)
        header = self._summary_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        table_container.addWidget(self._summary_table)

        self._summary_empty_label = QLabel("No bulk analysis groups created yet.")
        self._summary_empty_label.setAlignment(Qt.AlignCenter)
        self._summary_empty_label.setStyleSheet("color: #666; padding: 20px;")
        table_container.addWidget(self._summary_empty_label)
        self._summary_empty_label.hide()

        content_layout.addLayout(table_container, 2)

        tree_container = QVBoxLayout()
        tree_container.setSpacing(4)
        tree_label = QLabel("Folder coverage (read-only)")
        tree_label.setStyleSheet("color: #666; font-size: 11px;")
        tree_container.addWidget(tree_label)

        self._group_source_tree = QTreeWidget()
        self._group_source_tree.setHeaderHidden(True)
        self._group_source_tree.setUniformRowHeights(True)
        self._group_source_tree.setSelectionMode(QAbstractItemView.NoSelection)
        self._group_source_tree.setFocusPolicy(Qt.NoFocus)
        tree_container.addWidget(self._group_source_tree)

        content_layout.addLayout(tree_container, 1)

        layout.addLayout(content_layout)

        return self._summary_tab

    def set_project(self, project_manager: ProjectManager) -> None:
        """Attach the workspace to a project manager."""
        self._project_manager = project_manager
        self._running_groups.clear()
        self._workers.clear()
        self._workspace_metrics = None
        project_dir = project_manager.project_dir
        project_path = Path(project_dir).resolve() if project_dir else None
        self._project_path_label.setText(
            f"Active project: {project_path}" if project_path else "Active project: (unsaved)"
        )
        if self._edit_metadata_button:
            self._edit_metadata_button.setEnabled(True)
        self._update_highlight_button_state()
        self._update_metadata_label()
        self._populate_source_tree()
        self._update_source_root_label()
        self._update_last_scan_label()
        self._load_report_preferences()
        self.refresh()

    def project_manager(self) -> Optional[ProjectManager]:
        return self._project_manager

    def shutdown(self) -> None:
        """Cancel background work before disposing of the workspace."""

        self._workers.clear()
        self._running_groups.clear()
        self._bulk_progress.clear()
        self._bulk_failures.clear()
        self._highlight_errors.clear()

    def refresh(self) -> None:
        self._populate_source_tree()
        self._update_source_root_label()
        self._refresh_file_tracker()
        self._refresh_reports_tab()
        self._refresh_highlights_tab()
        self._update_highlight_button_state()
        if self._feature_flags.summary_groups_enabled:
            self._prune_running_groups()
            self._refresh_summary_groups()
        else:
            self._running_groups.clear()
        self._update_metadata_label()

    def _update_metadata_label(self) -> None:
        if not self._metadata_label:
            return
        metadata = self._project_manager.metadata if self._project_manager else None
        if not metadata:
            self._metadata_label.setText("Subject: — | DOB: —")
            return

        subject = metadata.subject_name.strip() if metadata.subject_name else "—"
        dob = metadata.date_of_birth.strip() if metadata.date_of_birth else "—"
        parts = [f"Subject: {subject}", f"DOB: {dob}"]
        if metadata.case_description:
            first_line = metadata.case_description.strip().splitlines()[0]
            if len(first_line) > 80:
                first_line = first_line[:77] + "…"
            parts.append(f"Case info: {first_line}")
        self._metadata_label.setText(" | ".join(parts))

    def _edit_project_metadata(self) -> None:
        if not self._project_manager:
            return

        dialog = ProjectMetadataDialog(self._project_manager.metadata, self)
        if dialog.exec() != QDialog.Accepted:
            return

        updated = dialog.result_metadata()
        self._project_manager.update_metadata(metadata=updated)
        self._project_manager.save_project()
        self._update_metadata_label()

    def begin_initial_conversion(self) -> None:
        """Trigger an initial scan/conversion after project creation."""
        if self._feature_flags.auto_run_conversion_on_create:
            self._trigger_conversion(auto_run=True)

    def _refresh_file_tracker(self) -> None:
        if not self._project_manager:
            return
        try:
            self._workspace_metrics = self._project_manager.get_workspace_metrics(refresh=True)
        except Exception as exc:
            self._counts_label.setText("Scan failed")
            if getattr(self, "_missing_highlights_label", None):
                self._missing_highlights_label.setText("")
            if getattr(self, "_missing_bulk_label", None):
                self._missing_bulk_label.setText("")
            return

        metrics = self._workspace_metrics.dashboard

        converted_total = metrics.imported_total
        if converted_total:
            pdf_total = metrics.highlights_total + metrics.pending_highlights
            highlight_text = f"Highlights: {metrics.highlights_total} of {pdf_total}"
            if metrics.pending_highlights:
                highlight_text += f" (pending {metrics.pending_highlights})"
            bulk_text = f"Bulk analysis: {metrics.bulk_analysis_total} of {converted_total}"
            if metrics.pending_bulk_analysis:
                bulk_text += f" (pending {metrics.pending_bulk_analysis})"
            counts_text = (
                f"Converted: {converted_total} | "
                f"{highlight_text} | "
                f"{bulk_text}"
            )
        else:
            counts_text = "Converted: 0 | Highlights: 0 | Bulk analysis: 0"
        self._counts_label.setText(counts_text)

        bulk_missing = list(self._workspace_metrics.bulk_missing)
        highlights_missing = list(self._workspace_metrics.highlights_missing)

        if getattr(self, "_missing_highlights_label", None):
            self._missing_highlights_label.setText(
                "Highlights missing: " + (", ".join(highlights_missing) if highlights_missing else "None")
            )

        if getattr(self, "_missing_bulk_label", None):
            self._missing_bulk_label.setText(
                "Bulk analysis missing: " + (", ".join(bulk_missing) if bulk_missing else "None")
            )

        self._update_last_scan_label()

    # ------------------------------------------------------------------
    # Source tree helpers
    # ------------------------------------------------------------------
    def _trigger_conversion(self, auto_run: bool) -> None:
        if not self._project_manager:
            return
        if self._conversion_running:
            QMessageBox.information(
                self,
                "Conversion Running",
                "Document conversion is already in progress.",
            )
            return

        jobs, duplicates = self._collect_conversion_jobs()
        if duplicates:
            self._show_duplicate_notice(duplicates)
        if not jobs:
            if not auto_run and not duplicates:
                QMessageBox.information(self, "Conversion", "No new files detected.")
            return

        if not auto_run:
            reply = QMessageBox.question(
                self,
                "Convert Documents",
                f"Convert {len(jobs)} new document(s) to markdown now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply != QMessageBox.Yes:
                return

        self._start_conversion(jobs)

    def _handle_rescan_clicked(self) -> None:
        self._trigger_conversion(auto_run=False)

    def _select_source_root(self) -> None:
        if not self._project_manager or not self._project_manager.project_dir:
            QMessageBox.warning(self, "Project Required", "Create or open a project first.")
            return
        start_dir = str(self._resolve_source_root() or self._project_manager.project_dir)
        chosen = QFileDialog.getExistingDirectory(self, "Select Source Folder", start_dir)
        if not chosen:
            return
        chosen_path = Path(chosen)
        relative = self._to_project_relative(chosen_path)
        self._project_manager.update_source_state(
            root=relative,
            selected_folders=[],
            warnings=[],
        )
        self._populate_source_tree()
        self._update_source_root_label()
        self._update_last_scan_label()
        self._set_root_warning([])

    def _prompt_reselect_source_root(self) -> None:
        if not self._project_manager:
            return
        root_spec = self._project_manager.source_state.root
        if not root_spec:
            return
        response = QMessageBox.question(
            self,
            "Source Folder Missing",
            "The previously selected source folder cannot be found.\n"
            "Do you want to locate it now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if response == QMessageBox.Yes:
            self._missing_root_prompted = False
            self._select_source_root()

    def _update_source_root_label(self) -> None:
        if not self._project_manager:
            self._source_root_label.setText("Source root: not set")
            return
        root_path = self._resolve_source_root()
        if not root_path or not root_path.exists():
            self._source_root_label.setText("Source root: not set")
        else:
            self._source_root_label.setText(f"Source root: {root_path}")

    def _update_last_scan_label(self) -> None:
        if not self._project_manager:
            self._last_scan_label.setText("")
            return
        metrics = None
        if self._workspace_metrics:
            metrics = self._workspace_metrics.dashboard
        elif self._project_manager.dashboard_metrics:
            metrics = self._project_manager.dashboard_metrics
        last_scan = metrics.last_scan if metrics else None
        if not last_scan and self._project_manager.source_state.last_scan:
            try:
                last_scan = datetime.fromisoformat(self._project_manager.source_state.last_scan)
            except ValueError:
                last_scan = self._project_manager.source_state.last_scan

        if not last_scan:
            self._last_scan_label.setText("Last scan: never")
            return
        if isinstance(last_scan, datetime):
            display = last_scan.strftime("Last scan: %Y-%m-%d %H:%M")
        else:
            display = f"Last scan: {last_scan}"
        self._last_scan_label.setText(display)

    def _populate_source_tree(self) -> None:
        if not hasattr(self, "_source_tree"):
            return
        self._source_tree.clear()

        if not self._project_manager:
            self._source_tree.setDisabled(True)
            self._set_root_warning([])
            return

        root_path = self._resolve_source_root()
        if not root_path or not root_path.exists():
            self._source_tree.setDisabled(True)
            warning = [
                "Source folder missing. Update the project location to resume scanning."
                if self._project_manager and self._project_manager.source_state.root
                else "Select a source folder to begin tracking documents."
            ]
            self._set_root_warning(warning)
            if self._project_manager:
                self._project_manager.update_source_state(warnings=warning)
                if not self._missing_root_prompted:
                    self._missing_root_prompted = True
                    self._prompt_reselect_source_root()
            return

        self._source_tree.setDisabled(False)
        self._missing_root_prompted = False

        selected = sorted(self._project_manager.source_state.selected_folders or [])
        self._current_warnings = self._compute_root_warnings(root_path)
        self._set_root_warning(self._current_warnings)
        if self._project_manager:
            self._project_manager.update_source_state(warnings=self._current_warnings)

        root_label = root_path.name or root_path.as_posix()
        root_item = QTreeWidgetItem([root_label])
        root_item.setData(0, Qt.UserRole, root_path.as_posix())
        self._source_tree.addTopLevelItem(root_item)

        if not selected:
            placeholder = QTreeWidgetItem(["No folders were selected during project setup."])
            placeholder.setFlags(Qt.NoItemFlags)
            root_item.addChild(placeholder)
        else:
            processed_dirs: set[Path] = set()
            for relative in selected:
                directory = (root_path / relative).resolve()
                if not directory.exists():
                    continue
                container = self._ensure_tree_path(root_item, root_path, relative)
                if directory.is_dir() and directory not in processed_dirs:
                    self._populate_directory_contents(container, directory, processed_dirs)
        self._source_tree.expandItem(root_item)

        if self._feature_flags.summary_groups_enabled:
            self._populate_group_source_tree()

    def _ensure_tree_path(self, root_item: QTreeWidgetItem, root_path: Path, relative_path: str) -> QTreeWidgetItem:
        current_item = root_item
        cumulative = Path()
        for part in Path(relative_path).parts:
            cumulative = cumulative / part
            child = self._find_child(current_item, part)
            if child is None:
                child = QTreeWidgetItem([part])
                child.setData(0, Qt.UserRole, (root_path / cumulative).resolve().as_posix())
                current_item.addChild(child)
            current_item = child
        return current_item

    def _populate_directory_contents(
        self,
        parent_item: QTreeWidgetItem,
        directory: Path,
        processed: set[Path],
    ) -> None:
        directory = directory.resolve()
        if directory in processed:
            return
        processed.add(directory)

        try:
            entries = sorted(
                directory.iterdir(),
                key=lambda entry: (not entry.is_dir(), entry.name.lower()),
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.debug("Failed to enumerate %s: %s", directory, exc)
            return

        for entry in entries:
            child = self._find_child(parent_item, entry.name)
            if child is None:
                child = QTreeWidgetItem([entry.name])
                child.setData(0, Qt.UserRole, entry.resolve().as_posix())
                parent_item.addChild(child)
            if entry.is_dir():
                self._populate_directory_contents(child, entry, processed)

    def _iter_directories(self, root_path: Path) -> List[str]:
        results: List[str] = []
        for path in root_path.rglob("*"):
            if path.is_dir():
                try:
                    rel = path.relative_to(root_path).as_posix()
                except ValueError:
                    continue
                results.append(rel)
        return results

    def _populate_group_source_tree(self) -> None:
        if not self._feature_flags.summary_groups_enabled or self._group_source_tree is None:
            return
        self._group_source_tree.clear()

        if not self._project_manager:
            placeholder = QTreeWidgetItem(["Open a project to view folders."])
            placeholder.setFlags(Qt.NoItemFlags)
            self._group_source_tree.addTopLevelItem(placeholder)
            return

        root_path = self._resolve_source_root()
        if not root_path or not root_path.exists():
            placeholder = QTreeWidgetItem(["Source folder not set."])
            placeholder.setFlags(Qt.NoItemFlags)
            self._group_source_tree.addTopLevelItem(placeholder)
            return

        directories = sorted(self._iter_directories(root_path))
        if not directories:
            placeholder = QTreeWidgetItem(["No subfolders available."])
            placeholder.setFlags(Qt.NoItemFlags)
            self._group_source_tree.addTopLevelItem(placeholder)
            return

        self._group_source_tree.setUpdatesEnabled(False)
        for relative_path in directories:
            parts = relative_path.split("/")
            parent = self._group_source_tree.invisibleRootItem()
            path_so_far: List[str] = []
            for part in parts:
                path_so_far.append(part)
                rel_key = "/".join(path_so_far)
                child = self._find_child(parent, part)
                if child is None:
                    child = QTreeWidgetItem([part])
                    parent.addChild(child)
                parent = child
        self._group_source_tree.expandAll()
        self._group_source_tree.setUpdatesEnabled(True)

    def _find_child(self, parent: QTreeWidgetItem, name: str) -> Optional[QTreeWidgetItem]:
        for index in range(parent.childCount()):
            child = parent.child(index)
            if child.text(0) == name:
                return child
        return None

    def _collect_selected_folders(self) -> List[str]:
        selected: List[str] = []
        root = self._source_tree.invisibleRootItem()
        stack = [root]
        while stack:
            current = stack.pop()
            for index in range(current.childCount()):
                child = current.child(index)
                stack.append(child)
                if child.checkState(0) == Qt.Checked:
                    rel = child.data(0, Qt.UserRole)
                    if rel:
                        selected.append(str(rel))
        selected.sort()
        return selected

    def _collect_conversion_jobs(self) -> Tuple[List[ConversionJob], Sequence[DuplicateSource]]:
        if not self._project_manager:
            return [], []
        plan = build_conversion_jobs(self._project_manager)
        jobs = [job for job in plan.jobs if job.source_path not in self._inflight_sources]
        return jobs, plan.duplicates

    def _set_root_warning(self, warnings: List[str]) -> None:
        if warnings:
            self._root_warning_label.setText("\n".join(warnings))
            self._root_warning_label.show()
        else:
            self._root_warning_label.clear()
            self._root_warning_label.hide()

    def _show_duplicate_notice(self, duplicates: Sequence[DuplicateSource]) -> None:
        if not duplicates:
            return

        preview_limit = 10
        listed = list(duplicates[:preview_limit])
        lines = [
            f"- {duplicate.duplicate_relative} matches {duplicate.primary_relative}"
            for duplicate in listed
        ]
        remaining = len(duplicates) - len(listed)
        if remaining > 0:
            lines.append(f"…and {remaining} more duplicate files.")

        message = (
            "Duplicate files detected. Matching documents will be skipped to avoid converting"
            " the same content twice.\n\n"
            + "\n".join(lines)
        )
        QMessageBox.warning(self, "Duplicate Files Skipped", message)

    def _compute_root_warnings(self, root_path: Path) -> List[str]:
        warnings: List[str] = []
        has_root_files = any(child.is_file() for child in root_path.iterdir())
        if has_root_files:
            warnings.append(
                "Files in the source root will be skipped. Move them into subfolders so they can be processed."
            )
        selected = self._project_manager.source_state.selected_folders if self._project_manager else []
        if not selected:
            warnings.append("Select at least one folder to include in scanning.")
        return warnings

    def _resolve_source_root(self) -> Optional[Path]:
        if not self._project_manager or not self._project_manager.project_dir:
            return None
        root_spec = (self._project_manager.source_state.root or "").strip()
        if not root_spec:
            return None
        root_path = Path(root_spec)
        if not root_path.is_absolute():
            root_path = (self._project_manager.project_dir / root_path).resolve()
        return root_path

    def _to_project_relative(self, path: Path) -> str:
        if not self._project_manager or not self._project_manager.project_dir:
            return path.as_posix()
        project_dir = Path(self._project_manager.project_dir).resolve()
        try:
            rel = path.resolve().relative_to(project_dir)
            return rel.as_posix()
        except ValueError:
            rel_str = os.path.relpath(path.resolve(), project_dir)
            return Path(rel_str).as_posix()

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------
    def _start_conversion(self, jobs: List[ConversionJob]) -> None:
        if not self._project_manager or not jobs:
            return

        self._conversion_running = True
        self._conversion_total = len(jobs)
        self._conversion_errors: List[str] = []
        self._rescan_button.setEnabled(False)
        self._counts_label.setText(f"Converting documents (0/{self._conversion_total})…")
        if self._extract_highlights_button:
            self._extract_highlights_button.setEnabled(False)

        self._inflight_sources.update(job.source_path for job in jobs)

        helper = self._project_manager.conversion_settings.helper
        options = dict(self._project_manager.conversion_settings.options or {})
        worker = ConversionWorker(jobs, helper=helper, options=options)
        worker.progress.connect(self._on_conversion_progress)
        worker.file_failed.connect(self._on_conversion_failed)
        worker.finished.connect(
            lambda success, failed, w=worker, js=jobs: self._on_conversion_finished(
                w, js, success, failed
            )
        )

       
        self._workers.start(self._conversion_key(), worker)

    def _on_conversion_progress(self, processed: int, total: int, relative_path: str) -> None:
        self._counts_label.setText(f"Converting documents ({processed}/{total})… {relative_path}")

    def _on_conversion_failed(self, source_path: str, error: str) -> None:
        message = f"{Path(source_path).name}: {error}"
        self._conversion_errors.append(message)

    def _on_conversion_finished(
        self,
        worker: ConversionWorker,
        jobs: Sequence[ConversionJob],
        successes: int,
        failures: int,
    ) -> None:
        stored = self._workers.pop(self._conversion_key())
        # Always attempt to delete the actual worker and any stored reference safely
        if worker and isValid(worker):
            worker.deleteLater()
        if stored and stored is not worker and isValid(stored):
            stored.deleteLater()
        for job in jobs:
            self._inflight_sources.discard(job.source_path)

        timestamp = datetime.utcnow().isoformat()
        self._project_manager.update_source_state(last_scan=timestamp, warnings=self._current_warnings)
        self._update_last_scan_label()

        self._conversion_running = False
        self._rescan_button.setEnabled(True)
        self._update_highlight_button_state()
        self._refresh_file_tracker()
        self._refresh_highlights_tab()
        if failures:
            error_text = "\n".join(self._conversion_errors) or "Unknown errors"
            QMessageBox.warning(
                self,
                "Conversion Issues",
                "Some documents failed to convert:\n\n" + error_text,
            )

    # ------------------------------------------------------------------
    # Highlight extraction helpers
    # ------------------------------------------------------------------
    def _open_highlights_folder(self) -> None:
        if not self._project_manager or not self._project_manager.project_dir:
            return
        folder = self._project_manager.project_dir / "highlights"
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _open_highlight_item(self, item: QTreeWidgetItem, column: int) -> None:  # noqa: ARG002
        path = item.data(0, Qt.UserRole)
        if not path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _populate_highlight_tree(self) -> None:
        if not self._highlight_tree:
            return
        tree = self._highlight_tree
        tree.clear()
        if not self._project_manager or not self._project_manager.project_dir:
            return

        project_dir = self._project_manager.project_dir
        documents_root = project_dir / "highlights" / "documents"
        colors_root = project_dir / "highlights" / "colors"

        documents_item = QTreeWidgetItem(["Documents", ""])
        documents_item.setExpanded(True)
        if documents_root.exists():
            for path in sorted(documents_root.rglob("*.highlights.md")):
                relative = path.relative_to(documents_root).as_posix()
                child = QTreeWidgetItem(["Document", relative])
                child.setData(0, Qt.UserRole, str(path))
                documents_item.addChild(child)
        tree.addTopLevelItem(documents_item)

        colors_item = QTreeWidgetItem(["Colors", ""])
        colors_item.setExpanded(True)
        if colors_root.exists():
            for path in sorted(colors_root.glob("*.md")):
                relative = path.relative_to(colors_root).as_posix()
                child = QTreeWidgetItem(["Color", relative])
                child.setData(0, Qt.UserRole, str(path))
                colors_item.addChild(child)
        tree.addTopLevelItem(colors_item)
        tree.resizeColumnToContents(0)

    def _refresh_highlights_tab(self) -> None:
        if not self._highlights_tab:
            return

        if not self._project_manager:
            if self._highlight_counts_label:
                self._highlight_counts_label.setText("Highlights extracted: 0 | Pending: 0")
            if self._highlight_last_run_label:
                self._highlight_last_run_label.setText("Last run: —")
            if self._highlight_status_label and not self._highlight_running:
                self._highlight_status_label.setText("Highlights have not been extracted yet.")
            if self._open_highlights_button:
                self._open_highlights_button.setEnabled(False)
            if self._highlight_tree:
                self._highlight_tree.clear()
            return

        if self._open_highlights_button:
            self._open_highlights_button.setEnabled(True)

        metrics = None
        try:
            if self._workspace_metrics is None:
                self._workspace_metrics = self._project_manager.get_workspace_metrics()
            metrics = self._workspace_metrics.dashboard if self._workspace_metrics else None
        except Exception:
            metrics = None

        if metrics and self._highlight_counts_label:
            pdf_total = metrics.highlights_total + metrics.pending_highlights
            message = f"Highlights extracted: {metrics.highlights_total} of {pdf_total}"
            if metrics.pending_highlights:
                message += f" (pending {metrics.pending_highlights})"
        else:
            message = "Highlights extracted: 0"
        if self._highlight_counts_label:
            self._highlight_counts_label.setText(message)

        state = self._project_manager.highlight_state
        last_run_text = "Last run: —"
        if state.last_run_at:
            try:
                parsed = datetime.fromisoformat(state.last_run_at)
                last_run_text = "Last run: " + parsed.astimezone().strftime("%Y-%m-%d %H:%M")
            except ValueError:
                last_run_text = f"Last run: {state.last_run_at}"
        if self._highlight_last_run_label:
            self._highlight_last_run_label.setText(last_run_text)

        if self._highlight_status_label and not self._highlight_running:
            if state.last_run_at:
                details = (
                    f"Last run captured {state.total_highlights} highlight(s) across "
                    f"{state.documents_with_highlights} document(s). Color files: {state.color_files}."
                )
                self._highlight_status_label.setText(details)
            else:
                self._highlight_status_label.setText("Highlights have not been extracted yet.")

        self._populate_highlight_tree()

    def _update_highlight_button_state(self) -> None:
        if not self._extract_highlights_button:
            return
        if not self._project_manager or self._highlight_running or self._conversion_running:
            self._extract_highlights_button.setEnabled(False)
            return
        try:
            jobs_available = bool(self._project_manager.build_highlight_jobs())
        except Exception:
            jobs_available = False
        self._extract_highlights_button.setEnabled(jobs_available)

    def _highlight_key(self) -> str:
        return "highlights:run"

    def _trigger_highlight_extraction(self) -> None:
        if not self._project_manager:
            return
        if self._highlight_running:
            QMessageBox.information(
                self,
                "Highlights",
                "Highlight extraction is already in progress.",
            )
            return

        jobs = self._project_manager.build_highlight_jobs()
        if not jobs:
            QMessageBox.information(
                self,
                "Highlights",
                "No converted PDFs are ready for highlight extraction.",
            )
            return

        self._start_highlight_worker(jobs)

    def _start_highlight_worker(self, jobs) -> None:
        self._highlight_running = True
        self._highlight_total = len(jobs)
        self._highlight_errors = []
        self._counts_label.setText(f"Extracting highlights (0/{self._highlight_total})…")
        if self._extract_highlights_button:
            self._extract_highlights_button.setEnabled(False)
        if self._highlight_status_label:
            self._highlight_status_label.setText(
                f"Extracting highlights (0/{self._highlight_total})…"
            )
        self._update_highlight_button_state()
        worker = HighlightWorker(jobs)
        worker.progress.connect(self._on_highlight_progress)
        worker.file_failed.connect(self._on_highlight_failed)
        worker.finished.connect(
            lambda success, failed, w=worker: self._on_highlight_finished(w, success, failed)
        )
        self._workers.start(self._highlight_key(), worker)

    def _on_highlight_progress(self, processed: int, total: int, relative_path: str) -> None:
        self._counts_label.setText(
            f"Extracting highlights ({processed}/{total})… {relative_path}"
        )
        if self._highlight_status_label:
            self._highlight_status_label.setText(
                f"Extracting highlights ({processed}/{total})… {relative_path}"
            )

    def _on_highlight_failed(self, source_path: str, error: str) -> None:
        self._highlight_errors.append(f"{Path(source_path).name}: {error}")

    def _on_highlight_finished(self, worker: HighlightWorker, successes: int, failures: int) -> None:
        stored = self._workers.pop(self._highlight_key())
        # Always attempt to delete the actual worker and any stored reference safely
        if worker and isValid(worker):
            worker.deleteLater()
        if stored and stored is not worker and isValid(stored):
            stored.deleteLater()

        self._highlight_running = False
        self._update_highlight_button_state()

        summary = worker.summary
        if summary and self._project_manager:
            self._project_manager.record_highlight_run(
                generated_at=summary.generated_at,
                documents_processed=summary.documents_processed,
                documents_with_highlights=summary.documents_with_highlights,
                total_highlights=summary.total_highlights,
                color_files_written=summary.color_files_written,
            )

        self._refresh_file_tracker()
        self._refresh_highlights_tab()

        if failures:
            message = "\n".join(self._highlight_errors) or "Unknown errors"
            QMessageBox.warning(
                self,
                "Highlight Extraction Issues",
                "Some highlights could not be extracted:\n\n" + message,
            )
        elif summary is None and self._highlight_status_label:
            self._highlight_status_label.setText("Highlight extraction finished.")

    # ------------------------------------------------------------------
    # Report generation helpers
    # ------------------------------------------------------------------
    def _build_report_model_combo(self) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(False)
        combo.addItem("Custom…", ("custom", ""))
        combo.addItem(
            "Anthropic Claude (claude-sonnet-4-5-20250929)",
            ("anthropic", "claude-sonnet-4-5-20250929"),
        )
        combo.addItem(
            "Anthropic Claude (claude-opus-4-1-20250805)",
            ("anthropic", "claude-opus-4-1-20250805"),
        )
        return combo

    def _on_report_model_changed(self) -> None:
        data = self._report_model_combo.currentData() if self._report_model_combo else None
        is_custom = bool(data) and data[0] == "custom"
        for widget in (
            self._report_custom_model_label,
            self._report_custom_model_edit,
            self._report_custom_context_label,
            self._report_custom_context_spin,
        ):
            if widget:
                widget.setVisible(is_custom)
        self._update_report_controls()

    def _browse_report_template(self) -> None:
        initial = None
        try:
            initial = get_template_custom_dir()
        except Exception:
            if self._project_manager and self._project_manager.project_dir:
                initial = self._project_manager.project_dir
            else:
                initial = Path.home()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Template",
            str(initial),
            "Markdown/Text Files (*.md *.txt);;All Files (*)",
        )
        if file_path and self._report_template_edit:
            self._report_template_edit.setText(file_path)
        self._update_report_controls()

    def _browse_refinement_prompt(self) -> None:
        initial = None
        try:
            initial = get_custom_dir()
        except Exception:
            initial = Path.home()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Refinement Prompt",
            str(initial),
            "Markdown/Text Files (*.md *.txt);;All Files (*)",
        )
        if file_path and self._report_refinement_prompt_edit:
            self._report_refinement_prompt_edit.setText(file_path)
        self._update_report_controls()

    def _browse_generation_system_prompt(self) -> None:
        initial = None
        try:
            initial = get_custom_dir()
        except Exception:
            initial = Path.home()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Generation System Prompt",
            str(initial),
            "Markdown/Text Files (*.md *.txt);;All Files (*)",
        )
        if file_path and self._report_generation_system_prompt_edit:
            self._report_generation_system_prompt_edit.setText(file_path)
        self._update_report_controls()

    def _browse_generation_user_prompt(self) -> None:
        initial = None
        try:
            initial = get_custom_dir()
        except Exception:
            initial = Path.home()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Generation User Prompt",
            str(initial),
            "Markdown/Text Files (*.md *.txt);;All Files (*)",
        )
        if file_path and self._report_generation_user_prompt_edit:
            self._report_generation_user_prompt_edit.setText(file_path)
        self._update_report_controls()

    def _browse_refinement_system_prompt(self) -> None:
        initial = None
        try:
            initial = get_custom_dir()
        except Exception:
            initial = Path.home()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Refinement System Prompt",
            str(initial),
            "Markdown/Text Files (*.md *.txt);;All Files (*)",
        )
        if file_path and self._report_refinement_system_prompt_edit:
            self._report_refinement_system_prompt_edit.setText(file_path)
        self._update_report_controls()

    def _default_refinement_user_prompt_path(self) -> str:
        try:
            bundled_path = get_bundled_dir() / "refinement_prompt.md"
            if bundled_path.exists():
                return str(bundled_path)
        except Exception:
            LOGGER.debug("Unable to resolve bundled refinement prompt path", exc_info=True)
        repo_dir = get_repo_prompts_dir()
        repo_path = repo_dir / "refinement_prompt.md"
        if repo_path.exists():
            return str(repo_path)
        return ""

    def _default_generation_user_prompt_path(self) -> str:
        try:
            bundled_path = get_bundled_dir() / "report_generation_user_prompt.md"
            if bundled_path.exists():
                return str(bundled_path)
        except Exception:
            LOGGER.debug(
                "Unable to resolve bundled generation user prompt path",
                exc_info=True,
            )
        repo_dir = get_repo_prompts_dir()
        repo_path = repo_dir / "report_generation_user_prompt.md"
        if repo_path.exists():
            return str(repo_path)
        return ""

    def _default_generation_system_prompt_path(self) -> str:
        try:
            bundled_path = get_bundled_dir() / "report_generation_system_prompt.md"
            if bundled_path.exists():
                return str(bundled_path)
        except Exception:
            LOGGER.debug(
                "Unable to resolve bundled generation system prompt path",
                exc_info=True,
            )
        repo_dir = get_repo_prompts_dir()
        repo_path = repo_dir / "report_generation_system_prompt.md"
        if repo_path.exists():
            return str(repo_path)
        return ""

    def _default_refinement_system_prompt_path(self) -> str:
        try:
            bundled_path = get_bundled_dir() / "report_refinement_system_prompt.md"
            if bundled_path.exists():
                return str(bundled_path)
        except Exception:
            LOGGER.debug(
                "Unable to resolve bundled refinement system prompt path",
                exc_info=True,
            )
        repo_dir = get_repo_prompts_dir()
        repo_path = repo_dir / "report_refinement_system_prompt.md"
        if repo_path.exists():
            return str(repo_path)
        return ""

    def _format_prompt_preview(self, template: str, context: dict[str, str]) -> str:
        class _SafeDict(dict):
            def __missing__(self, key: str) -> str:  # noqa: D401 - inline default placeholder
                return "{" + key + "}"

        safe_context = _SafeDict({k: (v or "") for k, v in context.items()})
        return template.format_map(safe_context)

    def _build_additional_documents_text(self, project_dir: Path) -> str:
        lines: List[str] = []
        for key in sorted(self._report_selected_inputs):
            if ":" not in key:
                continue
            category, relative = key.split(":", 1)
            absolute = (project_dir / relative).resolve()
            if not absolute.exists() or not absolute.is_file():
                continue
            try:
                content = absolute.read_text(encoding="utf-8").strip()
            except Exception:
                continue
            lines.append(f"<!--- report-input: {category} | {relative} --->")
            lines.append(f"# {category_display_name(category)}: {relative}")
            if content:
                lines.append(content)
            lines.append("")
        if not lines:
            return ""
        return "\n".join(lines).strip()

    def _preview_generation_prompt(self) -> None:
        if not self._project_manager or not self._project_manager.project_dir:
            QMessageBox.warning(self, "Prompt Preview", "Open a project to preview prompts.")
            return
        if not self._report_template_edit:
            return
        template_path_str = self._report_template_edit.text().strip()
        if not template_path_str:
            QMessageBox.warning(self, "Prompt Preview", "Select a template first.")
            return
        template_path = Path(template_path_str).expanduser()
        if not template_path.exists():
            QMessageBox.warning(self, "Prompt Preview", f"Template not found:\n{template_path}")
            return

        if not self._report_generation_user_prompt_edit:
            return
        gen_prompt_path_str = self._report_generation_user_prompt_edit.text().strip()
        if not gen_prompt_path_str:
            QMessageBox.warning(self, "Prompt Preview", "Select a generation user prompt first.")
            return
        gen_prompt_path = Path(gen_prompt_path_str).expanduser()
        if not gen_prompt_path.exists():
            QMessageBox.warning(self, "Prompt Preview", f"Generation user prompt not found:\n{gen_prompt_path}")
            return
        try:
            generation_user_prompt = read_generation_prompt(gen_prompt_path)
            validate_generation_prompt(generation_user_prompt)
        except ValueError as exc:
            QMessageBox.warning(self, "Prompt Preview", str(exc))
            return
        except Exception:
            QMessageBox.warning(self, "Prompt Preview", "Unable to read generation user prompt.")
            return

        try:
            sections = load_template_sections(template_path)
        except Exception:
            QMessageBox.warning(self, "Prompt Preview", "Unable to parse template sections.")
            return
        if not sections:
            QMessageBox.warning(self, "Prompt Preview", "Template does not contain any sections.")
            return
        section = sections[0]
        template_section = section.body.strip() or section.title or "Template section"

        project_dir = Path(self._project_manager.project_dir)
        additional_documents = self._build_additional_documents_text(project_dir)

        transcript_text = ""
        if self._report_transcript_edit and self._report_transcript_edit.text().strip():
            transcript_path = Path(self._report_transcript_edit.text().strip()).expanduser()
            if transcript_path.exists():
                try:
                    transcript_text = transcript_path.read_text(encoding="utf-8")
                except Exception:
                    transcript_text = ""

        system_prompt_text = ""
        if self._report_generation_system_prompt_edit and self._report_generation_system_prompt_edit.text().strip():
            system_path = Path(self._report_generation_system_prompt_edit.text().strip()).expanduser()
            if system_path.exists():
                try:
                    system_prompt_text = system_path.read_text(encoding="utf-8")
                except Exception:
                    system_prompt_text = ""
        if not system_prompt_text:
            system_prompt_text = "(Generation system prompt is empty.)"

        user_prompt_text = self._format_prompt_preview(
            generation_user_prompt,
            {
                "template_section": template_section,
                "transcript": transcript_text,
                "additional_documents": additional_documents,
            },
        )

        dialog = PromptPreviewDialog(self)
        dialog.set_prompts(system_prompt_text, user_prompt_text)
        dialog.exec()

    def _preview_refinement_prompt(self) -> None:
        if not self._project_manager or not self._project_manager.project_dir:
            QMessageBox.warning(self, "Prompt Preview", "Open a project to preview prompts.")
            return
        if not self._report_template_edit:
            return
        template_path_str = self._report_template_edit.text().strip()
        if not template_path_str:
            QMessageBox.warning(self, "Prompt Preview", "Select a template first.")
            return
        template_path = Path(template_path_str).expanduser()
        template_text = ""
        try:
            template_text = template_path.read_text(encoding="utf-8")
        except Exception:
            QMessageBox.warning(self, "Prompt Preview", "Unable to read template file.")
            return

        if not self._report_refinement_prompt_edit:
            return
        refinement_path_str = self._report_refinement_prompt_edit.text().strip()
        if not refinement_path_str:
            QMessageBox.warning(self, "Prompt Preview", "Select a refinement user prompt first.")
            return
        refinement_path = Path(refinement_path_str).expanduser()
        if not refinement_path.exists():
            QMessageBox.warning(self, "Prompt Preview", f"Refinement user prompt not found:\n{refinement_path}")
            return
        try:
            refinement_user_prompt = read_refinement_prompt(refinement_path)
            validate_refinement_prompt(refinement_user_prompt)
        except ValueError as exc:
            QMessageBox.warning(self, "Prompt Preview", str(exc))
            return
        except Exception:
            QMessageBox.warning(self, "Prompt Preview", "Unable to read refinement user prompt.")
            return

        generation_preview_section = ""
        try:
            sections = load_template_sections(template_path)
            if sections:
                generation_preview_section = sections[0].body.strip()
        except Exception:
            generation_preview_section = ""
        draft_preview = generation_preview_section or "Draft content preview"

        transcript_text = ""
        if self._report_transcript_edit and self._report_transcript_edit.text().strip():
            transcript_path = Path(self._report_transcript_edit.text().strip()).expanduser()
            if transcript_path.exists():
                try:
                    transcript_text = transcript_path.read_text(encoding="utf-8")
                except Exception:
                    transcript_text = ""

        system_prompt_text = ""
        if self._report_refinement_system_prompt_edit and self._report_refinement_system_prompt_edit.text().strip():
            system_path = Path(self._report_refinement_system_prompt_edit.text().strip()).expanduser()
            if system_path.exists():
                try:
                    system_prompt_text = system_path.read_text(encoding="utf-8")
                except Exception:
                    system_prompt_text = ""
        if not system_prompt_text:
            system_prompt_text = "(Refinement system prompt is empty.)"

        user_prompt_text = self._format_prompt_preview(
            refinement_user_prompt,
            {
                "draft_report": draft_preview,
                "template": template_text,
                "transcript": transcript_text,
            },
        )

        dialog = PromptPreviewDialog(self)
        dialog.set_prompts(system_prompt_text, user_prompt_text)
        dialog.exec()
    def _browse_report_transcript(self) -> None:
        initial = None
        if self._project_manager and self._project_manager.project_dir:
            initial = self._project_manager.project_dir
        else:
            initial = Path.home()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Transcript",
            str(initial),
            "Markdown/Text Files (*.md *.txt);;All Files (*)",
        )
        if file_path and self._report_transcript_edit:
            self._report_transcript_edit.setText(file_path)
        self._update_report_controls()

    def _collect_report_inputs(self) -> List[ReportInputDescriptor]:
        descriptors: List[ReportInputDescriptor] = []
        if not self._project_manager or not self._project_manager.project_dir:
            return descriptors

        project_dir = Path(self._project_manager.project_dir)

        def add_descriptor(category: str, absolute: Path, label: str) -> None:
            descriptors.append(
                ReportInputDescriptor(
                    category=category,
                    relative_path=absolute.relative_to(project_dir).as_posix(),
                    label=label,
                )
            )

        converted_root = project_dir / "converted_documents"
        if converted_root.exists():
            for path in sorted(converted_root.rglob("*")):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in {".md", ".txt"}:
                    continue
                add_descriptor(
                    REPORT_CATEGORY_CONVERTED,
                    path,
                    path.relative_to(converted_root).as_posix(),
                )

        bulk_root = project_dir / "bulk_analysis"
        if bulk_root.exists():
            for slug_dir in sorted(bulk_root.iterdir()):
                if not slug_dir.is_dir():
                    continue
                slug = slug_dir.name
                for path, rel in sorted(iter_map_outputs(project_dir, slug), key=lambda item: item[1]):
                    add_descriptor(
                        REPORT_CATEGORY_BULK_MAP,
                        path,
                        f"{slug}/{rel}",
                    )
                reduce_dir = slug_dir / "reduce"
                if reduce_dir.exists():
                    for path in sorted(reduce_dir.rglob("*.md")):
                        add_descriptor(
                            REPORT_CATEGORY_BULK_COMBINED,
                            path,
                            f"{slug_dir.name}/reduce/{path.relative_to(reduce_dir).as_posix()}",
                        )

        highlight_docs = project_dir / "highlights" / "documents"
        if highlight_docs.exists():
            for path in sorted(highlight_docs.rglob("*.md")):
                add_descriptor(
                    REPORT_CATEGORY_HIGHLIGHT_DOCUMENT,
                    path,
                    path.relative_to(highlight_docs).as_posix(),
                )

        highlight_colors = project_dir / "highlights" / "colors"
        if highlight_colors.exists():
            for path in sorted(highlight_colors.glob("*.md")):
                add_descriptor(
                    REPORT_CATEGORY_HIGHLIGHT_COLOR,
                    path,
                    path.relative_to(highlight_colors).as_posix(),
                )

        return descriptors

    def _populate_report_inputs_tree(self, descriptors: List[ReportInputDescriptor]) -> None:
        if not self._report_inputs_tree:
            return
        tree = self._report_inputs_tree
        tree.blockSignals(True)
        tree.clear()

        by_category: Dict[str, List[ReportInputDescriptor]] = {}
        for descriptor in descriptors:
            by_category.setdefault(descriptor.category, []).append(descriptor)

        for category, label in (
            (REPORT_CATEGORY_CONVERTED, category_display_name(REPORT_CATEGORY_CONVERTED)),
            (REPORT_CATEGORY_BULK_MAP, category_display_name(REPORT_CATEGORY_BULK_MAP)),
            (REPORT_CATEGORY_BULK_COMBINED, category_display_name(REPORT_CATEGORY_BULK_COMBINED)),
            (REPORT_CATEGORY_HIGHLIGHT_DOCUMENT, category_display_name(REPORT_CATEGORY_HIGHLIGHT_DOCUMENT)),
            (REPORT_CATEGORY_HIGHLIGHT_COLOR, category_display_name(REPORT_CATEGORY_HIGHLIGHT_COLOR)),
        ):
            entries = by_category.get(category)
            if not entries:
                continue
            parent = QTreeWidgetItem([label, ""])
            parent.setFlags(parent.flags() | _ITEM_IS_USER_CHECKABLE | _ITEM_IS_TRISTATE)
            parent.setCheckState(0, Qt.Unchecked)
            tree.addTopLevelItem(parent)

            for descriptor in entries:
                child = QTreeWidgetItem([descriptor.label, descriptor.relative_path])
                child.setFlags(child.flags() | _ITEM_IS_USER_CHECKABLE)
                key = descriptor.key()
                child.setData(0, Qt.UserRole, key)
                state = Qt.Checked if key in self._report_selected_inputs else Qt.Unchecked
                child.setCheckState(0, state)
                parent.addChild(child)

        tree.expandAll()
        tree.blockSignals(False)
        self._update_report_controls()

    def _on_report_input_changed(self, item: QTreeWidgetItem, column: int) -> None:  # noqa: ARG002
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        key = str(data)
        if item.checkState(0) == Qt.Checked:
            self._report_selected_inputs.add(key)
        else:
            self._report_selected_inputs.discard(key)
        self._update_report_controls()

    def _update_report_controls(self) -> None:
        if not self._report_generate_button:
            return
        if not self._project_manager:
            self._report_generate_button.setEnabled(False)
            return
        has_inputs = bool(self._report_selected_inputs)
        transcript_ok = bool(self._report_transcript_edit and self._report_transcript_edit.text().strip())
        template_text = self._report_template_edit.text().strip() if self._report_template_edit else ""
        template_ok = bool(template_text and Path(template_text).expanduser().is_file())
        refinement_text = (
            self._report_refinement_prompt_edit.text().strip()
            if self._report_refinement_prompt_edit
            else ""
        )
        refinement_ok = bool(refinement_text and Path(refinement_text).expanduser().is_file())
        generation_user_text = (
            self._report_generation_user_prompt_edit.text().strip()
            if self._report_generation_user_prompt_edit
            else ""
        )
        generation_user_ok = bool(
            generation_user_text and Path(generation_user_text).expanduser().is_file()
        )
        generation_system_text = (
            self._report_generation_system_prompt_edit.text().strip()
            if self._report_generation_system_prompt_edit
            else ""
        )
        generation_system_ok = bool(
            generation_system_text and Path(generation_system_text).expanduser().is_file()
        )
        refinement_system_text = (
            self._report_refinement_system_prompt_edit.text().strip()
            if self._report_refinement_system_prompt_edit
            else ""
        )
        refinement_system_ok = bool(
            refinement_system_text and Path(refinement_system_text).expanduser().is_file()
        )
        model_ok = True
        if self._report_model_combo:
            data = self._report_model_combo.currentData()
            if data and data[0] == "custom":
                model_ok = bool(self._report_custom_model_edit and self._report_custom_model_edit.text().strip())
        enabled = (
            (has_inputs or transcript_ok)
            and model_ok
            and template_ok
            and refinement_ok
            and generation_user_ok
            and generation_system_ok
            and refinement_system_ok
            and not self._report_running
        )
        self._report_generate_button.setEnabled(enabled)

    def _refresh_reports_tab(self) -> None:
        if not self._reports_tab:
            return
        if not self._project_manager or not self._project_manager.project_dir:
            self._report_selected_inputs.clear()
            if self._report_inputs_tree:
                self._report_inputs_tree.clear()
            if self._report_history_list:
                self._report_history_list.clear()
            self._update_report_controls()
            self._update_report_history_buttons()
            return

        descriptors = self._collect_report_inputs()
        self._populate_report_inputs_tree(descriptors)
        self._refresh_report_history()
        self._update_report_controls()

    def _start_report_job(self) -> None:
        if self._report_running:
            QMessageBox.information(self, "Report Generator", "A report generation run is already in progress.")
            return
        if not self._project_manager or not self._project_manager.project_dir:
            QMessageBox.warning(self, "Report Generator", "No project is currently loaded.")
            return

        model_data = self._report_model_combo.currentData() if self._report_model_combo else None
        provider_id = "anthropic"
        model_id = "claude-sonnet-4-5-20250929"
        custom_model = None
        if model_data:
            if model_data[0] == "custom":
                custom_model = self._report_custom_model_edit.text().strip() if self._report_custom_model_edit else ""
                if not custom_model:
                    QMessageBox.warning(self, "Report Generator", "Enter a model id for the custom option.")
                    return
            else:
                provider_id, model_id = model_data

        context_window = None
        if self._report_custom_context_spin and custom_model:
            context_window = int(self._report_custom_context_spin.value())
        elif self._report_custom_context_spin and not custom_model:
            context_window = None

        template_path: Path | None = None
        if self._report_template_edit:
            text = self._report_template_edit.text().strip()
            if text:
                template_path = Path(text).expanduser()
        if not template_path:
            QMessageBox.warning(
                self,
                "Report Generator",
                "Select a report template before generating a report.",
            )
            return
        if not template_path.is_file():
            QMessageBox.warning(
                self,
                "Report Generator",
                f"The selected template does not exist:\n{template_path}",
            )
            return

        generation_user_prompt_path: Path | None = None
        if self._report_generation_user_prompt_edit:
            text = self._report_generation_user_prompt_edit.text().strip()
            if text:
                generation_user_prompt_path = Path(text).expanduser()
        if not generation_user_prompt_path:
            QMessageBox.warning(
                self,
                "Report Generator",
                "Select a generation user prompt before generating a report.",
            )
            return
        if not generation_user_prompt_path.is_file():
            QMessageBox.warning(
                self,
                "Report Generator",
                f"The selected generation user prompt does not exist:\n{generation_user_prompt_path}",
            )
            return
        try:
            generation_user_content = read_generation_prompt(generation_user_prompt_path)
            validate_generation_prompt(generation_user_content)
        except ValueError as exc:
            QMessageBox.warning(self, "Report Generator", str(exc))
            return
        except Exception:
            QMessageBox.warning(
                self,
                "Report Generator",
                "Unable to read the generation user prompt.",
            )
            return

        generation_system_prompt_path: Path | None = None
        if self._report_generation_system_prompt_edit:
            text = self._report_generation_system_prompt_edit.text().strip()
            if text:
                generation_system_prompt_path = Path(text).expanduser()
        if not generation_system_prompt_path:
            QMessageBox.warning(
                self,
                "Report Generator",
                "Select a generation system prompt before generating a report.",
            )
            return
        if not generation_system_prompt_path.is_file():
            QMessageBox.warning(
                self,
                "Report Generator",
                f"The selected generation system prompt does not exist:\n{generation_system_prompt_path}",
            )
            return

        refinement_user_prompt_path: Path | None = None
        if self._report_refinement_prompt_edit:
            text = self._report_refinement_prompt_edit.text().strip()
            if text:
                refinement_user_prompt_path = Path(text).expanduser()
        if not refinement_user_prompt_path:
            QMessageBox.warning(
                self,
                "Report Generator",
                "Select a refinement user prompt before generating a report.",
            )
            return
        if not refinement_user_prompt_path.is_file():
            QMessageBox.warning(
                self,
                "Report Generator",
                f"The selected refinement user prompt does not exist:\n{refinement_user_prompt_path}",
            )
            return
        try:
            refinement_user_content = read_refinement_prompt(refinement_user_prompt_path)
            validate_refinement_prompt(refinement_user_content)
        except ValueError as exc:
            QMessageBox.warning(self, "Report Generator", str(exc))
            return
        except Exception:
            QMessageBox.warning(
                self,
                "Report Generator",
                "Unable to read the refinement user prompt.",
            )
            return

        refinement_system_prompt_path: Path | None = None
        if self._report_refinement_system_prompt_edit:
            text = self._report_refinement_system_prompt_edit.text().strip()
            if text:
                refinement_system_prompt_path = Path(text).expanduser()
        if not refinement_system_prompt_path:
            QMessageBox.warning(
                self,
                "Report Generator",
                "Select a refinement system prompt before generating a report.",
            )
            return
        if not refinement_system_prompt_path.is_file():
            QMessageBox.warning(
                self,
                "Report Generator",
                f"The selected refinement system prompt does not exist:\n{refinement_system_prompt_path}",
            )
            return

        transcript_path: Path | None = None
        if self._report_transcript_edit:
            text = self._report_transcript_edit.text().strip()
            if text:
                transcript_path = Path(text).expanduser()
                if not transcript_path.is_file():
                    QMessageBox.warning(
                        self,
                        "Report Generator",
                        f"The selected transcript does not exist:\n{transcript_path}",
                    )
                    return

        selected_pairs: List[tuple[str, str]] = []
        for key in sorted(self._report_selected_inputs):
            if ":" not in key:
                continue
            category, relative = key.split(":", 1)
            selected_pairs.append((category, relative))

        if not selected_pairs and not transcript_path:
            QMessageBox.warning(
                self,
                "Report Generator",
                "Select at least one input or provide a transcript before generating a report.",
            )
            return

        project_dir = Path(self._project_manager.project_dir)
        metadata = self._project_manager.metadata or ProjectMetadata(
            case_name=self._project_manager.project_name or ""
        )

        self._project_manager.update_report_preferences(
            selected_inputs=sorted(self._report_selected_inputs),
            provider_id=provider_id,
            model=model_id,
            custom_model=custom_model,
            context_window=context_window,
            template_path=str(template_path),
            transcript_path=str(transcript_path) if transcript_path else None,
            generation_user_prompt=str(generation_user_prompt_path),
            refinement_user_prompt=str(refinement_user_prompt_path),
            generation_system_prompt=str(generation_system_prompt_path),
            refinement_system_prompt=str(refinement_system_prompt_path),
        )

        worker = ReportWorker(
            project_dir=project_dir,
            inputs=selected_pairs,
            provider_id=provider_id,
            model=model_id,
            custom_model=custom_model,
            context_window=context_window,
            template_path=template_path,
            transcript_path=transcript_path,
            generation_user_prompt_path=generation_user_prompt_path,
            refinement_user_prompt_path=refinement_user_prompt_path,
            generation_system_prompt_path=generation_system_prompt_path,
            refinement_system_prompt_path=refinement_system_prompt_path,
            metadata=metadata,
        )

        worker.progress.connect(self._on_report_progress)
        worker.log_message.connect(self._append_report_log)
        worker.finished.connect(lambda result, w=worker: self._on_report_finished(w, result))
        worker.failed.connect(lambda message, w=worker: self._on_report_failed(w, message))

        self._report_last_result = None
        self._report_running = True
        if self._report_progress_bar:
            self._report_progress_bar.setValue(0)
        if self._report_log:
            self._report_log.clear()
        self._update_report_controls()
        self._update_report_history_buttons()
        self._workers.start(self._report_key(), worker)

    def _report_key(self) -> str:
        return "report:run"

    def _on_report_progress(self, percent: int, message: str) -> None:
        if self._report_progress_bar:
            self._report_progress_bar.setValue(percent)
        self._append_report_log(message)

    def _append_report_log(self, message: str) -> None:
        if not self._report_log:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._report_log.append(f"[{timestamp}] {message}")

    def _on_report_finished(self, worker: ReportWorker, result: Dict[str, object]) -> None:
        stored = self._workers.pop(self._report_key())
        if worker and isValid(worker):
            worker.deleteLater()
        if stored and stored is not worker and isValid(stored):
            stored.deleteLater()

        self._report_running = False
        self._update_report_controls()

        self._report_last_result = result
        self._append_report_log("Report generation completed successfully.")
        if self._report_progress_bar:
            self._report_progress_bar.setValue(100)

        if self._project_manager:
            timestamp_raw = str(result.get("timestamp"))
            try:
                timestamp = datetime.fromisoformat(timestamp_raw)
            except Exception:
                timestamp = datetime.now(timezone.utc)
            draft_path = Path(str(result.get("draft_path")))
            refined_path = Path(str(result.get("refined_path")))
            reasoning_value = result.get("reasoning_path")
            reasoning_path = Path(str(reasoning_value)) if reasoning_value else None
            manifest_value = result.get("manifest_path")
            manifest_path = Path(str(manifest_value)) if manifest_value else None
            inputs_value = result.get("inputs_path")
            inputs_path = Path(str(inputs_value)) if inputs_value else None
            provider = str(result.get("provider", "anthropic"))
            model = str(result.get("model", ""))
            custom_model = result.get("custom_model")
            context_window = result.get("context_window")
            try:
                context_window_int = int(context_window) if context_window is not None else None
            except (ValueError, TypeError):
                context_window_int = None
            inputs = list(result.get("inputs", []))

            instructions_snapshot = str(result.get("instructions", ""))
            generation_user_prompt = (
                str(result.get("generation_user_prompt") or "").strip()
                or (
                    self._report_generation_user_prompt_edit.text().strip()
                    if self._report_generation_user_prompt_edit
                    else ""
                )
            )
            refinement_user_prompt = (
                str(result.get("refinement_user_prompt") or "").strip()
                or (
                    self._report_refinement_prompt_edit.text().strip()
                    if self._report_refinement_prompt_edit
                    else ""
                )
            )
            generation_system_prompt = (
                str(result.get("generation_system_prompt") or "").strip()
                or (
                    self._report_generation_system_prompt_edit.text().strip()
                    if self._report_generation_system_prompt_edit
                    else ""
                )
            )
            refinement_system_prompt = (
                str(result.get("refinement_system_prompt") or "").strip()
                or (
                    self._report_refinement_system_prompt_edit.text().strip()
                    if self._report_refinement_system_prompt_edit
                    else ""
                )
            )

            template_value = (
                self._report_template_edit.text().strip()
                if self._report_template_edit and self._report_template_edit.text().strip()
                else None
            )
            transcript_value = (
                self._report_transcript_edit.text().strip()
                if self._report_transcript_edit and self._report_transcript_edit.text().strip()
                else None
            )

            self._project_manager.record_report_run(
                timestamp=timestamp,
                draft_path=draft_path,
                refined_path=refined_path,
                reasoning_path=reasoning_path,
                manifest_path=manifest_path,
                inputs_path=inputs_path,
                provider=provider,
                model=model,
                custom_model=str(custom_model) if custom_model else None,
                context_window=context_window_int,
                inputs=inputs,
                template_path=template_value,
                transcript_path=transcript_value,
                instructions=instructions_snapshot,
                generation_user_prompt=generation_user_prompt or None,
                refinement_user_prompt=refinement_user_prompt or None,
                generation_system_prompt=generation_system_prompt or None,
                refinement_system_prompt=refinement_system_prompt or None,
            )

        self._refresh_report_history()
        self._update_report_history_buttons()

    def _on_report_failed(self, worker: ReportWorker, message: str) -> None:
        stored = self._workers.pop(self._report_key())
        if worker and isValid(worker):
            worker.deleteLater()
        if stored and stored is not worker and isValid(stored):
            stored.deleteLater()

        self._report_running = False
        self._update_report_controls()
        self._update_report_history_buttons()

        QMessageBox.critical(self, "Report Generator", message)
        self._append_report_log(f"Error: {message}")

    def _refresh_report_history(self) -> None:
        if not self._report_history_list:
            return
        self._report_history_list.blockSignals(True)
        self._report_history_list.clear()

        if not self._project_manager:
            self._report_history_list.blockSignals(False)
            return

        history = self._project_manager.report_state.history
        for index, entry in enumerate(history):
            try:
                timestamp_display = datetime.fromisoformat(entry.timestamp).astimezone().strftime("%Y-%m-%d %H:%M")
            except Exception:
                timestamp_display = entry.timestamp
            model_label = entry.custom_model or entry.model or ""
            outputs_text = (
                Path(entry.refined_path).name
                if entry.refined_path
                else Path(entry.draft_path).name
            )
            item = QTreeWidgetItem([timestamp_display, model_label, outputs_text])
            item.setData(0, Qt.UserRole, index)
            self._report_history_list.addTopLevelItem(item)

        if history and self._report_history_list.topLevelItemCount() > 0:
            self._report_history_list.setCurrentItem(self._report_history_list.topLevelItem(0))

        self._report_history_list.blockSignals(False)
        self._update_report_history_buttons()

    def _on_report_history_selected(self) -> None:
        self._update_report_history_buttons()

    def _update_report_history_buttons(self) -> None:
        buttons = [
            self._report_open_draft_button,
            self._report_open_refined_button,
            self._report_open_reasoning_button,
            self._report_open_manifest_button,
            self._report_open_inputs_button,
        ]
        for button in buttons:
            if button:
                button.setEnabled(False)

        if not self._report_history_list or not self._project_manager:
            return

        item = self._report_history_list.currentItem()
        if not item:
            return

        index = item.data(0, Qt.UserRole)
        if index is None:
            return
        try:
            entry = self._project_manager.report_state.history[int(index)]
        except (ValueError, IndexError):
            return

        if self._report_open_draft_button and entry.draft_path:
            self._report_open_draft_button.setEnabled(True)
        if self._report_open_refined_button and entry.refined_path:
            self._report_open_refined_button.setEnabled(True)
        if self._report_open_reasoning_button and entry.reasoning_path:
            self._report_open_reasoning_button.setEnabled(bool(entry.reasoning_path))
        if self._report_open_manifest_button and entry.manifest_path:
            self._report_open_manifest_button.setEnabled(True)
        if self._report_open_inputs_button and entry.inputs_path:
            self._report_open_inputs_button.setEnabled(True)

    def _open_report_history_file(self, kind: str) -> None:
        if not self._project_manager or not self._report_history_list:
            return
        item = self._report_history_list.currentItem()
        if not item:
            return
        index = item.data(0, Qt.UserRole)
        if index is None:
            return
        try:
            entry = self._project_manager.report_state.history[int(index)]
        except (ValueError, IndexError):
            return

        mapping = {
            "draft": entry.draft_path,
            "refined": entry.refined_path,
            "reasoning": entry.reasoning_path,
            "manifest": entry.manifest_path,
            "inputs": entry.inputs_path,
        }
        target = mapping.get(kind)
        if not target:
            QMessageBox.information(self, "Report Files", "Requested file is not available.")
            return
        path = Path(target)
        if not path.exists():
            QMessageBox.warning(self, "Report Files", f"File not found: {path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_reports_folder(self) -> None:
        if not self._project_manager or not self._project_manager.project_dir:
            return
        folder = Path(self._project_manager.project_dir) / "reports"
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _load_report_preferences(self) -> None:
        if not self._project_manager:
            return
        state = self._project_manager.report_state
        self._report_selected_inputs = set(state.last_selected_inputs or [])

        if self._report_model_combo:
            if state.last_custom_model:
                custom_index = self._report_model_combo.findData(("custom", ""))
                if custom_index >= 0:
                    self._report_model_combo.setCurrentIndex(custom_index)
                if self._report_custom_model_edit:
                    self._report_custom_model_edit.setText(state.last_custom_model)
            else:
                target = (
                    state.last_provider or "anthropic",
                    state.last_model or "claude-sonnet-4-5-20250929",
                )
                index = self._report_model_combo.findData(target)
                if index >= 0:
                    self._report_model_combo.setCurrentIndex(index)
                else:
                    self._report_model_combo.setCurrentIndex(1)

        if self._report_custom_context_spin:
            if state.last_context_window:
                self._report_custom_context_spin.setValue(int(state.last_context_window))
            else:
                self._report_custom_context_spin.setValue(200_000)

        if self._report_template_edit:
            self._report_template_edit.setText(state.last_template or "")
        if self._report_transcript_edit:
            self._report_transcript_edit.setText(state.last_transcript or "")
        if self._report_generation_user_prompt_edit:
            if state.last_generation_user_prompt:
                self._report_generation_user_prompt_edit.setText(state.last_generation_user_prompt)
            elif not self._report_generation_user_prompt_edit.text().strip():
                self._report_generation_user_prompt_edit.setText(
                    self._default_generation_user_prompt_path()
                )
        if self._report_refinement_prompt_edit:
            if state.last_refinement_user_prompt:
                self._report_refinement_prompt_edit.setText(state.last_refinement_user_prompt)
            elif not self._report_refinement_prompt_edit.text().strip():
                self._report_refinement_prompt_edit.setText(
                    self._default_refinement_user_prompt_path()
                )
        if self._report_generation_system_prompt_edit:
            if state.last_generation_system_prompt:
                self._report_generation_system_prompt_edit.setText(state.last_generation_system_prompt)
            elif not self._report_generation_system_prompt_edit.text().strip():
                self._report_generation_system_prompt_edit.setText(
                    self._default_generation_system_prompt_path()
                )
        if self._report_refinement_system_prompt_edit:
            if state.last_refinement_system_prompt:
                self._report_refinement_system_prompt_edit.setText(state.last_refinement_system_prompt)
            elif not self._report_refinement_system_prompt_edit.text().strip():
                self._report_refinement_system_prompt_edit.setText(
                    self._default_refinement_system_prompt_path()
                )

        self._on_report_model_changed()
        self._update_report_controls()
        self._update_report_history_buttons()




    def _refresh_summary_groups(self) -> None:
        if not self._feature_flags.summary_groups_enabled:
            return
        if not self._summary_table or not self._summary_empty_label or not self._summary_info_label:
            return
        if not self._project_manager:
            self._summary_table.setRowCount(0)
            self._summary_empty_label.show()
            return

        groups = self._project_manager.list_summary_groups()
        total_docs = 0
        group_metrics_map: Dict[str, WorkspaceGroupMetrics] = {}
        if self._workspace_metrics:
            total_docs = self._workspace_metrics.dashboard.imported_total
            group_metrics_map = self._workspace_metrics.groups
        self._prune_running_groups({group.group_id for group in groups})

        self._summary_table.setRowCount(0)
        if not groups:
            self._summary_empty_label.show()
            self._summary_info_label.setText("No bulk analysis groups yet.")
            return

        self._summary_empty_label.hide()
        self._summary_info_label.setText(f"{len(groups)} bulk analysis group(s)")

        self._summary_table.setRowCount(len(groups))
        for row, group in enumerate(groups):
            group_metrics = group_metrics_map.get(group.group_id)
            self._populate_group_row(row, group, total_docs, group_metrics)

    def _populate_group_row(
        self,
        row: int,
        group: SummaryGroup,
        total_docs: int,
        metrics: WorkspaceGroupMetrics | None,
    ) -> None:
        if not self._feature_flags.summary_groups_enabled:
            return
        if not self._summary_table:
            return
        description = group.description or ""
        name_item = QTableWidgetItem(group.name)
        name_item.setData(Qt.UserRole, group.group_id)
        name_item.setToolTip(description)
        self._summary_table.setItem(row, 0, name_item)

        op_type = getattr(metrics, "operation", "per_document") if metrics else "per_document"
        converted_count = metrics.converted_count if metrics else 0
        if op_type == "combined":
            input_count = getattr(metrics, "combined_input_count", 0)
            coverage_text = f"Combined – Inputs: {input_count}"
        else:
            coverage_text = f"{converted_count} of {total_docs}" if total_docs else str(converted_count)
        files_item = QTableWidgetItem(coverage_text)
        files_item.setTextAlignment(Qt.AlignCenter)
        self._summary_table.setItem(row, 1, files_item)

        updated_text = group.updated_at.strftime("%Y-%m-%d %H:%M")
        updated_item = QTableWidgetItem(updated_text)
        updated_item.setTextAlignment(Qt.AlignCenter)
        self._summary_table.setItem(row, 2, updated_item)

        if group.group_id in self._running_groups:
            if group.group_id in self._cancelling_groups:
                status_text = "Cancelling…"
            else:
                progress = self._bulk_progress.get(group.group_id)
                if progress and progress[1]:
                    status_text = f"Running ({progress[0]}/{progress[1]})"
                else:
                    status_text = "Running…"
        else:
            if op_type == "combined":
                if metrics and getattr(metrics, "combined_input_count", 0) == 0:
                    status_text = "No inputs"
                elif metrics and getattr(metrics, "combined_is_stale", False):
                    status_text = "Stale"
                else:
                    status_text = "Ready"
            else:
                if not converted_count:
                    status_text = "No converted files"
                elif metrics and metrics.pending_bulk_analysis:
                    status_text = f"Pending bulk ({metrics.pending_bulk_analysis})"
                else:
                    status_text = "Ready"
        status_item = QTableWidgetItem(status_text)
        status_item.setTextAlignment(Qt.AlignCenter)
        self._summary_table.setItem(row, 3, status_item)

        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(6)

        if op_type == "combined":
            run_button = QPushButton("Run Combined")
            run_enabled = (metrics and getattr(metrics, "combined_input_count", 0) > 0) and group.group_id not in self._running_groups
            run_button.setEnabled(bool(run_enabled))
            run_button.clicked.connect(lambda _, g=group: self._start_combined_run(g))
            action_layout.addWidget(run_button)
        else:
            pending_count = metrics.pending_bulk_analysis if metrics else None
            converted_count = metrics.converted_count if metrics else 0

            run_pending = QPushButton("Run Pending")
            run_pending.setEnabled(
                group.group_id not in self._running_groups
                and (pending_count is None or pending_count > 0)
            )
            run_pending.clicked.connect(
                lambda _, g=group: self._start_group_run(g, force_rerun=False)
            )
            action_layout.addWidget(run_pending)

            run_all = QPushButton("Run All")
            run_all.setEnabled(
                group.group_id not in self._running_groups
                and ((pending_count is None) or converted_count > 0)
            )
            run_all.clicked.connect(
                lambda _, g=group: self._start_group_run(g, force_rerun=True)
            )
            action_layout.addWidget(run_all)

        preview_button = QPushButton("Preview Prompt")
        preview_button.clicked.connect(lambda _, g=group: self._show_group_prompt_preview(g))
        action_layout.addWidget(preview_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.setEnabled(group.group_id in self._running_groups)
        cancel_button.clicked.connect(lambda _, g=group: self._cancel_group_run(g))
        action_layout.addWidget(cancel_button)

        if op_type == "combined":
            open_latest = QPushButton("Open Latest")
            open_latest.clicked.connect(lambda _, g=group: self._open_latest_combined(g))
            action_layout.addWidget(open_latest)
            open_button = QPushButton("Open Folder")
            open_button.clicked.connect(lambda _, g=group: self._open_group_folder(g))
            action_layout.addWidget(open_button)
        else:
            open_button = QPushButton("Open Folder")
            open_button.clicked.connect(lambda _, g=group: self._open_group_folder(g))
            action_layout.addWidget(open_button)

        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(lambda _, g=group: self._confirm_delete_group(g))
        action_layout.addWidget(delete_button)

        self._summary_table.setCellWidget(row, 4, action_widget)

        tooltip_parts = []
        if description:
            tooltip_parts.append(description)
        if group.directories:
            tooltip_parts.append("Directories: " + ", ".join(group.directories))
        extra_files = sorted(set(group.files))
        if extra_files:
            tooltip_parts.append("Files: " + ", ".join(extra_files))
        if metrics and metrics.converted_files:
            tooltip_parts.append(
                "Converted files (" + str(metrics.converted_count) + "): " + ", ".join(metrics.converted_files)
            )
        if tooltip_parts:
            name_item.setToolTip("\n".join(tooltip_parts))
            files_item.setToolTip("\n".join(tooltip_parts))
            status_item.setToolTip("\n".join(tooltip_parts))

    def _show_create_group_dialog(self) -> None:
        if not self._feature_flags.summary_groups_enabled:
            return
        if not self._project_manager or not self._project_manager.project_dir:
            return
        dialog = SummaryGroupDialog(
            self._project_manager.project_dir,
            self,
            metadata=self._project_manager.metadata,
        )
        if dialog.exec() == QDialog.Accepted:
            group = dialog.build_group()
            try:
                self._project_manager.save_summary_group(group)
            except Exception as exc:
                QMessageBox.critical(self, "Create Bulk Analysis Group Failed", str(exc))
            else:
                self.refresh()

    def _confirm_delete_group(self, group: SummaryGroup) -> None:
        if not self._feature_flags.summary_groups_enabled:
            return
        if not self._project_manager:
            return
        message = (
            f"Delete bulk analysis group '{group.name}'?\n\n"
            "All generated bulk analysis outputs stored in this group will be deleted."
        )
        reply = QMessageBox.question(
            self,
            "Delete Bulk Analysis Group",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if not self._project_manager.delete_summary_group(group.group_id):
                QMessageBox.warning(self, "Delete Failed", "Could not delete the bulk analysis group.")
            else:
                self._cancel_group_run(group)
                self.refresh()

    def _open_group_folder(self, group: SummaryGroup) -> None:
        if not self._feature_flags.summary_groups_enabled:
            return
        if not self._project_manager or not self._project_manager.project_dir:
            return
        folder = self._project_manager.project_dir / "bulk_analysis" / group.folder_name
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _show_group_prompt_preview(self, group: SummaryGroup) -> None:
        if not self._feature_flags.summary_groups_enabled:
            return
        if not self._project_manager or not self._project_manager.project_dir:
            QMessageBox.warning(self, "Prompt Preview", "Open a project to preview prompts.")
            return

        project_dir = Path(self._project_manager.project_dir)
        metadata = self._project_manager.metadata

        try:
            preview = generate_prompt_preview(project_dir, group, metadata=metadata)
        except PromptPreviewError as exc:
            QMessageBox.warning(self, "Prompt Preview", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.exception("Prompt preview failed: %s", exc)
            QMessageBox.warning(self, "Prompt Preview", "Failed to generate prompt preview.")
            return

        dialog = PromptPreviewDialog(self)
        dialog.set_prompts(preview.system_prompt, preview.user_prompt)
        dialog.exec()

    def _open_latest_combined(self, group: SummaryGroup) -> None:
        if not self._feature_flags.summary_groups_enabled:
            return
        if not self._project_manager or not self._project_manager.project_dir:
            return
        folder = self._project_manager.project_dir / "bulk_analysis" / group.folder_name / "reduce"
        if not folder.exists():
            QMessageBox.information(self, "No Outputs", "No combined outputs found for this operation.")
            return
        latest = None
        latest_m = None
        for f in folder.glob("combined_*.md"):
            try:
                m = f.stat().st_mtime
            except OSError:
                continue
            if latest is None or m > (latest_m or 0):
                latest = f
                latest_m = m
        if latest is None:
            QMessageBox.information(self, "No Outputs", "No combined outputs found for this operation.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(latest)))

    def _start_group_run(self, group: SummaryGroup, *, force_rerun: bool = False) -> None:
        if not self._feature_flags.summary_groups_enabled:
            return
        if group.group_id in self._running_groups:
            QMessageBox.information(
                self,
                "Already Running",
                f"Bulk analysis for '{group.name}' is already in progress.",
            )
            return

        if not self._workspace_metrics and self._project_manager:
            try:
                self._workspace_metrics = self._project_manager.get_workspace_metrics()
            except Exception:
                self._workspace_metrics = None

        group_metrics = None
        if self._workspace_metrics:
            group_metrics = self._workspace_metrics.groups.get(group.group_id)

        if not group_metrics:
            QMessageBox.warning(
                self,
                "Bulk Analysis",
                "Project metrics are unavailable. Re-scan sources before running bulk analysis.",
            )
            return

        files: List[str] = []
        if force_rerun:
            converted = list(group_metrics.converted_files)
            if not converted:
                QMessageBox.warning(
                    self,
                    "No Converted Documents",
                    "This group does not have any converted documents yet. Run conversion first.",
                )
                return
            files = converted
        else:
            pending = list(group_metrics.pending_files)
            if pending:
                files = pending
            else:
                QMessageBox.information(
                    self,
                    "Up to Date",
                    "All documents already have bulk analysis results. Use 'Run All' to re-process everything.",
                )
                return

        if not self._project_manager or not self._project_manager.project_dir:
            QMessageBox.warning(self, "Missing Project", "The project directory is not available.")
            return

        provider_default = (
            (self._project_manager.settings or {}).get("llm_provider", ""),
            (self._project_manager.settings or {}).get("llm_model", ""),
        )
        worker = BulkAnalysisWorker(
            project_dir=self._project_manager.project_dir,
            group=group,
            files=files,
            metadata=self._project_manager.metadata,
            default_provider=provider_default,
            force_rerun=force_rerun,
        )
        worker.progress.connect(
            lambda done, total, path, gid=group.group_id: self._on_bulk_progress(gid, done, total, path)
        )
        worker.file_failed.connect(lambda rel, err, gid=group.group_id: self._on_bulk_failed(gid, rel, err))
        worker.finished.connect(
            lambda success, failed, w=worker, gid=group.group_id: self._on_bulk_finished(gid, w, success, failed)
        )
        worker.log_message.connect(lambda message, gid=group.group_id: self._on_bulk_log(gid, message))

        key = self._bulk_key(group.group_id)
        self._running_groups.add(group.group_id)
        self._bulk_progress[group.group_id] = (0, len(files))
        self._bulk_failures[group.group_id] = []
        self._cancelling_groups.discard(group.group_id)
        self._on_bulk_log(
            group.group_id,
            f"Starting bulk analysis for '{group.name}' ({len(files)} {'all documents' if force_rerun else 'pending documents'}).",
        )
        self._refresh_summary_groups()
        self._workers.start(key, worker)

    def _start_combined_run(self, group: SummaryGroup) -> None:
        if not self._feature_flags.summary_groups_enabled:
            return
        if group.group_id in self._running_groups:
            QMessageBox.information(self, "Already Running", f"Combined operation for '{group.name}' is already in progress.")
            return
        if not self._project_manager or not self._project_manager.project_dir:
            QMessageBox.warning(self, "Missing Project", "The project directory is not available.")
            return
        worker = BulkReduceWorker(
            project_dir=self._project_manager.project_dir,
            group=group,
            metadata=self._project_manager.metadata,
        )
        gid = group.group_id
        key = f"combine:{gid}"
        self._running_groups.add(gid)
        self._bulk_progress[gid] = (0, 1)
        self._bulk_failures[gid] = []
        self._cancelling_groups.discard(gid)
        if self._summary_info_label:
            self._summary_info_label.setText("Running combined operation…")
        worker.progress.connect(lambda done, total, msg, g=gid: self._on_bulk_progress(g, done, total, msg))
        worker.file_failed.connect(lambda rel, err, g=gid: self._on_bulk_failed(g, rel, err))
        worker.log_message.connect(lambda message, g=gid: self._on_bulk_log(g, message))
        worker.finished.connect(lambda success, failed, w=worker, g=gid: self._on_bulk_finished(g, w, success, failed))
        self._workers.start(key, worker)

    def _cancel_group_run(self, group: SummaryGroup) -> None:
        if not self._feature_flags.summary_groups_enabled:
            return
        key = self._bulk_key(group.group_id)
        worker = self._workers.get(key)
        if worker:
            worker.cancel()
            self._cancelling_groups.add(group.group_id)
            if self._summary_info_label:
                self._summary_info_label.setText("Cancelling bulk analysis…")
        else:
            self._bulk_progress.pop(group.group_id, None)
            self._bulk_failures.pop(group.group_id, None)
            self._cancelling_groups.discard(group.group_id)
            if self._summary_info_label:
                self._summary_info_label.setText("Bulk analysis cancelled.")
        self._refresh_summary_groups()

    def _on_bulk_progress(self, group_id: str, completed: int, total: int, relative_path: str) -> None:
        if group_id in self._cancelling_groups:
            return
        self._bulk_progress[group_id] = (completed, total)
        if self._summary_info_label:
            self._summary_info_label.setText(
                f"Running bulk analysis ({completed}/{total})… {relative_path}"
            )
        self._refresh_summary_groups()

    def _on_bulk_failed(self, group_id: str, relative_path: str, error: str) -> None:
        LOGGER.error("Bulk analysis failed for %s: %s", relative_path, error)
        self._bulk_failures.setdefault(group_id, []).append(f"{relative_path}: {error}")

    def _on_bulk_log(self, group_id: str, message: str) -> None:  # noqa: ARG002 - future use
        LOGGER.info("[BulkAnalysis][%s] %s", group_id, message)
        if self._summary_info_label:
            self._summary_info_label.setText(message)

    def _on_bulk_finished(self, group_id: str, worker, successes: int, failures: int) -> None:
        key = self._bulk_key(group_id)
        stored = self._workers.pop(key)
        self._running_groups.discard(group_id)
        # Delete the specific worker instance and any different stored worker safely
        if worker and isValid(worker):
            worker.deleteLater()
        if stored and stored is not worker and isValid(stored):
            stored.deleteLater()
        self._bulk_progress.pop(group_id, None)
        errors = self._bulk_failures.pop(group_id, [])
        was_cancelled = group_id in self._cancelling_groups
        if was_cancelled:
            self._cancelling_groups.discard(group_id)

        if self._summary_info_label:
            if was_cancelled:
                self._summary_info_label.setText("Bulk analysis cancelled.")
            elif failures:
                self._summary_info_label.setText(
                    f"Bulk analysis completed with {failures} error(s)."
                )
            else:
                self._summary_info_label.setText("Bulk analysis completed.")

        if errors:
            QMessageBox.warning(
                self,
                "Bulk Analysis Issues",
                "Some documents failed during bulk analysis:\n" + "\n".join(errors),
            )

        self._refresh_file_tracker()
        self._refresh_summary_groups()

    def _prune_running_groups(self, valid_ids: Optional[set[str]] = None) -> None:
        if not self._feature_flags.summary_groups_enabled:
            return
        if valid_ids is None:
            valid_ids = set()
            if self._project_manager:
                try:
                    valid_ids = {
                        group.group_id for group in self._project_manager.list_summary_groups()
                    }
                except Exception:
                    valid_ids = set()
        stale = [gid for gid in list(self._running_groups) if gid not in valid_ids]
        for gid in stale:
            key = self._bulk_key(gid)
            worker = self._workers.pop(key)
            if worker:
                worker.cancel()
                if isValid(worker):
                    worker.deleteLater()
            self._running_groups.discard(gid)
            self._bulk_progress.pop(gid, None)
            self._bulk_failures.pop(gid, None)
            self._cancelling_groups.discard(gid)

    # ------------------------------------------------------------------
    # Worker coordination helpers
    # ------------------------------------------------------------------
    def _conversion_key(self) -> str:
        return "conversion:active"

    def _bulk_key(self, group_id: str) -> str:
        return f"bulk:{group_id}"
