#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multi-line edge-end labels (for the SysML v2 metamodel figures, e.g.
fig-15: three stacked strings per association end — '+/partOwning
Definition', '0..1', '{subsets itemOwningDefinition}'). A '\n'-joined
source_label/target_label renders as STACKED lines at the same end."""

from diagramboxes import Diagram


def _svg(d):
    return d.render_svg()


def test_multiline_end_labels_braille_stack():
    d = Diagram()
    a = d.add_node('A')
    b = d.add_node('B')
    d.add_edge(a, b, source_label='+/partOwningDefinition\n0..1\n'
                               '{subsets itemOwningDefinition}')
    txt = d.render()
    assert '+/partOwningDefinition' in txt
    assert '0..1' in txt
    assert '{subsets itemOwningDefinition}' in txt


def test_multiline_end_labels_svg_stack():
    d = Diagram()
    a = d.add_node('A')
    b = d.add_node('B')
    d.add_edge(a, b, source_label='+/partOwningDefinition\n0..1\n'
                               '{subsets itemOwningDefinition}')
    svg = _svg(d)
    assert '+/partOwningDefinition' in svg
    assert '{subsets itemOwningDefinition}' in svg
    # three separate text elements near the same end (stacked rows)
    import re
    ys = [float(m.group(1)) for m in re.finditer(
        r'<text x="[-\d.]+" y="([-\d.]+)"[^>]*>\s*(?:\{subsets itemOwning'
        r'Definition\}|0\.\.1|\+/partOwningDefinition)', svg)]
    assert len(ys) == 3
    assert max(ys) - min(ys) >= 8   # stacked, not overlapping


def test_multiline_round_trips_with_newline():
    from diagramboxes import to_di, from_di
    d = Diagram()
    a = d.add_node('A')
    b = d.add_node('B')
    e = d.add_edge(a, b, source_label='+/x\n0..1\n{subsets ownedItem}')
    d2 = from_di(to_di(d))
    assert d2.edges[0].source_label == '+/x\n0..1\n{subsets ownedItem}'
    assert e.source_label.startswith('+/x')