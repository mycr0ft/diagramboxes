import os
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), '..', 'diagramboxes'))

from diagramboxes import Diagram


class EndLabelAvoidanceTest(unittest.TestCase):

    def test_two_straight_edges_same_anchor_second_stack_moves(self):
        d = Diagram()
        a = d.add_node('A', at=(0, 100))
        c = d.add_node('C', at=(600, 100))
        m = d.add_node('M', at=(200, 100))
        d.add_edge(a, m, target_label='aaaaaaaaaaaaaaaa')
        d.add_edge(c, m, target_label='bbbbbbbbbbbbbbbb')
        d.render()
        svg = d.render_svg()
        import re
        halos = [(float(x)/1.5, float(y)/1.5)
                 for x, y in re.findall(r'<rect[^>]*x="([\d.]+)"[^>]*y="([\d.]+)"',
                                        svg)]
        band = [h for h in halos if 70 < h[1] < 105]
        ys = sorted(set(h[1] for h in band))
        self.assertGreater(len(ys), 1,
                           'both stacks landed on the same row (erased)')

    def test_straight_stack_vs_crossing_route_moves(self):
        d = Diagram()
        a = d.add_node('A', at=(60, 100))
        m = d.add_node('M', at=(260, 100))
        v1 = d.add_node('V1', at=(140, 40))
        v2 = d.add_node('V2', at=(140, 300))
        d.add_edge(a, m, target_label='tttttttttttttttt')
        d.add_edge(v1, v2)
        d.render()
        svg = d.render_svg()
        import re
        halos = [(float(x)/1.5, float(y)/1.5)
                 for x, y in re.findall(r'<rect[^>]*x="([\d.]+)"[^>]*y="([\d.]+)"',
                                        svg)]
        t_h = [h for h in halos if h[0] > 150 and 80 < h[1] < 126]
        self.assertTrue(t_h)
        for hx, hy in t_h:
            on_line = 134 <= hx <= 146
            self.assertFalse(on_line and 50 <= hy <= 300,
                             'stack halo astride the crossing route')


if __name__ == '__main__':
    unittest.main()
