#!/usr/bin/env python3
"""Composite-node nesting demo (v0.4.0 layout pass).

Shows nodes nested inside composite parents — part assemblies and
nested state machines — with internal edges routed inside the parent
and cross-boundary edges re-anchored to the outermost ancestor.
"""

from diagramboxes import Diagram, FILLED

# ── structural: part assembly ────────────────────────────────────────
d = Diagram()
vehicle = d.add_node('Vehicle', ['part def'], rounded=True)
engine = d.add_node('Engine', ['part'], parent=vehicle, rounded=True)
gearbox = d.add_node('Gearbox', ['part'], parent=vehicle, rounded=True)
pump = d.add_node('Pump', ['part'], parent=vehicle, rounded=True)
tank = d.add_node('Tank', ['part'], rounded=True)
d.add_edge(pump, tank, label='supply')                            # crosses boundary
d.add_edge(engine, gearbox, target_style=FILLED, label='drives')  # internal

print(d.render(routing='orthogonal'))
print()

# ── behavioural: nested state machine ───────────────────────────────
d = Diagram()
sm = d.add_node('SM', ['state def'], rounded=True)
idle = d.add_node('Idle', ['state'], parent=sm, rounded=True)
run = d.add_node('Running', ['state'], parent=sm, rounded=True)
spin = d.add_node('Spinning', ['state'], parent=run, rounded=True)
stop = d.add_node('Stopped', ['state'], parent=run, rounded=True)
start = d.add_start(parent=sm)
final = d.add_final_state(parent=run)
d.add_edge(start, idle, target_style=None)   # initial transition
d.add_edge(idle, run, label='t1')
d.add_edge(run, stop, label='t2')
d.add_edge(spin, final, target_style=None)

print(d.render(routing='orthogonal'))
print()
open('nested_sm.svg', 'w').write(d.render_svg(routing='orthogonal'))
print('wrote nested_sm.svg')