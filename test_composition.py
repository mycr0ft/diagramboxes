#!/usr/bin/env python3
"""Composition / aggregation diagram — structural relationships only.

No ports, no flow connectors.  Exercises the filled-diamond (composition)
and empty-diamond (aggregation) arrowheads without the notational
mixing that an interconnection-style port diagram would never use.
"""

from boxes import Diagram, FILLED, DIAMOND

d = Diagram()

assembly = d.add_node('Assembly', ['block'],
    attributes=['+ mass : Mass', '# state : State'])
part_a = d.add_node('PartA', ['part'],
    attributes=['+ serial : int'])
part_b = d.add_node('PartB', ['part'])
subsystem = d.add_node('Subsystem', ['part'])
shared = d.add_node('SharedResource', ['block'])

d.compose(assembly, part_a, label='has')
d.compose(assembly, part_b, label='has')
d.compose(part_a, subsystem, label='contains')
d.aggregate(part_a, shared, label='uses')

print(d.render(routing='sugiyama', node_gap=40))