"""Zone 5: schematic renders one node per block and one connector per edge."""
from __future__ import annotations

import generate_datasheets as gen
import datasheet_spec as ds


def test_one_node_per_block():
    spec = ds.load_spec("triangulate")
    html = gen.schematic_html(spec)
    for block in spec["blocks"]:
        assert 'data-block="%s"' % block["id"] in html


def test_one_edge_group_per_edge():
    spec = ds.load_spec("triangulate")
    html = gen.schematic_html(spec)
    assert html.count("schem-edge") >= len(spec["edges"])


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
