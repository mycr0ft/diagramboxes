#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for SysML v1 flow-port glyphs and item flows (Delligatti §3.4.1.5,
§4.8–4.9, Figures 4.4/4.7).

- Nonatomic flow port: small square with a literal ``< >`` symbol inside
  (typed by a flow specification; multiple item types).
- Atomic flow port: direction arrow inside the square (already supported).
- Item flow: a FILLED triangular arrowhead somewhere along the connector
  (default midpoint, positionable), with the item type as a halo label
  near it. The type must name a block, value type, or signal in the model.
"""

import re

from diagramboxes import Diagram, to_di, from_di, to_di_xmi, from_di_xmi


def _item_flow_diagram(item=None):
    d = Diagram()
    eps = d.add_node('eps : Electrical Power Subsystem', dashed=True)
    pc = d.add_node('primaryComputer : Flight Computer [1]')
    po = eps.add_port('dataOut', side='right', direction='nonatomic')
    pi = pc.add_port('dataIn', side='left', direction='nonatomic')
    kw = dict(source_port=po, target_port=pi, target_style=NONE_END())
    if item:
        kw['item_flow'] = item
    d.add_edge(eps, pc, **kw)
    return d


def NONE_END():
    from diagramboxes import NONE
    return NONE


def test_nonatomic_flow_port_renders_lt_gt_glyph():
    d = _item_flow_diagram()
    svg = d.render_svg()
    assert re.search(r'>&lt; &gt;</text>', svg) or '> < >'.replace(' ', '') in svg.replace(' ', ''), \
        "nonatomic flow port square must contain the '< >' symbol"
    txt = d.render()
    assert '< >' in txt


def test_item_flow_adds_filled_arrowhead_and_halo_label_mid_route():
    without = _item_flow_diagram().render_svg()
    with_flow = _item_flow_diagram('° C').render_svg()
    assert 'fill="black"' not in without, \
        "no filled black arrowhead without an item flow"
    assert 'fill="black"' in with_flow, \
        "item flow renders as a filled-in triangular arrowhead"
    m = re.search(r'<g>\s*<rect class="halo"[^>]*/>\s*<text[^>]*>\s*° C\s*</text>\s*</g>',
                  with_flow)
    assert m, "item-flow type label renders in a halo group near the arrowhead"


def test_item_flow_position_controllable():
    d = Diagram()
    a = d.add_node('A', ['block'])
    b = d.add_node('B', ['block'])
    d.add_edge(a, b, item_flow='Power', item_position=0.25)
    # must render without error; positions are covered by the svg content
    svg = d.render_svg()
    assert 'Power' in svg
    d.render()


def test_item_flow_preserved_in_di_round_trip():
    d = Diagram()
    a = d.add_node('A', ['block'])
    b = d.add_node('B', ['block'])
    d.add_edge(a, b, item_flow='° C', item_position=0.4)
    d2 = from_di(to_di(d))
    e2 = d2.edges[0]
    assert e2.item_flow == '° C'
    assert e2.item_position == 0.4


def test_item_flow_preserved_in_xmi_round_trip():
    d = Diagram()
    a = d.add_node('A', ['block'])
    b = d.add_node('B', ['block'])
    d.add_edge(a, b, item_flow='° C')
    xml = to_di_xmi(to_di(d))
    d2 = from_di(from_di_xmi(xml))
    assert d2.edges[0].item_flow == '° C'


def test_port_to_port_bypass_clears_both_boxes():
    """When a wrap-around bypass routes through the band between two
    vertically stacked boxes (wide band), its horizontal leg must keep
    clearance from BOTH boxes — not hug an adjacent box's edge
    (Figure 4.7 fidelity finding: the ° C halo grazed the eps box)."""
    d = Diagram()
    eps = d.add_node('eps : Electrical Power Subsystem', dashed=True)
    pc = d.add_node('primaryComputer : Flight Computer [1]')
    po = eps.add_port('x', side='right', direction='nonatomic')
    pi = pc.add_port('', side='left', direction='nonatomic')
    d.add_edge(eps, pc, source_port=po, target_port=pi)
    d.layout(routing='orthogonal')
    src_bottom = eps.y + eps.h
    tgt_top = pc.y
    if tgt_top - src_bottom > 24:  # wide band: the bypass must respect it
        for (x1, y1), (x2, y2) in zip(e_waypoints(d), e_waypoints(d)[1:]):
            if x1 != x2 and abs(x2 - x1) > 20:  # horizontal leg
                assert y1 >= src_bottom + 6 and y1 <= tgt_top - 6, \
                    f"bypass leg y={y1} hugs a box (band {src_bottom}..{tgt_top})"


def e_waypoints(d):
    return d.edges[0].waypoints