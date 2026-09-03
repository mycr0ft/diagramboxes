#!/usr/bin/env python3
"""Individual SVG files for each convenience method and arrowhead style."""

from diagramboxes import Diagram, DEFINITION, REDEFINITION, REFERENCE_SUBSETTING, PORTION

def build(label, setup):
    d = Diagram()
    setup(d)
    svg = d.render_svg()
    name = label.lower().replace(' ', '_').replace('-', '_')
    path = f'/tmp/boxes_{name}.svg'
    with open(path, 'w') as f:
        f.write(svg)
    print(f'{label:20s} → {path}  ({len(svg)} chars)')

# ── convenience methods ──
build('Composition', lambda d:
    d.compose(d.add_node('Vehicle'), d.add_node('Engine'), label='composed of'))
build('Aggregation', lambda d:
    d.aggregate(d.add_node('Team'), d.add_node('Person'), label='member of'))
build('Generalization', lambda d:
    d.generalize(d.add_node('Mammal'), d.add_node('Animal'), label='kind of'))
build('Dependency', lambda d:
    d.depend(d.add_node('Logger'), d.add_node('Sensor'), label='reads'))
build('Annotation', lambda d:
    d.annotate(d.add_node('Model'), d.add_node('Spec'), label='annotated by'))

# ── custom arrowhead styles ──
build('Definition', lambda d:
    d.add_edge(d.add_node('Source'), d.add_node('Target'),
               target_style=DEFINITION, label='definition'))
build('Redefinition', lambda d:
    d.add_edge(d.add_node('A'), d.add_node('B'),
               target_style=REDEFINITION, label='redefinition'))
build('Ref-subsetting', lambda d:
    d.add_edge(d.add_node('X'), d.add_node('Y'),
               target_style=REFERENCE_SUBSETTING, label='ref-subset'))
build('Portion', lambda d:
    d.add_edge(d.add_node('Src'), d.add_node('Dst'),
               target_style=PORTION, label='portion'))
