#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for SysML v1-style NAMED compartments on Node.

Acceptance criteria come from the corpus
(~/proj/sysml-distilled/summary/03-block-definition-diagrams.md, §3.4,
Figure 3.1): a block can display multiple named compartments (parts,
references, values, constraints, ...), each drawn underneath the previous
one, separated by a horizontal line, with the compartment name as a
centered title line and its content lines below it.  The traditional
``attributes`` parameter keeps its role as the first, unnamed compartment.
"""

from diagramboxes import Diagram, Node, to_di, from_di, to_di_xmi, from_di_xmi


def _nodes_named(*args, **kw):
    """Diagram factory with one node added."""
    d = Diagram()
    d.add_node(*args, **kw)
    return d


def test_named_compartments_appear_in_svg_in_order():
    d = _nodes_named('Flight Computer', ['block'],
                     compartments=[('constraints', ['sm : Sufficient Memory']),
                                   ('values', ['memoryCapacity : Mb',
                                               'dataPerOrbit : Mb'])])
    svg = d.render_svg()
    order = [svg.index(s) for s in ('Flight Computer', 'constraints',
                                    'sm : Sufficient Memory', 'values',
                                    'memoryCapacity : Mb')]
    assert order == sorted(order), "compartment titles/content must be in listed order"


def test_named_compartments_appear_in_braille_render():
    d = _nodes_named('Flight Computer', ['block'],
                     compartments=[('values', ['memoryCapacity : Mb'])])
    txt = d.render()
    assert 'values' in txt
    assert 'memoryCapacity : Mb' in txt


def test_compartment_lines_grow_node_size():
    plain = Node('x')
    sized = Node('x', compartments=[('values', ['aVeryLongAttributeName : Type'])])
    assert sized.w > plain.w, "compartment content must widen the node"
    assert sized.h > plain.h, "compartment title + line must heighten the node"


def test_multiple_compartments_each_heighten_node():
    one = Node('x', compartments=[('values', ['mass : kg'])])
    two = Node('x', compartments=[('values', ['mass : kg']),
                                  ('constraints', ['sm : Sufficient Memory'])])
    assert two.h > one.h


def test_attributes_still_render_as_first_unnamed_compartment():
    d = _nodes_named('Flight Computer', ['block'],
                     attributes=['memoryCapacity : Mb'],
                     compartments=[('values', ['dataPerOrbit : Mb'])])
    svg = d.render_svg()
    assert svg.index('memoryCapacity : Mb') < svg.index('dataPerOrbit : Mb'), \
        "attributes stay the first (unnamed) compartment"


def test_di_round_trip_preserves_compartments():
    d = _nodes_named('A', ['block'],
                     compartments=[('values', ['mass : kg']),
                                   ('parts', ['p : Block [2]'])])
    d2 = from_di(to_di(d))
    n2 = [n for n in d2.nodes if n.name == 'A'][0]
    assert n2.compartments == [('values', ['mass : kg']),
                               ('parts', ['p : Block [2]'])]


def test_di_xmi_round_trip_preserves_compartments():
    d = _nodes_named('A', ['constraint'],
                     compartments=[('parameters', ['memoryCapacity : Mb'])])
    xml = to_di_xmi(to_di(d))
    d2 = from_di(from_di_xmi(xml))
    n2 = [n for n in d2.nodes if n.name == 'A'][0]
    assert n2.compartments == [('parameters', ['memoryCapacity : Mb'])]