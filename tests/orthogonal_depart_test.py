"""RED: edges must DEPART orthogonally from a side, not slide out of a
geometric corner.

Criterion (the gallery review): links leaving/arriving on geometric
corners must depart orthogonally from a side of the element. Applies
to the straight-routing fallback (center-to-center diagonals) and the
svg no-waypoint fallback: each edge's first visible leg must be
axis-parallel (dx == 0 or dy == 0) from a border anchor."""
import math
import re
import unittest

from diagramboxes import Diagram


def _routes(svg):
    out = []
    for pts in re.findall(r'<polyline[^>]*points="([^"]*)"', svg):
        out.append([(float(a), float(b))
                    for a, b in (p.split(',') for p in pts.split())])
    for m in re.finditer(
            r'<line[^>]*x1="([\d.]+)" y1="([\d.]+)" '
            r'x2="([\d.]+)" y2="([\d.]+)"', svg):
        out.append([(float(m.group(1)), float(m.group(2))),
                    (float(m.group(3)), float(m.group(4)))])
    return out


class TestOrthogonalDeparture(unittest.TestCase):
    def build(self):
        d = Diagram()
        a = d.add_node('Source', ['block'], at=(30, 30))
        b = d.add_node('Far Down Right', ['block'], at=(400, 260))
        d.add_edge(a, b, line_style='dashed')
        return d, a, b

    def test_straight_routing_leaves_from_a_side(self):
        d, a, b = self.build()
        d.render(routing='straight')
        e = d.edges[0]
        wps = list(e.waypoints)
        self.assertGreaterEqual(len(wps), 3,
                                'straight edge should carry a stub route')
        first = wps[0]
        on_border = (abs(first[0] - a.x) < 1 or
                     abs(first[0] - (a.x + a.w)) < 1 or
                     abs(first[1] - a.y) < 1 or
                     abs(first[1] - (a.y + a.h)) < 1)
        self.assertTrue(on_border, 'anchor is not on a box side: %s' % (first,))
        self.assertNotIn((a.cx, a.cy), [tuple(p) for p in wps],
                         'route still starts at the box center')

    def test_straight_departure_leg_is_axis_parallel(self):
        d, a, b = self.build()
        d.render(routing='straight')
        e = d.edges[0]
        wps = list(e.waypoints)
        self.assertTrue(wps[0][0] == wps[1][0] or wps[0][1] == wps[1][1],
                        'first leg is not orthogonal: %s' % (wps,))
        # and it ARRIVES axis-parallel at the target too
        self.assertTrue(wps[-1][0] == wps[-2][0] or
                        wps[-1][1] == wps[-2][1],
                        'last leg is not orthogonal: %s' % (wps,))


if __name__ == '__main__':
    unittest.main()