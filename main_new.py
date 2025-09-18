#!/usr/bin/env python3
"""Main entry point for the new dashboard-oriented UI."""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QDialog,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, QTimer

# Ensure src/ is on sys.path for direct execution
sys.path.insert(0, str(Path(__file__).parent))

from src.config.logging_config import setup_logging
from src.config.startup_config import configure_startup_logging
from src.config.observability import setup_observability
from src.new.core import (
    FeatureFlags,
    ProjectManager,
    ProjectMetadata,
    SecureSettings,
    WorkspaceController,
)
from src.new.dialogs import NewProjectDialog
from src.new.stages.welcome_stage import WelcomeStage


class SimplifiedMainWindow(QMainWindow):
    """Main window hosting the welcome screen and dashboard workspace."""

    def __init__(self) -> None:
        super().__init__()
        self.logger = logging.getLogger(__name__)

        # Core components
        self.settings = SecureSettings()
        self.feature_flags = FeatureFlags.from_settings(self.settings)
        self.project_manager: ProjectManager | None = None
        self.workspace_controller = WorkspaceController(self, feature_flags=self.feature_flags)
        self.workspace_controller.workspace_created.connect(self._on_workspace_created)

        # Runtime state
        self._workspace_widget: QWidget | None = None
        self._welcome_stage: WelcomeStage | None = None

        # Optional Phoenix observability
        self._configure_observability()

        # Base window configuration
        self.setWindowTitle("Forensic Report Drafter")
        self.resize(1200, 800)
        geometry = self.settings.get_window_geometry()
        if geometry:
            self.restoreGeometry(geometry)

        # Build UI chrome
        self._create_menu_bar()
        self._create_toolbar()
        self._create_central_stack()
        self.statusBar().showMessage("Ready")

        # Defer heavy startup actions until the event loop spins
        QTimer.singleShot(100, self._startup)

    # ------------------------------------------------------------------
    # UI construction helpers
    # ------------------------------------------------------------------
    def _configure_observability(self) -> None:
        phoenix_settings = self.settings.get("phoenix_settings", {})
        phoenix_enabled = (
            phoenix_settings.get("enabled", False)
            or os.getenv("PHOENIX_ENABLED", "false").lower() == "true"
        )
        if not phoenix_enabled:
            return

        self.logger.info("Initializing Phoenix observability")
        if os.getenv("PHOENIX_ENABLED"):
            phoenix_settings["enabled"] = True
        if os.getenv("PHOENIX_PORT"):
            phoenix_settings["port"] = int(os.getenv("PHOENIX_PORT"))
        if os.getenv("PHOENIX_PROJECT"):
            phoenix_settings["project"] = os.getenv("PHOENIX_PROJECT")
        setup_observability({"phoenix_settings": phoenix_settings})

    def _create_menu_bar(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        file_menu.addAction("New Project", self._new_project)
        file_menu.addAction("Open Project", self._open_project)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        edit_menu = menubar.addMenu("Edit")
        edit_menu.addAction("Settings", self._open_settings)

        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About", self._show_about)

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Main", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toolbar.addAction("New", self._new_project)
        toolbar.addAction("Open", self._open_project)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

    def _create_central_stack(self) -> None:
        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.setObjectName("dashboardStack")
        layout.addWidget(self._stack)

        self.setCentralWidget(central_widget)

    # ------------------------------------------------------------------
    # Startup and navigation
    # ------------------------------------------------------------------
    def _startup(self) -> None:
        self.logger.info("Initializing dashboard views")
        self._welcome_stage = WelcomeStage()
        self._welcome_stage.new_project_requested.connect(self._new_project)
        self._welcome_stage.project_opened.connect(self._load_project)
        self._stack.addWidget(self._welcome_stage)
        self._stack.setCurrentWidget(self._welcome_stage)

        missing = [p for p in ("anthropic", "gemini", "azure_openai") if not self.settings.has_api_key(p)]
        if missing:
            self.logger.info("Missing API keys for: %s", ", ".join(missing))

    def _show_welcome(self) -> None:
        if self._welcome_stage:
            self._stack.setCurrentWidget(self._welcome_stage)
        self._workspace_widget = None
        self._update_window_title()
        self.statusBar().showMessage("Ready")

    # ------------------------------------------------------------------
    # Project lifecycle helpers
    # ------------------------------------------------------------------
    def _new_project(self) -> None:
        self.logger.info("Starting new project workflow")

        dialog = NewProjectDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        config = dialog.result_config()
        if not config:
            return

        try:
            project_manager = ProjectManager()
            metadata = ProjectMetadata(case_name=config.name.strip())
            project_manager.create_project(config.output_base, metadata)
            project_manager.update_conversion_helper(
                config.conversion_helper,
                **config.conversion_options,
            )
        except Exception as exc:  # pragma: no cover - UI feedback
            self.logger.exception("Failed to create project")
            QMessageBox.critical(self, "Project Creation Failed", str(exc))
            return

        try:
            relative_root = self._project_relative_path(project_manager.project_dir, config.source_root)
            project_manager.update_source_state(
                root=relative_root,
                selected_folders=config.selected_folders,
                warnings=dialog.current_warnings(),
                last_scan=None,
            )
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.exception("Failed to persist source configuration", exc_info=exc)

        self._activate_workspace(project_manager)

        workspace = self.workspace_controller.current_workspace()
        if workspace:
            workspace.begin_initial_conversion()

        self.statusBar().showMessage(f"Project created: {config.name.strip()}")

    def _open_project(self) -> None:
        project_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            str(Path.home()),
            "Forensic Report Project (*.frpd)",
        )
        if not project_path:
            return
        self._load_project(Path(project_path))

    def _load_project(self, project_path: Path) -> None:
        self.logger.info("Loading project: %s", project_path)
        project_manager = ProjectManager()
        try:
            if not project_manager.load_project(project_path):
                raise RuntimeError("Project file could not be loaded.")
        except Exception as exc:  # pragma: no cover - UI feedback
            self.logger.exception("Failed to load project")
            QMessageBox.critical(self, "Failed to Load Project", str(exc))
            return

        if project_manager.version_warning:
            QMessageBox.warning(
                self,
                "Legacy Project",
                "This project was created with an older preview build and is not compatible with the dashboard. "
                "Use 'Remove Legacy Projects' from the welcome screen to delete it.",
            )
            project_manager.close_project()
            self.project_manager = None
            return

        self._activate_workspace(project_manager)
        case_name = project_manager.metadata.case_name if project_manager.metadata else project_path.stem
        self.statusBar().showMessage(f"Project loaded: {case_name}")

    def _activate_workspace(self, project_manager: ProjectManager) -> None:
        self.project_manager = project_manager
        workspace = self.workspace_controller.create_workspace(project_manager)
        workspace.set_project(project_manager)
        self._display_workspace(workspace)
        self._update_window_title(project_manager)

    def _project_relative_path(self, project_dir: Path | None, external: Path) -> str:
        external = external.resolve()
        if not project_dir:
            return external.as_posix()
        project_dir = Path(project_dir).resolve()
        try:
            return external.relative_to(project_dir).as_posix()
        except ValueError:
            rel = os.path.relpath(external, project_dir)
            return Path(rel).as_posix()

    def _display_workspace(self, workspace: QWidget) -> None:
        if self._workspace_widget is not None:
            index = self._stack.indexOf(self._workspace_widget)
            if index != -1:
                widget = self._stack.widget(index)
                self._stack.removeWidget(widget)
                widget.deleteLater()
        self._workspace_widget = workspace
        self._stack.addWidget(workspace)
        self._stack.setCurrentWidget(workspace)

    def _on_workspace_created(self, workspace: QWidget) -> None:  # pragma: no cover - hook for future extensions
        self.logger.debug("Workspace widget created: %s", workspace)

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------
    def _open_settings(self) -> None:
        from src.new.dialogs import SettingsDialog

        dialog = SettingsDialog(self)
        dialog.settings_changed.connect(self._on_settings_changed)
        dialog.exec()

    def _on_settings_changed(self) -> None:
        self.logger.info("Settings updated")

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Forensic Report Drafter",
            "<h3>Forensic Report Drafter</h3>"
            "<p>Dashboard prototype in development.</p>"
            "<p>A professional tool for forensic psychologists to analyze complex records.</p>",
        )

    def _update_window_title(self, project_manager: ProjectManager | None = None) -> None:
        project_manager = project_manager or self.project_manager
        if project_manager and project_manager.metadata:
            case_name = project_manager.metadata.case_name
            self.setWindowTitle(f"Forensic Report Drafter — {case_name}")
        else:
            self.setWindowTitle("Forensic Report Drafter")

    def closeEvent(self, event) -> None:  # noqa: N802
        self.settings.save_window_geometry(self.saveGeometry())
        if self.project_manager:
            self.project_manager.close_project()
        super().closeEvent(event)


def main() -> int:
    """Run the dashboard UI."""
    configure_startup_logging()
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Forensic Report Drafter (New UI)")

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Forensic Report Drafter")
    app.setOrganizationName("Forensic Psychology Tools")
    app.setApplicationDisplayName("Forensic Report Drafter")

    window = SimplifiedMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
