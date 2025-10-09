#!/usr/bin/env python3
"""Main entry point for the new dashboard-oriented UI."""

from __future__ import annotations

import os
import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QDialog,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QDialogButtonBox,
    QLabel,
)
from PySide6.QtCore import Qt, QTimer

from src.config.logging_config import setup_logging
from src.config.startup_config import configure_startup_logging
from src.config.observability import setup_observability
from src.app.core import (
    FeatureFlags,
    ProjectManager,
    ProjectMetadata,
    SecureSettings,
    WorkspaceController,
)
from src.app.ui.dialogs import NewProjectDialog
from src.app.ui.stages.welcome_stage import WelcomeStage
from src.config.prompt_store import (
    load_manifest as load_prompt_manifest,
    load_template_manifest,
    compute_repo_digest,
    sync_bundled_prompts,
    sync_bundled_templates,
    get_repo_prompts_dir,
    get_repo_templates_dir,
)


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
        self.setWindowTitle("Llestrade")
        self.resize(1200, 800)
        geometry = self.settings.get_window_geometry()
        if geometry:
            self.restoreGeometry(geometry)

        # Build UI chrome
        self._create_menu_bar()
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
        self._welcome_stage.settings_requested.connect(self._open_settings)
        self._stack.addWidget(self._welcome_stage)
        self._stack.setCurrentWidget(self._welcome_stage)

        missing = [p for p in ("anthropic", "gemini", "azure_openai") if not self.settings.has_api_key(p)]
        if missing:
            self.logger.info("Missing API keys for: %s", ", ".join(missing))

        # Offer prompt sync on initial setup or when bundled prompts changed
        try:
            self._maybe_offer_resource_sync()
        except Exception as exc:
            self.logger.debug("Prompt sync check failed: %s", exc)

    def _show_welcome(self, *, close_project: bool = False) -> None:
        if close_project or self._workspace_widget is not None:
            self._teardown_workspace(close_project=close_project)
        if self._welcome_stage:
            self._stack.setCurrentWidget(self._welcome_stage)
        self._update_window_title()
        self.statusBar().showMessage("Ready")

    # ------------------------------------------------------------------
    # Prompt sync offer
    # ------------------------------------------------------------------
    def _maybe_offer_resource_sync(self) -> None:
        prompt_manifest = load_prompt_manifest() or {}
        prompt_previous = (prompt_manifest.get("repo_digest") or {}).get("digest")
        prompt_current = compute_repo_digest(get_repo_prompts_dir()).get("digest")
        prompt_changed = prompt_previous != prompt_current

        template_manifest = load_template_manifest() or {}
        template_previous = (template_manifest.get("repo_digest") or {}).get("digest")
        template_current = compute_repo_digest(get_repo_templates_dir()).get("digest")
        template_changed = template_previous != template_current

        if not prompt_changed and not template_changed:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Update Bundled Resources")
        v = QVBoxLayout(dialog)
        if prompt_changed and template_changed:
            text = (
                "Bundled prompts and templates have changed.\n\n"
                "You can sync the updated resources into your local folders. "
                "Custom files will not be modified."
            )
        elif prompt_changed:
            text = (
                "Bundled prompts have changed.\n\n"
                "You can sync the updated prompts into your prompts folder. "
                "Your custom prompts will not be modified."
            )
        else:
            text = (
                "Bundled templates have changed.\n\n"
                "You can sync the updated templates into your templates folder. "
                "Your custom templates will not be modified."
            )
        label = QLabel(text)
        label.setWordWrap(True)
        v.addWidget(label)

        buttons = QDialogButtonBox()
        sync_prompts_btn = None
        sync_templates_btn = None
        if prompt_changed:
            sync_prompts_btn = buttons.addButton(
                "Sync Bundled Prompts", QDialogButtonBox.ActionRole
            )
        if template_changed:
            sync_templates_btn = buttons.addButton(
                "Sync Bundled Templates", QDialogButtonBox.ActionRole
            )
        later_btn = buttons.addButton("Later", QDialogButtonBox.RejectRole)
        settings_btn = buttons.addButton(
            "Open Prompts & Templates Settings", QDialogButtonBox.HelpRole
        )
        v.addWidget(buttons)

        def _on_clicked(btn):
            if btn == sync_prompts_btn:
                try:
                    result = sync_bundled_prompts(force=False)
                    copied = len(result.get("copied", []))
                    updated = len(result.get("updated", []))
                    skipped = len(result.get("skipped", []))
                    same = len(result.get("same", []))
                    self.statusBar().showMessage(
                        f"Prompts synced (copied={copied}, updated={updated}, skipped={skipped}, unchanged={same})",
                        5000,
                    )
                except Exception as exc:
                    QMessageBox.warning(self, "Prompt Sync Failed", str(exc))
                btn.setEnabled(False)
            elif btn == sync_templates_btn:
                try:
                    result = sync_bundled_templates(force=False)
                    copied = len(result.get("copied", []))
                    updated = len(result.get("updated", []))
                    skipped = len(result.get("skipped", []))
                    same = len(result.get("same", []))
                    self.statusBar().showMessage(
                        f"Templates synced (copied={copied}, updated={updated}, skipped={skipped}, unchanged={same})",
                        5000,
                    )
                except Exception as exc:
                    QMessageBox.warning(self, "Template Sync Failed", str(exc))
                btn.setEnabled(False)
            elif btn == settings_btn:
                dialog.accept()
                self._open_settings()
            else:
                dialog.reject()

        buttons.clicked.connect(lambda b: _on_clicked(b))
        dialog.exec()

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
            metadata = ProjectMetadata(
                case_name=config.name.strip(),
                subject_name=config.subject_name,
                date_of_birth=config.date_of_birth,
                case_description=config.case_description,
            )
            project_manager.create_project(config.output_base, metadata)
            project_manager.set_placeholders(config.placeholders)
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

        project_manager.save_project()

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
        self._teardown_workspace(close_project=True)
        self.project_manager = project_manager
        workspace = self.workspace_controller.create_workspace(project_manager)
        workspace.set_project(project_manager)
        if hasattr(workspace, "home_requested"):
            workspace.home_requested.connect(self._handle_workspace_home)
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
            old_workspace = self._workspace_widget
            self._disconnect_workspace_signals(old_workspace)
            shutdown = getattr(old_workspace, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception:
                    self.logger.debug("Workspace shutdown raised", exc_info=True)
            index = self._stack.indexOf(old_workspace)
            if index != -1:
                widget = self._stack.widget(index)
                self._stack.removeWidget(widget)
                widget.deleteLater()
        self._workspace_widget = workspace
        self._stack.addWidget(workspace)
        self._stack.setCurrentWidget(workspace)

    def _handle_workspace_home(self) -> None:
        self._show_welcome(close_project=True)

    def _teardown_workspace(self, *, close_project: bool = False) -> None:
        if self._workspace_widget is not None:
            self._disconnect_workspace_signals(self._workspace_widget)
            shutdown = getattr(self._workspace_widget, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception:
                    self.logger.debug("Workspace shutdown raised", exc_info=True)
            index = self._stack.indexOf(self._workspace_widget)
            if index != -1:
                widget = self._stack.widget(index)
                self._stack.removeWidget(widget)
                widget.deleteLater()
            self._workspace_widget = None
        if close_project and self.project_manager:
            try:
                self.project_manager.close_project()
            finally:
                self.project_manager = None

    def _disconnect_workspace_signals(self, workspace: QWidget) -> None:
        signal = getattr(workspace, "home_requested", None)
        if signal is None:
            return
        try:
            signal.disconnect(self._handle_workspace_home)
        except (TypeError, RuntimeError):  # Already disconnected or widget gone
            pass

    def _on_workspace_created(self, workspace: QWidget) -> None:  # pragma: no cover - hook for future extensions
        self.logger.debug("Workspace widget created: %s", workspace)

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------
    def _open_settings(self) -> None:
        from src.app.ui.dialogs import SettingsDialog

        dialog = SettingsDialog(self)
        dialog.settings_changed.connect(self._on_settings_changed)
        dialog.exec()

    def _on_settings_changed(self) -> None:
        self.logger.info("Settings updated")

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Llestrade",
            "<h3>Llestrade</h3>"
            "<p>Dashboard prototype in development.</p>"
            "<p>A professional tool for forensic psychologists to analyze complex records.</p>",
        )

    def _update_window_title(self, project_manager: ProjectManager | None = None) -> None:
        project_manager = project_manager or self.project_manager
        if project_manager and project_manager.metadata:
            case_name = project_manager.metadata.case_name
            self.setWindowTitle(f"Llestrade — {case_name}")
        else:
            self.setWindowTitle("Llestrade")

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
    logger.info("Starting Llestrade (Dashboard UI)")

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Llestrade")
    app.setOrganizationName("Forensic Psychology Tools")
    app.setApplicationDisplayName("Llestrade")

    window = SimplifiedMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
