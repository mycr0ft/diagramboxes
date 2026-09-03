#!/usr/bin/env python3
"""SVG version of view / package demo — nesting children inside view."""

from diagramboxes import Diagram, FILLED

d = Diagram()

ecu = d.add_node('ECU', ['block'],
    attributes=['+ voltage : float', '+ temp : float'])
sensor = d.add_node('SensorCluster', ['block'], rounded=True)
occ = d.add_node('OccurrenceRef', ['occurrence'], rounded=True, dashed=True)

pkg = d.add_view('Powertrain', ['package'], dashed=True)
vw = d.add_view('VehicleDynamics', ['view'])
vw.add_child(sensor)

d.uncontain(pkg, ecu, label='unowned')
d.contain(vw, sensor, label='owned')
d.depend(occ, ecu, label='refs')

svg = d.render_svg(routing='orthogonal', node_gap=20)
path = '/tmp/boxes_view.svg'
with open(path, 'w') as f:
    f.write(svg)
print(f'Saved SVG ({len(svg)} chars) to {path}')
