# -*- coding: utf-8 -*-
"""OMG Diagram Definition (DD) v1.1 — Diagram Interchange (DI) exchange.

Serialize / restore :class:`diagramboxes.layout.Diagram` objects through
the element shapes of the OMG Diagram Definition specification, v1.1
(https://www.omg.org/spec/DD/1.1, formal/2015-06-01).

DD splits graphical information into the **Diagram Interchange** model
(``DI`` — what tool users control: node bounds, edge waypoints, styles),
the shared **Diagram Common** datatypes (``DC::Point``, ``DC::Bounds``,
``DC::Dimension``, ``DC::Color``), and the **Diagram Graphics** model
(``DG`` — SVG-like primitives a renderer draws).  This module implements
**Diagram Information Interchange Conformance** (DD §13.2 level *a*):
a ``DI``-shaped, JSON-ready dictionary that carries everything
``diagramboxes`` needs to rebuild a diagram exactly, with element and
property names matching the standard so an XMI projection can be added
later.

Mapping (DI element → diagramboxes):

========================================  ==================================
DI element                                diagramboxes
========================================  ==================================
``DI::Diagram``                           :class:`~diagramboxes.layout.Diagram`
``DI::Shape``                             :class:`~diagramboxes.layout.Node`
                                          and every special node /
                                          pseudostate class
``DI::Edge`` (source, target, waypoints)  :class:`~diagramboxes.layout.Edge`
``DC::Point`` / ``DC::Bounds``            ``(x, y)`` / ``(x, y, w, h)``
``Style`` (``localStyle``)                line/arrow styles, ``dashed``,
                                          ``rounded`` as language-specific
                                          style properties
*language-specific DI* (the extension      ``Port`` / ``EntryPoint`` /
mechanism DD intends)                      ``ExitPoint``, pseudostate kinds,
                                          edge labels
========================================  ==================================

Element identity follows the DI ``localId`` scheme: every serialized
element carries a stable ``localId`` (``n1``, ``n2``, ``e1``, ...) and
edges reference endpoints by that id, so round-trips are stable and
hand-readable.

Geometry is serialized **as laid out** — call :meth:`Diagram.layout`
before :func:`to_di` if you want the computed coordinates embedded in
the interchange file (unlaid-out diagrams serialize with their
natural-size estimate at the origin, and re-layout cleanly on
restoration).

Round trip::

    from diagramboxes import Diagram
    from diagramboxes.di import to_di, from_di

    d = Diagram()
    a = d.add_node('A', ['block'])
    b = d.add_node('B')
    d.add_edge(a, b, label='conn')
    d.layout()
    payload = to_di(d)          # json.dumps(payload) → file
    d2 = from_di(payload)       # equal model, same ids

.. versionadded:: 0.6.0
"""

from __future__ import annotations

from diagramboxes.layout import (
    Diagram, Node, Edge, Port, Comment, View,
    StartNode, DoneNode, TerminateNode, ForkJoinNode, DecisionNode,
    InitialPseudostate, JunctionPseudostate, ChoicePseudostate,
    ForkPseudostate, JoinPseudostate, FinalState, TerminatePseudostate,
    HistoryPseudostate, EntryPoint, ExitPoint, StateNode,
)

__all__ = ["to_di", "from_di", "DI_VERSION", "DI_NS", "DC_NS", "DG_NS"]

# Standard namespace URIs from the DD v1.1 machine-readable files
# (ptc/14-03-04).
DI_VERSION = "1.1"
DC_NS = "http://www.omg.org/spec/DD/20131001/DC"
DI_NS = "http://www.omg.org/spec/DD/20131001/DI"
DG_NS = "http://www.omg.org/spec/DD/20131001/DG"

# The property that carries the diagramboxes class name on a DI::Shape.
# DD explicitly intends language-specific DI specializations; this is
# the discriminator from_di() uses to rebuild the right class while the
# emitted names stay DI-compatible.
_DD_KIND = "ddKind"

_ACTIVITY_CLASSES = (StartNode, DoneNode, TerminateNode, ForkJoinNode,
                     DecisionNode, HistoryPseudostate)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _all_elements(diagram):
    """Every first-class element (the four registration lists), in
    deterministic serialization order."""
    return (list(diagram.nodes) + list(diagram.comments)
            + list(diagram.views) + list(diagram.activities))


def _bounds_of(el):
    """(x, y, w, h) of an element (0-origin natural size if unlaid out)."""
    return [getattr(el, "x", 0), getattr(el, "y", 0),
            getattr(el, "w", 0), getattr(el, "h", 0)]


def _port_dict(p):
    """Language-specific payload of a boundary Port / EntryPoint /
    ExitPoint."""
    d = {
        "label": p.label,
        "side": p.side,
        "offset": p.offset,
        "direction": p.direction,
        "labelInside": bool(p.label_inside),
    }
    kind = getattr(p, "kind", None)
    if kind == "entry":
        d[_DD_KIND] = "EntryPoint"
    elif kind == "exit":
        d[_DD_KIND] = "ExitPoint"
    return d


def _port_from_dict(pd, parent):
    """Rebuild a Port / EntryPoint / ExitPoint from its dict."""
    kind = pd.get(_DD_KIND)
    cls = {"EntryPoint": EntryPoint, "ExitPoint": ExitPoint}.get(kind, Port)
    if cls is Port:
        p = Port(pd.get("label", ""), side=pd.get("side", "left"),
                 offset=pd.get("offset", 0.5),
                 direction=pd.get("direction"),
                 label_inside=pd.get("labelInside", False))
    else:
        p = cls(pd.get("label", ""), side=pd.get("side", "left"),
                offset=pd.get("offset", 0.5),
                direction=pd.get("direction"))
    p.parent = parent
    return p


def _edge_style_dict(e):
    return {
        "lineStyle": e.line_style,
        "sourceStyle": e.source_style,
        "targetStyle": e.target_style,
        "label": e.label,
    }


# ---------------------------------------------------------------------------
# serialization
# ---------------------------------------------------------------------------

def to_di(diagram):
    """Serialize a :class:`~diagramboxes.layout.Diagram` to a DI-shaped
    dictionary (DD v1.1 Diagram Information Interchange, level *a*).

    Parameters
    ----------
    diagram : diagramboxes.layout.Diagram
        Call :meth:`Diagram.layout` first if you want computed
        coordinates embedded in the output.

    Returns
    -------
    dict
        JSON-ready payload — ``json.dumps(payload)`` produces the
        interchange file; :func:`from_di` restores it exactly.
    """
    els = _all_elements(diagram)
    id_of = {}
    counter = 0
    for el in els:
        counter += 1
        id_of[id(el)] = "n%d" % counter
    for el in els:
        for child in getattr(el, "children", []) or []:
            if id(child) not in id_of:
                counter += 1
                id_of[id(child)] = "n%d" % counter

    def shape_dict(el):
        eid = id_of[id(el)]
        kind = type(el).__name__
        d = {
            "localId": eid,
            "xmiType": "DI:Shape",
            _DD_KIND: kind,
            "bounds": _bounds_of(el),
        }
        name = getattr(el, "name", None)
        if name is not None:
            d["name"] = name
        st = getattr(el, "stereotypes", None)
        if st:
            d["stereotypes"] = list(st)
        at = getattr(el, "attributes", None)
        if at:
            d["attributes"] = list(at)
        if getattr(el, "rounded", False):
            d["rounded"] = True
        if getattr(el, "dashed", False):
            d["dashed"] = True
        ports = getattr(el, "ports", None)
        if ports:
            d["ports"] = [_port_dict(p) for p in ports]
        children = getattr(el, "children", None)
        if children:
            d["ownedElement"] = [shape_dict(c) for c in children]
        sub = getattr(el, "substates", None)
        if sub:
            d["substates"] = [id_of[id(x)] for x in sub if id(x) in id_of]
        if isinstance(el, HistoryPseudostate):
            d["deep"] = bool(el.deep)
        if isinstance(el, ForkJoinNode):
            size = [getattr(el, "w", 36), getattr(el, "h", 8)]
            if size != [36, 8]:
                d["size"] = size
        if isinstance(el, DecisionNode):
            size = getattr(el, "size", 28)
            if size != 28:
                d["size"] = size
        if isinstance(el, Comment):
            d["text"] = el.text
        return d

    # Elements claimed as a child of any container (View.children /
    # Node.children) are nested inline, not emitted at top level.
    # NOTE: View.add_child does not set .parent, so containment is
    # detected from the children lists, not the parent attribute.
    claimed = set()
    for el in els:
        for child in getattr(el, "children", []) or []:
            claimed.add(id(child))
    owned = [shape_dict(el) for el in els if id(el) not in claimed]

    out = {
        "xmiType": "DI:Diagram",
        "namespace": DI_NS,
        "diVersion": DI_VERSION,
        "dcNs": DC_NS,
        "dgNs": DG_NS,
        "generator": "diagramboxes",
        "ownedElement": owned,
        "edges": [],
    }

    for e in diagram.edges:
        counter += 1
        eid = "e%d" % counter
        d = {
            "localId": eid,
            "xmiType": "DI:Edge",
            "source": id_of.get(id(e.source)),
            "target": id_of.get(id(e.target)),
            "waypoint": [[float(x), float(y)] for x, y in e.waypoints],
        }
        if e.source_port is not None:
            d["sourcePort"] = _port_dict(e.source_port)
        if e.target_port is not None:
            d["targetPort"] = _port_dict(e.target_port)
        d.update(_edge_style_dict(e))
        out["edges"].append(d)
    return out


def _shape_from_dict(sd):
    """Rebuild one element from a DI::Shape dict (geometry + ports;
    children and substates are wired by from_di's later passes)."""
    kind = sd.get(_DD_KIND, "Node")
    name = sd.get("name", "")
    if kind == "Comment":
        el = Comment(sd.get("text", ""))
    elif kind == "View":
        el = View(name, stereotypes=sd.get("stereotypes"),
                  attributes=sd.get("attributes"),
                  dashed=sd.get("dashed", False))
    elif kind == "StateNode":
        el = StateNode(name, stereotypes=sd.get("stereotypes"),
                       attributes=sd.get("attributes"),
                       dashed=sd.get("dashed", False))
    elif kind == "StartNode":
        el = StartNode(name)
    elif kind == "DoneNode":
        el = DoneNode(name)
    elif kind == "TerminateNode":
        el = TerminateNode(name)
    elif kind == "ForkJoinNode":
        size = sd.get("size")
        el = ForkJoinNode(name, *(size if size else (36, 8)))
    elif kind == "DecisionNode":
        el = DecisionNode(name, size=sd.get("size", 28))
    elif kind == "HistoryPseudostate":
        el = HistoryPseudostate(name, deep=sd.get("deep", False))
    else:
        el = Node(name, stereotypes=sd.get("stereotypes"),
                  attributes=sd.get("attributes"),
                  rounded=sd.get("rounded", False),
                  dashed=sd.get("dashed", False))
    b = sd.get("bounds") or [0, 0, 0, 0]
    el.x, el.y, el.w, el.h = b
    for pd in sd.get("ports", []):
        el.ports.append(_port_from_dict(pd, el))
    return el


def from_di(payload):
    """Restore a :class:`~diagramboxes.layout.Diagram` from a payload
    produced by :func:`to_di`.

    Parameters
    ----------
    payload : dict
        The DI-shaped dictionary (e.g. the object from ``json.load`` of
        an interchange file).

    Returns
    -------
    diagramboxes.layout.Diagram
        An equal model — same element ids, styles, ports, waypoints and
        geometry as the diagram that was serialized.
    """
    d = Diagram()
    by_local = {}            # localId -> element
    pending_children = []    # (parent_el, child_el) — wired in pass 2
    pending_substates = []   # (el, [substate localId])
    payload_top_ids = {sd["localId"]
                       for sd in payload.get("ownedElement", [])}

    def walk(sd):
        """Pass 1: build every element from its DI::Shape dict."""
        el = _shape_from_dict(sd)
        by_local[sd["localId"]] = el
        for sub in sd.get("substates") or []:
            pending_substates.append((el, sub))
        for cd in sd.get("ownedElement", []):
            walk(cd)
        if sd.get("localId") in payload_top_ids:
            if isinstance(el, Comment):
                d.comments.append(el)
            elif isinstance(el, View):
                d.views.append(el)
            elif isinstance(el, _ACTIVITY_CLASSES):
                d.activities.append(el)
            else:
                d.nodes.append(el)

    for sd in payload.get("ownedElement", []):
            walk(sd)

    # Pass 2: composite-structure children (parents exist by now)
    def wire(sd, el):
        for cd in sd.get("ownedElement", []):
            child = by_local[cd["localId"]]
            if hasattr(el, "add_child"):
                el.add_child(child)      # sets child.parent on Node
            else:
                el.children.append(child)
            wire(cd, child)

    for sd in payload.get("ownedElement", []):
        wire(sd, by_local[sd["localId"]])

    # Pass 3: substates (stored as localId lists on StateNode)
    def substates_of(sd, el):
        sub = sd.get("substates")
        if sub:
            el.substates = [by_local[lid] for lid in sub if lid in by_local]
        for cd in sd.get("ownedElement", []):
            substates_of(cd, by_local[cd["localId"]])

    for sd in payload.get("ownedElement", []):
        substates_of(sd, by_local[sd["localId"]])

    # Edges — DI::Edge
    for ed in payload.get("edges", []):
        s = by_local.get(ed.get("source"))
        t = by_local.get(ed.get("target"))
        if s is None or t is None:
            continue
        e = Edge(s, t,
                 line_style=ed.get("lineStyle", "solid"),
                 source_style=ed.get("sourceStyle"),
                 target_style=ed.get("targetStyle", "open"),
                 label=ed.get("label"))
        e.waypoints = [tuple(w) for w in ed.get("waypoint", [])]
        sp = ed.get("sourcePort")
        if sp:
            e.source_port = _port_from_dict(sp, s)
            s.ports.append(e.source_port)
        tp = ed.get("targetPort")
        if tp:
            e.target_port = _port_from_dict(tp, t)
            t.ports.append(e.target_port)
        d.edges.append(e)
    return d
