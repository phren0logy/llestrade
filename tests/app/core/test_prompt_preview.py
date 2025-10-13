from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import frontmatter

from src.app.core.bulk_analysis_groups import BulkAnalysisGroup
from src.app.core.project_manager import ProjectMetadata
from src.app.core.prompt_preview import generate_prompt_preview


def _write_converted_doc(path: Path, *, pdf_path: Path, content: str = "Document body") -> None:
    metadata = {
        "sources": [
            {
                "path": pdf_path.as_posix(),
                "relative": pdf_path.name,
                "kind": "pdf",
            }
        ]
    }
    post = frontmatter.Post(content, metadata=metadata)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def test_prompt_preview_populates_source_placeholders(tmp_path: Path) -> None:
    project_dir = tmp_path
    converted_dir = project_dir / "converted_documents"
    converted_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = project_dir / "sources" / "sample with space.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_text("pdf data", encoding="utf-8")

    converted_doc = converted_dir / "sample.md"
    _write_converted_doc(converted_doc, pdf_path=pdf_path, content="# Heading\nBody")

    group = BulkAnalysisGroup.create("Preview Group", files=["sample.md"])
    metadata = ProjectMetadata(case_name="Case Name")

    preview = generate_prompt_preview(
        project_dir,
        group,
        metadata=metadata,
        placeholder_values={},
        max_content_lines=5,
    )

    expected_url = quote(pdf_path.resolve().as_posix(), safe="/:")

    assert preview.values["source_pdf_absolute_url"] == expected_url
    assert preview.values["source_pdf_absolute_path"] == pdf_path.resolve().as_posix()
    assert preview.values["source_pdf_filename"] == pdf_path.name
    assert "Heading" in preview.values["document_content"]
    # Preview content should include actual document body
    assert "Body" in preview.user_rendered


def test_prompt_preview_combined_includes_reduce_context(tmp_path: Path) -> None:
    project_dir = tmp_path
    converted_dir = project_dir / "converted_documents"
    converted_dir.mkdir(parents=True, exist_ok=True)

    pdf_a = project_dir / "sources" / "a.pdf"
    pdf_b = project_dir / "sources" / "b.pdf"
    pdf_a.parent.mkdir(parents=True, exist_ok=True)
    pdf_a.write_text("pdf", encoding="utf-8")
    pdf_b.write_text("pdf", encoding="utf-8")

    doc_a = converted_dir / "folder" / "a.md"
    doc_a.parent.mkdir(parents=True, exist_ok=True)
    _write_converted_doc(doc_a, pdf_path=pdf_a, content="Content A")

    doc_b = converted_dir / "folder" / "b.md"
    _write_converted_doc(doc_b, pdf_path=pdf_b, content="Content B")

    group = BulkAnalysisGroup.create("Combined Group")
    group.operation = "combined"
    group.combine_converted_files = ["folder/a.md", "folder/b.md"]

    preview = generate_prompt_preview(
        project_dir,
        group,
        metadata=ProjectMetadata(case_name="Combined Case"),
        placeholder_values={},
        max_content_lines=5,
    )

    assert preview.values["reduce_source_count"] == "2"
    reduce_list = preview.values["reduce_source_list"]
    assert "a.pdf" in reduce_list
    assert "b.pdf" in reduce_list
    from urllib.parse import quote

    expected_first_url = quote(pdf_a.resolve().as_posix(), safe="/:")
    assert preview.values["source_pdf_absolute_url"] == expected_first_url
