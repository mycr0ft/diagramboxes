#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for combined fragments and interaction uses (SysML v1,
Delligatti §7.9–7.10): a rectangle over the participating lifelines with
a pentagon in the upper-left corner naming the interaction operator
(opt / alt / loop / par), dashed operand-separator lines with per-operand
guards, and the `ref` rectangle invoking a lower-level interaction."""

import re

from diagramboxes import (Diagram, to_di, from_di, to_di_xmi, from_di_xmi)


def _diag():
    d = Diagram()
    d.add_frame('sd', element_kind='interaction',
                element_name='Initialize MANS, Main Success Scenario')
    fc = d.add_lifeline('fc : Flight Computer')
    mans = d.add_lifeline('mans : MANS')
    return d, fc, mans


def test_opt_fragment_construction_and_round_trip():
    d, fc, mans = _diag()
    f = d.seq_fragment([fc, mans], y1=40, y2=90, operator='opt',
                       guard='isCommandValid == True')
    assert f.operator == 'opt'
    assert f.guard == 'isCommandValid == True'
    assert f.lifelines == [fc, mans]
    d2 = from_di(to_di(d))
    f2 = d2.fragments[0]
    assert f2.operator == 'opt'
    assert f2.guard == 'isCommandValid == True'
    assert [l.label for l in f2.lifelines] == [fc.label, mans.label]
    d3 = from_di(from_di_xmi(to_di_xmi(to_di(d))))
    assert d3.fragments[0].operator == 'opt'
    assert d3.fragments[0].guard == 'isCommandValid == True'


def test_alt_operands_dashed_separators_and_guards():
    d, fc, mans = _diag()
    f = d.seq_fragment([fc, mans], y1=40, y2=130, operator='alt',
                       guard='sensorStatus == True',
                       operands=[(80, 'sensorStatus == True'), (110, 'else')])
    assert len(f.operands) == 2
    svg = d.render_svg(routing='orthogonal')
    assert 'alt' in svg
    # dashed separator lines across the fragment at the operand rows (×1.5)
    assert re.search(r'<line[^>]*y1="120\.0"[^>]*stroke-dasharray', svg), \
        'operand separator at y=80 is dashed'
    assert re.search(r'<line[^>]*y1="165\.0"[^>]*stroke-dasharray', svg), \
        'operand separator at y=110 is dashed'
    # per-operand guards below their separator
    assert 'sensorStatus == True' in svg
    assert 'else' in svg
    braille = d.render(routing='orthogonal')
    assert 'alt' in braille and 'else' in braille


def test_loop_operator_range_in_pentagon():
    d, fc, mans = _diag()
    f = d.seq_fragment([fc, mans], y1=30, y2=80, operator='loop',
                       range='(2, *)', guard='sensorStatus == "Ready"')
    svg = d.render_svg(routing='orthogonal')
    assert 'loop (2, *)' in svg, 'operator + iteration range in the pentagon'
    assert 'sensorStatus == "Ready"' in svg


def test_interaction_use_ref():
    d, fc, mans = _diag()
    u = d.seq_ref([fc, mans], y1=40, y2=80,
                  name='Bring MANS Hardware Online')
    assert u.operator == 'ref'
    assert u.name == 'Bring MANS Hardware Online'
    svg = d.render_svg(routing='orthogonal')
    assert 'ref' in svg
    assert 'Bring MANS Hardware Online' in svg
    # the participating lifelines disappear behind the rectangle: opaque fill
    rect = re.search(r'<rect x="(-?[\d.]+)" y="60\.0"[^>]*fill="white"', svg)
    assert rect, 'interaction use paints opaque white'


def test_fragments_count_in_bounds():
    d, fc, mans = _diag()
    d.seq_fragment([fc, mans], y1=60, y2=200, operator='opt')
    svg = d.render_svg(routing='orthogonal')
    vb = re.search(r'viewBox="(-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)"', svg)
    assert re.search(r'<rect x="(-?[\d.]+)" y="90\.0"', svg), \
        'fragment rectangle drawn (scaled ×1.5)'
    vy, vh = float(vb.group(2)), float(vb.group(4))
    assert vy + vh >= 300, 'fragment bottom inside the viewBox (no clipping)'