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
    StartNode, DoneNode, TerminateNode, ForkJoinNode, DecisionNode, \
    SendSignalNode, AcceptEventNode, WaitTimeNode,
    InitialPseudostate, JunctionPseudostate, ChoicePseudostate,
    ForkPseudostate, JoinPseudostate, FinalState, TerminatePseudostate,
    HistoryPseudostate, EntryPoint, ExitPoint, StateNode, FramePort, \
    Lifeline, SeqMessage, SeqExec, SeqDestruction, SeqFragment, \
    SeqConstraint, ParParam, UseCase, Actor,
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
                     DecisionNode, HistoryPseudostate, SendSignalNode,
                     AcceptEventNode, WaitTimeNode)


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
    elif type(p).__name__ == "FramePort":
        d[_DD_KIND] = "FramePort"
    ifaces = getattr(p, "interfaces", None)
    if ifaces:
        d["interfaces"] = [{"name": i.name, "kind": i.kind}
                           for i in ifaces]
    return d


def _port_from_dict(pd, parent):
    """Rebuild a Port / EntryPoint / ExitPoint from its dict."""
    kind = pd.get(_DD_KIND)
    cls = {"EntryPoint": EntryPoint, "ExitPoint": ExitPoint,
           "FramePort": FramePort}.get(kind, Port) if kind else Port
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
    for idx, idf in enumerate(pd.get("interfaces", [])):
        p.add_interface(idf.get("name", ""), kind=idf.get("kind", "provided"),
                        index=idx)
    return p


def _edge_style_dict(e):
    return {
        "lineStyle": e.line_style,
        "sourceStyle": e.source_style,
        "targetStyle": e.target_style,
        "label": e.label,
        "sourceLabel": getattr(e, "source_label", None),
        "targetLabel": getattr(e, "target_label", None),
        "itemFlow": getattr(e, "item_flow", None),
        "itemPosition": getattr(e, "item_position", 0.5),
        "binding": getattr(e, "is_binding", False),
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
    for par in getattr(diagram, "par_params", []):
        # constraint-parameter squares (§9.6) — not laid-out nodes, but
        # binding edges reference them, so they need localIds
        if id(par) not in id_of:
            counter += 1
            id_of[id(par)] = "n%d" % counter

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
        comp = getattr(el, "compartments", None)
        if comp:
            d["compartments"] = [[t, list(ls)] for t, ls in comp]
        if getattr(el, "rounded", False):
            d["rounded"] = True
        if getattr(el, "chamfer", 0):
            d["chamfer"] = getattr(el, "chamfer")
        if getattr(el, "dashed", False):
            d["dashed"] = True
        if getattr(el, "is_actor", False):
            d["stickFigure"] = bool(getattr(el, "is_stick_figure", True))
        ports = getattr(el, "ports", None)
        if ports:
            d["ports"] = [_port_dict(p) for p in ports]
        standalone = getattr(el, "interfaces", None)
        if standalone:  # standalone node-level lollipop/socket symbols
            d["interfaces"] = [{"name": i.name, "kind": i.kind,
                                "side": i.side, "offset": i.offset}
                               for i in standalone]
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
            if getattr(el, "filled", False):
                d["filled"] = True
        if getattr(el, "rake", False):
            d["rake"] = True
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

    if getattr(diagram, "par_params", []):
        out["parParams"] = [{"localId": id_of.get(id(p)),
                             "name": p.name, "side": p.side,
                             "offset": p.offset,
                             "owner": [i for i, n in enumerate(diagram.nodes)
                                       if n is p.owner][0] if p.owner else None,
                             "bounds": [p.x, p.y, p.w, p.h]}
                            for p in diagram.par_params]

    if diagram.frame is not None:
        fr = diagram.frame
        fd = {"kind": fr.kind}
        if fr.element_kind:
            fd["elementKind"] = fr.element_kind
        if fr.element_name:
            fd["elementName"] = fr.element_name
        if fr.diagram_name:
            fd["diagramName"] = fr.diagram_name
        if diagram.frame_ports:
            fd["ports"] = [_port_dict(p) for p in diagram.frame_ports]
        out["diagramFrame"] = fd

    # ── sequence diagram elements (§7.4–7.7) ──
    li_index = {id(li): i for i, li in enumerate(diagram.lifelines)}
    if diagram.lifelines:
        out["lifelines"] = [
            {"localId": "li%d" % i, "label": li.label, "x": li.x,
             "headY": li.head_y, "created": li.created}
            for i, li in enumerate(diagram.lifelines)]
        out["sequenceMessages"] = [
            {"kind": m.kind,
             "src": li_index[id(m.src)] if m.src is not None else -1,
             "dst": li_index[id(m.dst)] if m.dst is not None else -1,
             "y": m.y, "label": m.label,
             "fromLeft": m.from_left, "toRight": m.to_right}
            for m in diagram.messages]
        out["sequenceExecSpecs"] = [
            {"li": li_index[id(s.lifeline)], "y1": s.y1, "y2": s.y2,
             "shaded": s.shaded} for s in diagram.exec_specs]
        out["sequenceDestructions"] = [
            {"li": li_index[id(x.lifeline)], "y": x.y}
            for x in diagram.destructions]
        out["sequenceFragments"] = [
            {"operator": f.operator, "range": f.frag_range,
             "guard": f.guard, "name": f.name, "y1": f.y1, "y2": f.y2,
             "li": [li_index[id(li)] for li in f.lifelines],
             "operands": [[row, g] for row, g in f.operands]}
            for f in diagram.fragments]
        out["sequenceConstraints"] = [
            {"li": li_index[id(c.lifeline)], "y": c.y, "text": c.text,
             "dx": c.dx, "rounded": c.rounded}
            for c in diagram.constraints]
    return out


def _shape_from_dict(sd):
    """Rebuild one element from a DI::Shape dict (geometry + ports;
    children and substates are wired by from_di's later passes)."""
    kind = sd.get(_DD_KIND, "Node")
    name = sd.get("name", "")
    if kind == "UseCase":
        el = UseCase(name)
    elif kind == "Actor":
        el = Actor(name, stick_figure=sd.get("stickFigure", True))
    elif kind == "Comment":
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
    elif kind == "SendSignalNode":
        el = SendSignalNode(name)
    elif kind == "AcceptEventNode":
        el = AcceptEventNode(name)
    elif kind == "WaitTimeNode":
        el = WaitTimeNode(name)
    else:
        el = Node(name, stereotypes=sd.get("stereotypes"),
                  attributes=sd.get("attributes"),
                  rounded=sd.get("rounded", False),
                  dashed=sd.get("dashed", False),
                  compartments=sd.get("compartments"),
                  chamfer=sd.get("chamfer", 0))
    if kind == "DecisionNode" and sd.get("filled"):
        el.filled = True
    b = sd.get("bounds") or [0, 0, 0, 0]
    el.x, el.y, el.w, el.h = b
    if sd.get("rake") and hasattr(el, "rake"):
        el.rake = True
    for pd in sd.get("ports", []):
        el.ports.append(_port_from_dict(pd, el))
    for idx, idf in enumerate(sd.get("interfaces", [])):
        if hasattr(el, "add_interface"):
            el.add_interface(idf.get("name", ""), kind=idf.get("kind", "provided"),
                             side=idf.get("side", "right"),
                             offset=idf.get("offset", 0.5), index=idx)
    return el




# ---------------------------------------------------------------------------
# XMI projection (same shapes, xmi:XMI document form)
# ---------------------------------------------------------------------------

def _xml_escape(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _bounds_xml(b, indent):
    x, y, w, h = b
    return '%s<bounds x="%g" y="%g" width="%g" height="%g"/>' % (
        indent, x, y, w, h)


def _point_xml(x, y, indent):
    return '%s<waypoint x="%g" y="%g"/>' % (indent, x, y)


def _shape_xml(sd, indent):
    """One DI::Shape element (recursive over ownedElement)."""
    eid = sd["localId"]
    kind = sd.get(_DD_KIND, "Node")
    sattrs = ['ddKind="%s"' % kind]
    if sd.get("rounded"):
        sattrs.append('rounded="true"')
    if sd.get("dashed"):
        sattrs.append('dashed="true"')
    if sd.get("rake"):
        sattrs.append('rake="true"')
    if sd.get("chamfer"):
        sattrs.append('chamfer="%g"' % sd["chamfer"])
    if sd.get("filled"):
        sattrs.append('filled="true"')
    lines = ['%s<di:Shape xmi:id="%s" %s>' % (indent, eid, " ".join(sattrs))]
    lines.append(_bounds_xml(sd.get("bounds") or [0, 0, 0, 0], indent + "  "))
    name = sd.get("name")
    if name is not None:
        lines.append('%s<name>%s</name>' % (indent + "  ", _xml_escape(name)))
    for st in sd.get("stereotypes", []):
        lines.append('%s<stereotype>%s</stereotype>'
                     % (indent + "  ", _xml_escape(st)))
    for at in sd.get("attributes", []):
        lines.append('%s<attribute>%s</attribute>'
                     % (indent + "  ", _xml_escape(at)))
    for comp_name, comp_lines in sd.get("compartments", []):
        lines.append('%s<compartment name="%s">' % (indent + "  ", _xml_escape(comp_name)))
        for at in comp_lines:
            lines.append('%s  <attribute>%s</attribute>'
                         % (indent + "  ", _xml_escape(at)))
        lines.append('%s</compartment>' % (indent + "  "))
    for pd in sd.get("ports", []):
        attrs = ['label="%s"' % _xml_escape(pd.get("label", "")),
                 'side="%s"' % pd.get("side", "left")]
        if pd.get("offset") is not None:
            attrs.append('offset="%g"' % pd["offset"])
        if pd.get("direction"):
            attrs.append('direction="%s"' % pd["direction"])
        if pd.get(_DD_KIND):
            attrs.append('%s="%s"' % (_DD_KIND, pd[_DD_KIND]))
        pif = pd.get("interfaces", [])
        if pif:
            lines.append('%s<port %s>' % (indent + "  ", " ".join(attrs)))
            for idf in pif:
                lines.append('%s  <interface name="%s" kind="%s"/>'
                             % (indent + "  ", _xml_escape(idf.get("name", "")),
                                idf.get("kind", "provided")))
            lines.append('%s</port>' % (indent + "  "))
        else:
            lines.append('%s<port %s/>' % (indent + "  ", " ".join(attrs)))
    for idf in sd.get("interfaces", []):
        lines.append('%s<interface name="%s" kind="%s" side="%s" offset="%g"/>'
                     % (indent + "  ", _xml_escape(idf.get("name", "")),
                        idf.get("kind", "provided"), idf.get("side", "right"),
                        idf.get("offset", 0.5)))
    for cd in sd.get("ownedElement", []):
        lines.append(_shape_xml(cd, indent + "  "))
    if sd.get("substates"):
        lines.append('%s<substates>%s</substates>'
                     % (indent + "  ",
                        " ".join(sd["substates"])))
    if sd.get("deep"):
        lines.append('%s<deep>true</deep>' % indent)
    if sd.get("text"):
        lines.append('%s<body>%s</body>' % (indent + "  ", _xml_escape(sd["text"])))
    lines.append('%s</di:Shape>' % indent)
    return "\n".join(lines)


def _xmi_id(el):
    """Read ``xmi:id`` handling both namespaced and plain spellings."""
    XMI = "{http://www.omg.org/spec/XMI/20131001}"
    return el.get(XMI + "id") or el.get("xmi:id")


def _parse_shape_element(el):
    """Parse one di:Shape XML element into a DI payload dict."""
    sd = {"xmiType": "DI:Shape", "localId": _xmi_id(el),
          _DD_KIND: el.get("ddKind", "Node")}
    if el.get("rounded") == "true":
        sd["rounded"] = True
    if el.get("dashed") == "true":
        sd["dashed"] = True
    if el.get("rake") == "true":
        sd["rake"] = True
    if el.get("chamfer"):
        try:
            sd["chamfer"] = int(float(el.get("chamfer")))
        except ValueError:
            pass
    if el.get("filled") == "true":
        sd["filled"] = True
    b = el.find("bounds")
    if b is not None:
        sd["bounds"] = [float(b.get("x", 0)), float(b.get("y", 0)),
                        float(b.get("width", 0)), float(b.get("height", 0))]
    nm = el.find("name")
    if nm is not None:
        sd["name"] = nm.text or ""
    body = el.find("body")
    if body is not None:
        sd["text"] = body.text or ""
    deep = el.find("deep")
    if deep is not None:
        sd["deep"] = deep.text == "true"
    subs = el.find("substates")
    if subs is not None and subs.text:
        sd["substates"] = subs.text.split()
    stereotypes = [st.text for st in el.findall("stereotype") if st.text]
    if stereotypes:
        sd["stereotypes"] = stereotypes
    attributes = [at.text for at in el.findall("attribute") if at.text]
    if attributes:
        sd["attributes"] = attributes
    compartments = []
    for comp in el.findall("compartment"):
        comp_lines = [at.text for at in comp.findall("attribute") if at.text]
        compartments.append([comp.get("name", ""), comp_lines])
    if compartments:
        sd["compartments"] = compartments
    ports = []
    for pe in el.findall("port"):
        pd = {"label": pe.get("label", ""), "side": pe.get("side", "left")}
        if pe.get("offset") is not None:
            pd["offset"] = float(pe.get("offset"))
        if pe.get("direction"):
            pd["direction"] = pe.get("direction")
        if pe.get(_DD_KIND):
            pd[_DD_KIND] = pe.get(_DD_KIND)
        pif = [{"name": ie.get("name", ""), "kind": ie.get("kind", "provided")}
               for ie in pe.findall("interface")]
        if pif:
            pd["interfaces"] = pif
        ports.append(pd)
    if ports:
        sd["ports"] = ports
    standalone = [{"name": ie.get("name", ""),
                   "kind": ie.get("kind", "provided"),
                   "side": ie.get("side", "right"),
                   "offset": float(ie.get("offset", 0.5))}
                  for ie in el.findall("interface")]
    if standalone:
        sd["interfaces"] = standalone
    kids = []
    for child in el.findall("ownedElement"):
        kids.append(_parse_shape_element(child))
    if kids:
        sd["ownedElement"] = kids
    return sd


def to_di_xmi(payload, name="Diagram"):
    """Project a :func:`to_di` payload into an XMI document using the
    DD v1.1 DI/DC namespaces (the form DI-reading tools consume).

    Parameters
    ----------
    payload : dict
        A DI-shaped dictionary from :func:`to_di`.
    name : str, optional
        Diagram name written on the ``di:Diagram`` element.

    Returns
    -------
    str
        The ``xmi:XMI`` XML document as text.

    .. versionadded:: 0.6.1
    """
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<xmi:XMI xmi:version="2.5"',
        '     xmlns:xmi="http://www.omg.org/spec/XMI/20131001"',
        '     xmlns:di="%s"' % DI_NS,
        '     xmlns:dc="%s"' % DC_NS,
        '     xmlns:dg="%s">' % DG_NS,
        '  <di:Diagram xmi:id="_d" name="%s">' % _xml_escape(name),
    ]
    for sd in payload.get("ownedElement", []):
        out.append(_shape_xml(sd, "    "))
    for ed in payload.get("edges", []):
        eattrs = []
        if ed.get("lineStyle"):
            eattrs.append('lineStyle="%s"' % ed["lineStyle"])
        if ed.get("sourceStyle"):
            eattrs.append('sourceStyle="%s"' % ed["sourceStyle"])
        if ed.get("targetStyle"):
            eattrs.append('targetStyle="%s"' % ed["targetStyle"])
        lines = ['    <di:Edge xmi:id="%s" source="%s" target="%s"%s>'
                 % (ed["localId"], ed.get("source"), ed.get("target"),
                    (" " + " ".join(eattrs)) if eattrs else "")]
        if ed.get("binding"):
            lines[-1] = lines[-1][:-1] + ' binding="true">'
        for x, y in ed.get("waypoint", []):
            lines.append(_point_xml(x, y, "      "))
        label = ed.get("label")
        if label:
            lines.append('      <name>%s</name>' % _xml_escape(label))
        for end, tag in (("sourceLabel", "sourceLabel"),
                         ("targetLabel", "targetLabel")):
            v = ed.get(end)
            if v:
                lines.append('      <%s>%s</%s>' % (tag, _xml_escape(v), tag))
        item_flow = ed.get("itemFlow")
        if item_flow:
            pos = ed.get("itemPosition")
            lines.append('      <itemFlow%s>%s</itemFlow>'
                         % (' position="%g"' % pos if pos is not None else '',
                            _xml_escape(item_flow)))
        sp = ed.get("sourcePort")
        if sp:
            attrs = ['label="%s"' % _xml_escape(sp.get("label", "")),
                     'side="%s"' % sp.get("side", "left")]
            if sp.get("offset") is not None:
                attrs.append('offset="%g"' % sp["offset"])
            if sp.get("direction"):
                attrs.append('direction="%s"' % sp["direction"])
            lines.append('      <sourcePort %s/>' % " ".join(attrs))
        tp = ed.get("targetPort")
        if tp:
            attrs = ['label="%s"' % _xml_escape(tp.get("label", "")),
                     'side="%s"' % tp.get("side", "left")]
            if tp.get("offset") is not None:
                attrs.append('offset="%g"' % tp["offset"])
            if tp.get("direction"):
                attrs.append('direction="%s"' % tp["direction"])
            lines.append('      <targetPort %s/>' % " ".join(attrs))
        lines.append('    </di:Edge>')
        out.append("\n".join(lines))
    fd = payload.get("diagramFrame")
    if fd:
        fattrs = ['kind="%s"' % fd.get("kind", "bdd")]
        for jk, xk in (("elementKind", "elementKind"),
                       ("elementName", "elementName"),
                       ("diagramName", "diagramName")):
            if fd.get(jk):
                fattrs.append('%s="%s"' % (xk, _xml_escape(fd[jk])))
        out.append('    <di:DiagramFrame %s>' % " ".join(fattrs))
        for pd in fd.get("ports", []):
            pattrs = ['label="%s"' % _xml_escape(pd.get("label", "")),
                      'side="%s"' % pd.get("side", "left")]
            if pd.get("offset") is not None:
                pattrs.append('offset="%g"' % pd["offset"])
            if pd.get("direction"):
                pattrs.append('direction="%s"' % pd["direction"])
            out.append('      <port %s/>' % " ".join(pattrs))
            for idf in pd.get("interfaces", []):
                out.append('        <interface name="%s" kind="%s"/>'
                           % (_xml_escape(idf.get("name", "")),
                              idf.get("kind", "provided")))
        out.append('    </di:DiagramFrame>')
    li_els = payload.get("lifelines", [])
    for i, ld in enumerate(li_els):
        attrs = ['label="%s"' % _xml_escape(ld.get("label", "")),
                 'x="%g"' % ld.get("x", 0),
                 'headY="%g"' % ld.get("headY", 0)]
        if ld.get("created"):
            attrs.append('created="true"')
        out.append('    <di:Lifeline %s/>' % " ".join(attrs))
    for md in payload.get("sequenceMessages", []):
        attrs = ['kind="%s"' % md.get("kind", "async"),
                 'src="%d"' % md.get("src", 0),
                 'dst="%d"' % md.get("dst", 0),
                 'y="%g"' % md.get("y", 0)]
        if md.get("label"):
            attrs.append('label="%s"' % _xml_escape(md["label"]))
        if not md.get("fromLeft", True):
            attrs.append('fromLeft="false"')
        if not md.get("toRight", True):
            attrs.append('toRight="false"')
        out.append('    <di:SeqMessage %s/>' % " ".join(attrs))
    for sd_ in payload.get("sequenceExecSpecs", []):
        out.append('    <di:SeqExec li="%d" y1="%g" y2="%g"%s/>'
                   % (sd_.get("li", 0), sd_.get("y1", 0), sd_.get("y2", 0),
                      ' shaded="true"' if sd_.get("shaded") else ''))
    for dd in payload.get("sequenceDestructions", []):
        out.append('    <di:SeqDestruction li="%d" y="%g"/>'
                   % (dd.get("li", 0), dd.get("y", 0)))
    for fd_ in payload.get("sequenceFragments", []):
        liids = " ".join(str(i) for i in fd_.get("li", []))
        fattrs = ['operator="%s"' % fd_.get("operator", "opt"),
                  'y1="%g"' % fd_.get("y1", 0),
                  'y2="%g"' % fd_.get("y2", 0),
                  'lifelines="%s"' % liids]
        if fd_.get("range"):
            fattrs.append('range="%s"' % _xml_escape(fd_["range"]))
        if fd_.get("guard"):
            fattrs.append('guard="%s"' % _xml_escape(fd_["guard"]))
        if fd_.get("name"):
            fattrs.append('name="%s"' % _xml_escape(fd_["name"]))
        out.append('    <di:SeqFragment %s>' % " ".join(fattrs))
        for row, guard in fd_.get("operands", []):
            gattrs = ['y="%g"' % row]
            if guard:
                gattrs.append('guard="%s"' % _xml_escape(guard))
            out.append('      <operand %s/>' % " ".join(gattrs))
        out.append('    </di:SeqFragment>')
    for pp in payload.get("parParams", []):
        pattrs = ['localId="%s"' % pp.get("localId", ""),
                  'name="%s"' % _xml_escape(pp.get("name", "")),
                  'side="%s"' % pp.get("side", "left"),
                  'offset="%g"' % pp.get("offset", 0.5)]
        if pp.get("owner") is not None:
            pattrs.append('owner="%d"' % pp["owner"])
        out.append('    <di:ParParam %s/>' % " ".join(pattrs))
    for ce in payload.get("sequenceConstraints", []):
        cattrs = ['li="%d"' % ce.get("li", 0),
                  'y="%g"' % ce.get("y", 0),
                  'text="%s"' % _xml_escape(ce.get("text", ""))]
        if ce.get("dx"):
            cattrs.append('dx="%g"' % ce["dx"])
        if ce.get("rounded"):
            cattrs.append('rounded="true"')
        out.append('    <di:SeqConstraint %s/>' % " ".join(cattrs))
    out.append("  </di:Diagram>")
    out.append("</xmi:XMI>")
    return "\n".join(out)


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

    # Frame + frame ports first: edges may reference them by identity
    frd = payload.get("diagramFrame")
    if frd:
        d.add_frame(frd.get("kind", "bdd"),
                    element_kind=frd.get("elementKind"),
                    element_name=frd.get("elementName"),
                    diagram_name=frd.get("diagramName"))
        for pd in frd.get("ports", []):
            d.frame_ports.append(_port_from_dict(pd, None))

    # ── sequence diagram elements (§7.4–7.7) ──
    for ld in payload.get("lifelines", []):
        li = d.add_lifeline(ld.get("label", ""),
                            x=ld.get("x"), created=ld.get("created", False))
        if ld.get("headY") is not None:
            li.head_y = int(ld["headY"])
    lis = list(d.lifelines)
    for md in payload.get("sequenceMessages", []):
        si, ti = md.get("src", 0), md.get("dst", 0)
        src = lis[si] if 0 <= si < len(lis) else None
        dst = lis[ti] if 0 <= ti < len(lis) else None
        if src is None and dst is None:
            continue
        kind = md.get("kind", "async")
        d.messages.append(SeqMessage(src, dst, kind,
                                     md.get("y", 0), md.get("label"),
                                     from_left=md.get("fromLeft", True),
                                     to_right=md.get("toRight", True)))
        if kind == 'create' and dst is not None and md.get("headY") is not None:
            dst.head_y = int(md["headY"])
    for sd_ in payload.get("sequenceExecSpecs", []):
        i = sd_.get("li", 0)
        if i < len(lis):
            d.seq_exec(lis[i], sd_.get("y1", 0), sd_.get("y2", 0),
                       shaded=sd_.get("shaded", False))
    for dd in payload.get("sequenceDestructions", []):
        i = dd.get("li", 0)
        if i < len(lis):
            d.destructions.append(SeqDestruction(lis[i], dd.get("y", 0)))
    for fd_ in payload.get("sequenceFragments", []):
        members = [lis[i] for i in fd_.get("li", []) if i < len(lis)]
        if not members:
            continue
        d.fragments.append(SeqFragment(
            members, fd_.get("y1", 0), fd_.get("y2", 0),
            fd_.get("operator", 'opt'), guard=fd_.get("guard"),
            operands=fd_.get("operands"), name=fd_.get("name"),
            frag_range=fd_.get("range")))
    for cd_ in payload.get("sequenceConstraints", []):
        i = cd_.get("li", 0)
        if i < len(lis):
            d.constraints.append(SeqConstraint(
                lis[i], cd_.get("y", 0), cd_.get("text", ""),
                dx=cd_.get("dx", 0), state_notation=cd_.get("rounded", False)))

    def _edge_port(pd, ref):
        """Rebuild an edge-anchored port. FramePort references bind to the
        Diagram's frame_ports instance (single shared object)."""
        if pd.get(_DD_KIND) == "FramePort":
            for fp in d.frame_ports:
                if (fp.label, fp.side, fp.offset) == (
                        pd.get("label", ""), pd.get("side", "left"),
                        pd.get("offset", 0.5)):
                    return fp
        return _port_from_dict(pd, ref)

    # Parametric constraint parameters (§9.6) — restore before edges so
    # binding endpoints resolve by localId
    for pd in payload.get("parParams", []):
        oi = pd.get("owner")
        owner = None
        if oi is not None and 0 <= int(oi) < len(d.nodes):
            owner = d.nodes[int(oi)]
        p = ParParam(pd.get("name", ""), side=pd.get("side", "left"),
                     offset=pd.get("offset", 0.5), owner=owner)
        b = pd.get("bounds") or [0, 0, 8, 8]
        p.x, p.y, p.w, p.h = b
        p.placed = bool(b[2] and b[3])
        d.par_params.append(p)
        if pd.get("localId"):
            by_local[pd["localId"]] = p

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
                 label=ed.get("label"),
                 source_label=ed.get("sourceLabel"),
                 target_label=ed.get("targetLabel"),
                 item_flow=ed.get("itemFlow"),
                 item_position=ed.get("itemPosition", 0.5))
        e.waypoints = [tuple(w) for w in ed.get("waypoint", [])]
        e.is_binding = bool(ed.get("binding"))
        sp = ed.get("sourcePort")
        if sp:
            e.source_port = _edge_port(sp, s)
            s.ports.append(e.source_port)
        tp = ed.get("targetPort")
        if tp:
            e.target_port = _port_from_dict(tp, t)
            t.ports.append(e.target_port)
        d.edges.append(e)
    return d


def from_di_xmi(xml_text):
    """Restore a :func:`from_di`-compatible payload from an ``xmi:XMI``
    document produced by :func:`to_di_xmi`.  Chain with
    :func:`from_di` for the Diagram object::

        d2 = from_di(from_di_xmi(xml_text))

    .. versionadded:: 0.6.1
    """
    import xml.etree.ElementTree as ET

    di_tag = "{%s}" % DI_NS
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError("invalid XMI document: %s" % exc)
    diagram = root.find("%sDiagram" % di_tag)
    if diagram is None:
        raise ValueError("no di:Diagram element in the XMI document")

    sd = {"xmiType": "DI:Diagram", "namespace": DI_NS,
          "diVersion": DI_VERSION, "dcNs": DC_NS, "dgNs": DG_NS,
          "generator": "diagramboxes", "ownedElement": [], "edges": []}

    def walk(el):
        """Parse the diagram's direct di:Shape children."""
        for child in el.findall("%sShape" % di_tag):
            shape_sd = _parse_shape_element(child)
            sd["ownedElement"].append(shape_sd)
            walk_shape(child, shape_sd)

    def walk_shape(el, shape_sd):
        for child in el:
            tag = child.tag.split("}")[-1]
            if tag == "Shape":
                sub_sd = _parse_shape_element(child)
                shape_sd.setdefault("ownedElement", []).append(sub_sd)
                walk_shape(child, sub_sd)

    for child in diagram:
        tag = child.tag.split("}")[-1]
        if tag == "Shape":
            shape_sd = _parse_shape_element(child)
            sd["ownedElement"].append(shape_sd)
            walk_shape(child, shape_sd)
        elif tag == "ownedElement":
            for sub in child:
                stag = sub.tag.split("}")[-1]
                if stag == "Shape":
                    shape_sd = _parse_shape_element(sub)
                    sd["ownedElement"].append(shape_sd)
                    walk_shape(sub, shape_sd)

    for el in diagram.findall("%sEdge" % di_tag):
        d = {"xmiType": "DI:Edge", "localId": _xmi_id(el),
             "source": el.get("source"), "target": el.get("target"),
             "waypoint": []}
        for w in el.findall("waypoint"):
            d["waypoint"].append([float(w.get("x", 0)), float(w.get("y", 0))])
        nm = el.find("name")
        if nm is not None:
            d["label"] = nm.text or ""
        spe = el.find("sourcePort")
        if spe is not None:
            d["sourcePort"] = {"label": spe.get("label", ""),
                               "side": spe.get("side", "left")}
            if spe.get("offset") is not None:
                d["sourcePort"]["offset"] = float(spe.get("offset"))
            if spe.get("direction"):
                d["sourcePort"]["direction"] = spe.get("direction")
        tpe = el.find("targetPort")
        if tpe is not None:
            d["targetPort"] = {"label": tpe.get("label", ""),
                               "side": tpe.get("side", "left")}
            if tpe.get("offset") is not None:
                d["targetPort"]["offset"] = float(tpe.get("offset"))
            if tpe.get("direction"):
                d["targetPort"]["direction"] = tpe.get("direction")
        ls = el.get("lineStyle")
        if ls:
            d["lineStyle"] = ls
        ss = el.get("sourceStyle")
        if ss:
            d["sourceStyle"] = ss
        ts = el.get("targetStyle")
        if ts:
            d["targetStyle"] = ts
        if el.get("binding") == "true":
            d["binding"] = True
        sl = el.find("sourceLabel")
        if sl is not None:
            d["sourceLabel"] = sl.text or ""
        tl = el.find("targetLabel")
        if tl is not None:
            d["targetLabel"] = tl.text or ""
        item_flow = el.find("itemFlow")
        if item_flow is not None:
            d["itemFlow"] = item_flow.text or ""
            pos_attr = item_flow.get("position")
            if pos_attr is not None:
                d["itemPosition"] = float(pos_attr)
        sd["edges"].append(d)

    fr = diagram.find("%sDiagramFrame" % di_tag)
    if fr is not None:
        fd: dict = {"kind": str(fr.get("kind", "bdd"))}
        for xk, jk in (("elementKind", "elementKind"),
                       ("elementName", "elementName"),
                       ("diagramName", "diagramName")):
            if fr.get(xk):
                fd[jk] = str(fr.get(xk))
        ports: list = []
        for pel in fr.findall("port"):
            pd: dict = {"label": str(pel.get("label", "")),
                        "side": str(pel.get("side", "left"))}
            off = pel.get("offset")
            if off is not None:
                pd["offset"] = float(off)
            if pel.get("direction"):
                pd["direction"] = str(pel.get("direction"))
            pd[_DD_KIND] = "FramePort"
            ifaces: list = []
            for iel in pel.findall("interface"):
                ifaces.append({"name": str(iel.get("name", "")),
                               "kind": str(iel.get("kind", "provided"))})
            if ifaces:
                pd["interfaces"] = ifaces
            ports.append(pd)
        if ports:
            fd["ports"] = ports
        sd["diagramFrame"] = fd

    for ppel in diagram.findall("%sParParam" % di_tag):
        pd = {"localId": str(ppel.get("localId", "")),
              "name": str(ppel.get("name", "")),
              "side": str(ppel.get("side", "left")),
              "offset": float(ppel.get("offset", 0.5))}
        if ppel.get("owner"):
            pd["owner"] = int(ppel.get("owner"))
        sd.setdefault("parParams", []).append(pd)

    lif_els = diagram.findall("%sLifeline" % di_tag)
    for le in lif_els:
        ld = {"label": str(le.get("label", "")),
              "x": float(le.get("x", 0)),
              "headY": float(le.get("headY", 0)),
              "created": le.get("created") == "true"}
        sd.setdefault("lifelines", []).append(ld)
    if lif_els:
        for me in diagram.findall("%sSeqMessage" % di_tag):
            sd.setdefault("sequenceMessages", []).append({
                "kind": str(me.get("kind", "async")),
                "src": int(me.get("src", 0)),
                "dst": int(me.get("dst", 0)),
                "y": float(me.get("y", 0)),
                "label": str(me.get("label")) if me.get("label") else None,
                "fromLeft": me.get("fromLeft", "true") != "false",
                "toRight": me.get("toRight", "true") != "false",
            })
        for se in diagram.findall("%sSeqExec" % di_tag):
            sd.setdefault("sequenceExecSpecs", []).append({
                "li": int(se.get("li", 0)),
                "y1": float(se.get("y1", 0)),
                "y2": float(se.get("y2", 0)),
                "shaded": se.get("shaded") == "true",
            })
        for de in diagram.findall("%sSeqDestruction" % di_tag):
            sd.setdefault("sequenceDestructions", []).append({
                "li": int(de.get("li", 0)),
                "y": float(de.get("y", 0)),
            })
        for fe in diagram.findall("%sSeqFragment" % di_tag):
            fds = {"operator": str(fe.get("operator", "opt")),
                   "y1": float(fe.get("y1", 0)),
                   "y2": float(fe.get("y2", 0)),
                   "li": [int(v) for v in (fe.get("lifelines") or "").split()],
                   "operands": []}
            if fe.get("range"):
                fds["range"] = str(fe.get("range"))
            if fe.get("guard"):
                fds["guard"] = str(fe.get("guard"))
            if fe.get("name"):
                fds["name"] = str(fe.get("name"))
            for op in fe.findall("operand"):
                fds["operands"].append(
                    [float(op.get("y", 0)), str(op.get("guard"))]
                    if op.get("guard") else [float(op.get("y", 0)), None])
            sd.setdefault("sequenceFragments", []).append(fds)
        for ce in diagram.findall("%sSeqConstraint" % di_tag):
            sd.setdefault("sequenceConstraints", []).append({
                "li": int(ce.get("li", 0)),
                "y": float(ce.get("y", 0)),
                "text": str(ce.get("text", "")),
                "dx": float(ce.get("dx", 0)),
                "rounded": ce.get("rounded") == "true",
            })
    return sd
