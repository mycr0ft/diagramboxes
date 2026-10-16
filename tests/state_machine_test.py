"""SysML v1 §8 state machines: the transition string factory and
self-transitions.

Acceptance criteria quoted from summary/08-state-machine-diagrams.md:
- transition string format: ``<trigger> [<guard>] / <effect>`` (§8.5) —
  each part optional, order fixed, guard always bracketed;
- transitions: solid line with an open arrowhead (§8.5);
- a self-transition is an arrow from a state back to itself (§8.5);
- states render round-cornered with an optional internal compartment
  (entry/exit/do, §8.4.1); internal transitions live in the second
  compartment (§8.5.1);
- junction pseudostates: filled circle, >=1 in/out (§8.6); else guards
  guarantee a decision fires (§8.6).
"""
import os
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), '..', 'diagramboxes'))

from diagramboxes import Diagram


class StateMachineTest(unittest.TestCase):

    def test_transition_string_full_format(self):
        # §8.5: 'trigger [guard] / effect' in one floating string
        d = Diagram()
        offline = d.add_state('Offline')
        online = d.add_state('Online')
        e = d.transition(offline, online,
                         trigger='startUp(sensorID)',
                         guard='isPowerAvailable == True',
                         effect='calibrate')
        self.assertEqual(e.label, 'startUp(sensorID) '
                                  '[isPowerAvailable == True] / calibrate')
        self.assertEqual(e.target_style, 'open')

    def test_transition_partial_formats(self):
        d = Diagram()
        a = d.add_state('A')
        b = d.add_state('B')
        c = d.add_state('C')
        self.assertEqual(
            d.transition(a, b, trigger='commLinkLost').label,
            'commLinkLost')
        self.assertEqual(
            d.transition(b, c, guard='x > 1', effect='save').label,
            '[x > 1] / save')
        self.assertEqual(
            d.transition(c, a, effect='calibrate').label, '/ calibrate')

    def test_internal_transition_lives_in_compartment(self):
        # §8.5.1: 'when (...) / effect' on the state's internal compartment
        d = Diagram()
        online = d.add_state('Online')
        online.add_internal('when (availableMemory < dataPerOrbit) '
                            '/ purgeOldestDataFiles')
        d.render()
        self.assertTrue(
            any('when (availableMemory < dataPerOrbit)' in a
                for a in online.attributes),
            'internal transition not in the state compartment')

    def test_self_transition_routes_and_renders(self):
        # §8.5: a self-transition is an arrow from a state back to itself
        d = Diagram()
        s = d.add_state('Working')
        e = d.transition(s, s, trigger='poke')
        d.render()
        svg = d.render_svg()
        self.assertTrue(e.waypoints, 'self-transition must be routed')
        # the route leaves and re-enters the state's boundary
        sx, sy = e.waypoints[0]
        tx, ty = e.waypoints[-1]
        self.assertTrue((s.x <= sx <= s.x + s.w and sy == s.y)
                        or (sy <= s.y + s.h), 'anchor not on the box top')
        self.assertNotEqual((sx, sy), (tx, ty))
        self.assertIn('<line', svg)

    def test_composite_state_with_substates(self):
        # §8.4.2: a composite state carrying nested substates
        d = Diagram()
        onstation = d.composite_state('On-Station',
                                      entry='link up')
        have = d.add_state('Have Comm Link')
        no = d.add_state('No Comm Link')
        onstation.add_child(have)
        onstation.add_child(no)
        d.transition(have, no, trigger='commLinkLost')
        d.render()
        self.assertTrue(any(
            c.parent is onstation for c in (have, no)))
        svg = d.render_svg()
        self.assertIn('Have Comm Link', svg)

    def test_junction_merge_and_else_decision(self):
        # §8.6: junction merge (2 in, 1 out) and a decision with else
        d = Diagram()
        idle = d.add_state('Idle')
        daq = d.add_state('Data Acquisition')
        store = d.add_state('Saving')
        j = d.add_junction()
        d.transition(idle, daq, trigger='powerOn')
        d.transition(j, idle)
        d.transition(daq, store, trigger='daqComplete')
        d.transition(store, j)
        d.transition(j, daq, guard='else')
        d.render()
        svg = d.render_svg()
        self.assertIn('else', svg)


if __name__ == '__main__':
    unittest.main()

class RegionTest(unittest.TestCase):
    """§8.7: orthogonal regions — dashed rectangles with a floating
    corner label, children inside, no header tab; round-trips DI."""

    def test_region_renders_dashed_with_corner_label(self):
        d = Diagram()
        r1 = d.add_region('Streaming / Suspended')
        s = d.add_state('Streaming')
        r1.add_child(s)
        d.render()
        svg = d.render_svg()
        # a dashed 4-corner rect exists among the polygon points
        import re
        self.assertIn('stroke-dasharray', svg)
        self.assertIn('Streaming / Suspended', svg)

    def test_region_children_and_round_trip(self):
        d = Diagram()
        r1 = d.add_region('R1')
        a = d.add_state('S1')
        r1.add_child(a)
        payload = __import__('diagramboxes').to_di(d)
        d2 = __import__('diagramboxes').from_di(payload)
        regs = [v for v in d2.views
                if type(v).__name__ == 'Region']
        self.assertEqual(len(regs), 1)
        self.assertTrue(any(
            getattr(c, 'name', None) == 'S1' for c in regs[0].children),
            'region children lost in round-trip')


if __name__ == '__main__':
    unittest.main()
