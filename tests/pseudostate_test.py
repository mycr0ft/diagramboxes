#!/usr/bin/env python3
"""Tests for state-machine pseudostate primitives and classes."""
from __future__ import annotations

import pytest

from diagramboxes import (
    Diagram, Node, Edge, Port,
    StartNode, DoneNode, TerminateNode, ForkJoinNode, DecisionNode,
    # state-machine aliases
    InitialPseudostate, JunctionPseudostate, ChoicePseudostate,
    ForkPseudostate, JoinPseudostate, FinalState, TerminatePseudostate,
    HistoryPseudostate, EntryPoint, ExitPoint, StateNode,
    OPEN, NONE,
)
from diagramboxes.primitives import draw_history_node, draw_entry_exit_point
from diagramboxes.svg_canvas import svg_draw_history_node, svg_draw_entry_exit_point


# ── class hierarchy ──

def test_aliases_subclass_activity_nodes():
    assert issubclass(InitialPseudostate, StartNode)
    assert issubclass(JunctionPseudostate, StartNode)
    assert issubclass(ChoicePseudostate, DecisionNode)
    assert issubclass(ForkPseudostate, ForkJoinNode)
    assert issubclass(JoinPseudostate, ForkJoinNode)
    assert issubclass(FinalState, DoneNode)
    assert issubclass(TerminatePseudostate, TerminateNode)


def test_entry_exit_points_subclass_port():
    assert issubclass(EntryPoint, Port)
    assert issubclass(ExitPoint, Port)


def test_history_pseudostate_has_deep_flag():
    h_shallow = HistoryPseudostate()
    h_deep = HistoryPseudostate(deep=True)
    assert h_shallow.deep is False
    assert h_deep.deep is True


def test_history_pseudostate_has_layout_attrs():
    h = HistoryPseudostate(r=8)
    assert h.w == h.h == 18
    # cx/cy are properties
    h.x, h.y = 40, 60
    assert h.cx == 49
    # y+half-height; y*h = 60*18 with //2 = 9 → cy = 69
    assert h.cy == 69
    assert h.box() == (40, 60, 58, 78)


def test_state_node_defaults_to_state_stereotype():
    s = StateNode('on')
    assert s.stereotypes == ['state']
    assert s.rounded is True
    assert s.substates == []


def test_state_node_substates_kept():
    inner = StateNode('Running')
    outer = StateNode('Operational', substates=[inner])
    assert outer.substates == [inner]


def test_state_node_explicit_stereotypes_respected():
    s = StateNode('Off', stereotypes=['composite'])
    assert s.stereotypes == ['composite']


# ── Diagram add_* factory methods ──

def test_diagram_add_initial():
    d = Diagram()
    i = d.add_initial()
    assert isinstance(i, InitialPseudostate)
    assert i in d.activities


def test_diagram_add_junction():
    d = Diagram()
    j = d.add_junction('J1')
    assert isinstance(j, JunctionPseudostate)
    assert j.name == 'J1'


def test_diagram_add_choice():
    d = Diagram()
    c = d.add_choice('pick')
    assert isinstance(c, ChoicePseudostate)


def test_diagram_add_fork_pseudostate():
    d = Diagram()
    f = d.add_fork_pseudostate()
    assert isinstance(f, ForkPseudostate)


def test_diagram_add_join_pseudostate():
    d = Diagram()
    j = d.add_join_pseudostate()
    assert isinstance(j, JoinPseudostate)


def test_diagram_add_final_state():
    d = Diagram()
    fin = d.add_final_state()
    assert isinstance(fin, FinalState)


def test_diagram_add_terminate():
    d = Diagram()
    t = d.add_terminate()
    assert isinstance(t, TerminatePseudostate)


def test_diagram_add_history_shallow_and_deep():
    d = Diagram()
    sh = d.add_history()
    dp = d.add_history(deep=True)
    assert isinstance(sh, HistoryPseudostate) and sh.deep is False
    assert isinstance(dp, HistoryPseudostate) and dp.deep is True


def test_diagram_add_state_returns_state_node():
    d = Diagram()
    s = d.add_state('On')
    assert isinstance(s, StateNode)
    assert s in d.nodes


def test_diagram_add_entry_point_on_state():
    d = Diagram()
    s = d.add_state('On')
    ep = d.add_entry_point(s, 'enter', side='left')
    assert isinstance(ep, EntryPoint)
    assert ep.parent is s
    assert ep.kind == 'entry'
    assert ep in s.ports


def test_diagram_add_exit_point_on_state():
    d = Diagram()
    s = d.add_state('On')
    xp = d.add_exit_point(s, 'leave', side='right')
    assert isinstance(xp, ExitPoint)
    assert xp.parent is s
    assert xp.kind == 'exit'
    assert xp in s.ports


# ── rendering end-to-end ──

def test_render_with_all_pseudostates_does_not_raise():
    d = Diagram()
    s = d.add_state('On')
    i = d.add_initial()
    j = d.add_junction('J1')
    c = d.add_choice('audit')
    f = d.add_fork_pseudostate()
    jo = d.add_join_pseudostate()
    fin = d.add_final_state()
    te = d.add_terminate()
    h1 = d.add_history()
    h2 = d.add_history(deep=True)
    d.add_edge(i, s, target_style=NONE)
    d.add_edge(s, c, target_style=NONE)
    d.add_edge(c, j, target_style=NONE, label='ok')
    d.add_edge(j, f, target_style=NONE)
    d.add_edge(f, jo, target_style=NONE)
    d.add_edge(jo, fin, target_style=NONE)
    d.add_edge(s, te, target_style=NONE, label='kill')
    d.add_edge(s, h1, target_style=NONE)
    d.add_edge(s, h2, target_style=NONE)
    out = d.render(routing='orthogonal')
    assert isinstance(out, str)
    assert 'On' in out


def test_render_svg_with_all_pseudostates_does_not_raise():
    d = Diagram()
    s = d.add_state('On')
    i = d.add_initial()
    j = d.add_junction()
    c = d.add_choice()
    f = d.add_fork_pseudostate()
    jo = d.add_join_pseudostate()
    fin = d.add_final_state()
    te = d.add_terminate()
    h = d.add_history(deep=True)
    d.add_edge(i, s, target_style=NONE)
    d.add_edge(s, c, target_style=NONE)
    d.add_edge(c, j, target_style=NONE)
    d.add_edge(j, f, target_style=NONE)
    d.add_edge(f, jo, target_style=NONE)
    d.add_edge(s, h, target_style=NONE)
    svg = d.render_svg(routing='orthogonal')
    assert svg.lstrip().startswith('<svg')
    # state stereotype emitted
    assert '\u00abstate\u00bb' in svg


def test_render_renders_entry_exit_points():
    d = Diagram()
    outer = d.add_state('Operational')
    ep = d.add_entry_point(outer, 'enter', side='left', offset=0.3)
    xp = d.add_exit_point(outer, 'exit', side='right', offset=0.7)
    inner = d.add_state('Running')
    d.add_edge(outer, inner, source_port=ep, target_style=NONE)
    d.add_edge(inner, outer, target_port=xp, target_style=NONE)
    svg = d.render_svg(routing='orthogonal')
    assert svg.lstrip().startswith('<svg')


def test_render_with_history_and_terminals():
    d = Diagram()
    s = d.add_state('On')
    h = d.add_history(deep=True)
    fin = d.add_final_state()
    d.add_edge(s, h, target_style=NONE, label='resume')
    d.add_edge(s, fin, target_style=NONE, label='done')
    svg = d.render_svg(routing='orthogonal')
    assert 'H*' in svg


# ── primitive drawing functions (smoke tests) ──

def test_draw_history_node_smoke():
    from drawille import Canvas
    c = Canvas()
    draw_history_node(c, 30, 30, 6)
    # one braille character = 2×4 px; expect the canvas is non-empty
    assert len(c.frame()) > 0


def test_draw_entry_exit_point_smoke():
    from drawille import Canvas
    c = Canvas()
    draw_entry_exit_point(c, 30, 30, 6, label='in', kind='entry')
    assert len(c.frame()) > 0


def test_svg_draw_history_node_smoke():
    from diagramboxes.svg_canvas import SvgCanvas
    c = SvgCanvas()
    svg_draw_history_node(c, 30, 30, 6, deep=True)
    out = c.output(width=80, height=80)
    assert '<circle' in out
    assert 'H*' in out


def test_svg_draw_entry_exit_point_smoke():
    from diagramboxes.svg_canvas import SvgCanvas
    c = SvgCanvas()
    svg_draw_entry_exit_point(c, 30, 30, 6, label='in', kind='entry')
    out = c.output(width=80, height=80)
    assert '<circle' in out
    assert 'in' in out