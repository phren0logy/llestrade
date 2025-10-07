from __future__ import annotations

from pathlib import Path

from src.app.core.bulk_analysis_groups import BulkAnalysisGroup
from src.app.core.project_manager import ProjectManager


def test_prune_bulk_analysis_groups_removes_missing_entries(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "bulk_analysis").mkdir()

    manager = ProjectManager()
    manager.project_dir = project_dir
    manager.project_path = project_dir / "project.frpd"
    manager.bulk_analysis_groups = {}

    group = BulkAnalysisGroup.create(
        "Legal Docs",
        files=["documents/doc.md"],
        directories=["documents"],
    )
    group.operation = "combined"
    group.combine_converted_files = ["documents/doc.md"]
    group.combine_converted_directories = ["documents"]
    group.combine_map_files = ["legal/docs/documents/doc_analysis.md"]
    group.combine_map_directories = ["legal/documents"]

    saved = manager.save_bulk_analysis_group(group)

    outputs_dir = (
        project_dir
        / "bulk_analysis"
        / saved.folder_name
        / "outputs"
        / "legal"
        / "documents"
    )
    outputs_dir.mkdir(parents=True)
    (outputs_dir / "doc_analysis.md").write_text("content", encoding="utf-8")

    # No converted documents or highlights exist; group references should be pruned.
    manager.prune_bulk_analysis_groups(missing_directories=["documents"])

    reloaded_groups = manager.refresh_bulk_analysis_groups()
    assert len(reloaded_groups) == 1
    reloaded = reloaded_groups[0]
    assert reloaded.directories == []
    assert reloaded.files == []
    assert reloaded.combine_converted_files == []
    assert reloaded.combine_converted_directories == []
    assert reloaded.combine_map_files == []
    assert reloaded.combine_map_directories == []
