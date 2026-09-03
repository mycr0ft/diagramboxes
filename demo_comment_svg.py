#!/usr/bin/env python3
"""SVG version of comment/dog-ear demo."""

from diagramboxes import Diagram, FILLED, DASHED

d = Diagram()

ecu = d.add_node('ECU', ['block'],
    attributes=['+ voltage : float', '+ temp : float'])
sensor = d.add_node('SensorCluster', ['block'])
actuator = d.add_node('ActuatorDriver', ['block'],
    attributes=['+ apply()'])

note = d.add_comment('Requires firmware v2.1+')
note2 = d.add_comment('Uses CAN bus protocol')

d.add_edge(ecu, sensor, source_style=FILLED, target_style=None, label='reads')
d.add_edge(ecu, actuator, source_style=FILLED, target_style=None, label='commands')
d.add_edge(note, ecu, line_style=DASHED, target_style=None)
d.add_edge(note2, sensor, line_style=DASHED, target_style=None)

svg = d.render_svg(routing='orthogonal', node_gap=20)
path = '/tmp/boxes_comment.svg'
with open(path, 'w') as f:
    f.write(svg)
print(f'Saved SVG ({len(svg)} chars) to {path}')
