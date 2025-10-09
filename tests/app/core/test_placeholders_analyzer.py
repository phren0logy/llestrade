from __future__ import annotations

from src.app.core.placeholders.analyzer import (
    analyse_prompts,
    highlight_placeholders_raw,
    render_preview_html,
)


def test_analyse_prompts_tracks_missing_required_and_optional() -> None:
    analysis = analyse_prompts(
        system_template="System uses {project_name}",
        user_template="User needs {custom_value} and {optional_note}",
        available_values={"project_name": "Case A", "custom_value": ""},
        required_keys={"project_name", "custom_value"},
        optional_keys={"optional_note"},
    )

    assert analysis.used == {"project_name", "custom_value", "optional_note"}
    assert analysis.missing_required == {"custom_value"}
    assert analysis.missing_optional == {"optional_note"}


def test_highlight_placeholders_raw_marks_missing_required() -> None:
    html = highlight_placeholders_raw(
        "Prompt {foo} {bar}",
        values={"foo": "value", "bar": ""},
        required={"foo", "bar"},
    )
    assert '<span class="placeholder ok required">{foo}</span>' in html
    assert '<span class="placeholder missing required">{bar}</span>' in html


def test_render_preview_html_inserts_values_or_blank() -> None:
    html = render_preview_html(
        "Preview {foo} {bar}",
        values={"foo": "VALUE", "bar": ""},
        required={"foo", "bar"},
    )
    assert '<span class="placeholder ok required">VALUE</span>' in html
    assert (
        '<span class="placeholder missing required">&nbsp;</span>' in html
        or '<span class="placeholder missing required"></span>' in html
    )
