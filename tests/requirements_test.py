#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for requirements-diagram notation (SysML v1, Delligatti §11):
«requirement» boxes with id/text compartments and the dependency-based
relationship keywords «trace», «deriveReqt», «refine», «satisfy»,
«verify» (dashed line, open arrowhead, keyword label at the midline).
"""

from diagramboxes import (Diagram, DASHED, OPEN, to_di, from_di, to_di_xmi,
                          from_di_xmi)


def _reqs():
    d = Diagram()
    base = d.add_requirement('Hohmann Transfer', req_id='R-HT',
                             text='The satellite shall execute a Hohmann '
                                  'transfer to the operational orbit')
    derived = d.add_requirement('Thruster Burn', req_id='R-TB',
                                text='The propulsion subsystem shall deliver '
                                     'the required delta-v')
    return d, base, derived


def test_add_requirement_builds_stereotyped_box_with_id_text_compartments():
    d, base, derived = _reqs()
    assert base.stereotypes == ['requirement']
    assert ('id', ['R-HT']) in base.compartments
    texts = [ls for t, ls in base.compartments if t == 'text']
    assert texts and 'Hohmann transfer' in texts[0][0]
    assert derived.name == 'Thruster Burn'


def test_requirements_render_keyword_and_compartments():
    d, base, derived = _reqs()
    svg = d.render_svg(routing='orthogonal')
    assert '«requirement»' in svg
    assert 'R-HT' in svg
    assert 'Hohmann Transfer' in svg


def test_relationship_conveniences_use_dependency_notation():
    d, base, derived = _reqs()
    block = d.add_node('MANS', ['block'])
    e1 = d.req_derive(derived, base)
    assert e1.source is derived and e1.target is base
    assert e1.line_style == DASHED and e1.target_style == OPEN
    assert 'deriveReqt' in e1.label
    e2 = d.req_trace(base, derived)
    assert e2.line_style == DASHED and e2.target_style == OPEN
    assert 'trace' in e2.label
    e3 = d.req_satisfy(block, base)
    assert e3.source is block and e3.target is base
    assert 'satisfy' in e3.label
    e4 = d.req_refine(derived, base)
    assert 'refine' in e4.label
    e5 = d.req_verify(block, base)
    assert 'verify' in e5.label
    # all render in braille and SVG without error
    d.render(routing='orthogonal')
    svg = d.render_svg(routing='orthogonal')
    assert '«deriveReqt»' in svg
    assert '«satisfy»' in svg
    assert '«verify»' in svg


def test_requirements_survive_di_and_xmi_round_trip():
    d, base, derived = _reqs()
    block = d.add_node('MANS', ['block'])
    d.req_derive(derived, base)
    d.req_satisfy(block, base)
    d2 = from_di(to_di(d))
    r2 = d2.nodes[0]
    assert r2.stereotypes == ['requirement']
    assert ('id', ['R-HT']) in r2.compartments
    e1 = d2.edges[0]
    assert 'deriveReqt' in e1.label
    e2 = d2.edges[1]
    assert 'satisfy' in e2.label
    d3 = from_di(from_di_xmi(to_di_xmi(to_di(d))))
    assert d3.nodes[0].stereotypes == ['requirement']
    assert 'deriveReqt' in d3.edges[0].label