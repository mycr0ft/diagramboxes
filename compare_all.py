#!/usr/bin/env python3
"""Compare all 4 routing modes side-by-side."""

from diagramboxes import Diagram, OPEN, TRIANGLE, FILLED, DASHED
from diagramboxes.elk import layout_with_elk
from drawille import Canvas


def build_diagram():
    d = Diagram()
    d.add_node('System', ['block'])
    d.add_node('SubsystemA', ['block'])
    d.add_node('SubsystemB', ['block'])
    d.add_node('PowerSupply', ['block'])
    d.add_node('Controller', ['part'])
    d.add_node('SensorArray',  ['part'])
    d.add_node('Actuator', ['part'])
    d.add_node('Battery')
    d.add_node('MCU')
    d.add_node('Memory')
    d.add_node('Wireless')
    d.add_node('Thermometer')
    d.add_node('Motor')
    d.add_node('Regulator')
    d.add_node('FlashStorage', ['block'])

    d.add_edge(d.nodes[0], d.nodes[1], source_style=FILLED, target_style=OPEN, label='composed of')
    d.add_edge(d.nodes[0], d.nodes[2], source_style=FILLED, target_style=OPEN, label='composed of')
    d.add_edge(d.nodes[0], d.nodes[3], source_style=FILLED, target_style=OPEN, label='composed of')
    d.add_edge(d.nodes[1], d.nodes[4], source_style=FILLED, target_style=OPEN, label='composed of')
    d.add_edge(d.nodes[1], d.nodes[5], source_style=FILLED, target_style=OPEN, label='composed of')
    d.add_edge(d.nodes[2], d.nodes[6], source_style=FILLED, target_style=OPEN, label='composed of')
    d.add_edge(d.nodes[2], d.nodes[10], source_style=FILLED, target_style=OPEN, label='composed of')
    d.add_edge(d.nodes[3], d.nodes[7], target_style=OPEN, label='powers')
    d.add_edge(d.nodes[3], d.nodes[13], target_style=OPEN, label='powers')
    d.add_edge(d.nodes[4], d.nodes[8], source_style=FILLED, target_style=OPEN, label='composed of')
    d.add_edge(d.nodes[4], d.nodes[9], source_style=FILLED, target_style=OPEN, label='composed of')
    d.add_edge(d.nodes[5], d.nodes[11], target_style=TRIANGLE, label='generalizes')
    d.add_edge(d.nodes[6], d.nodes[12], target_style=TRIANGLE, label='generalizes')
    d.add_edge(d.nodes[4], d.nodes[14], line_style=DASHED, target_style=OPEN, label='stores data on')
    d.add_edge(d.nodes[1], d.nodes[10], line_style=DASHED, target_style=OPEN, label='depends on')
    return d


for mode in ['straight', 'orthogonal', 'sugiyama', 'elk']:
    d = build_diagram()
    if mode == 'elk':
        c = Canvas()
        # elk sets node positions and edge waypoints via apply_elk_result
        try:
            layout_with_elk(d, node_modules='/home/jfox/boxes/node_modules')
            for e in d.edges:
                if not e.waypoints:
                    c.set_text(10, 10, 'ELKJS FAILED')
            for n in d.nodes:
                from diagramboxes.primitives import draw_class_box
                draw_class_box(c, n.x, n.y, n.x + n.w, n.y + n.h, n.name, n.stereotypes)
            for e in d.edges:
                from diagramboxes.primitives import draw_polyline
                if e.waypoints:
                    draw_polyline(c, e.waypoints, line_style=e.line_style,
                                  source=e.source_style, target=e.target_style, label=e.label)
            result = c.frame()
        except Exception as ex:
            result = f'ELK ERROR: {ex}'
    else:
        result = d.render(routing=mode)

    print(f'===== {mode.upper()} =====')
    print(result)
    print()
