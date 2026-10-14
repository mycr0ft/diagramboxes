#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for allocation notation (SysML v1, Delligatti §12): «allocate»
dependency conveniences — dashed line, open arrowhead, keyword label.
There is no allocation diagram; allocation is a cross-cutting
relationship (§12.2)."""

from diagramboxes import Diagram, DASHED, OPEN


def test_allocate_conveniences_use_dependency_notation():
    d = Diagram()
    req = d.add_requirement('Altimetry', req_id='R-ALT', text='...')
    block = d.add_node('AltimeterSensorAssembly', ['block'])
    action = d.add_node('Measure Altitude')

    e1 = d.allocation(req, block)          # requirement → structure
    assert e1.line_style == DASHED and e1.target_style == OPEN
    assert 'allocate' in e1.label
    e2 = d.allocation(action, block)       # behavior → structure
    assert 'allocate' in e2.label
    d.render(routing='orthogonal')
    svg = d.render_svg(routing='orthogonal')
    assert '«allocate»' in svg