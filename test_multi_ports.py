#!/usr/bin/env python3
"""Stress test: multiple ports per side with auto-distribution.

Pure interconnection-style port flow — every edge is a connector between
an explicit ``source_port`` and ``target_port`` (open arrow at target).
No structural relationships are mixed in; composition / aggregation is
exercised in ``test_composition.py`` instead.
"""

from diagramboxes import Diagram, OPEN, TRIANGLE, FILLED, DIAMOND, DASHED

d = Diagram()

# A hub node with many ports on each side
hub = d.add_node('Hub', ['block'], attributes=['+ route()', '# max_conn : int'])

# Surrounding leaf nodes
left_a   = d.add_node('LeftA', ['part'])
left_b   = d.add_node('LeftB', ['part'])
left_c   = d.add_node('LeftC', ['part'])
right_a  = d.add_node('RightA', ['part'])
right_b  = d.add_node('RightB', ['part'])
top_a    = d.add_node('TopA', ['part'])
top_b    = d.add_node('TopB', ['part'])
bot_a    = d.add_node('BotA', ['part'])
bot_b    = d.add_node('BotB', ['part'])

# Add multiple auto-distributed ports on each side of hub
hub_l1 = hub.add_port('L1', side='left', direction='in')
hub_l2 = hub.add_port('L2', side='left', direction='in')
hub_l3 = hub.add_port('L3', side='left', direction='in')
hub_r1 = hub.add_port('R1', side='right', direction='out')
hub_r2 = hub.add_port('R2', side='right', direction='out')
hub_t1 = hub.add_port('T1', side='top', direction='in')
hub_t2 = hub.add_port('T2', side='top', direction='in')
hub_b1 = hub.add_port('B1', side='bottom', direction='out')
hub_b2 = hub.add_port('B2', side='bottom', direction='out')

# Single ports on leaf nodes
la_in  = left_a.add_port('in',  side='right', direction='in')
lb_in  = left_b.add_port('in',  side='right', direction='in')
lc_in  = left_c.add_port('in',  side='right', direction='in')
ra_out = right_a.add_port('out', side='left', direction='out')
rb_out = right_b.add_port('out', side='left', direction='out')
ta_out = top_a.add_port('out', side='bottom', direction='out')
tb_out = top_b.add_port('out', side='bottom', direction='out')
ba_out = bot_a.add_port('out', side='top', direction='out')
bb_out = bot_b.add_port('out', side='top', direction='out')

# Top-down edges (tree)
d.add_edge(left_a, hub, source_port=la_in, target_port=hub_l1,
           target_style=OPEN, label='conn1')
d.add_edge(left_b, hub, source_port=lb_in, target_port=hub_l2,
           target_style=OPEN, label='conn2')
d.add_edge(left_c, hub, source_port=lc_in, target_port=hub_l3,
           target_style=OPEN, label='conn3')

d.add_edge(hub, right_a, source_port=hub_r1, target_port=ra_out,
           target_style=OPEN, label='out1')
d.add_edge(hub, right_b, source_port=hub_r2, target_port=rb_out,
           target_style=OPEN, label='out2')

d.add_edge(top_a, hub, source_port=ta_out, target_port=hub_t1,
           target_style=OPEN, label='top1')
d.add_edge(top_b, hub, source_port=tb_out, target_port=hub_t2,
           target_style=OPEN, label='top2')

d.add_edge(hub, bot_a, source_port=hub_b1, target_port=ba_out,
           target_style=OPEN, label='bot1')
d.add_edge(hub, bot_b, source_port=hub_b2, target_port=bb_out,
           target_style=OPEN, label='bot2')

# Also add a port-to-port edge between two left leaves to test lateral edges
la_out = left_a.add_port('extra', side='left', direction='out')
lc_in2 = left_c.add_port('extra', side='right', direction='in')
d.add_edge(left_a, left_c, source_port=la_out, target_port=lc_in2,
           line_style=DASHED, target_style=OPEN, label='lateral')

print(d.render(routing='pyelk', node_gap=40))
