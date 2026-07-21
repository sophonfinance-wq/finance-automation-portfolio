"""Zone 2: die stack renders both representations and one focusable button per layer."""
from __future__ import annotations

import re

import datasheet_spec as ds
import generate_datasheets as gen


def test_static_svg_has_one_layer_group_per_layer():
    spec = ds.load_spec("triangulate")
    html = gen.die_stack_html(spec)
    assert 'class="die-svg"' in html
    groups = html.count('class="die-layer"')
    assert groups == len(spec["layers"]), (groups, len(spec["layers"]))


def test_static_svg_is_isometric_and_dimensional():
    """The hero reads as a 3-D exploded stack: each layer draws a top face AND a front
    face (two polygons), so it is genuinely dimensional, not a flat vertical list."""
    spec = ds.load_spec("triangulate")
    html = gen.die_stack_html(spec)
    assert html.count("<polygon") == 2 * len(spec["layers"])


def test_each_layer_has_a_focusable_button_in_dom_order():
    spec = ds.load_spec("triangulate")
    html = gen.die_stack_html(spec)
    buttons = re.findall(r'<button class="die-face"[^>]*data-layer="([^"]+)"', html)
    assert buttons == [layer["id"] for layer in spec["layers"]]
    assert html.count('aria-controls="die-panel"') == len(spec["layers"])
    assert html.count('aria-expanded="false"') == len(spec["layers"])


def test_both_representations_present():
    spec = ds.load_spec("triangulate")
    html = gen.die_stack_html(spec)
    assert 'class="die-svg"' in html   # static fallback
    assert 'class="die-3d"' in html    # interactive
    assert 'class="die-panel"' in html # info panel


def test_layer_copy_carries_source_links():
    spec = ds.load_spec("triangulate")
    html = gen.die_stack_html(spec)
    for layer in spec["layers"]:
        assert layer["source_link"] in html
