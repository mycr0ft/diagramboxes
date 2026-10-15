#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Use case diagram notation (Delligatti §5.4-5.11, Figures 5.1-5.3):
the uc frame, use case ellipses with the verb-phrase name inside, the
system boundary (subject) rectangle, actors in both notations (stick
figure and «actor» rectangle), actor→use case associations with
multiplicity, and the «include»/«extend» dashed-open-arrow relationships.

Corpus acceptance criteria:
- 'Notation: an ellipse (oval); the use case name ... displayed inside
  or beneath the ellipse (inside is much more common).' (§5.5)
- 'Notation: a rectangle enclosing the use cases — not to be confused
  with the diagram frame. The subject name appears at the top inside
  the rectangle' (§5.6)
- 'Two notations (§3.8): a stick figure, or a rectangle with the
  keyword «actor» preceding the name.' (§5.7)
- 'Notation: a dashed line with an open arrowhead and the keyword
  «include» floating next to it' (§5.10); same form for «extend» (§5.11)
"""

import re

from diagramboxes import (Diagram, OPEN, DASHED, to_di, from_di,
                          to_di_xmi, from_di_xmi)


def test_usecase_is_ellipse_named_inside():
    d = Diagram()
    d.add_frame('uc', element_kind='package', element_name='Behavior')
    uc = d.usecase('Execute Hohmann transfer')
    assert getattr(uc, 'is_use_case', False)
    txt = d.render()
    assert 'Execute Hohmann transfer' in txt
    svg = d.render_svg()
    assert '<ellipse' in svg
    assert 'Execute Hohmann transfer' in svg


def test_actor_stick_figure_and_label_below():
    d = Diagram()
    d.add_frame('uc', element_kind='package', element_name='Behavior')
    a = d.actor('Flight Controller')
    assert getattr(a, 'is_stick_figure', False)
    txt = d.render()
    assert 'Flight Controller' in txt
    svg = d.render_svg()
    assert 'Flight Controller' in svg
    # stick figure parts: a head circle and a vertical body line
    assert '<circle' in svg


def test_actor_rectangle_notation():
    d = Diagram()
    d.add_frame('uc', element_kind='package', element_name='Behavior')
    a = d.actor('DellSat-77 Ground Station', stick_figure=False)
    assert a.stereotypes == ['actor']
    assert a.name == 'DellSat-77 Ground Station'
    assert 'Ground Station' in d.render()


def test_subject_encloses_use_cases():
    d = Diagram()
    d.add_frame('uc', element_kind='package', element_name='Behavior')
    sb = d.subject('DellSat-77 Satellite')
    uc1 = d.usecase('Generate electricity from solar panels')
    sb.add_child(uc1)
    d.render()
    # the subject node's bounds contain the use case's bounds
    assert sb.x <= uc1.x and uc1.x + uc1.w <= sb.x + sb.w
    assert sb.y <= uc1.y
    assert 'DellSat-77 Satellite' in d.render()


def test_include_and_extend_are_dashed_open_named():
    d = Diagram()
    base = d.usecase('Execute Hohmann transfer')
    inc = d.usecase('Send command')
    ext = d.usecase('Abort via safing')
    i = d.include(base, inc)
    e = d.extend(ext, base)
    for rel, kw in ((i, 'include'), (e, 'extend')):
        assert rel.line_style == DASHED
        assert rel.target_style == OPEN
        assert kw in (rel.label or '')
    assert '«include»' in d.render()
    assert '«extend»' in d.render()


def test_actor_usecase_association_with_multiplicity():
    d = Diagram()
    a = d.actor('Radar Operator')
    uc = d.usecase('Track satellite trajectory')
    e = d.association(a, uc, source_label='1..2', target_label='0..*')
    assert e.line_style != DASHED          # solid
    assert e.source_style in (None, 'none')  # plain association line
    txt = d.render()
    assert '1..2' in txt and '0..*' in txt


def test_usecase_generalization():
    d = Diagram()
    sup = d.usecase('Send command')
    sub = d.usecase('Send real-time command')
    g = d.generalize(sub, sup)
    assert g.target_style == 'triangle'
    assert 'Send real-time command' in d.render()


def test_usecase_round_trips_di_and_xmi():
    d = Diagram()
    d.add_frame('uc', element_kind='package', element_name='Behavior')
    sb = d.subject('DellSat-77 Satellite')
    base = d.usecase('Execute Hohmann transfer')
    sb.add_child(base)
    fc = d.actor('Flight Controller')
    inc = d.usecase('Send command')
    sub = d.usecase('Send real-time command')
    d.generalize(sub, inc)
    d.include(base, inc)
    d.association(fc, base, target_label='0..*')
    for payload in (to_di(d), to_di_xmi(to_di(d))):
        d2 = (from_di(from_di_xmi(payload)) if isinstance(payload, str)
              else from_di(payload))
        top = d2.nodes
        kids = [c for n in top for c in n.children]
        ucs = [n for n in top + kids if getattr(n, 'is_use_case', False)]
        actors = [n for n in top + kids if getattr(n, 'is_actor', False)]
        assert len(ucs) == 3 and len(actors) == 1
        assert any(getattr(n, 'is_stick_figure', False)
                   for n in actors)
        assert [n.name for n in d2.nodes if n.stereotypes] == []
        rel = [e for e in d2.edges if (e.label or '') == '«include»']
        assert len(rel) == 1 and rel[0].line_style == DASHED
        d2.render()
        assert '«include»' in d2.render()