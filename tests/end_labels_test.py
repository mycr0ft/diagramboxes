#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for per-edge-end labels (SysML v1, Delligatti §3.5, Figure 3.1).

Associations can show a role name and multiplicity near EACH end of the
line (e.g. ``eps 1``, ``demod 1``) in addition to the name label at the
Manhattan midpoint (e.g. the trunk caption ``satellite 0..1``).
``Edge.label`` already covers the midpoint; this adds ``source_label``
and ``target_label`` pinned near each end of the routed path.
"""

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