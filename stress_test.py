#!/usr/bin/env python3
"""Stress test: system architecture with ports, attributes, and mixed routing."""

from diagramboxes import Diagram, OPEN, TRIANGLE, FILLED, DIAMOND, DASHED

d = Diagram()

# Layer 0
system = d.add_node('System', ['block'])

# Layer 1
sub_a  = d.add_node('SubsystemA', ['block'])
sub_b  = d.add_node('SubsystemB', ['block'])
psu    = d.add_node('PowerSupply', ['block'],
    attributes=['+ voltage : 12V', '+ current : 5A'])

# Layer 2
ctrl   = d.add_node('Controller', ['part'],
    attributes=['+ process()', '# timeout : int'])
sensor = d.add_node('SensorArray',  ['part'])
act    = d.add_node('Actuator', ['part'])
bat    = d.add_node('Battery')

# Layer 3
mcu    = d.add_node('MCU', attributes=['+ clock : 48MHz'])
mem    = d.add_node('Memory')
wifi   = d.add_node('Wireless')
therm  = d.add_node('Thermometer')
motor  = d.add_node('Motor')
reg    = d.add_node('Regulator')

# Layer 4
flash  = d.add_node('FlashStorage', ['block'])

# Ports on Controller for lateral connections
ctrl_data = ctrl.add_port('data', side='right', direction='out')
ctrl_dbg  = ctrl.add_port('dbg',  side='right', direction='out')

# Ports on MCU
mcu_data  = mcu.add_port('data', side='left', direction='in')
mcu_dbg   = mcu.add_port('dbg',  side='left', direction='in')
mcu_out   = mcu.add_port('out',  side='right', direction='out')

# Ports on Memory
mem_in    = mem.add_port('in',   side='left', direction='in')

# Ports on Wireless
wifi_in   = wifi.add_port('in',  side='left', direction='in')

# ── Edges ──

# Layer 0 → Layer 1 (traditional)
d.add_edge(system, sub_a, source_style=FILLED, target_style=OPEN, label='composed of')
d.add_edge(system, sub_b, source_style=FILLED, target_style=OPEN, label='composed of')
d.add_edge(system, psu,   source_style=FILLED, target_style=OPEN, label='composed of')

# Layer 1 → Layer 2 (traditional)
d.add_edge(sub_a, ctrl,   source_style=FILLED, target_style=OPEN, label='composed of')
d.add_edge(sub_a, sensor, source_style=FILLED, target_style=OPEN, label='composed of')
d.add_edge(sub_b, act,    source_style=FILLED, target_style=OPEN, label='composed of')
d.add_edge(sub_b, wifi,   source_style=FILLED, target_style=OPEN, label='composed of')
d.add_edge(psu,   bat,    target_style=OPEN,   label='powers')
d.add_edge(psu,   reg,    target_style=OPEN,   label='powers')

# Layer 2 → Layer 3 (traditional)
d.add_edge(ctrl, mcu,   source_style=FILLED, target_style=OPEN, label='composed of')
d.add_edge(ctrl, mem,   source_style=FILLED, target_style=OPEN, label='composed of')
d.add_edge(sensor, therm, target_style=TRIANGLE, label='generalizes')
d.add_edge(act,  motor, target_style=TRIANGLE, label='generalizes')

# Port-to-port: Controller → MCU (data bus)
d.add_edge(ctrl, mcu, source_port=ctrl_data, target_port=mcu_data,
           target_style=OPEN, label='data bus')
d.add_edge(ctrl, mcu, source_port=ctrl_dbg, target_port=mcu_dbg,
           line_style=DASHED, target_style=OPEN, label='debug')

# Port-to-port: MCU → Memory
d.add_edge(mcu, mem, source_port=mcu_out, target_port=mem_in,
           target_style=OPEN, label='store')

# Port-to-port: MCU → Wireless
d.add_edge(mcu, wifi, source_port=mcu_out, target_port=wifi_in,
           target_style=OPEN, label='xmit')

# Non-adjacent: Layer 2 → Layer 4 (skips Layer 3)
d.add_edge(ctrl, flash, line_style=DASHED, target_style=OPEN, label='stores data on')

# Cross-hierarchy dependency
d.add_edge(sub_a, wifi,  line_style=DASHED, target_style=OPEN, label='depends on')

print(d.render(routing='orthogonal', node_gap=50))
