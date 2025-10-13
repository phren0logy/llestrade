"""Controller for the reports tab."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMessageBox, QTreeWidgetItem, QWidget

from src.app.core.bulk_paths import iter_map_outputs
from src.app.core.project_manager import ProjectManager, ProjectMetadata
from src.app.core.prompt_placeholders import format_prompt, placeholder_summary, get_prompt_spec
from src.app.core.placeholders.analyzer import analyse_prompts
from src.app.core.prompt_preview import PromptPreview
from src.app.core.refinement_prompt import (
    read_generation_prompt,
    read_refinement_prompt,
    validate_generation_prompt,
    validate_refinement_prompt,
)
from src.app.core.report_inputs import (
    REPORT_CATEGORY_BULK_COMBINED,
    REPORT_CATEGORY_BULK_MAP,
    REPORT_CATEGORY_CONVERTED,
    REPORT_CATEGORY_HIGHLIGHT_COLOR,
    REPORT_CATEGORY_HIGHLIGHT_DOCUMENT,
    ReportInputDescriptor,
    category_display_name,
)
from src.app.core.report_prompt_context import build_report_preview_placeholders
from src.app.ui.workspace.qt_flags import ITEM_IS_TRISTATE, ITEM_IS_USER_CHECKABLE
from src.app.ui.workspace.reports_tab import ReportsTab
from src.app.ui.workspace.services import (
    ReportDraftJobConfig,
    ReportRefinementJobConfig,
    ReportsService,
)
from src.app.ui.dialogs.prompt_preview_dialog import PromptPreviewDialog
from src.config.prompt_store import (
    get_bundled_dir,
    get_custom_dir,
    get_repo_prompts_dir,
    get_template_custom_dir,
)
from src.app.core.secure_settings import SecureSettings
from src.common.llm.bedrock_catalog import DEFAULT_BEDROCK_MODELS, list_bedrock_models


@dataclass(slots=True)
class _HistorySelection:
    draft_path: Optional[Path]
    refined_path: Optional[Path]
    reasoning_path: Optional[Path]
    manifest_path: Optional[Path]
    inputs_path: Optional[Path]


class ReportsController:
    """Coordinate report generation UI and worker orchestration."""

    def __init__(
        self,
        workspace: QWidget,
        tab: ReportsTab,
        *,
        service: ReportsService,
    ) -> None:
        self._workspace = workspace
        self._tab = tab
        self._service = service

        self._project_manager: Optional[ProjectManager] = None
        self._selected_inputs: set[str] = set()
        self._last_result: Optional[Dict[str, object]] = None
        self._report_running = False
        self._active_run_kind: Optional[str] = None

        self._populate_model_options()
        self._connect_signals()
        self._initialise_prompt_tooltips()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def set_project(self, project_manager: Optional[ProjectManager]) -> None:
        self._project_manager = project_manager
        self._selected_inputs.clear()
        if project_manager is None:
            self._reset_view()
            return

        self._tab.open_reports_button.setEnabled(True)
        self._load_preferences()
        self.refresh()

    def refresh(self) -> None:
        descriptors = self._collect_report_inputs()
        self._populate_report_inputs_tree(descriptors)
        self._refresh_report_history()
        self._update_report_controls()

    def shutdown(self) -> None:
        self._report_running = False
        self._selected_inputs.clear()
        self._last_result = None
        self._tab.progress_bar.setValue(0)
        self._tab.log_text.clear()
        self._tab.history_list.clear()
        self._tab.open_reports_button.setEnabled(False)

    def _validate_placeholders_before_run(
        self,
        *,
        include_generation: bool,
        include_refinement: bool,
    ) -> bool:
        manager = self._project_manager
        if not manager or not manager.project_dir:
            return False

        values = manager.placeholder_mapping()
        missing_required: set[str] = set()
        missing_optional: set[str] = set()
        dynamic_keys = {
            "template_section",
            "transcript",
            "additional_documents",
            "draft_report",
            "template",
            "document_content",
            "chunk_index",
            "chunk_total",
        }

        def _analyse(template: str, spec_key: str | None, *, is_system: bool) -> None:
            nonlocal missing_required, missing_optional
            if not template.strip():
                return
            required: Iterable[str] = ()
            optional: Iterable[str] = ()
            if spec_key:
                spec = get_prompt_spec(spec_key)
                if spec:
                    required = spec.required
                    optional = spec.optional
            analysis = analyse_prompts(
                template if is_system else "",
                template if not is_system else "",
                available_values=values,
                required_keys=required,
                optional_keys=optional,
            )
            missing_required |= set(analysis.missing_required) - dynamic_keys
            missing_optional |= set(analysis.missing_optional) - dynamic_keys

        generation_user = self._read_prompt_file(self._tab.generation_user_prompt_edit.text())
        generation_system = self._read_prompt_file(self._tab.generation_system_prompt_edit.text())
        refinement_user = self._read_prompt_file(self._tab.refinement_user_prompt_edit.text())
        refinement_system = self._read_prompt_file(self._tab.refinement_system_prompt_edit.text())

        if include_generation:
            _analyse(generation_user, "report_generation_user_prompt", is_system=False)
            _analyse(generation_system, "report_generation_system_prompt", is_system=True)
        if include_refinement:
            _analyse(refinement_user, "refinement_prompt", is_system=False)
            _analyse(refinement_system, "report_refinement_system_prompt", is_system=True)

        if missing_required or missing_optional:
            messages: list[str] = []
            if missing_required:
                messages.append(
                    "Required placeholders without values:\n  - "
                    + "\n  - ".join(sorted(f"{{{key}}}" for key in missing_required))
                )
            if missing_optional:
                messages.append(
                    "Optional placeholders without values:\n  - "
                    + "\n  - ".join(sorted(f"{{{key}}}" for key in missing_optional))
                )
            messages.append("Continue with the report run?")
            reply = QMessageBox.question(
                self._workspace,
                "Placeholder Values Missing",
                "\n\n".join(messages),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            return reply == QMessageBox.Yes
        return True

    def is_running(self) -> bool:
        return self._report_running

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------
    def _connect_signals(self) -> None:
        self._tab.model_combo.currentIndexChanged.connect(self._on_report_model_changed)
        self._tab.template_browse_button.clicked.connect(self._browse_report_template)
        self._tab.transcript_browse_button.clicked.connect(self._browse_report_transcript)
        self._tab.generation_user_prompt_browse.clicked.connect(self._browse_generation_prompt)
        self._tab.generation_user_prompt_preview.clicked.connect(self._preview_generation_prompt)
        self._tab.generation_system_prompt_browse.clicked.connect(self._browse_generation_system_prompt)
        self._tab.refinement_user_prompt_browse.clicked.connect(self._browse_refinement_prompt)
        self._tab.refinement_user_prompt_preview.clicked.connect(self._preview_refinement_prompt)
        self._tab.refinement_system_prompt_browse.clicked.connect(self._browse_refinement_system_prompt)
        self._tab.refine_draft_browse_button.clicked.connect(self._browse_refinement_draft)
        self._tab.generate_draft_button.clicked.connect(self._start_draft_job)
        self._tab.run_refinement_button.clicked.connect(self._start_refinement_job)
        self._tab.open_reports_button.clicked.connect(self._open_reports_folder)
        self._tab.inputs_tree.itemChanged.connect(self._on_report_input_changed)
        self._tab.history_list.itemSelectionChanged.connect(self._on_report_history_selected)
        self._tab.open_draft_button.clicked.connect(lambda: self._open_report_history_file("draft"))
        self._tab.open_refined_button.clicked.connect(lambda: self._open_report_history_file("refined"))
        self._tab.open_reasoning_button.clicked.connect(lambda: self._open_report_history_file("reasoning"))
        self._tab.open_manifest_button.clicked.connect(lambda: self._open_report_history_file("manifest"))
        self._tab.open_inputs_button.clicked.connect(lambda: self._open_report_history_file("inputs"))

    def _populate_model_options(self) -> None:
        combo = self._tab.model_combo
        if combo.count() > 0:
            return
        combo.addItem("Custom…", ("custom", ""))
        combo.addItem(
            "Anthropic Claude (claude-sonnet-4-5-20250929)",
            ("anthropic", "claude-sonnet-4-5-20250929"),
        )
        combo.addItem(
            "Anthropic Claude (claude-opus-4-1-20250805)",
            ("anthropic", "claude-opus-4-1-20250805"),
        )

        try:
            settings = SecureSettings()
            bedrock_settings = settings.get("aws_bedrock_settings", {}) or {}
            bedrock_models = list_bedrock_models(
                region=bedrock_settings.get("region"),
                profile=bedrock_settings.get("profile"),
            )
        except Exception:
            bedrock_models = list(DEFAULT_BEDROCK_MODELS)

        for model in bedrock_models:
            label = f"AWS Bedrock Claude ({model.name})"
            combo.addItem(label, ("anthropic_bedrock", model.model_id))


    def _initialise_prompt_tooltips(self) -> None:
        self._tab.generation_system_prompt_edit.setToolTip(
            placeholder_summary("report_generation_system_prompt")
        )
        self._tab.refinement_system_prompt_edit.setToolTip(
            placeholder_summary("report_refinement_system_prompt")
        )

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------
    def _load_preferences(self) -> None:
        manager = self._project_manager
        if not manager:
            return

        state = manager.report_state
        self._selected_inputs = set(state.last_selected_inputs or [])

        provider = state.last_provider or "anthropic"
        model = state.last_model or "claude-sonnet-4-5-20250929"
        for index in range(self._tab.model_combo.count()):
            data = self._tab.model_combo.itemData(index)
            if not data:
                continue
            if data[0] == "custom" and state.last_custom_model:
                self._tab.model_combo.setCurrentIndex(index)
                self._tab.custom_model_edit.setText(state.last_custom_model or "")
                if state.last_context_window:
                    self._tab.custom_context_spin.setValue(int(state.last_context_window))
                break
            if data[0] == provider and data[1] == model:
                self._tab.model_combo.setCurrentIndex(index)
                break
        else:
            self._tab.model_combo.setCurrentIndex(0)

        if state.last_template:
            self._tab.template_edit.setText(state.last_template)
        if state.last_transcript:
            self._tab.transcript_edit.setText(state.last_transcript)
        if state.last_generation_user_prompt:
            self._tab.generation_user_prompt_edit.setText(state.last_generation_user_prompt)
        if state.last_refinement_user_prompt:
            self._tab.refinement_user_prompt_edit.setText(state.last_refinement_user_prompt)
        if state.last_generation_system_prompt:
            self._tab.generation_system_prompt_edit.setText(state.last_generation_system_prompt)
        if state.last_refinement_system_prompt:
            self._tab.refinement_system_prompt_edit.setText(state.last_refinement_system_prompt)
        if state.last_refinement_draft:
            self._tab.refine_draft_edit.setText(state.last_refinement_draft)

        self._ensure_default_prompts()

    def _save_preferences(
        self,
        *,
        provider_id: str,
        model: str,
        custom_model: Optional[str],
        context_window: Optional[int],
        template_path: Optional[Path],
        transcript_path: Optional[Path],
        generation_user_prompt: Optional[Path],
        refinement_user_prompt: Optional[Path],
        generation_system_prompt: Optional[Path],
        refinement_system_prompt: Optional[Path],
        refinement_draft: Optional[Path],
    ) -> None:
        manager = self._project_manager
        if not manager:
            return

        manager.update_report_preferences(
            selected_inputs=sorted(self._selected_inputs),
            provider_id=provider_id,
            model=model,
            custom_model=custom_model,
            context_window=context_window,
            template_path=str(template_path) if template_path else None,
            transcript_path=str(transcript_path) if transcript_path else None,
            generation_user_prompt=str(generation_user_prompt) if generation_user_prompt else None,
            refinement_user_prompt=str(refinement_user_prompt) if refinement_user_prompt else None,
            generation_system_prompt=str(generation_system_prompt) if generation_system_prompt else None,
            refinement_system_prompt=str(refinement_system_prompt) if refinement_system_prompt else None,
            refinement_draft=str(refinement_draft) if refinement_draft else None,
        )

    # ------------------------------------------------------------------
    # Inputs
    # ------------------------------------------------------------------
    def _collect_report_inputs(self) -> List[ReportInputDescriptor]:
        manager = self._project_manager
        if not manager or not manager.project_dir:
            return []

        project_dir = Path(manager.project_dir)
        descriptors: List[ReportInputDescriptor] = []

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
                if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
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
        tree = self._tab.inputs_tree
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
            parent.setFlags(parent.flags() | ITEM_IS_USER_CHECKABLE | ITEM_IS_TRISTATE)
            parent.setCheckState(0, Qt.Unchecked)
            tree.addTopLevelItem(parent)

            for descriptor in entries:
                child = QTreeWidgetItem([descriptor.label, descriptor.relative_path])
                child.setFlags(child.flags() | ITEM_IS_USER_CHECKABLE)
                key = descriptor.key()
                child.setData(0, Qt.UserRole, key)
                state = Qt.Checked if key in self._selected_inputs else Qt.Unchecked
                child.setCheckState(0, state)
                parent.addChild(child)

        tree.expandAll()
        tree.blockSignals(False)

    # ------------------------------------------------------------------
    # UI updates
    # ------------------------------------------------------------------
    def _update_report_controls(self) -> None:
        has_inputs = bool(self._selected_inputs)
        template_ok = bool(self._tab.template_edit.text().strip())
        gen_user_ok = bool(self._tab.generation_user_prompt_edit.text().strip())
        gen_system_ok = bool(self._tab.generation_system_prompt_edit.text().strip())
        ref_user_ok = bool(self._tab.refinement_user_prompt_edit.text().strip())
        ref_system_ok = bool(self._tab.refinement_system_prompt_edit.text().strip())
        transcript_ok = bool(self._tab.transcript_edit.text().strip())
        refinement_draft_candidate = self._tab.refine_draft_edit.text().strip()
        refinement_draft_exists = bool(refinement_draft_candidate) and Path(refinement_draft_candidate).expanduser().is_file()

        manager_loaded = self._project_manager is not None
        idle = not self._report_running

        can_run_draft = (
            manager_loaded
            and idle
            and template_ok
            and gen_user_ok
            and gen_system_ok
            and (has_inputs or transcript_ok)
        )

        can_run_refine = (
            manager_loaded
            and idle
            and ref_user_ok
            and ref_system_ok
            and refinement_draft_exists
        )

        self._tab.generate_draft_button.setEnabled(can_run_draft)
        self._tab.run_refinement_button.setEnabled(can_run_refine)

    def _update_report_history_buttons(self) -> None:
        buttons = [
            self._tab.open_draft_button,
            self._tab.open_refined_button,
            self._tab.open_reasoning_button,
            self._tab.open_manifest_button,
            self._tab.open_inputs_button,
        ]
        for button in buttons:
            button.setEnabled(False)

        manager = self._project_manager
        if not manager:
            return

        item = self._tab.history_list.currentItem()
        if not item:
            return

        index = item.data(0, Qt.UserRole)
        if index is None:
            return

        try:
            entry = manager.report_state.history[int(index)]
        except (IndexError, ValueError, TypeError):
            return

        self._tab.open_draft_button.setEnabled(bool(entry.draft_path))
        self._tab.open_refined_button.setEnabled(bool(entry.refined_path))
        self._tab.open_reasoning_button.setEnabled(bool(entry.reasoning_path))
        self._tab.open_manifest_button.setEnabled(bool(entry.manifest_path))
        self._tab.open_inputs_button.setEnabled(bool(entry.inputs_path))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_report_model_changed(self) -> None:
        data = self._tab.model_combo.currentData()
        is_custom = bool(data) and data[0] == "custom"
        for widget in (
            self._tab.custom_model_label,
            self._tab.custom_model_edit,
            self._tab.custom_context_label,
            self._tab.custom_context_spin,
        ):
            widget.setVisible(is_custom)
        self._update_report_controls()

    def _on_report_input_changed(self, item: QTreeWidgetItem, column: int) -> None:  # noqa: ARG002
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        key = str(data)
        if item.checkState(0) == Qt.Checked:
            self._selected_inputs.add(key)
        else:
            self._selected_inputs.discard(key)
        self._update_report_controls()

    def _on_report_history_selected(self) -> None:
        self._update_report_history_buttons()

    # ------------------------------------------------------------------
    # Browse helpers
    # ------------------------------------------------------------------
    def _browse_report_template(self) -> None:
        initial = self._safe_initial(get_template_custom_dir)
        file_path, _ = QFileDialog.getOpenFileName(
            self._workspace,
            "Select Template",
            str(initial),
            "Markdown/Text Files (*.md *.txt);;All Files (*)",
        )
        if file_path:
            self._tab.template_edit.setText(file_path)
        self._update_report_controls()

    def _browse_report_transcript(self) -> None:
        initial = self._project_dir_or_home()
        file_path, _ = QFileDialog.getOpenFileName(
            self._workspace,
            "Select Transcript",
            str(initial),
            "Markdown/Text Files (*.md *.txt);;All Files (*)",
        )
        if file_path:
            self._tab.transcript_edit.setText(file_path)
        self._update_report_controls()

    def _browse_generation_prompt(self) -> None:
        initial = self._safe_initial(get_custom_dir)
        file_path, _ = QFileDialog.getOpenFileName(
            self._workspace,
            "Select Generation User Prompt",
            str(initial),
            "Markdown/Text Files (*.md *.txt);;All Files (*)",
        )
        if file_path:
            self._tab.generation_user_prompt_edit.setText(file_path)
        self._update_report_controls()

    def _browse_refinement_prompt(self) -> None:
        initial = self._safe_initial(get_custom_dir)
        file_path, _ = QFileDialog.getOpenFileName(
            self._workspace,
            "Select Refinement Prompt",
            str(initial),
            "Markdown/Text Files (*.md *.txt);;All Files (*)",
        )
        if file_path:
            self._tab.refinement_user_prompt_edit.setText(file_path)
        self._update_report_controls()

    def _browse_generation_system_prompt(self) -> None:
        initial = self._safe_initial(get_custom_dir)
        file_path, _ = QFileDialog.getOpenFileName(
            self._workspace,
            "Select Generation System Prompt",
            str(initial),
            "Markdown/Text Files (*.md *.txt);;All Files (*)",
        )
        if file_path:
            self._tab.generation_system_prompt_edit.setText(file_path)
        self._update_report_controls()

    def _browse_refinement_system_prompt(self) -> None:
        initial = self._safe_initial(get_custom_dir)
        file_path, _ = QFileDialog.getOpenFileName(
            self._workspace,
            "Select Refinement System Prompt",
            str(initial),
            "Markdown/Text Files (*.md *.txt);;All Files (*)",
        )
        if file_path:
            self._tab.refinement_system_prompt_edit.setText(file_path)
        self._update_report_controls()

    def _browse_refinement_draft(self) -> None:
        initial = self._project_dir_or_home()
        reports_dir = initial / "reports"
        if reports_dir.exists():
            initial = reports_dir
        file_path, _ = QFileDialog.getOpenFileName(
            self._workspace,
            "Select Draft for Refinement",
            str(initial),
            "Draft Reports (*-draft.md);;Markdown Files (*.md);;All Files (*)",
        )
        if file_path:
            self._tab.refine_draft_edit.setText(file_path)
        self._update_report_controls()

    # ------------------------------------------------------------------
    # Prompt previews
    # ------------------------------------------------------------------
    def _preview_generation_prompt(self) -> None:
        self._show_prompt_preview(
            title="Generation Prompt Preview",
            prompt_path=self._tab.generation_user_prompt_edit.text().strip(),
            system_prompt_path=self._tab.generation_system_prompt_edit.text().strip(),
            prompt_spec_key="report_generation_user_prompt",
            system_spec_key="report_generation_system_prompt",
        )

    def _preview_generation_system_prompt(self) -> None:
        self._show_prompt_preview(
            title="Generation System Prompt Preview",
            prompt_path=self._tab.generation_system_prompt_edit.text().strip(),
            system_prompt_path="",
            system_spec_key="report_generation_system_prompt",
        )

    def _preview_refinement_prompt(self) -> None:
        self._show_prompt_preview(
            title="Refinement Prompt Preview",
            prompt_path=self._tab.refinement_user_prompt_edit.text().strip(),
            system_prompt_path=self._tab.refinement_system_prompt_edit.text().strip(),
            prompt_spec_key="refinement_prompt",
            system_spec_key="report_refinement_system_prompt",
        )

    def _preview_refinement_system_prompt(self) -> None:
        self._show_prompt_preview(
            title="Refinement System Prompt Preview",
            prompt_path=self._tab.refinement_system_prompt_edit.text().strip(),
            system_prompt_path="",
            system_spec_key="report_refinement_system_prompt",
        )

    def _show_prompt_preview(
        self,
        *,
        title: str,
        prompt_path: str,
        system_prompt_path: str,
        prompt_spec_key: str | None = None,
        system_spec_key: str | None = None,
    ) -> None:
        manager = self._project_manager
        if not manager or not manager.project_dir:
            QMessageBox.warning(self._workspace, title, "Open a project first.")
            return

        system_template = self._read_prompt_file(system_prompt_path) if system_prompt_path else ""
        user_template = self._read_prompt_file(prompt_path) if prompt_path else ""

        selected_descriptors = [
            descriptor
            for descriptor in self._collect_report_inputs()
            if descriptor.key() in self._selected_inputs
        ]

        placeholder_values = build_report_preview_placeholders(
            project_manager=manager,
            metadata=manager.metadata,
            template_path=self._optional_path(self._tab.template_edit.text()),
            transcript_path=self._optional_path(self._tab.transcript_edit.text()),
            draft_path=self._optional_path(self._tab.refine_draft_edit.text()),
            selected_inputs=selected_descriptors,
        )

        values = placeholder_values
        system_rendered = format_prompt(system_template, values) if system_template else ""
        user_rendered = format_prompt(user_template, values) if user_template else ""

        required: set[str] = set()
        optional: set[str] = set()
        if system_spec_key:
            spec = get_prompt_spec(system_spec_key)
            if spec:
                required.update(spec.required)
                optional.update(spec.optional)
        if prompt_spec_key:
            spec = get_prompt_spec(prompt_spec_key)
            if spec:
                required.update(spec.required)
                optional.update(spec.optional)

        preview = PromptPreview(
            system_template=system_template,
            user_template=user_template,
            system_rendered=system_rendered,
            user_rendered=user_rendered,
            values=values,
            required=required,
            optional=optional,
        )

        dialog = PromptPreviewDialog(self._workspace)
        dialog.set_preview(preview)
        dialog.exec()

    def _read_prompt_file(self, path_str: str) -> str:
        path_str = (path_str or "").strip()
        if not path_str:
            return ""
        manager = self._project_manager
        if not manager or not manager.project_dir:
            return ""
        path = Path(path_str).expanduser()
        candidates: List[Path] = []
        if path.is_absolute():
            candidates.append(path)
        else:
            candidates.extend(
                [
                    Path(manager.project_dir) / path,
                    get_custom_dir() / path,
                    get_bundled_dir() / path,
                    get_repo_prompts_dir() / path,
                ]
            )
        for candidate in candidates:
            try:
                if candidate.exists():
                    return candidate.read_text(encoding="utf-8")
            except Exception:
                continue
        return ""

    # ------------------------------------------------------------------
    # Job orchestration
    # ------------------------------------------------------------------
    def _start_draft_job(self) -> None:
        if self._report_running:
            QMessageBox.information(
                self._workspace,
                "Report Generator",
                "A report run is already in progress.",
            )
            return

        manager = self._project_manager
        if not manager or not manager.project_dir:
            QMessageBox.warning(self._workspace, "Report Generator", "No project is currently loaded.")
            return

        if not self._validate_placeholders_before_run(include_generation=True, include_refinement=False):
            return

        provider_id, model_id, custom_model, context_window = self._resolve_model_selection()
        if provider_id is None:
            return

        template_path = self._validate_required_path(
            self._tab.template_edit.text(),
            "Report Generator",
            "Select a report template before generating a draft.",
        )
        if template_path is None:
            return

        gen_user_path = self._validate_prompt_path(
            self._tab.generation_user_prompt_edit.text(),
            "Report Generator",
            "Select a generation user prompt before generating a draft.",
            validator=validate_generation_prompt,
            reader=read_generation_prompt,
        )
        if gen_user_path is None:
            return

        gen_system_path = self._validate_required_path(
            self._tab.generation_system_prompt_edit.text(),
            "Report Generator",
            "Select a generation system prompt before generating a draft.",
        )
        if gen_system_path is None:
            return

        transcript_path = self._optional_path(self._tab.transcript_edit.text())
        if transcript_path and not transcript_path.is_file():
            QMessageBox.warning(
                self._workspace,
                "Report Generator",
                f"The selected transcript does not exist:\n{transcript_path}",
            )
            return

        selected_pairs = self._resolve_selected_inputs()
        if not selected_pairs and not transcript_path:
            QMessageBox.warning(
                self._workspace,
                "Report Generator",
                "Select at least one input or provide a transcript before generating a draft.",
            )
            return

        project_dir = Path(manager.project_dir)
        metadata = manager.metadata or ProjectMetadata(case_name=manager.project_name or "")

        self._save_preferences(
            provider_id=provider_id,
            model=model_id,
            custom_model=custom_model,
            context_window=context_window,
            template_path=template_path,
            transcript_path=transcript_path,
            generation_user_prompt=gen_user_path,
            refinement_user_prompt=self._optional_path(self._tab.refinement_user_prompt_edit.text()),
            generation_system_prompt=gen_system_path,
            refinement_system_prompt=self._optional_path(self._tab.refinement_system_prompt_edit.text()),
            refinement_draft=None,
        )

        config = ReportDraftJobConfig(
            project_dir=project_dir,
            inputs=selected_pairs,
            provider_id=provider_id,
            model=model_id,
            custom_model=custom_model,
            context_window=context_window,
            template_path=template_path,
            transcript_path=transcript_path,
            generation_user_prompt_path=gen_user_path,
            generation_system_prompt_path=gen_system_path,
            metadata=metadata,
            placeholder_values=manager.project_placeholder_values(),
            project_name=manager.project_name,
        )

        started = self._service.run_draft(
            config,
            on_started=self._on_report_started,
            on_progress=self._on_report_progress,
            on_log=self._append_report_log,
            on_finished=self._on_report_finished,
            on_failed=self._on_report_failed,
        )
        if not started:
            QMessageBox.information(
                self._workspace,
                "Report Generator",
                "A report run is already in progress. Please wait for it to finish.",
            )
            return

        self._active_run_kind = "draft"

    def _start_refinement_job(self) -> None:
        if self._report_running:
            QMessageBox.information(
                self._workspace,
                "Report Generator",
                "A report run is already in progress.",
            )
            return

        manager = self._project_manager
        if not manager or not manager.project_dir:
            QMessageBox.warning(self._workspace, "Report Generator", "No project is currently loaded.")
            return

        if not self._validate_placeholders_before_run(include_generation=False, include_refinement=True):
            return

        provider_id, model_id, custom_model, context_window = self._resolve_model_selection()
        if provider_id is None:
            return

        draft_path = self._validate_required_path(
            self._tab.refine_draft_edit.text(),
            "Report Generator",
            "Select an existing draft before running refinement.",
        )
        if draft_path is None:
            return

        template_path = self._optional_path(self._tab.template_edit.text())
        if template_path and not template_path.is_file():
            QMessageBox.warning(
                self._workspace,
                "Report Generator",
                f"The selected template does not exist:\n{template_path}",
            )
            return

        ref_user_path = self._validate_prompt_path(
            self._tab.refinement_user_prompt_edit.text(),
            "Report Generator",
            "Select a refinement user prompt before running refinement.",
            validator=validate_refinement_prompt,
            reader=read_refinement_prompt,
        )
        if ref_user_path is None:
            return

        ref_system_path = self._validate_required_path(
            self._tab.refinement_system_prompt_edit.text(),
            "Report Generator",
            "Select a refinement system prompt before running refinement.",
        )
        if ref_system_path is None:
            return

        transcript_path = self._optional_path(self._tab.transcript_edit.text())
        if transcript_path and not transcript_path.is_file():
            QMessageBox.warning(
                self._workspace,
                "Report Generator",
                f"The selected transcript does not exist:\n{transcript_path}",
            )
            return

        selected_pairs = self._resolve_selected_inputs()
        project_dir = Path(manager.project_dir)
        metadata = manager.metadata or ProjectMetadata(case_name=manager.project_name or "")

        self._save_preferences(
            provider_id=provider_id,
            model=model_id,
            custom_model=custom_model,
            context_window=context_window,
            template_path=template_path,
            transcript_path=transcript_path,
            generation_user_prompt=self._optional_path(self._tab.generation_user_prompt_edit.text()),
            refinement_user_prompt=ref_user_path,
            generation_system_prompt=self._optional_path(self._tab.generation_system_prompt_edit.text()),
            refinement_system_prompt=ref_system_path,
            refinement_draft=draft_path,
        )

        config = ReportRefinementJobConfig(
            project_dir=project_dir,
            draft_path=draft_path,
            inputs=selected_pairs,
            provider_id=provider_id,
            model=model_id,
            custom_model=custom_model,
            context_window=context_window,
            template_path=template_path,
            transcript_path=transcript_path,
            refinement_user_prompt_path=ref_user_path,
            refinement_system_prompt_path=ref_system_path,
            metadata=metadata,
            placeholder_values=manager.project_placeholder_values(),
            project_name=manager.project_name,
        )

        started = self._service.run_refinement(
            config,
            on_started=self._on_report_started,
            on_progress=self._on_report_progress,
            on_log=self._append_report_log,
            on_finished=self._on_report_finished,
            on_failed=self._on_report_failed,
        )
        if not started:
            QMessageBox.information(
                self._workspace,
                "Report Generator",
                "A report run is already in progress. Please wait for it to finish.",
            )
            return

        self._active_run_kind = "refinement"

    def _on_report_started(self) -> None:
        self._report_running = True
        self._last_result = None
        self._tab.progress_bar.setValue(0)
        self._tab.log_text.clear()
        self._update_report_controls()
        self._update_report_history_buttons()

    def _on_report_progress(self, percent: int, message: str) -> None:
        self._tab.progress_bar.setValue(percent)
        self._append_report_log(message)

    def _append_report_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._tab.log_text.append(f"[{timestamp}] {message}")

    def _on_report_finished(self, result: Dict[str, object]) -> None:
        self._report_running = False
        run_type = self._active_run_kind or str(result.get("run_type") or "draft")
        self._active_run_kind = None
        self._update_report_controls()
        self._tab.progress_bar.setValue(100)
        self._append_report_log("Report run completed successfully.")

        self._last_result = result
        self._persist_report_history(run_type, result)
        self._refresh_report_history()
        self._update_report_history_buttons()

    def _on_report_failed(self, message: str) -> None:
        self._report_running = False
        self._active_run_kind = None
        self._update_report_controls()
        self._update_report_history_buttons()
        QMessageBox.critical(self._workspace, "Report Generator", message)
        self._append_report_log(f"Error: {message}")

    # ------------------------------------------------------------------
    # History helpers
    # ------------------------------------------------------------------
    def _refresh_report_history(self) -> None:
        manager = self._project_manager
        history_list = self._tab.history_list
        history_list.blockSignals(True)
        history_list.clear()

        if not manager:
            history_list.blockSignals(False)
            return

        history = manager.report_state.history
        for index, entry in enumerate(history):
            try:
                timestamp_display = datetime.fromisoformat(entry.timestamp).astimezone().strftime("%Y-%m-%d %H:%M")
            except Exception:
                timestamp_display = entry.timestamp
            model_label = entry.custom_model or entry.model or ""
            filename = (
                Path(entry.refined_path).name
                if entry.refined_path
                else Path(entry.draft_path).name
            )
            run_label = (entry.run_type or "draft").replace("_", " ").title()
            outputs_text = f"{run_label}: {filename}"
            item = QTreeWidgetItem([timestamp_display, model_label, outputs_text])
            item.setData(0, Qt.UserRole, index)
            history_list.addTopLevelItem(item)

        if history and history_list.topLevelItemCount() > 0:
            history_list.setCurrentItem(history_list.topLevelItem(0))

        history_list.blockSignals(False)
        self._update_report_history_buttons()

    def _persist_report_history(self, run_type: str, result: Dict[str, object]) -> None:
        manager = self._project_manager
        if not manager:
            return

        timestamp_raw = str(result.get("timestamp"))
        try:
            timestamp = datetime.fromisoformat(timestamp_raw)
        except Exception:
            timestamp = datetime.now(timezone.utc)

        def _maybe_path(raw: object) -> Optional[Path]:
            if not raw:
                return None
            try:
                return Path(str(raw)).expanduser()
            except Exception:
                return None

        draft_path = _maybe_path(result.get("draft_path"))
        refined_path = _maybe_path(result.get("refined_path"))
        reasoning_path = _maybe_path(result.get("reasoning_path"))
        manifest_path = _maybe_path(result.get("manifest_path"))
        inputs_path = _maybe_path(result.get("inputs_path"))

        provider = str(result.get("provider", "anthropic"))
        model = str(result.get("model", ""))
        custom_model = result.get("custom_model")
        context_window = result.get("context_window")
        try:
            context_window_int = int(context_window) if context_window is not None else None
        except (ValueError, TypeError):
            context_window_int = None
        inputs = list(result.get("inputs", []))

        template_value = str(result.get("template_path") or "").strip() or None
        transcript_value = str(result.get("transcript_path") or "").strip() or None

        generation_user_prompt = str(result.get("generation_user_prompt") or "").strip() or None
        generation_system_prompt = str(result.get("generation_system_prompt") or "").strip() or None
        refinement_user_prompt = str(result.get("refinement_user_prompt") or "").strip() or None
        refinement_system_prompt = str(result.get("refinement_system_prompt") or "").strip() or None

        if run_type == "refinement" and refined_path is not None:
            manager.record_report_refinement_run(
                timestamp=timestamp,
                draft_path=(draft_path or refined_path),
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
                refinement_user_prompt=refinement_user_prompt,
                refinement_system_prompt=refinement_system_prompt,
                refined_tokens=result.get("refinement_tokens"),
            )
        else:
            if draft_path is None and result.get("draft_path"):
                draft_path = Path(str(result["draft_path"])).expanduser()
            if draft_path is None:
                return
            manager.record_report_draft_run(
                timestamp=timestamp,
                draft_path=draft_path,
                manifest_path=manifest_path,
                inputs_path=inputs_path,
                provider=provider,
                model=model,
                custom_model=str(custom_model) if custom_model else None,
                context_window=context_window_int,
                inputs=inputs,
                template_path=template_value,
                transcript_path=transcript_value,
                generation_user_prompt=generation_user_prompt,
                generation_system_prompt=generation_system_prompt,
                draft_tokens=result.get("draft_tokens"),
            )

    def _open_report_history_file(self, kind: str) -> None:
        selection = self._current_history_selection()
        if not selection:
            return

        path_map = {
            "draft": selection.draft_path,
            "refined": selection.refined_path,
            "reasoning": selection.reasoning_path,
            "manifest": selection.manifest_path,
            "inputs": selection.inputs_path,
        }
        target = path_map.get(kind)
        if not target:
            QMessageBox.information(self._workspace, "Report Outputs", "There is no file for this entry.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _current_history_selection(self) -> Optional[_HistorySelection]:
        manager = self._project_manager
        if not manager:
            return None
        item = self._tab.history_list.currentItem()
        if not item:
            return None
        index = item.data(0, Qt.UserRole)
        if index is None:
            return None
        try:
            entry = manager.report_state.history[int(index)]
        except (ValueError, TypeError, IndexError):
            return None
        return _HistorySelection(
            draft_path=Path(entry.draft_path) if entry.draft_path else None,
            refined_path=Path(entry.refined_path) if entry.refined_path else None,
            reasoning_path=Path(entry.reasoning_path) if entry.reasoning_path else None,
            manifest_path=Path(entry.manifest_path) if entry.manifest_path else None,
            inputs_path=Path(entry.inputs_path) if entry.inputs_path else None,
        )

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------
    def _open_reports_folder(self) -> None:
        manager = self._project_manager
        if not manager or not manager.project_dir:
            QMessageBox.information(self._workspace, "Reports", "Open a project first.")
            return
        folder = Path(manager.project_dir) / "reports"
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _ensure_default_prompts(self) -> None:
        if not self._tab.generation_user_prompt_edit.text().strip():
            default_generation = self._default_generation_user_prompt_path()
            if default_generation:
                self._tab.generation_user_prompt_edit.setText(default_generation)
        if not self._tab.generation_system_prompt_edit.text().strip():
            default_generation_system = self._default_generation_system_prompt_path()
            if default_generation_system:
                self._tab.generation_system_prompt_edit.setText(default_generation_system)
        if not self._tab.refinement_user_prompt_edit.text().strip():
            default_refinement = self._default_refinement_user_prompt_path()
            if default_refinement:
                self._tab.refinement_user_prompt_edit.setText(default_refinement)
        if not self._tab.refinement_system_prompt_edit.text().strip():
            default_refinement_system = self._default_refinement_system_prompt_path()
            if default_refinement_system:
                self._tab.refinement_system_prompt_edit.setText(default_refinement_system)

    def _default_generation_user_prompt_path(self) -> str:
        for candidate in (
            get_repo_prompts_dir() / "reports" / "default_generation_user.md",
            get_bundled_dir() / "reports" / "default_generation_user.md",
        ):
            if candidate.exists():
                return str(candidate)
        return ""

    def _default_generation_system_prompt_path(self) -> str:
        for candidate in (
            get_repo_prompts_dir() / "reports" / "default_generation_system.md",
            get_bundled_dir() / "reports" / "default_generation_system.md",
        ):
            if candidate.exists():
                return str(candidate)
        return ""

    def _default_refinement_user_prompt_path(self) -> str:
        for candidate in (
            get_repo_prompts_dir() / "reports" / "default_refinement_user.md",
            get_bundled_dir() / "reports" / "default_refinement_user.md",
        ):
            if candidate.exists():
                return str(candidate)
        return ""

    def _default_refinement_system_prompt_path(self) -> str:
        for candidate in (
            get_repo_prompts_dir() / "reports" / "default_refinement_system.md",
            get_bundled_dir() / "reports" / "default_refinement_system.md",
        ):
            if candidate.exists():
                return str(candidate)
        return ""

    def _safe_initial(self, provider) -> Path:
        try:
            return Path(provider())
        except Exception:
            return self._project_dir_or_home()

    def _project_dir_or_home(self) -> Path:
        manager = self._project_manager
        if manager and manager.project_dir:
            return Path(manager.project_dir)
        return Path.home()

    def _reset_view(self) -> None:
        self._tab.inputs_tree.clear()
        self._tab.history_list.clear()
        self._tab.log_text.clear()
        self._tab.progress_bar.setValue(0)
        self._tab.generate_draft_button.setEnabled(False)
        self._tab.run_refinement_button.setEnabled(False)
        self._tab.open_reports_button.setEnabled(False)
        self._tab.refine_draft_edit.clear()

    def _optional_path(self, value: str) -> Optional[Path]:
        value = value.strip()
        return Path(value).expanduser() if value else None

    def _validate_required_path(self, value: str, title: str, message: str) -> Optional[Path]:
        value = value.strip()
        if not value:
            QMessageBox.warning(self._workspace, title, message)
            return None
        path = Path(value).expanduser()
        if not path.is_file():
            QMessageBox.warning(self._workspace, title, f"The selected file does not exist:\n{path}")
            return None
        return path

    def _validate_prompt_path(
        self,
        value: str,
        title: str,
        message: str,
        *,
        validator,
        reader,
    ) -> Optional[Path]:
        path = self._validate_required_path(value, title, message)
        if path is None:
            return None
        try:
            content = reader(path)
            validator(content)
        except ValueError as exc:
            QMessageBox.warning(self._workspace, title, str(exc))
            return None
        except Exception:
            QMessageBox.warning(self._workspace, title, "Unable to read the selected prompt.")
            return None
        return path

    def _resolve_model_selection(self) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[int]]:
        data = self._tab.model_combo.currentData()
        if not data:
            return "anthropic", "claude-sonnet-4-5-20250929", None, None
        if data[0] != "custom":
            return data[0], data[1], None, None

        custom_model = self._tab.custom_model_edit.text().strip()
        if not custom_model:
            QMessageBox.warning(
                self._workspace,
                "Report Generator",
                "Enter a model id for the custom option.",
            )
            return None, None, None, None
        context_window = int(self._tab.custom_context_spin.value())
        return "custom", "", custom_model, context_window

    def _resolve_selected_inputs(self) -> List[tuple[str, str]]:
        selected_pairs: List[tuple[str, str]] = []
        for key in sorted(self._selected_inputs):
            if ":" not in key:
                continue
            category, relative = key.split(":", 1)
            selected_pairs.append((category, relative))
        return selected_pairs


__all__ = ["ReportsController"]
