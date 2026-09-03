#!/usr/bin/env python3
"""Demo: render the same state machine as demo_state.py, but as SVG."""
from diagramboxes import Diagram, NONE, OPEN


d = Diagram()
off  = d.add_state('Off', attributes=['entry / powerOn()', 'exit / powerOff()'])
on   = d.add_state('On',  attributes=['entry / ignite()',  'exit / quench()'])
run  = d.add_state('Running', attributes=['do / spin()'])
fail = d.add_state('Failed')
standby = d.add_state('Standby', substates=[run])

init  = d.add_initial()
j1    = d.add_junction('J1')
choice= d.add_choice('audit')
fork  = d.add_fork_pseudostate()
join  = d.add_join_pseudostate()
final = d.add_final_state()
term  = d.add_terminate()
hsh   = d.add_history()
hdp   = d.add_history(deep=True)

enter = d.add_entry_point(on, 'enter', side='left', offset=0.25, direction='in')
leave = d.add_exit_point(on, 'leave', side='right', offset=0.25, direction='out')

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

svg = d.render_svg(routing='orthogonal', scale=1.5)
out_path = '/tmp/diagram_state.svg'
with open(out_path, 'w') as f:
    f.write(svg)
print(f'Wrote {out_path} ({len(svg)} bytes)')