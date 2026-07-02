"""Generated-artifact checks — structure, self-containment, accessibility.

The document is regenerated in-process (``generate.render()``), parsed with
``html.parser`` via the shared :class:`~atlas_tests.conftest.DocIndex`, and its
embedded JSON payload is compared against the data model record for record.
"""

from __future__ import annotations

import re

import pytest

import atlas_data as data
import generate

VIEW_KEYS = ("overview", "drives", "workstreams", "find", "calendar")
HEX_COLOR = re.compile(r"#[0-9a-f]{6}\Z")

#: Every element id the client script looks up must exist in the shell.
REQUIRED_IDS = (
    "nav",
    "view-overview", "view-drives", "view-workstreams",
    "view-find", "view-calendar",
    "ov-workstreams", "ov-drives", "ov-notes",
    "drive-rail", "folder-list", "drive-detail",
    "ws-tabs", "ws-meta", "ws-pipeline", "ws-stepdetail",
    "findbox", "findcount", "findrows", "nores",
    "cal-monthly", "cal-quarterly", "cal-annual",
)

DRIVE_PARAMS = [pytest.param(d, id=d.key) for d in data.DRIVES]
WS_PARAMS = [pytest.param(w, id=w.key) for w in data.WORKSTREAMS]
PALETTE_PARAMS = [pytest.param(k, v, id=k) for k, v in data.PALETTE.items()]
FINDIT_PARAMS = [
    pytest.param(i, id="row%02d" % (i + 1)) for i in range(len(data.FINDIT))
]


# ---------------------------------------------------------------------------
# Document shell
# ---------------------------------------------------------------------------

def test_document_declares_doctype_and_language(rendered: str) -> None:
    assert rendered.lstrip().startswith("<!DOCTYPE html>")
    assert '<html lang="en">' in rendered


def test_meta_charset_is_utf8(doc) -> None:
    charsets = [a.get("charset", "") for t, a in doc.tags if t == "meta"]
    assert any(c.lower() == "utf-8" for c in charsets)


def test_meta_viewport_present(doc) -> None:
    assert any(
        t == "meta" and a.get("name") == "viewport" and a.get("content")
        for t, a in doc.tags
    )


def test_meta_description_matches_model(doc) -> None:
    descriptions = [
        a.get("content") for t, a in doc.tags
        if t == "meta" and a.get("name") == "description"
    ]
    assert descriptions == [data.META["description"]]


def test_title_matches_model(doc) -> None:
    assert "".join(doc.title_text) == data.META["title"]


def test_tags_are_balanced(doc) -> None:
    assert doc.balance_errors == []
    assert doc.stack == [], "unclosed tags: %r" % doc.stack


def test_element_ids_are_unique(doc) -> None:
    duplicates = {i for i in doc.ids if doc.ids.count(i) > 1}
    assert not duplicates


@pytest.mark.parametrize("element_id", REQUIRED_IDS)
def test_required_container_present(doc, element_id: str) -> None:
    assert element_id in doc.ids


# ---------------------------------------------------------------------------
# Self-containment: one file, zero external resources
# ---------------------------------------------------------------------------

def test_no_src_or_href_attributes_anywhere(doc) -> None:
    offenders = [
        (t, a) for t, a in doc.tags
        if {"src", "href", "xlink:href"}.intersection(a)
    ]
    assert offenders == []


def test_no_external_resource_tags(doc) -> None:
    banned = {"link", "iframe", "object", "frame", "audio", "video", "img"}
    used = {t for t, _ in doc.tags}
    assert not banned.intersection(used)


def test_no_external_urls_in_document(rendered: str) -> None:
    lowered = rendered.lower()
    assert "http://" not in lowered
    assert "https://" not in lowered


def test_exactly_two_inline_scripts(doc) -> None:
    script_attrs = [a for t, a in doc.tags if t == "script"]
    assert len(script_attrs) == 2
    assert all("src" not in a for a in script_attrs)
    assert len(doc.scripts) == 2


def test_payload_script_never_closes_early() -> None:
    assert "</" not in generate.payload_json()


# ---------------------------------------------------------------------------
# Navigation and views
# ---------------------------------------------------------------------------

def test_nav_has_exactly_five_view_buttons(doc) -> None:
    views = [b.get("data-view") for b in doc.nav_buttons]
    assert views == list(VIEW_KEYS)


def test_exactly_one_nav_button_starts_active(doc) -> None:
    active = [b for b in doc.nav_buttons if "active" in b.get("class", "")]
    assert len(active) == 1
    assert active[0].get("data-view") == "overview"
    assert active[0].get("aria-current") == "page"


def test_five_view_sections(doc) -> None:
    view_sections = [
        s for s in doc.sections if "view" in s.get("class", "").split()
    ]
    assert len(view_sections) == len(VIEW_KEYS)


@pytest.mark.parametrize("view", VIEW_KEYS)
def test_view_has_section_with_label(doc, view: str) -> None:
    matches = [
        s for s in doc.sections if s.get("id") == "view-" + view
    ]
    assert len(matches) == 1
    assert "view" in matches[0].get("class", "").split()
    assert matches[0].get("aria-label", "").strip()


@pytest.mark.parametrize("view", VIEW_KEYS)
def test_view_has_nav_button(doc, view: str) -> None:
    matches = [b for b in doc.nav_buttons if b.get("data-view") == view]
    assert len(matches) == 1
    assert matches[0].get("type") == "button"


# ---------------------------------------------------------------------------
# Keyboard reachability / accessibility
# ---------------------------------------------------------------------------

def test_static_interactive_elements_are_buttons(doc) -> None:
    # Nothing in the shell relies on inline handlers or click-on-div.
    assert all(b.get("type") == "button" for b in doc.buttons)
    assert not any("tabindex" in a for _, a in doc.tags)


def test_no_inline_event_handler_attributes(doc) -> None:
    offenders = [
        (t, k) for t, a in doc.tags for k in a if k.startswith("on")
    ]
    assert offenders == []


def test_dynamic_interactive_elements_are_buttons(doc) -> None:
    app_js = doc.scripts[1]
    # Cards, drive rail, folders, tabs and steps are all real <button>s.
    assert app_js.count('createElement("button")') >= 4
    assert "addEventListener" in app_js


def test_dynamic_text_is_escaped_by_the_script(doc) -> None:
    app_js = doc.scripts[1]
    assert "function esc(" in app_js
    assert "&amp;" in app_js and "&lt;" in app_js


def test_search_input_is_labelled(doc) -> None:
    inputs = [a for t, a in doc.tags if t == "input"]
    assert any(a.get("id") == "findbox" for a in inputs)
    labels = [a for t, a in doc.tags if t == "label"]
    assert any(a.get("for") == "findbox" for a in labels)


def test_filter_result_counter_is_a_status_region(doc) -> None:
    assert any(
        a.get("role") == "status" and a.get("id") == "findcount"
        for _, a in doc.tags
    )


def test_reduced_motion_and_focus_styles_present(rendered: str) -> None:
    assert "prefers-reduced-motion" in rendered
    assert ":focus-visible" in rendered


def test_footer_carries_fictional_disclaimer(doc) -> None:
    footer = " ".join(doc.footer_text)
    assert "fictional" in footer.lower()
    assert "Sophon Finance Systems" in footer


# ---------------------------------------------------------------------------
# Palette tokens reach the stylesheet
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key,value", PALETTE_PARAMS)
def test_css_variable_binds_palette_token(rendered: str, key, value) -> None:
    assert "--%s:%s" % (key.replace("_", "-"), value) in rendered


# ---------------------------------------------------------------------------
# Embedded payload matches the data model exactly
# ---------------------------------------------------------------------------

def test_payload_top_level_shape(payload) -> None:
    assert set(payload) == {
        "tags", "notes", "drives", "workstreams", "findit", "calendar",
        "nores",
    }


def test_payload_tags_match_model(payload) -> None:
    assert payload["tags"] == data.META["tags"]


def test_payload_nores_matches_model(payload) -> None:
    assert payload["nores"] == data.META["find_nores"]


def test_payload_notes_match_model(payload) -> None:
    assert len(payload["notes"]) == len(data.META["notes"])
    for note, model in zip(payload["notes"], data.META["notes"]):
        assert note["title"] == model["title"]
        assert note["action"] == model["action"]
        assert note["kicker_color"] == data.PALETTE[model["kicker_color"]]


def test_payload_drive_count_matches_model(payload) -> None:
    assert len(payload["drives"]) == len(data.DRIVES)


@pytest.mark.parametrize("drive", DRIVE_PARAMS)
def test_payload_drive_matches_model(payload, drive) -> None:
    match = [d for d in payload["drives"] if d["key"] == drive.key]
    assert len(match) == 1
    rendered_drive = match[0]
    assert rendered_drive["label"] == drive.label
    assert rendered_drive["color"] == data.PALETTE[drive.color]
    assert len(rendered_drive["folders"]) == len(drive.folders)
    assert [f["name"] for f in rendered_drive["folders"]] == [
        f.name for f in drive.folders
    ]


@pytest.mark.parametrize("drive", DRIVE_PARAMS)
def test_payload_folder_briefings_complete(payload, drive) -> None:
    rendered_drive = [
        d for d in payload["drives"] if d["key"] == drive.key
    ][0]
    for rendered_folder, model_folder in zip(
        rendered_drive["folders"], drive.folders
    ):
        assert rendered_folder["tag"] == model_folder.tag
        assert rendered_folder["purpose"] == model_folder.purpose
        assert len(rendered_folder["keys"]) == len(model_folder.keys)
        assert len(rendered_folder["rows"]) == len(model_folder.rows)
        assert len(rendered_folder["tips"]) == len(model_folder.tips)


def test_payload_workstream_count_matches_model(payload) -> None:
    assert len(payload["workstreams"]) == len(data.WORKSTREAMS)


@pytest.mark.parametrize("ws", WS_PARAMS)
def test_payload_workstream_matches_model(payload, ws) -> None:
    match = [w for w in payload["workstreams"] if w["key"] == ws.key]
    assert len(match) == 1
    rendered_ws = match[0]
    assert rendered_ws["title"] == ws.title
    assert rendered_ws["kicker_color"] == data.PALETTE[ws.kicker_color]
    assert len(rendered_ws["meta"]) == len(ws.meta)
    assert len(rendered_ws["steps"]) == len(ws.steps)
    assert [s["name"] for s in rendered_ws["steps"]] == [
        s.name for s in ws.steps
    ]


@pytest.mark.parametrize("ws", WS_PARAMS)
def test_payload_step_io_complete(payload, ws) -> None:
    rendered_ws = [
        w for w in payload["workstreams"] if w["key"] == ws.key
    ][0]
    for rendered_step, model_step in zip(rendered_ws["steps"], ws.steps):
        assert rendered_step["detail"] == model_step.detail
        assert rendered_step["io"] == [list(r) for r in model_step.io]


def test_payload_findit_count_matches_model(payload) -> None:
    assert len(payload["findit"]) == len(data.FINDIT)


@pytest.mark.parametrize("index", FINDIT_PARAMS)
def test_payload_findit_row_matches_model(payload, index: int) -> None:
    assert payload["findit"][index] == list(data.FINDIT[index])


@pytest.mark.parametrize("bucket", ["monthly", "quarterly", "annual"])
def test_payload_calendar_bucket_matches_model(payload, bucket: str) -> None:
    assert payload["calendar"][bucket] == [
        list(row) for row in data.CALENDAR[bucket]
    ]
