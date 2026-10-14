#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for package-diagram notation (SysML v1, Delligatti §10): package
folder symbols with the tab (specialized kinds via stereotypes «model»,
«modelLibrary», «profile», «view»), crosshair containment (circled plus on
the namespace end), and the «import» / «conform» dependency conveniences.
"""

import re

from diagramboxes import Diagram, DASHED, OPEN, to_di, from_di, to_di_xmi, \
    from_di_xmi


def test_add_package_builds_folder_and_specialized_kind():
    d = Diagram()
    pkg = d.add_package('Domain')
    lib = d.add_package('Libraries', stereotypes=['modelLibrary'])
    assert pkg.stereotypes == ['package']
    assert lib.stereotypes == ['package', 'modelLibrary']
    svg = d.render_svg(routing='orthogonal')
    assert '«package»' in svg
    assert '«modelLibrary»' in svg


def test_package_folder_tab_drawn_in_svg():
    d = Diagram()
    d.add_package('Domain')
    svg = d.render_svg(routing='orthogonal')
    assert re.search(r'class="pkg-tab"[^>]*/?>', svg), \
        "folder tab on the upper-left side of the package symbol"


def test_crosshair_containment_notation():
    d = Diagram()
    domain = d.add_package('Domain')
    structure = d.add_package('Structure')
    e = d.pkg_contain(domain, structure)
    assert e.source is domain        # namespace (container) end
    assert e.source_style == 'circled_plus'
    assert e.line_style == 'solid'
    svg = d.render_svg(routing='orthogonal')
    assert 'class="crosshair"' in svg, "circled plus on the namespace end"


def test_pkg_import_and_conform_conveniences():
    d = Diagram()
    vt = d.add_package('Value Types')
    lt = d.add_package('Libraries Value Types', stereotypes=['modelLibrary'])
    vp = d.add_node('Reliability Viewpoint',
                    attributes=['stakeholders : System Engineer'])
    view = d.add_package('Reliability View', stereotypes=['view'])
    e1 = d.pkg_import(vt, lt)
    assert e1.line_style == DASHED and e1.target_style == OPEN
    assert 'import' in e1.label
    e2 = d.pkg_conform(view, vp)
    assert e2.line_style == DASHED and e2.target_style == OPEN
    assert 'conform' in e2.label
    svg = d.render_svg(routing='orthogonal')
    assert '«import»' in svg
    assert '«conform»' in svg


def test_packages_survive_di_and_xmi_round_trip():
    d = Diagram()
    domain = d.add_package('Domain')
    structure = d.add_package('Structure')
    d.pkg_import(structure, domain)
    d.pkg_contain(domain, structure)
    d2 = from_di(to_di(d))
    assert d2.nodes[0].stereotypes == ['package']
    assert d2.edges[0].label == '«import»'
    assert d2.edges[1].source_style == 'circled_plus'
    d3 = from_di(from_di_xmi(to_di_xmi(to_di(d))))
    assert d3.edges[1].source_style == 'circled_plus'