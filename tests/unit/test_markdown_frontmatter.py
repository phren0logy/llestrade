from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import frontmatter

from src.common.markdown import (
    PromptReference,
    SourceReference,
    apply_frontmatter,
    build_document_metadata,
    compute_file_checksum,
    infer_project_path,
)


def test_build_metadata_and_apply_frontmatter(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    source_path = project_dir / "converted_documents" / "sample.md"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("# Sample\nBody\n", encoding="utf-8")

    checksum = compute_file_checksum(source_path)
    metadata = build_document_metadata(
        project_path=project_dir,
        generator="unit-test",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        sources=[
            SourceReference(
                path=source_path,
                relative="converted_documents/sample.md",
                kind="md",
                role="input",
                checksum=checksum,
            )
        ],
        prompts=[PromptReference(identifier="prompt-id", role="user")],
        extra={"custom": "value"},
    )

    result = apply_frontmatter("Report body", metadata, merge_existing=False)
    post = frontmatter.loads(result)

    assert post.metadata["generator"] == "unit-test"
    assert post.metadata["project_path"].endswith("project")
    assert post.metadata["sources"][0]["checksum"] == checksum
    assert post.metadata["prompts"][0]["id"] == "prompt-id"
    assert post.metadata["custom"] == "value"
    assert post.content == "Report body"


def test_apply_frontmatter_merges_existing_metadata() -> None:
    original = "---\ngenerator: old\nretain: yes\n---\n\nBody"
    updated = apply_frontmatter(original, {"generator": "new", "extra": True})
    post = frontmatter.loads(updated)

    assert post.metadata["generator"] == "new"
    assert post.metadata["retain"] is True
    assert post.metadata["extra"] is True
    assert post.content == "Body"


def test_infer_project_path(tmp_path: Path) -> None:
    project_dir = tmp_path / "case"
    file_path = project_dir / "converted_documents" / "alpha.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("content", encoding="utf-8")

    inferred = infer_project_path(file_path)
    assert inferred is not None
    assert inferred.resolve() == project_dir.resolve()
