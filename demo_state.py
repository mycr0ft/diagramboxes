#!/usr/bin/env python3
"""Demo: a small UML/SysML state-machine diagram showing every pseudostate.

Run with:
    poetry run python demo_state.py            # braille terminal output
    poetry run python demo_state_svg.py        # SVG output to /tmp/diagram_state.svg
"""
from diagramboxes import Diagram, NONE, OPEN


d = Diagram()

# Real states
off  = d.add_state('Off', attributes=['entry / powerOn()', 'exit / powerOff()'])
on   = d.add_state('On',  attributes=['entry / ignite()',  'exit / quench()'])
run  = d.add_state('Running', attributes=['do / spin()'])
fail = d.add_state('Failed')

# Composite state (parent with substate) — show conceptual nesting via layout
# (substates currently still render as siblings; nested rendering is a
# planned enhancement)
standby = d.add_state('Standby', substates=[run])

# Pseudostates
init  = d.add_initial()
j1    = d.add_junction('J1')
choice= d.add_choice('audit')
fork  = d.add_fork_pseudostate()
join  = d.add_join_pseudostate()
final = d.add_final_state()
term  = d.add_terminate()
hsh   = d.add_history()              # shallow H
hdp   = d.add_history(deep=True)     # deep H*

# Boundary points on composite state
enter = d.add_entry_point(on, 'enter', side='left', offset=0.25, direction='in')
leave = d.add_exit_point(on, 'leave', side='right', offset=0.25, direction='out')

# ── edges: exercise every pseudostate ──
d.add_edge(init, off, target_style=NONE)
d.add_edge(off, on, source_port=enter, target_style=OPEN, label='START')
d.add_edge(on, choice, target_style=NONE, label='tick')
d.add_edge(choice, run, target_style=OPEN, label='ok')
d.add_edge(choice, fail, target_style=OPEN, label='bad')
d.add_edge(run, join, target_style=NONE)
d.add_edge(fail, join, target_style=NONE, label='reset')
d.add_edge(join, final, target_style=OPEN)
d.add_edge(on, term, source_port=leave, target_style=OPEN, label='abort')
d.add_edge(on, hsh, target_style=NONE)
d.add_edge(on, hdp, target_style=NONE)
d.add_edge(choice, j1, target_style=NONE, label='retry')
d.add_edge(j1, fork, target_style=NONE)
d.add_edge(fork, run, target_style=OPEN)
d.add_edge(fork, standby, target_style=OPEN)

# Render
print(d.render(routing='orthogonal', node_gap=20, layer_gap=50))