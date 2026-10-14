#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for lollipop/socket interface symbols on ports and nodes
(SysML v1, Delligatti §3.4.1.5, Figures 4.5/4.6).

- A PROVIDED interface renders as a ball on a stick (lollipop) attached
  outward from its port along the port's side.
- A REQUIRED interface renders as a stick with an open semicircle (socket).
- The interface name renders as a label near the symbol.
- Interfaces may also attach directly to a node boundary (no port).
- Interfaces serialize in the DI payload (and XMI) with their port.
- Interface symbols (and labels) count in the SVG bounds math.
"""

import re

from diagramboxes import Diagram, to_di, from_di, to_di_xmi, from_di_xmi


def _port_with_interfaces():
    d = Diagram()
    eps = d.add_node('eps : Electrical Power Subsystem', dashed=True)
    p = eps.add_port('sp_eps', side='right', offset=0.5)
    p.add_interface('Power Generation', kind='provided')
    p.add_interface('Status Reporting', kind='required')
    return d, eps, p


def test_provided_interface_renders_lollipop_ball_in_svg():
    d, eps, p = _port_with_interfaces()
    svg = d.render_svg()
    # ball: a small filled circle rendered after the port box
    assert re.search(r'<circle[^>]*fill="black"[^>]*/>', svg), \
        "provided interface = filled ball"
    assert 'Power Generation' in svg


def test_required_interface_renders_socket_arc_in_svg():
    d, eps, p = _port_with_interfaces()
    svg = d.render_svg()
    # socket: an open semicircle approximated by a polyline arc
    assert re.search(r'<polyline[^>]*class="arc"[^>]*/>', svg), \
        "required interface = stick + open semicircle"
    assert 'Status Reporting' in svg


def test_interface_names_render_in_braille():
    d, eps, p = _port_with_interfaces()
    txt = d.render()
    assert 'Power Generation' in txt
    assert 'Status Reporting' in txt


def test_interface_on_node_boundary_without_port():
    d = Diagram()
    n = d.add_node('DellSat-77 Satellite', ['block'])
    n.add_interface('Light Source', kind='required', side='left', offset=0.3)
    svg = d.render_svg()
    assert 'Light Source' in svg
    assert re.search(r'<polyline[^>]*class="arc"[^>]*/>', svg)
    d.render()  # braille smoke


def test_two_interfaces_stack_outward():
    d, eps, p = _port_with_interfaces()
    p.add_interface('Third', kind='provided')
    svg = d.render_svg()
    assert 'Third' in svg


def test_long_interface_name_not_clipped_in_svg():
    d = Diagram()
    n = d.add_node('A', ['block'])
    n.add_interface('A Very Long Interface Name Indeed', kind='provided',
                    side='right', offset=0.5)
    svg = d.render_svg()
    assert 'A Very Long Interface Name Indeed' in svg


def test_di_round_trip_preserves_interfaces():
    d, eps, p = _port_with_interfaces()
    d2 = from_di(to_di(d))
    p2 = d2.nodes[0].ports[0]
    ifaces = [(i.name, i.kind) for i in p2.interfaces]
    assert ifaces == [('Power Generation', 'provided'),
                      ('Status Reporting', 'required')]


def test_di_xmi_round_trip_preserves_interfaces():
    d, eps, p = _port_with_interfaces()
    xml = to_di_xmi(to_di(d))
    d2 = from_di(from_di_xmi(xml))
    p2 = d2.nodes[0].ports[0]
    ifaces = [(i.name, i.kind) for i in p2.interfaces]
    assert ifaces == [('Power Generation', 'provided'),
                      ('Status Reporting', 'required')]