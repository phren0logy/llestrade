from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.app.core.project_manager import ProjectManager, ProjectMetadata, ProjectPlaceholders


def test_project_placeholder_mapping_includes_system_values(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    manager = ProjectManager()
    manager.project_dir = project_dir
    manager.project_path = project_dir / "project.frpd"
    manager.metadata = ProjectMetadata(case_name="Sample Case")
    manager.placeholders = ProjectPlaceholders()
    manager.placeholders.set_value("client_name", "ACME")
    manager.placeholders.set_value("case_number", "2024-001")
    manager._ensure_system_placeholders(manager.metadata.case_name)

    mapping = manager.placeholder_mapping()
    assert mapping["client_name"] == "ACME"
    assert mapping["case_number"] == "2024-001"
    assert mapping["project_name"] == "Sample Case"
    assert mapping["timestamp"]
    assert "source_pdf_filename" in mapping


def test_project_placeholder_values_excludes_system_keys(tmp_path: Path) -> None:
    manager = ProjectManager()
    manager.placeholders.set_value("client", "ACME")
    manager._ensure_system_placeholders("Case Name")

    values = manager.project_placeholder_values()
    assert values == {"client": "ACME"}
