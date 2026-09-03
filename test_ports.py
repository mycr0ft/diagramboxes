#!/usr/bin/env python3
"""Test ports as boxes and attributes — with wider spacing."""

from diagramboxes import Diagram, OPEN, TRIANGLE, FILLED, DASHED

d = Diagram()

sensor = d.add_node('TemperatureSensor', ['block'],
    attributes=['+ id : int', '+ value : float', '- threshold : float'])
controller = d.add_node('Controller', ['block'],
    attributes=['+ process()', '- validate()'])
display = d.add_node('Display', ['block'])

in_port = sensor.add_port('in', side='right', direction='in')
out_port = sensor.add_port('out', side='right', direction='out')
ctrl_in = controller.add_port('in', side='left', direction='in')
ctrl_out = controller.add_port('out', side='right', direction='out')
disp_in = display.add_port('in', side='left', direction='in')

d.add_edge(sensor, controller, source_port=out_port, target_port=ctrl_in,
           target_style=OPEN, label='data')
d.add_edge(controller, display, source_port=ctrl_out, target_port=disp_in,
           target_style=OPEN, label='update')
d.add_edge(sensor, display, line_style=DASHED, target_style=OPEN, label='bypass')

# Use wider node_gap to accommodate ports
print(d.render(routing='pyelk', node_gap=40))
