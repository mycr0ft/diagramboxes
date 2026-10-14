#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression: a TRIANGLE arrowhead (generalization, Delligatti §3.6) must
render HOLLOW in SVG — filled white with a stroked outline — not as an
invalid ``fill="triangle"`` attribute that browsers paint solid."""

import re

from diagramboxes import Diagram, TRIANGLE


def test_generalization_triangle_hollow_in_svg():
    d = Diagram()
    a = d.add_node('A', ['block'])
    b = d.add_node('B', ['block'])
    d.add_edge(a, b, target_style=TRIANGLE)
    svg = d.render_svg()
    assert 'fill="triangle"' not in svg, \
        "TRIANGLE leaked into the SVG as an invalid color attribute"
    assert re.search(r'<polygon[^>]*fill="white"', svg), \
        "hollow triangle must render white-filled with a stroked outline"