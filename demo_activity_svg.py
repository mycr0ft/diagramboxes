#!/usr/bin/env python3
"""SVG version of activity diagram control nodes demo."""

from diagramboxes import Diagram, OPEN

d = Diagram()

start = d.add_start('go')
fork = d.add_fork('fork', w=36, h=4)
action1 = d.add_node('DoThis', ['action'], rounded=True)
action2 = d.add_node('DoThat', ['action'], rounded=True)
join = d.add_join('join', w=36, h=4)
dec = d.add_decision('ok?', size=28)
action3 = d.add_node('WrapUp', ['action'], rounded=True)
merge = d.add_merge('merge', size=28)
done = d.add_done('done')
term = d.add_terminate('kill')

d.add_edge(start, fork, source_style=None, target_style=None)
d.add_edge(fork, action1, source_style=None, target_style=OPEN)
d.add_edge(fork, action2, source_style=None, target_style=OPEN)
d.add_edge(action1, join, source_style=None, target_style=OPEN)
d.add_edge(action2, join, source_style=None, target_style=OPEN)
d.add_edge(join, dec, source_style=None, target_style=OPEN)
d.add_edge(dec, action3, label='yes', source_style=None, target_style=OPEN)
d.add_edge(dec, term, label='no', source_style=None, target_style=OPEN)
d.add_edge(action3, merge, source_style=None, target_style=OPEN)
d.add_edge(merge, done, source_style=None, target_style=OPEN)

svg = d.render_svg(routing='orthogonal', node_gap=20, layer_gap=30)
path = '/tmp/boxes_activity.svg'
with open(path, 'w') as f:
    f.write(svg)
print(f'Saved SVG ({len(svg)} chars) to {path}')
