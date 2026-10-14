#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the SVG appearance upgrades (svg-only; braille path unchanged).

Corpus basis (SysML Distilled): compartment names are italic titles
(§3.4 / Figure 3.1); the diagram-kind frame header is a dog-ear folded
tag at the frame's top-left (§2.4/§3.3); labels must not be overprinted
by the lines beneath them (readability finding from the Figure 3.1
fidelity review).
"""

import re

from diagramboxes import Diagram, TRIANGLE


def _labeled():
    d = Diagram()
    a = d.add_node('A', ['block'])
    b = d.add_node('B', ['block'])
    d.add_edge(a, b, label='satellite 0..1',
               source_label='src 1', target_label='tgt 2')
    return d


def test_edge_labels_render_with_white_halo():
    svg = _labeled().render_svg()
    for lab in ('satellite 0..1', 'src 1', 'tgt 2'):
        # halo: a <g> whose white rect is immediately followed by the text
        m = re.search(
            r'<g>\s*<rect [^>]*fill="white"[^>]*/>\s*'
            r'<text [^>]*>' + re.escape(lab) + r'</text>\s*</g>', svg)
        assert m, f"label {lab!r} must be halo-grouped (white rect + text)"


def test_compartment_titles_render_italic():
    d = Diagram()
    d.add_node('Flight Computer', ['block'],
               compartments=[('values', ['memoryCapacity : Mb'])])
    svg = d.render_svg()
    m = re.search(r'<text[^>]*font-style="italic"[^>]*>values</text>', svg)
    assert m, "compartment title must render as italic text"


def test_proportional_font_family_by_default():
    svg = _labeled().render_svg()
    assert 'font-family="monospace"' not in svg, \
        "text must use a proportional stack, not drawille's monospace"
    assert 'font-family="Helvetica' in svg


def test_frame_header_is_dog_eared_tag():
    d = Diagram()
    d.add_node('A', ['block'])
    d.add_frame('bdd', element_kind='package', element_name='Structure',
                diagram_name='demo name')
    svg = d.render_svg()
    # the frame path draws a folded-corner tag: polygon + plain header text
    m = re.search(r'<g>\s*<polygon[^>]*/>\s*'
                  r'<text[^>]*>'
                  r'bdd \[package\] Structure \[demo name\]</text>\s*</g>', svg)
    assert m, "frame header must be a dog-ear tag polygon + header text in a group"