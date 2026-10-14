#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for frame ports (SysML v1, Delligatti §4.8, Figure 4.6): ports
placed on the diagram-kind frame's border (the IBD header block's
boundary), possibly carrying interface symbols, and connected to
internal parts. Also covers DI/XMI round-trip of the frame itself.
"""

import re

from diagramboxes import (Diagram, Port, OPEN, to_di, from_di, to_di_xmi,
                          from_di_xmi, PORT_W)


def _framed():
    d = Diagram()
    d.add_frame('ibd', element_kind='block',
                element_name='DellSat-77 Satellite',
                diagram_name='Services View')
    eps = d.add_node('eps : Electrical Power Subsystem')
    fp = d.add_frame_port('solarPanel', side='left', offset=0.5)
    fp.add_interface('Light Source', kind='required')
    return d, eps, fp


def test_frame_port_straddles_frame_border():
    d, eps, fp = _framed()
    d.layout(routing='orthogonal')
    d._place_frame_ports()
    x1, y1, x2, y2 = d._frame_rect()
    # frame port half in, half out of the border (straddles)
    assert abs(fp.x + PORT_W // 2 - x1) < 2
    assert y1 < fp.y < y2, "frame port sits along the frame side"


def test_edge_from_frame_port_to_internal_part():
    d = Diagram()
    d.add_frame('ibd', element_kind='block',
                element_name='DellSat-77 Satellite', diagram_name='Services View')
    eps = d.add_node('eps : Electrical Power Subsystem')
    fp = d.add_frame_port('solarPanel', side='left', offset=0.5)
    d.add_edge(eps, eps, source_port=fp, target_style=OPEN)
    d.render(routing='orthogonal')   # braille smoke: routes after placement
    svg = d.render_svg(routing='orthogonal')
    assert 'solarPanel' in svg
    assert svg.count('<polyline') >= 1, "frame-port edge connects after placement"


def test_frame_port_with_interface_renders():
    d, eps, fp = _framed()
    svg = d.render_svg(routing='orthogonal')
    assert 'Light Source' in svg
    assert re.search(r'<polyline[^>]*class="arc"[^>]*/>', svg), \
        "required-interface socket on the frame port"


def test_svg_viewbox_never_clips_negative_origin_content():
    """Vision review of Figure 4.6 (3/10): the viewBox anchors at fixed
    (-pad, -pad) and clipped the frame header/ports when frame ports and
    interface arcs pushed content into negative coordinates."""
    d, eps, fp = _framed()
    svg = d.render_svg(routing='orthogonal')
    m = re.search(r'viewBox="(-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)"', svg)
    assert m, svg
    vx, vy, vw, vh = (float(g) for g in m.groups())
    ys = [float(g) for g in re.findall(r'<(?:rect|line|polyline|text)[^>]*?\by="(-?[\d.]+)"', svg)]
    ys += [float(g) for g in re.findall(r'<(?:rect|text)[^>]*?\bx="(-?[\d.]+)"', svg)]
    # every drawn coordinate must be inside the viewBox
    assert all(vy <= y <= vy + vh and vx <= x <= vx + vw
               for y, x in zip(ys[::2], ys[1::2])), \
        "drawn content falls outside the viewBox"


def test_frame_port_label_flips_to_frame_interior():
    """Vision round 3 (Figure 4.6): the port name belongs on the frame's
    interior side so it never collides with the outward interface
    label/arc (book: 'solarPanel [2]' inside, 'Light Source' outside)."""
    d, eps, fp = _framed()
    svg = d.render_svg(routing='orthogonal')
    prect = re.search(r'<rect x="(-?[\d.]+)" y="(-?[\d.]+)" '
                      r'width="[\d.]+" height="[\d.]+" fill="white"', svg)
    assert prect, svg
    px = float(prect.group(1))
    lm = re.search(r'<text x="(-?[\d.]+)" [^>]*anchor="(?:start|end|middle)"[^>]*>solarPanel', svg)
    assert lm, svg
    lx = float(lm.group(1))
    assert lx > px, f"port label '{lx}' must sit inside the frame (right of box at {px})"
    ifm = re.search(r'<text x="(-?[\d.]+)"[^>]*>Light Source</text>', svg)
    assert ifm, svg
    assert float(ifm.group(1)) < px, \
        "interface label stays on the outward (left) side"


def test_frame_and_frame_ports_survive_di_round_trip():
    d, eps, fp = _framed()
    d2 = from_di(to_di(d))
    assert d2.frame is not None
    assert d2.frame.kind == 'ibd'
    assert d2.frame.element_name == 'DellSat-77 Satellite'
    assert len(d2.frame_ports) == 1
    fp2 = d2.frame_ports[0]
    assert fp2.label == 'solarPanel'
    assert [(i.name, i.kind) for i in fp2.interfaces] == \
        [('Light Source', 'required')]


def test_frame_survives_xmi_round_trip():
    d, eps, fp = _framed()
    d2 = from_di(from_di_xmi(to_di_xmi(to_di(d))))
    assert d2.frame is not None
    assert d2.frame.kind == 'ibd'
    assert len(d2.frame_ports) == 1