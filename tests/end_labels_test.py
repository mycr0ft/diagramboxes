#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for per-edge-end labels (SysML v1, Delligatti §3.5, Figure 3.1).

Associations can show a role name and multiplicity near EACH end of the
line (e.g. ``eps 1``, ``demod 1``) in addition to the name label at the
Manhattan midpoint (e.g. the trunk caption ``satellite 0..1``).
``Edge.label`` already covers the midpoint; this adds ``source_label``
and ``target_label`` pinned near each end of the routed path.
"""

import re

from diagramboxes import Diagram, to_di, from_di, to_di_xmi, from_di_xmi


def _edge_with_end_labels():
    d = Diagram()
    a = d.add_node('Satellite', ['block'])
    b = d.add_node('Distribution Bus', ['block'])
    d.add_edge(a, b, label='satellite 0..1',
               source_label='eps 1', target_label='db 1')
    return d


def test_end_labels_render_in_svg():
    svg = _edge_with_end_labels().render_svg()
    assert 'eps 1' in svg
    assert 'db 1' in svg
    assert 'satellite 0..1' in svg, "midpoint label must still render"
    assert svg.count('eps 1') == 1


def test_end_labels_render_in_braille():
    txt = _edge_with_end_labels().render()
    assert 'eps 1' in txt
    assert 'db 1' in txt


def test_end_label_position_helper():
    from diagramboxes.primitives import edge_end_label_positions
    # horizontal route
    spos, tpos = edge_end_label_positions([(10, 10), (100, 10)])
    assert spos == (22, 5) and tpos == (88, 5)
    # vertical route
    spos, tpos = edge_end_label_positions([(50, 10), (50, 100)])
    assert spos == (56, 22) and tpos == (56, 88)


def test_di_round_trip_preserves_end_labels():
    d = _edge_with_end_labels().__class__()  # noqa - placeholder replaced below
    d = Diagram()
    a = d.add_node('A', ['block'])
    b = d.add_node('B', ['block'])
    d.add_edge(a, b, source_label='s 1', target_label='t 2', label='name')
    d2 = from_di(to_di(d))
    e2 = d2.edges[0]
    assert e2.source_label == 's 1'
    assert e2.target_label == 't 2'
    assert e2.label == 'name'


def test_di_xmi_round_trip_preserves_end_labels():
    d = Diagram()
    a = d.add_node('A', ['block'])
    b = d.add_node('B', ['block'])
    d.add_edge(a, b, source_label='s 1', target_label='t 2', label='name')
    xml = to_di_xmi(to_di(d))
    d2 = from_di(from_di_xmi(xml))
    e2 = d2.edges[0]
    assert e2.source_label == 's 1'
    assert e2.target_label == 't 2'


def test_end_labels_avoid_collisions_across_parallel_edges():
    """The Figure 3.1 garble: multiple per-end labels near the same
    target node must not overprint each other — later labels search
    clear offsets via the per-render label registry."""
    d = Diagram()
    cdhs = d.add_node('CDHS', ['block'])
    fc = d.add_node('Flight Computer', ['block'])
    d.add_edge(cdhs, fc, target_label='primaryComputer 1')
    d.add_edge(cdhs, fc, target_label='backupComputer 1..2')
    d.add_edge(cdhs, fc, target_label='mod 1')
    svg = d.render_svg()
    assert 'primaryComputer 1' in svg
    assert 'backupComputer 1..2' in svg
    assert 'mod 1' in svg
    # the three labels' halo text elements sit at DISTINCT y positions
    ys = [float(m.group(1)) for m in re.finditer(
        r'<text[^>]*y="([\d.]+)"[^>]*>(?:primaryComputer 1'
        r'|backupComputer 1\.\.2|mod 1)</text>', svg)]
    assert len(ys) == 3
    assert max(ys) - min(ys) >= 6, f"labels still collide: ys={ys}"