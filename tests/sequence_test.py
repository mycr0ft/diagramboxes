#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for sequence-diagram notation (SysML v1, Delligatti §7.4–7.7):
lifelines (head rectangle + dashed tail), the four message kinds
(async solid/open, sync solid/filled, reply dashed/open, create
dashed/open landing at the created lifeline's head), destruction
occurrences (X at the tail end), and execution specifications (thin
vertical rectangles, with message ends attaching to their edges)."""

import re

from diagramboxes import (Diagram, to_di, from_di, to_di_xmi, from_di_xmi)


def _diag(frame=True):
    d = Diagram()
    if frame:
        d.add_frame('sd', element_kind='interaction',
                    element_name='Execute Hohmann Transfer, Main Success Scenario')
    fc = d.add_lifeline('fc : Flight Computer')
    mans = d.add_lifeline('mans : MANS')
    return d, fc, mans


def test_add_lifeline_head_and_auto_x():
    d, fc, mans = _diag()
    assert fc.label == 'fc : Flight Computer'
    assert mans.x > fc.x, 'lifelines auto-space in registration order'
    heads = d.render_svg(routing='orthogonal')
    assert 'fc : Flight Computer' in heads
    assert 'mans : MANS' in heads
    # dashed tail below each head
    assert re.search(r'<polyline[^>]*stroke-dasharray', heads), \
        'lifeline tail drawn dashed in SVG'


def test_message_kinds_line_and_arrowheads():
    d, fc, mans = _diag()
    ia = d.seq_async(fc, mans, y=30, label='measureAltitude')
    isy = d.seq_sync(fc, mans, y=44, label='fireThrusters')
    ir = d.seq_reply(mans, fc, y=56)
    assert all(m.y in (30, 44, 56) for m in (ia, isy, ir))
    assert (ia.kind, isy.kind, ir.kind) == ('async', 'sync', 'reply')
    assert ia.line_style == 'solid' and isy.line_style == 'solid'
    assert ir.line_style == 'dashed'
    svg = d.render_svg(routing='orthogonal')
    assert 'measureAltitude' in svg and 'fireThrusters' in svg
    lines = re.findall(r'<line [^>]*/>', svg)
    # async/sync messages draw solid; reply draws dashed (svg scale 1.5)
    assert any('y1="45.0"' in l and 'stroke-dasharray' not in l for l in lines), \
        'async message solid'
    assert any('y1="66.0"' in l and 'stroke-dasharray' not in l for l in lines), \
        'sync message solid'
    assert any('y1="84.0"' in l and 'stroke-dasharray' in l for l in lines), \
        'reply message dashed'
    braille = d.render(routing='orthogonal')
    assert 'measureAltitude' in braille
    # sync arrowhead filled: FILLED polygon in svg
    assert re.search(r'<polygon[^>]*fill="black"', svg), \
        'synchronous message draws a filled-in arrowhead'


def test_create_message_targets_created_head():
    d, fc, mans = _diag()
    mansdd = d.add_lifeline('mansdd : MANS Device Driver', created=True)
    m = d.seq_create(fc, mansdd, label='initializeMANS')
    assert m.kind == 'create'
    assert mansdd.head_y == m.y, \
        'head top sits at the creation row'
    assert mansdd.tail_start == m.y + mansdd.h, \
        'dashed tail starts at the head bottom'
    svg = d.render_svg(routing='orthogonal')
    assert 'initializeMANS' in svg


def test_destruction_occurrence_x():
    d, fc, mans = _diag()
    d.destroy(mans, y=70)
    braille = d.render(routing='orthogonal')
    svg = d.render_svg(routing='orthogonal')
    assert braille, 'braille renders with the destruction occurrence'
    # two short diagonal lines for the X, at the tail end
    diags = [l for l in re.findall(r'<line [^>]*/>', svg)
             if 'y1="99.0"' in l or 'y1="111.0"' in l]
    assert len(diags) >= 2, 'destruction X drawn'


def test_execution_spec_attaches_message_ends():
    d, fc, mans = _diag()
    d.seq_sync(fc, mans, y=40, label='initialize')
    d.seq_exec(fc, 40, 60)          # fc active from 40 to 60
    d2 = d.render_svg(routing='orthogonal')
    assert d2.count('<rect') >= 3, 'thin exec rectangle drawn'
    e = d.messages[0]
    assert e.x1 == fc.x + 4, \
        'message tail attaches to the exec spec edge, not the dashed line'
    assert e.x2 == mans.x


def test_found_and_lost_messages():
    """§7.5: found/lost messages — ends at the frame boundary mid-air.
    Figure 7.10 opens with a found initializeMANS() (left frame border)
    and closes with fc's reply leaving LEFTWARD to the frame border."""
    fc = None
    d, fc, mans = _diag(frame=False)
    fin = d.seq_found(fc, y=20, label='initializeMANS( )', kind='sync')
    fl = d.seq_lost(fc, y=40, label='initializeMANS( ) : "Ready"',
                    kind='reply', to_right=False)
    d.seq_exec(fc, 20, 40)
    assert fin.src is None and fin.dst is fc
    assert fl.src is fc and fl.dst is None and fl.kind == 'reply'
    d2 = d.render_svg(routing='orthogonal')
    e = d.messages[0]
    assert e.x1 == fc.x - 90, 'found message starts mid-air left of fc'
    assert e.x2 == fc.x - 4, 'arrowhead docks at the exec-spec edge (§7.7)'
    f = d.messages[1]
    assert f.x1 == fc.x - 4, 'lost message departs at the spec edge'
    assert f.x2 == fc.x - 90, 'leaves mid-air to the LEFT when to_right=False'
    d3 = from_di(to_di(d))
    assert d3.messages[0].src is None and d3.messages[0].dst is not None
    assert d3.messages[1].src is not None and d3.messages[1].dst is None
    d4 = from_di(from_di_xmi(to_di_xmi(to_di(d))))
    assert d4.messages[0].src is None and d4.messages[1].dst is None


def test_found_lost_attach_to_frame_border_when_framed():
    """Book (Figure 7.10): found/lost ends attach DIRECTLY to the frame
    border, not float inside it."""
    d, fc, mans = _diag()
    d.seq_found(fc, y=20, label='initializeMANS( )', kind='sync')
    d.seq_lost(fc, y=40, label='r', kind='reply', to_right=False)
    svg = d.render_svg(routing='orthogonal')
    m1, m2 = d.messages
    fr = d._frame_rect()
    assert fr is not None
    x1 = fr[0]
    assert abs(m1.x1 - (x1 + 2)) < 1, 'found line attaches at the left border'
    assert abs(m2.x2 - (x1 + 2)) < 1, 'lost line terminates at the left border'


def test_sequence_survives_di_and_xmi_round_trip():
    d, fc, mans = _diag()
    mansdd = d.add_lifeline('mansdd : MANS Device Driver', created=True)
    d.seq_create(fc, mansdd, label='initializeMANS')
    d.seq_sync(mansdd, mans, y=40, label='initialize')
    d.seq_exec(fc, 20, 50)
    d.destroy(mansdd, y=60)
    d2 = from_di(to_di(d))
    assert [n.label for n in d2.lifelines] == [
        'fc : Flight Computer', 'mans : MANS',
        'mansdd : MANS Device Driver']
    assert d2.messages[0].kind == 'create'
    assert d2.messages[0].label == 'initializeMANS'
    assert d2.exec_specs[0].y1 == 20
    assert d2.destructions[0].y == 60
    d3 = from_di(from_di_xmi(to_di_xmi(to_di(d))))
    assert d3.messages[0].kind == 'create'
    assert d3.destructions[0].y == 60