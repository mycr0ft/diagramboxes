#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the diagram-kind frame primitive (SysML v1, Delligatti §2.4/§3.3).

Every SysML diagram kind is drawn inside a frame whose header names
(1) the diagram kind (bdd, ibd, uc, act, sd, stm, par, pkg, req),
(2) the kind of model element the frame represents in brackets,
(3) the model element name, and (4) the diagram name in brackets:

    bdd [package] Structure [DellSat-77 Satellite Structure and Properties]
"""

from diagramboxes import Diagram


def _diagram_with_frame():
    d = Diagram()
    a = d.add_node('A', ['block'])
    b = d.add_node('B', ['block'])
    d.add_edge(a, b, label='satellite 0..1')
    d.add_frame('bdd', element_kind='package', element_name='Structure',
                diagram_name='DellSat-77 Satellite Structure and Properties')
    return d


def test_frame_header_string_renders_in_svg():
    svg = _diagram_with_frame().render_svg()
    assert ('bdd [package] Structure '
            '[DellSat-77 Satellite Structure and Properties]') in svg


def test_frame_header_string_renders_in_braille():
    txt = _diagram_with_frame().render()
    assert 'bdd' in txt and '[package]' in txt and '[DellSat-77 Satellite Structure and Properties]' in txt


def test_frame_encloses_content_in_svg():
    # with a frame the canvas grows: header strip adds height and the
    # border rectangle surrounds the content — verify the svg contains
    # two <rect> elements (frame + first node) and is taller than the
    # frameless render of the same content.
    framed = _diagram_with_frame().render_svg()
    d2 = _diagram_with_frame()
    d2.frame = None
    bare = d2.render_svg()
    import re
    h = lambda s: float(re.search(r'height="([\d.]+)"', s).group(1))
    assert h(framed) > h(bare)


def test_render_without_frame_unchanged():
    d = Diagram()
    d.add_node('A', ['block'])
    d.add_frame('sd', element_kind='interaction', element_name='seq',
                diagram_name='demo')
    d.frame = None  # caller may clear it
    svg = d.render_svg()
    assert 'bdd' not in svg and 'demo' not in svg