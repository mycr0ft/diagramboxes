#!/usr/bin/env python3
"""Generate SVG output from a diagram and save to file."""

from diagramboxes import Diagram, OPEN, TRIANGLE, FILLED, DASHED

d = Diagram()

ecu = d.add_node('ECU', ['block'],
    attributes=['+ voltage : float', '+ temp : float', '# state : int'])
sensor = d.add_node('SensorCluster', ['block'],
    attributes=['- calibrate()', '+ read()'])
actuator = d.add_node('ActuatorDriver', ['block'],
    attributes=['+ apply()', '- limit()'])
display = d.add_node('DisplayUnit', ['block'])

sns_out = sensor.add_port('out', side='right', offset=0.25, direction='out')
sns_cfg = sensor.add_port('cfg', side='right', offset=0.75, direction='out')
act_data = actuator.add_port('data', side='left', offset=0.25, direction='in')
act_cfg = actuator.add_port('cfg', side='left', offset=0.75, direction='in')
act_out = actuator.add_port('out', side='right', offset=0.5, direction='out')
disp_in = display.add_port('in', side='left', offset=0.5, direction='in')

d.add_edge(ecu, sensor, source_style=FILLED, target_style=OPEN, label='reads')
d.add_edge(ecu, actuator, source_style=FILLED, target_style=OPEN, label='commands')
d.add_edge(ecu, display, source_style=FILLED, target_style=OPEN, label='updates')
d.add_edge(sensor, actuator, source_port=sns_out, target_port=act_data,
           target_style=OPEN, label='data')
d.add_edge(sensor, actuator, source_port=sns_cfg, target_port=act_cfg,
           line_style=DASHED, target_style=OPEN, label='config')
d.add_edge(actuator, display, source_port=act_out, target_port=disp_in,
           target_style=OPEN, label='output')

svg = d.render_svg(routing='orthogonal', node_gap=60)
with open('/tmp/diagram.svg', 'w') as f:
    f.write(svg)
print(f'Saved SVG ({len(svg)} chars) to /tmp/diagram.svg')
