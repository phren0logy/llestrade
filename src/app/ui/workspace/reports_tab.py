"""Presentation widget for the reports tab."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QTextEdit,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)


class ReportsTab(QWidget):
    """Encapsulate the UI elements used by the reports workflow."""

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.inputs_tree = QTreeWidget()
        self.inputs_tree.setColumnCount(2)
        self.inputs_tree.setHeaderLabels(["Input", "Project Path"])
        self.inputs_tree.setUniformRowHeights(True)
        self.inputs_tree.setSelectionMode(QTreeWidget.NoSelection)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(False)

        self.custom_model_label = QLabel("Custom model id:")
        self.custom_model_edit = QLineEdit()

        self.custom_context_label = QLabel("Context window:")
        self.custom_context_spin = QSpinBox()
        self.custom_context_spin.setRange(10_000, 400_000)
        self.custom_context_spin.setSingleStep(1_000)

        self.template_edit = QLineEdit()
        self.template_browse_button = QPushButton("Browse…")

        self.transcript_edit = QLineEdit()
        self.transcript_browse_button = QPushButton("Browse…")

        self.generation_user_prompt_edit = QLineEdit()
        self.generation_user_prompt_browse = QPushButton("Browse…")
        self.generation_user_prompt_preview = QPushButton("Preview generation prompt")

        self.generation_system_prompt_edit = QLineEdit()
        self.generation_system_prompt_browse = QPushButton("Browse…")
        self.generation_system_prompt_preview = QPushButton("Preview generation system prompt")

        self.refinement_user_prompt_edit = QLineEdit()
        self.refinement_user_prompt_browse = QPushButton("Browse…")
        self.refinement_user_prompt_preview = QPushButton("Preview refinement prompt")

        self.refinement_system_prompt_edit = QLineEdit()
        self.refinement_system_prompt_browse = QPushButton("Browse…")
        self.refinement_system_prompt_preview = QPushButton("Preview refinement system prompt")

        self.refine_draft_edit = QLineEdit()
        self.refine_draft_browse_button = QPushButton("Browse…")

        self.generate_draft_button = QPushButton("Generate Draft")
        self.run_refinement_button = QPushButton("Run Refinement")
        self.open_reports_button = QPushButton("Open Reports Folder")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(140)

        self.history_list = QTreeWidget()
        self.history_list.setColumnCount(3)
        self.history_list.setHeaderLabels(["Generated", "Model", "Outputs"])

        self.open_draft_button = QPushButton("Open Draft")
        self.open_refined_button = QPushButton("Open Refined")
        self.open_reasoning_button = QPushButton("Open Reasoning")
        self.open_manifest_button = QPushButton("Open Manifest")
        self.open_inputs_button = QPushButton("Open Inputs")

        self._build_layout()

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)

        inputs_group = QGroupBox("Select Inputs")
        inputs_layout = QVBoxLayout(inputs_group)
        inputs_layout.addWidget(self.inputs_tree)
        top_layout.addWidget(inputs_group, 1)

        config_group = QGroupBox("Configuration")
        config_layout = QVBoxLayout(config_group)
        config_layout.setSpacing(6)

        model_row = QHBoxLayout()
        model_row.setContentsMargins(0, 0, 0, 0)
        model_row.addWidget(QLabel("Model:"))
        model_row.addWidget(self.model_combo)
        config_layout.addLayout(model_row)

        custom_model_row = QHBoxLayout()
        custom_model_row.setContentsMargins(0, 0, 0, 0)
        custom_model_row.addWidget(self.custom_model_label)
        custom_model_row.addWidget(self.custom_model_edit)
        config_layout.addLayout(custom_model_row)

        context_row = QHBoxLayout()
        context_row.setContentsMargins(0, 0, 0, 0)
        context_row.addWidget(self.custom_context_label)
        context_row.addWidget(self.custom_context_spin)
        context_row.addWidget(QLabel("tokens"))
        config_layout.addLayout(context_row)

        template_label = QLabel("Template (required):")
        config_layout.addWidget(template_label)
        template_row = QHBoxLayout()
        template_row.setContentsMargins(0, 0, 0, 0)
        template_row.addWidget(self.template_edit)
        template_row.addWidget(self.template_browse_button)
        config_layout.addLayout(template_row)

        transcript_label = QLabel("Transcript (optional):")
        config_layout.addWidget(transcript_label)
        transcript_row = QHBoxLayout()
        transcript_row.setContentsMargins(0, 0, 0, 0)
        transcript_row.addWidget(self.transcript_edit)
        transcript_row.addWidget(self.transcript_browse_button)
        config_layout.addLayout(transcript_row)

        generation_user_label = QLabel("Generation user prompt:")
        config_layout.addWidget(generation_user_label)
        generation_user_row = QHBoxLayout()
        generation_user_row.setContentsMargins(0, 0, 0, 0)
        generation_user_row.addWidget(self.generation_user_prompt_edit)
        generation_user_row.addWidget(self.generation_user_prompt_browse)
        config_layout.addLayout(generation_user_row)
        config_layout.addWidget(self.generation_user_prompt_preview)

        generation_system_label = QLabel("Generation system prompt:")
        config_layout.addWidget(generation_system_label)
        generation_system_row = QHBoxLayout()
        generation_system_row.setContentsMargins(0, 0, 0, 0)
        generation_system_row.addWidget(self.generation_system_prompt_edit)
        generation_system_row.addWidget(self.generation_system_prompt_browse)
        config_layout.addLayout(generation_system_row)
        config_layout.addWidget(self.generation_system_prompt_preview)

        refinement_user_label = QLabel("Refinement user prompt:")
        config_layout.addWidget(refinement_user_label)
        refinement_user_row = QHBoxLayout()
        refinement_user_row.setContentsMargins(0, 0, 0, 0)
        refinement_user_row.addWidget(self.refinement_user_prompt_edit)
        refinement_user_row.addWidget(self.refinement_user_prompt_browse)
        config_layout.addLayout(refinement_user_row)
        config_layout.addWidget(self.refinement_user_prompt_preview)

        refinement_system_label = QLabel("Refinement system prompt:")
        config_layout.addWidget(refinement_system_label)
        refinement_system_row = QHBoxLayout()
        refinement_system_row.setContentsMargins(0, 0, 0, 0)
        refinement_system_row.addWidget(self.refinement_system_prompt_edit)
        refinement_system_row.addWidget(self.refinement_system_prompt_browse)
        config_layout.addLayout(refinement_system_row)
        config_layout.addWidget(self.refinement_system_prompt_preview)

        refinement_draft_label = QLabel("Existing draft for refinement:")
        config_layout.addWidget(refinement_draft_label)
        refinement_draft_row = QHBoxLayout()
        refinement_draft_row.setContentsMargins(0, 0, 0, 0)
        refinement_draft_row.addWidget(self.refine_draft_edit)
        refinement_draft_row.addWidget(self.refine_draft_browse_button)
        config_layout.addLayout(refinement_draft_row)

        top_layout.addWidget(config_group, 1)
        layout.addLayout(top_layout)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.addWidget(self.generate_draft_button)
        button_row.addWidget(self.run_refinement_button)
        button_row.addWidget(self.open_reports_button)
        button_row.addStretch()
        layout.addLayout(button_row)

        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_text)

        history_group = QGroupBox("Recent Reports")
        history_layout = QVBoxLayout(history_group)
        history_layout.addWidget(self.history_list)

        history_buttons = QHBoxLayout()
        history_buttons.addWidget(self.open_draft_button)
        history_buttons.addWidget(self.open_refined_button)
        history_buttons.addWidget(self.open_reasoning_button)
        history_buttons.addWidget(self.open_manifest_button)
        history_buttons.addWidget(self.open_inputs_button)
        history_buttons.addStretch()
        history_layout.addLayout(history_buttons)

        layout.addWidget(history_group)


__all__ = ["ReportsTab"]
