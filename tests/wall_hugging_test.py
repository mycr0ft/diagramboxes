"""RED: routed edges must not run ALONG a box's wall.

Criterion (the gallery review): leaving the box along the wall overlaps
the box outline and reads as attachment ambiguity. For pairs anchored
top/bottom (vertical ladders) the dodge channel must be a Y-channel:
the edge exits PERPENDICULAR (vertical leg, length >= 8), crosses in
the free band, enters perpendicular. No route may turn within 8px of
the box it departed, and no leg may be collinear with (within 2px of)
the departed box's wall for more than 6px."""
import re
import unittest

from diagramboxes import Diagram


class TestWallHugging(unittest.TestCase):
    def build(self):
        d = Diagram()
        up = d.add_node('Upper', ['block'], at=(60, 30))
        low = d.add_node('Lower', ['block'], at=(160, 200))
        d.add_edge(up, low, line_style='dashed')
        return d, up, low

    def test_ladder_exits_perpendicular_with_clearance(self):
        d, up, low = self.build()
        d.render(routing='orthogonal')
        wps = list(d.edges[0].waypoints)
        self.assertGreaterEqual(len(wps), 3, 'ladder needs a channel route')
        first = wps[0]
        second = wps[1]
        # the first leg leaves PERPENDICULAR from the departed box: the
        # upper box's bottom or top anchor => vertical leg
        self.assertEqual(first[0], second[0],
                         'first leg is not vertical: %s -> %s'
                         % (first, second))
        self.assertGreaterEqual(abs(second[1] - first[1]), 8,
                                'exit leg shorter than clearance 8')

    def test_real_poc_no_wall_hugging(self):
        import os
        script = '/home/jfox/proj/sysml-distilled/reproduced/fig3_1_bdd.py'
        if not os.path.exists(script):
            self.skipTest('PoC script missing')
        os.system('cd /home/jfox/proj/diagramboxes && poetry run python %s '
                  '> /dev/null 2>&1' % script)
        svg = open('/home/jfox/proj/sysml-distilled/reproduced/'
                   'fig3_1.svg').read()
        polys = [[(float(a), float(b)) for a, b in
                  (p.split(',') for p in pts.split())]
                 for pts in re.findall(
                     r'<polyline[^>]*points="([^"]*)"', svg)]
        rects = [(float(m.group(1)), float(m.group(2)),
                  float(m.group(3)), float(m.group(4)))
                 for m in re.finditer(
                     r'<rect[^>]*?x="([\d.]+)" y="([\d.]+)" '
                     r'width="([\d.]+)" height="([\d.]+)"', svg)]
        boxes = [r for r in rects if r[2] > 40 and r[3] > 18]
        if boxes:
            boxes.remove(max(boxes, key=lambda r: r[2] * r[3]))
        for p in polys:
            for (x1, y1), (x2, y2) in zip(p, p[1:]):
                L = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** .5
                if L < 7:
                    continue
                for bx, by, bw, bh in boxes:
                    on_wall = (
                        (abs(y1 - by) < 2 and abs(y2 - by) < 2
                         and min(x1, x2) < bx + bw - 4
                         and max(x1, x2) > bx + 4) or
                        (abs(y1 - (by + bh)) < 2 and
                         abs(y2 - (by + bh)) < 2
                         and min(x1, x2) < bx + bw - 4
                         and max(x1, x2) > bx + 4))
                    if on_wall:
                        self.fail('route leg runs on the wall of box '
                                  '(%.0f,%.0f): (%.0f,%.0f)->(%.0f,%.0f)'
                                  % (bx, by, x1, y1, x2, y2))


if __name__ == '__main__':
    unittest.main()