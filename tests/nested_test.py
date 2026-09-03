"""Composite-node nesting tests (diagramboxes v0.4.0 layout pass).

Covers: parent/children wiring, composite sizing, child placement
inside the parent box, internal (same-parent) edge routing clipped at
child boundaries, cross-boundary edge re-anchoring to the outermost
ancestor, parented pseudostates (start/final inside composites), and
both renderers.
"""

from diagramboxes import (
    Diagram, Edge, FILLED, StartNode, DoneNode,
)
from diagramboxes.layout import Node


def _inside(child, parent):
    return (parent.x <= child.x
            and child.x + child.w <= parent.x + parent.w
            and parent.y <= child.y
            and child.y + child.h <= parent.y + parent.h)


def _make_nested_diagram():
    d = Diagram()
    vehicle = d.add_node('Vehicle', ['part def'], rounded=True)
    engine = d.add_node('Engine', ['part'], parent=vehicle, rounded=True)
    gearbox = d.add_node('Gearbox', ['part'], parent=vehicle, rounded=True)
    pump = d.add_node('Pump', ['part'], parent=vehicle, rounded=True)
    tank = d.add_node('Tank', ['part'], rounded=True)
    d.add_edge(pump, tank, label='supply')
    d.add_edge(engine, gearbox, target_style=FILLED, label='drives')
    return d, vehicle, engine, gearbox, pump, tank


class TestNestingStructure:
    def test_add_node_parent_wiring(self):
        d = Diagram()
        p = d.add_node('P')
        c = d.add_node('C', parent=p)
        assert c.parent is p
        assert c in p.children
        assert c in d.nodes  # still registered globally

    def test_node_add_child(self):
        d = Diagram()
        p = d.add_node('P')
        c = d.add_node('C')
        p.add_child(c)
        assert c.parent is p and c in p.children

    def test_leaf_nodes_unaffected(self):
        d = Diagram()
        a = d.add_node('A')
        b = d.add_node('B')
        d.add_edge(a, b)
        d.layout(routing='orthogonal')
        assert not a.children and a.parent is None


class TestNestedLayout:
    def test_children_inside_parent(self):
        d, vehicle, engine, gearbox, pump, tank = _make_nested_diagram()
        d.layout(routing='orthogonal')
        for c in (engine, gearbox, pump):
            assert _inside(c, vehicle), c.name

    def test_parent_inflated_to_contain_children(self):
        d, vehicle, engine, gearbox, pump, tank = _make_nested_diagram()
        d.layout(routing='orthogonal')
        # Vehicle must be at least as wide as its widest row of children
        row_w = max(engine.w + gearbox.w + 4, pump.w)
        assert vehicle.w >= row_w
        assert vehicle.h >= engine.h + gearbox.h + pump.h

    def test_internal_edge_clipped_at_boundaries(self):
        d, vehicle, engine, gearbox, pump, tank = _make_nested_diagram()
        d.layout(routing='orthogonal')
        internal = [e for e in d.edges
                    if getattr(e, '_nested_internal', False)]
        assert len(internal) == 1
        e = internal[0]
        assert e.source is engine and e.target is gearbox
        (sx, sy), (tx, ty) = e.waypoints
        # waypoints sit on the engine/gearbox borders, not at centres
        assert (sx, sy) != (engine.cx, engine.cy)
        assert (tx, ty) != (gearbox.cx, gearbox.cy)

    def test_cross_boundary_edge_reanchored_to_ancestor(self):
        d, vehicle, engine, gearbox, pump, tank = _make_nested_diagram()
        d.layout(routing='orthogonal')
        supply = next(e for e in d.edges if e.label == 'supply')
        assert supply.source is vehicle and supply.target is tank
        assert supply._nested_orig[0].name == 'Pump'

    def test_internal_edges_excluded_from_layering(self):
        d, vehicle, engine, gearbox, pump, tank = _make_nested_diagram()
        layers, layer_of = d._assign_layers()
        for lyr in layers:
            for n in lyr:
                assert n in (vehicle, tank)

    def test_deep_nesting_two_levels(self):
        d = Diagram()
        sm = d.add_node('SM', ['state def'], rounded=True)
        run = d.add_node('Running', ['state'], parent=sm, rounded=True)
        spin = d.add_node('Spinning', ['state'], parent=run, rounded=True)
        d.layout(routing='orthogonal')
        assert _inside(run, sm)
        assert _inside(spin, run)

    def test_no_double_inflation(self):
        d, vehicle, engine, gearbox, pump, tank = _make_nested_diagram()
        d._size_nested_tree()
        h1 = vehicle.h
        d._size_nested_tree()
        assert vehicle.h == h1  # idempotent


class TestParentedActivities:
    def _state_machine(self):
        d = Diagram()
        sm = d.add_node('SM', ['state def'], rounded=True)
        idle = d.add_node('Idle', ['state'], parent=sm, rounded=True)
        run = d.add_node('Running', ['state'], parent=sm, rounded=True)
        spin = d.add_node('Spinning', ['state'], parent=run, rounded=True)
        stop = d.add_node('Stopped', ['state'], parent=run, rounded=True)
        start = d.add_start(parent=sm)
        final = d.add_final_state(parent=run)
        d.add_edge(start, idle, target_style=None)
        d.add_edge(idle, run, label='t1')
        d.add_edge(run, stop, label='t2')
        d.add_edge(spin, final, target_style=None)
        return d, sm, idle, run, spin, stop, start, final

    def test_pseudostates_inside_composites(self):
        d, sm, idle, run, spin, stop, start, final = self._state_machine()
        d.layout(routing='orthogonal')
        assert _inside(start, sm)
        assert _inside(final, run)
        for n in (idle, run):
            assert _inside(n, sm)
        for n in (spin, stop):
            assert _inside(n, run)

    def test_internal_transitions(self):
        d, sm, idle, run, spin, stop, start, final = self._state_machine()
        d.layout(routing='orthogonal')
        internal = [(e.source.name, e.target.name) for e in d.edges
                    if getattr(e, '_nested_internal', False)]
        assert ('Start', 'Idle') in internal
        assert ('Idle', 'Running') in internal
        assert ('Running', 'Stopped') in internal
        assert ('Spinning', 'final') in internal

    def test_unparented_activities_still_top_level(self):
        d = Diagram()
        d.add_start()
        d.add_node('A')
        d.layout(routing='orthogonal')
        assert d.activities[0].parent is None


class TestNestedRendering:
    def test_braille_render_contains_nested_text(self):
        d, vehicle, engine, gearbox, pump, tank = _make_nested_diagram()
        frame = d.render(routing='orthogonal')
        for name in ('Vehicle', 'Engine', 'Gearbox', 'Pump', 'Tank'):
            assert name in frame

    def test_svg_render_contains_nested_text(self):
        d, vehicle, engine, gearbox, pump, tank = _make_nested_diagram()
        svg = d.render_svg(routing='orthogonal')
        for name in ('Vehicle', 'Engine', 'Gearbox', 'Pump', 'Tank'):
            assert name in svg

    def test_svg_nested_rects_contained(self):
        import re
        d, vehicle, engine, gearbox, pump, tank = _make_nested_diagram()
        svg = d.render_svg(routing='orthogonal')
        rects = [(float(m.group(1)), float(m.group(2)),
                  float(m.group(3)), float(m.group(4)))
                 for m in re.finditer(
                     r'<rect x="([\d.]+)" y="([\d.]+)" '
                     r'width="([\d.]+)" height="([\d.]+)"', svg)]
        assert len(rects) == 5
        vx, vy, vw, vh = max(rects, key=lambda r: r[2] * r[3])
        for x, y, w, h in rects:
            if (x, y, w, h) == (vx, vy, vw, vh):
                continue
            inside = (vx <= x and x + w <= vx + vw
                      and vy <= y and y + h <= vy + vh)
            overlaps = not (x + w < vx or x > vx + vw
                            or y + h < vy or y > vy + vh)
            # child rects sit fully inside; the top-level Tank rect
            # sits fully outside — nothing may partially overlap
            assert inside or not overlaps

    def test_other_engines_place_children(self):
        d, vehicle, engine, gearbox, pump, tank = _make_nested_diagram()
        d.layout(routing='sugiyama')
        assert _inside(engine, vehicle)