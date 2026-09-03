#!/usr/bin/env python3
"""Demo of all convenience methods and arrowhead styles."""

from diagramboxes import Diagram, DEFINITION, REDEFINITION, REFERENCE_SUBSETTING, PORTION

def show(title, f):
    d = Diagram()
    f(d)
    print(f'\n  {title}')
    print(d.render(node_gap=20))

show('Composition (filled diamond at whole)', lambda d:
    d.compose(d.add_node('Vehicle'), d.add_node('Engine'), label='composed of'))

show('Aggregation (empty diamond at whole)', lambda d:
    d.aggregate(d.add_node('Team'), d.add_node('Person'), label='member of'))

show('Generalization (open triangle at parent)', lambda d:
    d.generalize(d.add_node('Mammal'), d.add_node('Animal'), label='kind of'))

show('Dependency (dashed, open arrow at supplier)', lambda d:
    d.depend(d.add_node('Logger'), d.add_node('Sensor'), label='reads'))

show('Annotation (SysMLv2, same style as dependency)', lambda d:
    d.annotate(d.add_node('Model'), d.add_node('Spec'), label='annotated by'))

show('Definition arrowhead (triangle + ÷-style dots)', lambda d:
    d.add_edge(d.add_node('Source'), d.add_node('Target'),
               target_style=DEFINITION, label='definition'))

show('Redefinition arrowhead (triangle + bar)', lambda d:
    d.add_edge(d.add_node('A'), d.add_node('B'),
               target_style=REDEFINITION, label='redefinition'))

show('Reference-subsetting arrowhead (two pairs of ÷-style dots)', lambda d:
    d.add_edge(d.add_node('X'), d.add_node('Y'),
               target_style=REFERENCE_SUBSETTING, label='ref-subset'))

show('Portion arrowhead (pac-man)', lambda d:
    d.add_edge(d.add_node('Src'), d.add_node('Dst'),
               target_style=PORTION, label='portion'))
