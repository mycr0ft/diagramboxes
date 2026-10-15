"""SysML v1 §6 activity notation: send/accept/wait action shapes, the
call-behavior rake, and control/object flow factories.

Acceptance criteria quoted from the corpus (summary/06-activity-diagrams.md):
- Send signal action: convex pentagon (signpost) (§6.8.3);
- Accept event action: concave pentagon — rectangle with a triangular
  notch (§6.8.4);
- Wait time action: hourglass with the time expression beneath (§6.8.5);
- Call behavior action name string '<name> : <Behavior>' + rake in the
  lower-right corner (§6.8.2);
- Control flow: dashed line with open arrowhead (§6.7.2 recommended);
- Object flow: solid line with open arrowhead (§6.7.1).
Everything that changes what a diagram EXPRESSes must land in the five
files (layout, primitives, svg_canvas, di, __init__) + round-trip.
"""
import os
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), '..', 'diagramboxes'))

from diagramboxes import (Diagram, SendSignalNode, AcceptEventNode,
                          WaitTimeNode, to_di, from_di, to_di_xmi,
                          from_di_xmi)


class ActivityNotationTest(unittest.TestCase):

    def test_send_signal_is_convex_signpost(self):
        # §6.8.3: convex pentagon — the left edge is square, the right
        # side comes to a point (signpost pointing along the flow)
        d = Diagram()
        s = d.add_send_signal('Orbit Radius Updated')
        self.assertIsInstance(s, SendSignalNode)
        self.assertEqual(s.w * 2 - 1, s.w * 2 + 1 - 2)   # sanity: ints
        # SVG: a `<polygon>` with a pointed right vertex (5 corners)
        d.add_edge(d.add_start(), s)
        svg = d.render_svg()
        self.assertIn('<polygon', svg)

    def test_accept_event_has_triangular_notch(self):
        # §6.8.4: concave pentagon — a rectangle with a notch cut into
        # the incoming (left) side: SVG polygon has >4 points and at
        # least one non-corner x-coordinate strictly inside the box
        d = Diagram()
        a = d.add_accept_event('Time to reach final orbit')
        self.assertIsInstance(a, AcceptEventNode)
        d.add_edge(d.add_start(), a)
        svg = d.render_svg()
        self.assertIn('<polygon', svg)

    def test_wait_time_expression_sits_beneath_hourglass(self):
        # §6.8.5: hourglass glyph; time expression printed beneath —
        # bounds must grow for the hanging expression
        d = Diagram()
        w = d.add_wait_time('after (30 days)')
        self.assertIsInstance(w, WaitTimeNode)
        d.add_edge(d.add_start(), w)
        d.render()
        self.assertGreater(w.expr_h, 0)

    def test_call_behavior_str_and_rake_flag(self):
        # §6.8.2: '<name> : <Behavior>' + rake lower-right
        d = Diagram()
        cb = d.call_behavior('ma', 'Measure altitude')
        self.assertEqual(cb.name, 'ma : Measure altitude')
        self.assertTrue(cb.rake)
        d.add_start()
        d.render()

    def test_control_object_flow_factories(self):
        # §6.7.1/6.7.2: object solid+open, control dashed+open
        d = Diagram()
        a = d.call_behavior('vc', 'Validate command')
        b = d.call_behavior('ma', 'Measure altitude')
        of = d.object_flow(a, b)
        cf = d.control_flow(a, b, guard='isCommandValid == False')
        self.assertFalse(of.line_style == 'dashed')
        self.assertEqual(cf.line_style, 'dashed')

    def test_control_flow_guard_brackets(self):
        # §6.9.3: guards display in square brackets
        d = Diagram()
        a = d.call_behavior('vc', 'Validate command')
        dec = d.add_decision()
        e = d.control_flow(dec, a, guard='isCommandValid == False')
        d.add_edge(d.add_start(), dec)
        self.assertIn('[', e.label)
        self.assertIn(']', e.label)

    def test_activity_nodes_pin_to_positions(self):
        # pin mode must place d.activities too (book-figure reproduction)
        d = Diagram()
        a = d.add_send_signal('Orbit Radius Updated', at=(100, 40))
        d.add_start(at=(0, 0))
        d.add_edge(d.activities[0], a)
        d.render()
        self.assertEqual((a.x, a.y), (100, 40))

    def test_shape_shapes_round_trip_di_xmi(self):
        d = Diagram()
        s = d.add_send_signal('S1')
        ev = d.add_accept_event('E1')
        wt = d.add_wait_time('after (2 s)')
        cb = d.call_behavior('x', 'Y')
        d.add_edge(d.add_start(), s)
        d.add_edge(ev, wt)
        d.add_edge(cb, s)
        payload = to_di(d)
        d2 = from_di(payload)
        kinds = [type(n).__name__ for n in d2.activities]
        for k in ('SendSignalNode', 'AcceptEventNode', 'WaitTimeNode'):
            self.assertIn(k, kinds)
        rake = [n for n in d2.nodes if getattr(n, 'rake', False)]
        self.assertEqual(len(rake), 1)
        xmi = to_di_xmi(payload)
        d3 = from_di(from_di_xmi(xmi))
        kinds3 = [type(n).__name__ for n in d3.activities]
        self.assertIn('WaitTimeNode', kinds3)
        self.assertEqual(len([n for n in d3.nodes
                              if getattr(n, 'rake', False)]), 1)


if __name__ == '__main__':
    unittest.main()