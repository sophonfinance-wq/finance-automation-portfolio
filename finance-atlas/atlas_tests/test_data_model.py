"""Data-model integrity — every record the atlas renders is complete.

Each drive, folder briefing, workstream step, Find-It row, calendar event,
chip, note, legend entry and palette token is checked individually, so a
single incomplete record fails as exactly one test.
"""

from __future__ import annotations

import re

import pytest

import atlas_data as data

ALLOWED_TAGS = {"live", "ref", "archive", "secure"}
VIEW_KEYS = {"overview", "drives", "workstreams", "find", "calendar"}
HEX_COLOR = re.compile(r"#[0-9a-f]{6}\Z")
FICTIONAL_DRIVE_PREFIXES = ("G:\\", "W:\\", "L:\\", "R:\\")


def _slug(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "-", text).strip("-")[:40] or "x"


def _nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


DRIVE_PARAMS = [pytest.param(d, id=d.key) for d in data.DRIVES]
FOLDER_PARAMS = [
    pytest.param(d, f, id="%s-%s" % (d.key, _slug(f.name)))
    for d in data.DRIVES
    for f in d.folders
]
WS_PARAMS = [pytest.param(w, id=w.key) for w in data.WORKSTREAMS]
STEP_PARAMS = [
    pytest.param(w, s, id="%s-step%d-%s" % (w.key, i + 1, _slug(s.name)))
    for w in data.WORKSTREAMS
    for i, s in enumerate(w.steps)
]
FINDIT_PARAMS = [
    pytest.param(row, id="%02d-%s" % (i + 1, _slug(row[0])))
    for i, row in enumerate(data.FINDIT)
]
CAL_PARAMS = [
    pytest.param(bucket, row, id="%s-%d-%s" % (bucket, i + 1, _slug(row[1])))
    for bucket, rows in data.CALENDAR.items()
    for i, row in enumerate(rows)
]
PALETTE_PARAMS = [pytest.param(k, v, id=k) for k, v in data.PALETTE.items()]
CHIP_PARAMS = [
    pytest.param(chip, id="chip%d-%s" % (i + 1, _slug(chip[1])))
    for i, chip in enumerate(data.META["chips"])
]
NOTE_PARAMS = [
    pytest.param(note, id="note%d-%s" % (i + 1, _slug(note["title"])))
    for i, note in enumerate(data.META["notes"])
]
LEGEND_PARAMS = [
    pytest.param(entry, id="legend%d-%s" % (i + 1, _slug(entry[1])))
    for i, entry in enumerate(data.META["legend"])
]


# ---------------------------------------------------------------------------
# Folder briefings
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("drive,folder", FOLDER_PARAMS)
def test_folder_identity_fields(drive, folder) -> None:
    assert _nonempty_str(folder.name)
    assert _nonempty_str(folder.desc)
    assert _nonempty_str(folder.purpose)


@pytest.mark.parametrize("drive,folder", FOLDER_PARAMS)
def test_folder_tag_is_allowed_and_labelled(drive, folder) -> None:
    assert folder.tag in ALLOWED_TAGS
    assert folder.tag in data.META["tags"], "tag must have a display label"


@pytest.mark.parametrize("drive,folder", FOLDER_PARAMS)
def test_folder_has_key_locations(drive, folder) -> None:
    assert folder.keys, "every briefing lists at least one key location"
    assert all(_nonempty_str(k) for k in folder.keys)


@pytest.mark.parametrize("drive,folder", FOLDER_PARAMS)
def test_folder_has_working_notes(drive, folder) -> None:
    assert folder.tips, "every briefing carries at least one working note"
    assert all(_nonempty_str(t) for t in folder.tips)


@pytest.mark.parametrize("drive,folder", FOLDER_PARAMS)
def test_folder_briefing_rows_wellformed(drive, folder) -> None:
    for row in folder.rows:
        assert len(row) == 2
        assert _nonempty_str(row[0]) and _nonempty_str(row[1])


# ---------------------------------------------------------------------------
# Drives
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("drive", DRIVE_PARAMS)
def test_drive_identity(drive) -> None:
    assert _nonempty_str(drive.key)
    assert _nonempty_str(drive.label)
    assert _nonempty_str(drive.sub)
    assert drive.color in data.PALETTE


@pytest.mark.parametrize("drive", DRIVE_PARAMS)
def test_drive_has_folders(drive) -> None:
    # The client script selects folders[0] on drive selection.
    assert len(drive.folders) >= 1


@pytest.mark.parametrize("drive", DRIVE_PARAMS)
def test_drive_folder_names_unique(drive) -> None:
    names = [f.name for f in drive.folders]
    assert len(names) == len(set(names))


def test_drive_keys_unique() -> None:
    keys = [d.key for d in data.DRIVES]
    assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# Workstreams and steps
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ws", WS_PARAMS)
def test_workstream_identity(ws) -> None:
    assert _nonempty_str(ws.key)
    assert _nonempty_str(ws.title)
    assert _nonempty_str(ws.kicker)
    assert _nonempty_str(ws.blurb)
    assert ws.kicker_color in data.PALETTE


@pytest.mark.parametrize("ws", WS_PARAMS)
def test_workstream_meta_present(ws) -> None:
    assert ws.meta, "every workstream shows header facts"
    for row in ws.meta:
        assert len(row) == 2
        assert _nonempty_str(row[0]) and _nonempty_str(row[1])


@pytest.mark.parametrize("ws", WS_PARAMS)
def test_workstream_has_pipeline(ws) -> None:
    assert len(ws.steps) >= 3, "a pipeline needs at least three steps"


def test_workstream_keys_unique() -> None:
    keys = [w.key for w in data.WORKSTREAMS]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("ws,step", STEP_PARAMS)
def test_step_name_and_detail(ws, step) -> None:
    assert _nonempty_str(step.name)
    assert _nonempty_str(step.detail)


@pytest.mark.parametrize("ws,step", STEP_PARAMS)
def test_step_io_rows_nonempty(ws, step) -> None:
    assert step.io, "every step shows at least one input/output row"
    for row in step.io:
        assert len(row) == 2
        assert _nonempty_str(row[0]) and _nonempty_str(row[1])


# ---------------------------------------------------------------------------
# Find It
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("row", FINDIT_PARAMS)
def test_findit_row_has_four_nonempty_fields(row) -> None:
    assert len(row) == 4
    assert all(_nonempty_str(field) for field in row)


@pytest.mark.parametrize("row", FINDIT_PARAMS)
def test_findit_location_is_a_fictional_drive_path(row) -> None:
    assert row[1].startswith(FICTIONAL_DRIVE_PREFIXES), row[1]


def test_findit_needs_are_unique() -> None:
    needs = [row[0] for row in data.FINDIT]
    assert len(needs) == len(set(needs))


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bucket,event", CAL_PARAMS)
def test_calendar_event_has_when_what_detail(bucket, event) -> None:
    assert len(event) == 3
    assert all(_nonempty_str(field) for field in event)


def test_calendar_buckets_are_the_three_cadences() -> None:
    assert set(data.CALENDAR) == {"monthly", "quarterly", "annual"}
    for rows in data.CALENDAR.values():
        assert rows, "every cadence column shows at least one event"


# ---------------------------------------------------------------------------
# Palette, chips, notes, legend, page metadata
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key,value", PALETTE_PARAMS)
def test_palette_value_is_lowercase_hex(key, value) -> None:
    assert HEX_COLOR.match(value), "%s=%r" % (key, value)


@pytest.mark.parametrize("chip", CHIP_PARAMS)
def test_chip_wellformed(chip) -> None:
    assert len(chip) == 2
    assert _nonempty_str(chip[0]) and _nonempty_str(chip[1])


@pytest.mark.parametrize("note", NOTE_PARAMS)
def test_note_wellformed_and_action_resolves(note) -> None:
    assert _nonempty_str(note["kicker"])
    assert _nonempty_str(note["title"])
    assert _nonempty_str(note["text"])
    assert note["kicker_color"] in data.PALETTE
    action = note["action"]
    assert action["view"] in VIEW_KEYS
    if "drive" in action:
        drive = {d.key: d for d in data.DRIVES}[action["drive"]]
        if "folder" in action:
            assert action["folder"] in {f.name for f in drive.folders}


@pytest.mark.parametrize("entry", LEGEND_PARAMS)
def test_legend_color_resolves(entry) -> None:
    color_key, label = entry
    assert color_key in data.PALETTE
    assert _nonempty_str(label)


def test_meta_page_strings_present() -> None:
    for key in (
        "title", "description", "wordmark_main", "wordmark_sub", "h1",
        "hero_heading", "hero_text", "hint", "find_placeholder",
        "find_nores", "footer_left", "footer_right",
    ):
        assert _nonempty_str(data.META[key]), key


def test_wordmark_is_the_brand() -> None:
    assert data.META["wordmark_main"] == "SOPHON FINANCE SYSTEMS"


def test_footer_carries_fictional_disclaimer() -> None:
    assert "fictional" in str(data.META["footer_left"]).lower()


def test_title_is_marked_as_demonstration() -> None:
    assert "demonstration" in str(data.META["title"]).lower()


def test_tags_mapping_covers_exactly_the_allowed_set() -> None:
    assert set(data.META["tags"]) == ALLOWED_TAGS
    for label in data.META["tags"].values():
        assert _nonempty_str(label)


def test_regions_are_the_fictional_three() -> None:
    joined = " ".join(row[1] for w in data.WORKSTREAMS for row in w.meta)
    for region in ("Northwest", "Southwest", "Central"):
        assert region in joined


# ---------------------------------------------------------------------------
# Advertised scope: the README's counts match the data model
# ---------------------------------------------------------------------------

def test_model_shape_counts() -> None:
    assert len(data.DRIVES) == 5
    assert sum(len(d.folders) for d in data.DRIVES) == 14
    assert len(data.WORKSTREAMS) == 4
    assert sum(len(w.steps) for w in data.WORKSTREAMS) == 24
    assert len(data.FINDIT) == 33
    assert sum(len(rows) for rows in data.CALENDAR.values()) == 16


def test_readme_advertises_model_counts(readme_text: str) -> None:
    folders = sum(len(d.folders) for d in data.DRIVES)
    events = sum(len(rows) for rows in data.CALENDAR.values())
    assert "%d folder briefings" % folders in readme_text
    assert "(%d rows)" % len(data.FINDIT) in readme_text
    assert "(%d events)" % events in readme_text
