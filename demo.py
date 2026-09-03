#!/usr/bin/env python3
"""SysML block diagram demo — orthogonal routing with ports and attributes."""

from diagramboxes import Diagram, OPEN, TRIANGLE, FILLED, DASHED

d = Diagram()

# Layer 0
ecu = d.add_node('ECU', ['block'],
    attributes=['+ voltage : float', '+ temp : float', '# state : int'])

# Layer 1
sensor = d.add_node('SensorCluster', ['block'],
    attributes=['- calibrate()', '+ read()'])
actuator = d.add_node('ActuatorDriver', ['block'],
    attributes=['+ apply()', '- limit()'])
display = d.add_node('DisplayUnit', ['block'])

# Ports for lateral connections — auto-distributed per side
sns_out = sensor.add_port('out', side='right', direction='out')
sns_cfg = sensor.add_port('cfg', side='right', direction='out')
act_data = actuator.add_port('data', side='left', direction='in')
act_cfg = actuator.add_port('cfg', side='left', direction='in')
act_out = actuator.add_port('out', side='right', direction='out')
disp_in = display.add_port('in', side='left', direction='in')

# Top-down edges (traditional)
d.add_edge(ecu, sensor, source_style=FILLED, target_style=OPEN, label='reads')
d.add_edge(ecu, actuator, source_style=FILLED, target_style=OPEN, label='commands')
d.add_edge(ecu, display, source_style=FILLED, target_style=OPEN, label='updates')

# Lateral port-to-port edges (no arrowheads — port direction arrows suffice)
d.add_edge(sensor, actuator, source_port=sns_out, target_port=act_data,
           target_style=None, label='data')
d.add_edge(sensor, actuator, source_port=sns_cfg, target_port=act_cfg,
           line_style=DASHED, target_style=None, label='config')
d.add_edge(actuator, display, source_port=act_out, target_port=disp_in,
           target_style=None, label='output')

print(d.render(routing='orthogonal', node_gap=50))
