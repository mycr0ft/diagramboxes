#!/usr/bin/env python3
"""Render a diagram to SVG and wrap in an HTML file for easy viewing."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from diagramboxes import Diagram, OPEN, TRIANGLE, FILLED, DASHED

def build_demo():
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
    return d

if __name__ == '__main__':
    d = build_demo()
    svg = d.render_svg(routing='orthogonal', node_gap=60)

    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Diagram SVG</title>
<style>
  body {{ background: #fff; margin: 20px; }}
  svg {{ border: 1px solid #ccc; max-width: 100%; height: auto; }}
</style>
</head><body>
{svg}
</body></html>
'''
    path = '/tmp/diagram_view.html'
    with open(path, 'w') as f:
        f.write(html)
    print(f'Saved: {path}')

    # Also save bare SVG
    path2 = '/tmp/diagram.svg'
    with open(path2, 'w') as f:
        f.write(svg)
    print(f'Saved: {path2}')
