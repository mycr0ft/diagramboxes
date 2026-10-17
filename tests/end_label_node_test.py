"""RED: per-end labels must never land inside the endpoint node's box.

Criterion: Figure 3.1 — the compose edge into the top border printed
'primaryComputer 1' EXACTLY on the Flight Computer block's title row
(the geometric edge_end_label_positions anchor + its +6/+12 offsets
fall inside the box; the halo then erases the title). The same landing
inside a box puts '0..1' inside the DellSat-77 Satellite box. Rule: an
end label's anchor that falls inside the endpoint node's rect (padded)
pushes OUT through the nearest border, clear of the box."""
import re
import unittest

from diagramboxes import Diagram


def _end_label_pos(svg, needle):
    for x, y, t in re.findall(
            r'<text[^>]*x="([\d.]+)" y="([\d.]+)"[^>]*>([^<]*)</text>', svg):
        if t.strip() == needle:
            return (float(x), float(y))
    return None


class TestEndLabelOutsideBox(unittest.TestCase):
    def test_target_end_label_clears_the_target_block(self):
        d = Diagram()
        whole = d.add_node('Whole', ['block'],
                           compartments=[('values', ['x : 1'])])
        part = d.add_node('Flight Computer', ['block'],
                          compartments=[('constraints', ['sm : X']),
                                        ('values', ['a', 'b'])])
        d.compose(whole, part, target_label='primaryComputer 1',
                  source_label='0..1')
        svg = d.render_svg(routing='orthogonal')
        pos = _end_label_pos(svg, 'primaryComputer 1')
        self.assertIsNotNone(pos, 'end label not rendered')
        x, y, w, h = part.x, part.y, part.w, part.h
        lx, ly = pos
        inside = (x - 5 <= lx <= x + w + 5) and (y - 9 <= ly <= y + h + 9)
        self.assertFalse(inside,
                         'end label at (%.0f,%.0f) inside the target box '
                         '(%.0f,%.0f,%.0f,%.0f)' % (lx, ly, x, y, w, h))

    def test_source_end_label_clears_the_source_block(self):
        d = Diagram()
        whole = d.add_node('DellSat-77', ['block'])
        part = d.add_node('Part', ['block'])
        d.compose(whole, part, target_label='part 1', source_label='0..1')
        svg = d.render_svg(routing='orthogonal')
        pos = _end_label_pos(svg, '0..1')
        self.assertIsNotNone(pos)
        x, y, w, h = whole.x, whole.y, whole.w, whole.h
        lx, ly = pos
        inside = (x - 5 <= lx <= x + w + 5) and (y - 9 <= ly <= y + h + 9)
        self.assertFalse(inside)

    def test_no_end_label_inside_any_box_on_the_real_poc(self):
        # the shipped Figure 3.1 PoC: no end label sits inside any box
        import os
        script = '/home/jfox/proj/sysml-distilled/reproduced/fig3_1_bdd.py'
        if not os.path.exists(script):
            self.skipTest('PoC script missing')
        os.system('cd /home/jfox/proj/diagramboxes && poetry run python %s '
                  '> /dev/null 2>&1' % script)
        svg = open('/home/jfox/proj/sysml-distilled/reproduced/'
                   'fig3_1.svg').read()
        rects = [(float(m.group(1)), float(m.group(2)),
                  float(m.group(3)), float(m.group(4)))
                 for m in re.finditer(
                     r'<rect[^>]*?x="([\d.]+)" y="([\d.]+)" '
                     r'width="([\d.]+)" height="([\d.]+)"', svg)]
        boxes = [r for r in rects if r[2] > 40 and r[3] > 18]
        # the diagram FRAME is not a block: drop the outermost rect
        if boxes:
            outer = max(boxes, key=lambda r: r[2] * r[3])
            boxes = [r for r in boxes if r is not outer]
        END_LABELS = ('primaryComputer 1', 'backupComputer 1..2', '0..1',
                      'eps 1', 'aocs 1', 'ecs 1', 'cdhs 1', 'mod 1',
                      'tx 1', '2..3')
        for x, y, t in re.findall(
                r'<text[^>]*x="([\d.]+)" y="([\d.]+)"[^>]*>([^<]*)</text>',
                svg):
            if t.strip() not in END_LABELS:
                continue
            lx, ly = float(x), float(y)
            for bx, by, bw, bh in boxes:
                if (bx - 5 <= lx <= bx + bw + 5 and
                        by - 9 <= ly <= by + bh + 9):
                    self.fail("end label '%s' at (%.0f,%.0f) inside box "
                              "(%.0f,%.0f,%.0f,%.0f)"
                              % (t, lx, ly, bx, by, bw, bh))


if __name__ == '__main__':
    unittest.main()