"""RED: straight-edge labels must hug their lines (the fan «import»/
«conform»/«apply» labels on Figure 10.3's straight routing drifted up to
200-500 units from their edges because the SVG path placed labels by
Manhattan-midpoint + a fixed band, colliding and cascading). Criteria:
on a 2-point edge, the label sits within 30 svg units of the edge
segment and ABOVE no more than the label's own height band."""
import re
import unittest

from diagramboxes import Diagram


def _label_dist(svg):
    texts = [(float(x), float(y), t) for x, y, t in re.findall(
        r'<text[^>]*x="([\d.]+)" y="([\d.]+)"[^>]*>([^<]*)</text>', svg)]
    labels = [tx for tx in texts if tx[2].startswith('\u00ab')]
    routes = []
    for pts in re.findall(r'<polyline[^>]*points="([^"]*)"', svg):
        seg = [(float(a), float(b)) for a, b in
               (p.split(',') for p in pts.split() if ',' in p)]
        if len(seg) >= 2:
            routes.append(seg)
    for m in re.finditer(r'<line[^>]*x1="([\d.]+)" y1="([\d.]+)" '
                         r'x2="([\d.]+)" y2="([\d.]+)"', svg):
        s = [(float(m.group(1)), float(m.group(2))),
             (float(m.group(3)), float(m.group(4)))]
        if ((s[1][0] - s[0][0]) ** 2 + (s[1][1] - s[0][1]) ** 2) ** .5 > 30:
            routes.append(s)
    if not routes or not labels:
        raise AssertionError('parse found %d routes, %d labels'
                             % (len(routes), len(labels)))
    worst = 0.0
    for lx, ly, _t in labels:
        best = min(_seg_dist(lx, ly, s) for r in routes
                   for s in zip(r, r[1:]))
        worst = max(worst, best)
    return worst


def _seg_dist(px, py, seg):
    (x1, y1), (x2, y2) = seg
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy or 1
    t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / L2))
    cx, cy = x1 + t * dx, y1 + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** .5


class TestStraightEdgeLabel(unittest.TestCase):
    def test_fan_labels_hug_their_lines(self):
        d = Diagram()
        a = d.add_node('View')
        targets = [d.add_node('T%d' % i) for i in range(5)]
        for t in targets:
            d.add_edge(a, t, line_style='dashed',
                       label='«import»')
        svg = d.render_svg(routing='straight')
        worst = _label_dist(svg)
        self.assertLess(worst, 30.0,
                        'a straight-edge label sits %.0f units off its line'
                        % worst)

    def test_orthogonal_labels_still_mid_route(self):
        d = Diagram()
        a = d.add_node('A')
        b = d.add_node('B', at=(160, 220))
        d.add_edge(a, b, line_style='dashed', label='«x»')
        svg = d.render_svg(routing='orthogonal')
        worst = _label_dist(svg)
        self.assertLess(worst, 40.0, 'elbow label off its route by %.0f' % worst)


if __name__ == '__main__':
    unittest.main()