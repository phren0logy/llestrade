"""Highlights tab controller."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Sequence

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QMessageBox, QTreeWidgetItem, QWidget

from src.app.core.file_tracker import WorkspaceMetrics
from src.app.core.project_manager import HighlightState, ProjectManager
from src.app.ui.workspace.highlights_tab import HighlightsTab
from src.app.workers.highlight_worker import HighlightExtractionSummary


class HighlightsController:
    """Coordinate highlights presentation and user interactions."""

    def __init__(
        self,
        workspace: QWidget,
        tab: HighlightsTab,
        *,
        on_extract_requested: Callable[[], None],
        counts_label: QLabel,
    ) -> None:
        self._workspace = workspace
        self._tab = tab
        self._project_manager: Optional[ProjectManager] = None
        self._on_extract_requested = on_extract_requested
        self._counts_label = counts_label

        self._running = False
        self._total_jobs = 0
        self._conversion_running = False

        self._errors: list[str] = []
        self._last_relative_path: str = ""

        self._tab.extract_button.clicked.connect(self._handle_extract_clicked)
        self._tab.open_folder_button.clicked.connect(self._open_highlights_folder)
        self._tab.tree.itemDoubleClicked.connect(self._open_highlight_item)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def set_project(self, project_manager: Optional[ProjectManager]) -> None:
        self._project_manager = project_manager
        if project_manager is None:
            self._reset_view()
        else:
            self._tab.open_folder_button.setEnabled(True)

    def set_conversion_running(self, running: bool) -> None:
        self._conversion_running = running
        self._update_extract_button_state()

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    def refresh(
        self,
        *,
        metrics: WorkspaceMetrics | None,
        highlight_state: HighlightState | None,
    ) -> None:
        if not self._project_manager:
            self._reset_view()
            return

        self._tab.open_folder_button.setEnabled(True)

        dashboard = metrics.dashboard if metrics else None
        if dashboard:
            pdf_total = dashboard.highlights_total + dashboard.pending_highlights
            message = f"Highlights extracted: {dashboard.highlights_total} of {pdf_total}"
            if dashboard.pending_highlights:
                message += f" (pending {dashboard.pending_highlights})"
        else:
            message = "Highlights extracted: 0"
        self._tab.counts_label.setText(message)

        state = highlight_state or HighlightState()
        last_run_text = "Last run: —"
        if state.last_run_at:
            try:
                parsed = datetime.fromisoformat(state.last_run_at)
                last_run_text = "Last run: " + parsed.astimezone().strftime("%Y-%m-%d %H:%M")
            except ValueError:
                last_run_text = f"Last run: {state.last_run_at}"
        self._tab.last_run_label.setText(last_run_text)

        if not self._running:
            if state.last_run_at:
                details = (
                    f"Last run captured {state.total_highlights} highlight(s) across "
                    f"{state.documents_with_highlights} document(s). "
                    f"Color files: {state.color_files}."
                )
                self._tab.status_label.setText(details)
            else:
                self._tab.status_label.setText("Highlights have not been extracted yet.")

        self._populate_tree()
        self._update_extract_button_state()

    # ------------------------------------------------------------------
    # Extraction flow
    # ------------------------------------------------------------------
    def begin_extraction(self, total_jobs: int) -> None:
        self._running = True
        self._total_jobs = total_jobs
        self._errors.clear()
        self._last_relative_path = ""

        self._counts_label.setText(f"Extracting highlights (0/{total_jobs})…")
        self._tab.status_label.setText(f"Extracting highlights (0/{total_jobs})…")
        self._tab.extract_button.setEnabled(False)
        self._update_extract_button_state()

    def update_progress(self, processed: int, total: int, relative_path: str) -> None:
        self._last_relative_path = relative_path
        message = f"Extracting highlights ({processed}/{total})… {relative_path}"
        self._counts_label.setText(message)
        self._tab.status_label.setText(message)

    def record_failure(self, source_path: str, error: str) -> None:
        name = Path(source_path).name
        self._errors.append(f"{name}: {error}")

    def finish(
        self,
        *,
        summary: HighlightExtractionSummary | None,
        failures: int,
    ) -> None:
        self._running = False
        self._total_jobs = 0
        self._counts_label.setText("Highlights extracted.")
        self._update_extract_button_state()

        if failures:
            message = "\n".join(self._errors) or "Unknown errors"
            QMessageBox.warning(
                self._workspace,
                "Highlight Extraction Issues",
                "Some highlights could not be extracted:\n\n" + message,
            )
        elif summary is None:
            self._tab.status_label.setText("Highlight extraction finished.")

    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _handle_extract_clicked(self) -> None:
        if self._on_extract_requested:
            self._on_extract_requested()

    def _open_highlights_folder(self) -> None:
        manager = self._project_manager
        if not manager or not manager.project_dir:
            QMessageBox.information(
                self._workspace,
                "Highlights",
                "Open or create a project before accessing highlights.",
            )
            return
        folder = manager.project_dir / "highlights"
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _open_highlight_item(self, item: QTreeWidgetItem, column: int) -> None:  # noqa: ARG002
        path = item.data(0, Qt.UserRole)
        if not path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _populate_tree(self) -> None:
        tree = self._tab.tree
        tree.clear()
        manager = self._project_manager
        if not manager or not manager.project_dir:
            return

        project_dir = manager.project_dir
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

    def _reset_view(self) -> None:
        self._tab.counts_label.setText("Highlights extracted: 0 | Pending: 0")
        self._tab.last_run_label.setText("Last run: —")
        if not self._running:
            self._tab.status_label.setText("Highlights have not been extracted yet.")
        self._tab.open_folder_button.setEnabled(False)
        self._tab.tree.clear()
        self._update_extract_button_state()

    def _update_extract_button_state(self) -> None:
        if not self._project_manager or self._running or self._conversion_running:
            self._tab.extract_button.setEnabled(False)
            return
        try:
            jobs_available = bool(self._project_manager.build_highlight_jobs())
        except Exception:
            jobs_available = False
        self._tab.extract_button.setEnabled(jobs_available)


__all__ = ["HighlightsController"]
