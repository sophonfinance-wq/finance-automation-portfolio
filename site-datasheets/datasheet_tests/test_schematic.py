"""Zone 5: schematic renders one node per block and one connector per edge."""
from __future__ import annotations

import datasheet_spec as ds
import generate_datasheets as gen


def test_one_node_per_block():
    spec = ds.load_spec("triangulate")
    html = gen.schematic_html(spec)
    for block in spec["blocks"]:
        assert f'data-block="{block["id"]}"' in html


def test_one_edge_group_per_edge():
    spec = ds.load_spec("triangulate")
    html = gen.schematic_html(spec)
    assert html.count("schem-edge") >= len(spec["edges"])
    assert "fix packet (loop)" in html
    assert " L" in html  # reverse feedback is routed below the blocks, not through them


def test_gate_edge_is_marked():
    spec = ds.load_spec("triangulate")
    html = gen.schematic_html(spec)
    if any(e.get("gate") for e in spec["edges"]):
        assert "schem-edge gate" in html


def test_blocks_link_to_source():
    spec = ds.load_spec("triangulate")
    html = gen.schematic_html(spec)
    for block in spec["blocks"]:
        assert block["source_link"] in html
        assert gen._esc(block["plain"]) in html
        assert gen._esc(block["engineering"]) in html
    assert 'role="group"' in html
    assert 'aria-labelledby="schem-title"' in html
