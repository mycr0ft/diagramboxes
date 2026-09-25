# -*- coding: utf-8 -*-
"""DI (OMG DD v1.1 Diagram Interchange) round-trip tests for di.py."""
import json

import pytest

from diagramboxes import Diagram
from diagramboxes.di import DI_NS, DI_VERSION, from_di, to_di
from diagramboxes.layout import (
    Comment, EntryPoint, Node, StateNode, View,
)


def _sample():
    """A diagram exercising every serialized feature."""
    d = Diagram()
    a = d.add_node('A', ['block'], attributes=['+ x : int'])
    b = d.add_node('B')
    p = a.add_port('out', side='right', offset=0.5, direction='out')
    d.add_edge(a, b, source_port=p, target_style='open', label='conn')
    d.add_comment('hello')
    v = d.add_view('Top', stereotypes=['view'])
    d.add_node('Inner', parent=v)
    s = d.add_state('S1')
    d.add_state('S1a')
    s.substates.append(d.nodes[-1])
    d.add_entry_point(s, 'entry1', side='top', offset=0.3)
    d.add_history(deep=True)
    d.add_start()
    d.add_edge(a, d.comments[0], label='note')
    d.layout()
    return d


class TestToDi:
    def test_diagram_header(self):
        payload = to_di(_sample())
        assert payload["xmiType"] == "DI:Diagram"
        assert payload["namespace"] == DI_NS
        assert payload["diVersion"] == DI_VERSION
        assert payload["generator"] == "diagramboxes"

    def test_shape_ids_are_stable_and_prefixed(self):
        payload = to_di(_sample())
        ids = [sd["localId"] for sd in payload["ownedElement"]]
        assert all(i.startswith("n") for i in ids)
        assert len(ids) == len(set(ids))
        for ed in payload["edges"]:
            assert ed["localId"].startswith("e")
            assert ed["source"] in ids and ed["target"] in ids

    def test_view_child_nested_not_top_level(self):
        payload = to_di(_sample())
        tops = {sd.get("name") for sd in payload["ownedElement"]}
        assert "Top" in tops
        # nested under the view, not a top-level element
        view_sd = next(sd for sd in payload["ownedElement"]
                       if sd.get("name") == "Top")
        assert view_sd["ownedElement"][0]["name"] == "Inner"
        assert "Inner" not in tops

    def test_edge_waypoints_and_styles(self):
        d = _sample()
        payload = to_di(d)
        ed = next(e for e in payload["edges"] if e.get("label") == "conn")
        assert ed["sourcePort"]["label"] == "out"
        assert ed["targetStyle"] == "open"
        assert len(ed["waypoint"]) == len(d.edges[0].waypoints)

    def test_entry_point_kind_preserved(self):
        payload = to_di(_sample())
        s_sd = next(sd for sd in payload["ownedElement"]
                    if sd.get("ddKind") == "StateNode")
        kinds = {p["label"]: p.get("ddKind") for p in s_sd["ports"]}
        assert kinds["entry1"] == "EntryPoint"

    def test_json_serializable(self):
        payload = to_di(_sample())
        assert json.loads(json.dumps(payload)) == payload


class TestFromDi:
    def test_round_trip_structure(self):
        d = _sample()
        d2 = from_di(to_di(d))
        assert len(d2.nodes) == len(d.nodes) - 1      # Inner is nested
        assert len(d2.comments) == len(d.comments) == 1
        assert len(d2.views) == 1
        assert len(d2.activities) == 2                # history + start
        assert len(d2.edges) == len(d.edges) == 2

    def test_round_trip_render_identical(self):
        d = _sample()
        d2 = from_di(to_di(d))
        assert d2.render(routing='orthogonal') == \
            d.render(routing='orthogonal')

    def test_round_trip_ports_and_waypoints(self):
        d = _sample()
        d2 = from_di(to_di(d))
        e2 = next(e for e in d2.edges if e.label == 'conn')
        e1 = next(e for e in d.edges if e.label == 'conn')
        assert e2.source_port.label == 'out'
        assert e2.source_port.direction == 'out'
        assert e2.waypoints == e1.waypoints
        assert e2.line_style == e1.line_style
        assert e2.target_style == e1.target_style

    def test_round_trip_composite_state(self):
        d = _sample()
        d2 = from_di(to_di(d))
        s2 = next(n for n in d2.nodes if isinstance(n, StateNode))
        assert [x.name for x in s2.substates] == ['S1a']
        assert any(p.label == 'entry1' and getattr(p, 'kind', None) == 'entry'
                   for p in s2.ports)

    def test_round_trip_history_deep_flag(self):
        d = _sample()
        d2 = from_di(to_di(d))
        assert any(getattr(x, 'deep', None) is True for x in d2.activities)

    def test_comment_text_preserved(self):
        d = _sample()
        d2 = from_di(to_di(d))
        assert d2.comments[0].text == 'hello'


class TestJsonFile:
    def test_json_file_round_trip(self, tmp_path):
        import os
        d = _sample()
        payload = to_di(d)
        path = os.path.join(str(tmp_path), 'di.json')
        with open(path, 'w') as f:
            json.dump(payload, f, indent=1)
        with open(path) as f:
            loaded = json.load(f)
        d2 = from_di(loaded)
        assert d2.render(routing='orthogonal') == \
            d.render(routing='orthogonal')

    def test_unlaid_out_diagram_relayouts(self):
        """A diagram serialized without layout() restores and lays out
        cleanly (positions recompute)."""
        d = Diagram()
        a = d.add_node('A')
        b = d.add_node('B')
        d.add_edge(a, b)
        d2 = from_di(to_di(d))
        d2.layout()
        assert d2.nodes[0].w > 0 and d2.edges[0].waypoints
