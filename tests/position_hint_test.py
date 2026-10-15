"""Position hints (pins) — fixed coordinates for whole-figure reproduction.

The SysML v2 release SVGs carry exact box positions; reproducing them
needs the renderer to honor those positions instead of its auto-layout.
Pin mode engages only when EVERY node has a hint (partial pinning falls
back to auto-layout, so existing diagrams change nothing).
"""
import os
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), '..', 'diagramboxes'))

from diagramboxes import Diagram


class PositionHintTest(unittest.TestCase):

    def test_pinned_nodes_honor_hints(self):
        d = Diagram()
        a = d.add_node('A', at=(0, 0))
        b = d.add_node('B', at=(120, 0))
        c = d.add_node('C', at=(0, 90))
        d.add_edge(a, b)
        d.add_edge(a, c)
        d.render()
        self.assertEqual((a.x, a.y), (0, 0))
        self.assertEqual((b.x, b.y), (120, 0))
        self.assertEqual((c.x, c.y), (0, 90))

    def test_pinned_vertical_route_clears_side_box(self):
        # A and C stack vertically at x=0; B sits beside the route —
        # the orthogonal channel must not cross B's box
        d = Diagram()
        a = d.add_node('A', at=(0, 0))
        b = d.add_node('B', at=(10, 40))
        c = d.add_node('C', at=(0, 110))
        d.add_edge(a, c)
        d.render()
        e = d.edges[0]
        hit = any(b.x <= w and w <= b.x + b.w and
                  b.y <= h and h <= b.y + b.h
                  for w, h in e.waypoints)
        self.assertFalse(hit, 'route crosses an obstacle node')

    def test_pinned_same_row_edge_uses_facing_sides(self):
        # A |-> B on one row: anchors on the facing vertical sides
        d = Diagram()
        a = d.add_node('A', at=(0, 0))
        b = d.add_node('B', at=(140, 0))
        d.add_edge(a, b)
        d.render()
        e = d.edges[0]
        sx, sy = e.waypoints[0]
        tx, ty = e.waypoints[-1]
        self.assertEqual(sy, a.cy == b.cy and a.cy)  # same row: straight
        self.assertGreater(tx, sx)

    def test_pinned_self_association_routes_loop(self):
        d = Diagram()
        a = d.add_node('B', at=(0, 0))
        d.add_edge(a, a)
        d.render()
        e = d.edges[0]
        self.assertEqual(len(e.waypoints), 4)
        sx, sy = e.waypoints[0]
        self.assertEqual(sx, a.x + a.w)   # leaves the right side
        bx, ly = e.waypoints[-1]
        self.assertGreater(ly, sy)        # re-enters lower

    def test_unpinned_diagram_keeps_auto_layout(self):
        d = Diagram()
        a = d.add_node('A')
        b = d.add_node('B')
        d.add_edge(a, b)
        d.render()
        # auto-layout: layer rows start at the margin, nodes differ
        self.assertNotEqual((a.x, a.y), (b.x, b.y))
        self.assertLess(a.y, b.y)  # B in the second layer below A


if __name__ == '__main__':
    unittest.main()