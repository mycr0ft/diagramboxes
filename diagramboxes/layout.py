"""Diagram layout engine — Node, Edge, Port, Diagram classes with routing.

This module provides the core data model (``Node``, ``Edge``, ``Port``,
``Diagram``) and routing strategies selectable via ``layout(routing=...)``:

- **straight**    — ``_route_straight()`` center-to-center lines
- **orthogonal**  — ``_route_orthogonal()`` homegrown 3-segment Manhattan
                   with obstacle avoidance and edge-edge spacing
- **sugiyama**    — delegates to ``sugiyama.sugiyama_layout()``
- **elk**         — delegates to ``elk.layout_with_elk()`` (Node.js + elkjs)
- **pyelk**       — delegates to ``pyelk_layout.layout_with_pyelk()``
                   (pure-Python, ``pip install pyelk``)

Port sub-routing (``_port_route``) handles Z-shaped (3-segment) paths between
explicit ``source_port``/``target_port`` on edges.

After calling ``layout()``, the diagram is ready for rendering via
``render()`` (drawille terminal output) or ``render_svg()`` (SVG output).

See also
--------
sugiyama.py      : pure-Python Sugiyama pipeline
elk.py           : ELKjs subprocess integration (Node.js)
pyelk_layout.py  : pyelk integration (pure-Python ELK port)
primitives.py    : drawille-based terminal drawing
svg_canvas.py    : SVG vector drawing
"""

from drawille import Canvas
from diagramboxes.primitives import draw_polyline, draw_relation, draw_class_box, draw_port_box, \
    draw_comment_box, draw_view_box, draw_start_node, draw_done_node, draw_terminate_node, \
    draw_fork_join_node, draw_decision_node, \
    draw_history_node, draw_entry_exit_point, \
    SOLID, DASHED, OPEN, NONE, FILLED, DIAMOND, TRIANGLE, CIRCLE, UNOWNED, PORT_W, PORT_H
from diagramboxes.svg_canvas import SvgCanvas, svg_draw_edge, svg_draw_node, svg_draw_port, svg_draw_comment, svg_draw_view, \
    svg_draw_start_node, svg_draw_done_node, svg_draw_terminate_node, \
    svg_draw_fork_join_node, svg_draw_decision_node, \
    svg_draw_history_node, svg_draw_entry_exit_point

_MIN_PORT_SPACING = 8
from collections import defaultdict
from diagramboxes.sugiyama import sugiyama_layout


class Port:
    """A small box on a node's boundary for structured connections.

    Ports are positioned along a node side using a proportional offset
    (0.0 = top/left, 1.0 = bottom/right).  They are rendered as 8×8 px
    boxes with an optional direction arrow inside and the label outside.

    Parameters
    ----------
    label : str
        Text shown outside the port box (away from the node).
    side : {'left', 'right', 'top', 'bottom'}
        Which edge of the parent node the port sits on.
    offset : float or None
        Proportional position along the side (0.0–1.0), or ``None`` for
        auto-distribution (evenly spaced with minimum gap).
    direction : {'in', 'out', 'inout', None}
        ``'in'``  → arrow points toward node interior (input).
        ``'out'`` → arrow points away from node (output).
        ``'inout'`` → bidirectional double-headed arrow.
        ``None``  → no arrow drawn (default).

    See also
    --------
    Node.add_port : Attach a port to a node.
    Edge : source_port / target_port parameters use Port objects.
    """

    def __init__(self, label, side='left', offset=0.5, direction=None,
                 label_inside=False):
        self.label = label
        self.side = side
        self.offset = offset
        self.direction = direction
        self.label_inside = label_inside  # draw label inside the node (v0.4.0)
        self.parent = None
        self.x = self.y = 0

    @property
    def w(self):
        return PORT_W

    @property
    def h(self):
        return PORT_H

    @property
    def cx(self):
        return self.x + PORT_W // 2

    @property
    def cy(self):
        return self.y + PORT_H // 2

    def box(self):
        return (self.x, self.y, self.x + PORT_W, self.y + PORT_H)

    def update_pos(self):
        if not self.parent:
            return
        px, py, pw, ph = self.parent.x, self.parent.y, self.parent.w, self.parent.h
        if self.side == 'left':
            self.x = px - PORT_W
            self.y = py + int(ph * self.offset) - PORT_H // 2
        elif self.side == 'right':
            self.x = px + pw
            self.y = py + int(ph * self.offset) - PORT_H // 2
        elif self.side == 'top':
            self.x = px + int(pw * self.offset) - PORT_W // 2
            self.y = py - PORT_H
        elif self.side == 'bottom':
            self.x = px + int(pw * self.offset) - PORT_W // 2
            self.y = py + ph


class Node:
    """A diagram node (classifier) with optional stereotypes and attributes.

    Nodes are positioned by the layout engine and drawn as rectangular
    boxes with centered text.  Stereotypes appear above the name in
    guillemets (\\u00ab...\\u00bb).  Attributes appear below a separator
    line.

    Parameters
    ----------
    name : str
        Primary label shown inside the box.
    stereotypes : list of str, optional
        Stereotype labels shown above the name (e.g. ``['block']``).
    attributes : list of str, optional
        Attribute/method lines shown below a separator
        (e.g. ``['+ voltage : float', '# state : int']``).

    See also
    --------
    Diagram.add_node : Factory method for creating registered nodes.
    Port : Attachable boundary ports.
    """

    def __init__(self, name, stereotypes=None, attributes=None, rounded=False, dashed=False):
        self.name = name
        self.stereotypes = stereotypes or []
        self.attributes = attributes or []
        self.rounded = rounded
        self.dashed = dashed
        self.ports = []
        # Composite-structure nesting (v0.4.0): a node may own child nodes
        # drawn *inside* its box (e.g. composite states, part assemblies).
        self.parent = None
        self.children = []
        self.x = self.y = self.w = self.h = 0
        self._calc_size()

    def _calc_size(self):
        tw = []
        if self.stereotypes:
            tw.extend(len(f'\u00ab{s}\u00bb') for s in self.stereotypes)
        tw.append(len(self.name))
        if self.attributes:
            tw.extend(len(a) for a in self.attributes)
        max_tw = max(tw) if tw else 0
        self.w = max(max_tw * 2 + 6, 26)
        total_lines = len(self.stereotypes) + 1
        if self.attributes:
            total_lines += 1 + len(self.attributes)
        self.h = total_lines * 5 + 8

    def add_port(self, label, side='left', offset=None, direction=None,
                 label_inside=False):
        p = Port(label, side, offset, direction, label_inside=label_inside)
        p.parent = self
        self.ports.append(p)
        return p

    def add_attribute(self, text):
        self.attributes.append(text)
        self._calc_size()

    def add_child(self, node):
        """Nest ``node`` inside this node (composite structure, v0.4.0).

        The child keeps its own box; the layout engine inflates this
        node's size to contain it and places children in rows below the
        title/attribute area.  Edges between siblings of the same parent
        are routed inside the parent; edges crossing the boundary are
        re-anchored to the outermost ancestor (UML composite-structure
        convention).
        """
        node.parent = self
        self.children.append(node)
        return node

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    def contains(self, px, py):
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h


class Comment:
    """A comment/documentation node with a folded (dog-ear) corner.

    Comments are drawn as rectangles with the top-right corner folded
    over (dog-ear), distinguishing them from regular classifier diagramboxes.

    Parameters
    ----------
    text : str
        The comment text shown inside the box.
    """

    def __init__(self, text):
        self.text = text
        self.x = self.y = 0
        self.w = max(len(text) * 2 + 6, 26)
        self.h = 21

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)


_ACTIVITY_RADIUS = 8


class StartNode:
    """Activity start node — filled circle.

    Parameters
    ----------
    name : str
        Optional label (defaults to 'Start').
    """

    def __init__(self, name='Start'):
        self.name = name
        self.r = _ACTIVITY_RADIUS
        d = self.r * 2 + 2
        self.w = self.h = d
        self.x = self.y = 0
        self.parent = None  # composite-structure parent (v0.4.0)

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)


class DoneNode:
    """Activity done / accept node — bullseye (inset filled circle).

    Parameters
    ----------
    name : str
        Optional label (defaults to 'Done').
    """

    def __init__(self, name='Done'):
        self.name = name
        self.r = _ACTIVITY_RADIUS
        d = self.r * 2 + 2
        self.w = self.h = d
        self.x = self.y = 0
        self.parent = None  # composite-structure parent (v0.4.0)

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)


class TerminateNode:
    """Activity terminate node — open circle with an X through the center.

    Parameters
    ----------
    name : str
        Optional label (defaults to 'Terminate').
    """

    def __init__(self, name='Terminate'):
        self.name = name
        self.r = _ACTIVITY_RADIUS
        d = self.r * 2 + 2
        self.w = self.h = d
        self.x = self.y = 0
        self.parent = None  # composite-structure parent (v0.4.0)

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)


class ForkJoinNode:
    """Activity fork / join node — a thick synchronization bar.

    Parameters
    ----------
    name : str
        Optional label.
    w : int
        Width of the bar (default 36).
    h : int
        Height of the bar (default 8).
    """

    def __init__(self, name='', w=36, h=8):
        self.name = name
        self.w = w
        self.h = h
        self.x = self.y = 0
        self.parent = None  # composite-structure parent (v0.4.0)

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)


class DecisionNode:
    """Activity decision / merge node — a diamond shape.

    Parameters
    ----------
    name : str
        Optional label shown inside the diamond.
    """

    def __init__(self, name='', size=28):
        self.name = name
        self.size = size
        self.w = size
        self.h = size
        self.x = self.y = 0
        self.parent = None  # composite-structure parent (v0.4.0)

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)


# ── state-machine pseudostates ──
#
# These share shapes with the activity control nodes above.  They exist as
# distinct classes so that diagram authors (and the sysmlpy adapter) can
# mark intent explicitly and so that future per-kind rendering tweaks (for
# example, labelling a choice diamond with its guard) have a clear home.
#
# UML 2.5 / SysML v2 state-machine pseudostate canonical set:
#   initial, final, terminate, junction, choice, fork, join,
#   shallow-history, deep-history, entry-point, exit-point.
# All are covered here except entry/exit points which are boundary markers
# on a StateNode — see EntryPoint / ExitPoint below.

class InitialPseudostate(StartNode):
    """Filled black circle — state-machine initial pseudostate.

    Visually identical to the activity :class:`StartNode`; the source of
    the single automatic transition into the first real state.
    """

    def __init__(self, name='initial'):
        super().__init__(name=name)


class JunctionPseudostate(StartNode):
    """Filled black circle — state-machine junction pseudostate.

    Visually identical to the initial pseudostate but used as an
    intermediate merge/branch point in compound transition paths.  Named
    junctions (```junction J1;```) get a label rendered alongside.  Drawn
    through the same primitive as :class:`StartNode`.
    """

    def __init__(self, name=''):
        super().__init__(name=name)


class ChoicePseudostate(DecisionNode):
    """Diamond — state-machine choice pseudostate.

    Identical shape to the activity :class:`DecisionNode`; selects one
    outgoing transition at runtime based on guard expressions.  Held as a
    distinct class so the intent is structural.
    """

    def __init__(self, name=''):
        super().__init__(name=name)


class ForkPseudostate(ForkJoinNode):
    """Thick synchronization bar — state-machine fork pseudostate.

    Splits one incoming transition into multiple orthogonal region entries.
    Visually identical to the activity :class:`ForkJoinNode`.
    """

    def __init__(self, name='', w=36, h=8):
        super().__init__(name=name, w=w, h=h)


class JoinPseudostate(ForkJoinNode):
    """Thick synchronization bar — state-machine join pseudostate.

    Merges multiple orthogonal region exits into one outgoing transition.
    Visually identical to the activity :class:`ForkJoinNode`.
    """

    def __init__(self, name='', w=36, h=8):
        super().__init__(name=name, w=w, h=h)


class FinalState(DoneNode):
    """Bullseye — state-machine final state (activity-final shape).

    Visually identical to the activity :class:`DoneNode`; entering it
    terminates the enclosing state machine.
    """

    def __init__(self, name='final'):
        super().__init__(name=name)


class TerminatePseudostate(TerminateNode):
    """Open circle with X — state-machine terminate pseudostate.

    Entering a terminate pseudostate ends the execution of the owning
    state machine without running any exit behaviours of enclosing states.
    Visually identical to the activity :class:`TerminateNode`.
    """

    def __init__(self, name='terminate'):
        super().__init__(name=name)


# State-machine history pseudostate — needs its own primitive.

class HistoryPseudostate:
    """Shallow- or deep-history pseudostate — open circle with ``H`` / ``H*``.

    Resumes the most-recent active substate of the owning composite state
    (shallow) or the most-recent active recursive substate configuration
    (deep).  Drawn via :func:`diagramboxes.primitives.draw_history_node` /
    :func:`diagramboxes.svg_canvas.svg_draw_history_node`.

    Parameters
    ----------
    name : str
        Optional label (defaults to ``''``; the rendered glyph already
        says ``H`` / ``H*``).
    deep : bool
        ``True`` → deep history (``H*``); ``False`` → shallow (``H``).
    r : int
        Radius of the surrounding circle.  Defaults to ``8`` (slightly
        larger than the activity start node so the H glyph fits).
    """

    def __init__(self, name='', deep=False, r=8):
        self.name = name
        self.deep = deep
        self.r = r
        d = r * 2 + 2
        self.w = self.h = d
        self.x = self.y = 0
        self.parent = None  # composite-structure parent (v0.4.0)

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)


# Entry/exit point — hollow circle attachable to a state's boundary.
# Lives in the same bucket as Port so routing treats it identically (port-
# to-port Z-shaped routing).  The only difference is its rendering: a hollow
# circle (via draw_entry_exit_point / svg_draw_entry_exit_point) instead of
# the small filled square used by the regular Port primitive.

class EntryPoint(Port):
    """Hollow-circle boundary marker — state entry point.

    A named point on a composite state's boundary at which an external
    transition can enter and then dispatch to an internal substate.  Drawn
    as an open circle of the same diameter as a :class:`Port` box.  Connected
    via the regular port-to-port routing path, so edges between an entry
    point and an internal substate work exactly like edges between two
    ports.
    """

    def __init__(self, label, side='left', offset=0.5, direction=None):
        super().__init__(label, side=side, offset=offset, direction=direction)
        self.kind = 'entry'


class ExitPoint(Port):
    """Hollow-circle boundary marker — state exit point.

    A named point on a composite state's boundary through which an internal
    substate can hand control to an external transition.  Visually identical
    to :class:`EntryPoint`; the intent is signalled through ``kind`` and
    by the direction of the connecting edges (entry edges in, exit edges
    out).
    """

    def __init__(self, label, side='right', offset=0.5, direction=None):
        super().__init__(label, side=side, offset=offset, direction=direction)
        self.kind = 'exit'


class StateNode(Node):
    """Rounded-corner node for a UML/SysML state.

    Visually identical to a :class:`Node` with ``rounded=True`` (which is
    already a base ``Node`` capability) but with two niceties:

    1.  Defaults to the ``«state»`` stereotype when none is supplied, so
        rendering code can simply emit a SysML state without typing
        ``stereotypes=['state']`` every time.
    2.  Accepts an optional list of ``substates`` (other :class:`StateNode`
        or any :class:`Node` subclass).  At present these are rendered as
        top-level siblings — a future layout pass can render them nested
        inside the parent state's content area (mirroring
        :class:`View.children`).

    Parameters
    ----------
    name : str
        State name shown inside the box.
    stereotypes : list of str, optional
        Defaults to ``['state']``.  Pass an empty list to suppress the
        stereotype line entirely.
    attributes : list of str, optional
        Entry/exit/do behaviour lines shown below the separator.
    substates : list of Node, optional
        Child states for future composite-state layout.
    """

    def __init__(self, name, stereotypes=None, attributes=None,
                 substates=None, dashed=False):
        if stereotypes is None:
            stereotypes = ['state']
        super().__init__(name, stereotypes=stereotypes,
                         attributes=attributes, rounded=True, dashed=dashed)
        self.substates = list(substates) if substates else []


class View:
    """A view / package node with a folder-tab label area.

    Views are drawn as a rectangle with a "tab" at the top-left corner
    containing the name (and optional stereotypes).  Attributes appear
    in the main content area below a separator.  This matches the UML
    ``«package»`` and SysML ``«view»`` notation.

    Views can also contain child nodes, which are drawn inside the
    content area (below the tab) rather than as top-level elements.

    Parameters
    ----------
    name : str
        Primary label shown in the tab.
    stereotypes : list of str, optional
        Stereotype labels (e.g. ``['view']``, ``['package']``).
    attributes : list of str, optional
        Attribute/method lines shown below a separator.
    """

    def __init__(self, name, stereotypes=None, attributes=None, dashed=False):
        self.name = name
        self.stereotypes = stereotypes or []
        self.attributes = attributes or []
        self.children = []
        self.dashed = dashed
        self.x = self.y = self.w = self.h = 0
        self._calc_size()

    def _tab_height(self):
        return (1 + len(self.stereotypes)) * 5 + 4

    def _calc_size(self):
        tw = []
        if self.stereotypes:
            tw.extend(len(f'\u00ab{s}\u00bb') for s in self.stereotypes)
        tw.append(len(self.name))
        if self.attributes:
            tw.extend(len(a) for a in self.attributes)
        max_tw = max(tw) if tw else 0
        tab_h = self._tab_height()
        attr_h = (1 + len(self.attributes)) * 5 if self.attributes else 0
        if self.children:
            pad = 8
            child_gap = 4
            max_child_w = max(n.w for n in self.children)
            total_child_h = sum(n.h for n in self.children) + child_gap * (len(self.children) - 1)
            self.w = max(max_tw * 2 + 6, max_child_w + pad * 2, 26)
            self.h = tab_h + 2 + attr_h + total_child_h + pad * 2
        else:
            self.w = max(max_tw * 2 + 6, 26)
            self.h = tab_h + attr_h + 6

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    @property
    def content_y(self):
        """Y-coordinate where the content / children area starts."""
        return self.y + self._tab_height() + 2

    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    def add_attribute(self, text):
        self.attributes.append(text)
        self._calc_size()

    def add_child(self, node):
        """Add a node as a child rendered inside this view/package.

        Child nodes are positioned inside the content area of the view
        during layout and are not drawn as top-level diagramboxes.
        """
        self.children.append(node)
        self._calc_size()


class Edge:
    """A directed or undirected connection between two nodes (or ports).

    Edges can connect directly between nodes (using automatic boundary
    ports) or between explicit ``Port`` objects on each node.  The
    routing engine computes ``waypoints`` — a list of (x, y) waypoints
    that define the edge path.

    Parameters
    ----------
    source, target : Node
        The endpoints of the edge.
    line_style : {'solid', 'dashed'}, optional
        Line appearance.  Default ``SOLID``.
    source_style, target_style : str or None, optional
        Arrowhead at each end: ``NONE``, ``OPEN``, ``TRIANGLE``,
        ``DIAMOND``, ``FILLED``.  Default target_style is ``OPEN``.
    label : str, optional
        Text label placed at the Manhattan midpoint of the route.
    source_port, target_port : Port or None, optional
        Explicit port objects for structured (port-to-port) connections.
        When both are set, the routing uses L-shaped paths instead of
        the standard 3-segment boundary-port routing.

    See also
    --------
    Diagram.add_edge : Factory method.
    Port : Port objects used with source_port / target_port.
    """

    def __init__(self, source, target, *, line_style=SOLID, source_style=None,
                 target_style=OPEN, label=None, source_port=None, target_port=None):
        self.source = source
        self.target = target
        self.source_port = source_port
        self.target_port = target_port
        self.line_style = line_style
        self.source_style = source_style
        self.target_style = target_style
        self.label = label
        self.waypoints = []

    def route(self, *points):
        self.waypoints = list(points)


_SPECIAL_TYPES = (Comment, View, StartNode, DoneNode, TerminateNode, ForkJoinNode, DecisionNode)


class Diagram:
    """Top-level container for nodes, edges, and layout configuration.

    A Diagram holds a collection of Nodes and Edges and provides
    layout and rendering methods.  Layout is computed lazily on
    ``render()`` / ``render_svg()``.

    Usage
    -----
    ::

        d = Diagram()
        n1 = d.add_node('A', ['block'], attributes=['+ x'])
        n2 = d.add_node('B')
        p = n1.add_port('out', side='right', offset=0.5)
        d.add_edge(n1, n2, source_port=p, target_style=OPEN, label='conn')
        print(d.render(routing='orthogonal'))

    See also
    --------
    Node, Edge, Port : Element types.
    render, render_svg : Output methods.
    layout : Manual layout invocation.
    """

    def __init__(self):
        self.nodes = []
        self.comments = []
        self.views = []
        self.activities = []
        self.edges = []

    def add_node(self, name, stereotypes=None, attributes=None, rounded=False, dashed=False,
                 parent=None):
        """Create a new node and register it with the diagram.

        Parameters
        ----------
        name : str
            Node label shown inside the box.
        stereotypes : list of str, optional
            Stereotype labels (e.g. ``['block']``, ``['part']``).
        attributes : list of str, optional
            Attribute lines shown below a separator.
        rounded : bool, optional
            If True, draw with rounded corners (e.g. SysMLv2 part usages).
        dashed : bool, optional
            If True, draw border with dashed lines (e.g. occurrence refs).
        parent : Node, optional
            If given, the new node is nested inside ``parent`` as a
            composite-structure child (v0.4.0) instead of being laid out
            as a top-level node.

        Returns
        -------
        Node
            The newly created node.
        """
        n = Node(name, stereotypes, attributes, rounded, dashed)
        if parent is not None:
            parent.add_child(n)
        self.nodes.append(n)
        return n

    def add_comment(self, text):
        """Create a comment node and register it with the diagram.

        Comments are drawn as rectangles with a folded (dog-ear)
        top-right corner.  They are placed below regular nodes in
        the layout.

        Parameters
        ----------
        text : str
            The comment text shown inside the box.

        Returns
        -------
        Comment
        """
        c = Comment(text)
        self.comments.append(c)
        return c

    def add_view(self, name, stereotypes=None, attributes=None, dashed=False):
        """Create a view / package node and register it with the diagram.

        Views are drawn as rectangles with a folder-tab containing the
        name (and optional stereotypes).  They are placed below regular
        nodes in the layout.

        Parameters
        ----------
        name : str
            Primary label shown in the tab.
        stereotypes : list of str, optional
            Stereotype labels (e.g. ``['view']``, ``['package']``).
        attributes : list of str, optional
            Attribute/method lines shown below a separator.
        dashed : bool, optional
            If True, the border is drawn dashed (for imported packages).

        Returns
        -------
        View
        """
        v = View(name, stereotypes, attributes, dashed)
        self.views.append(v)
        return v

    def add_start(self, name='Start', parent=None):
        """Add an activity start node (filled circle).

        Parameters
        ----------
        name : str
            Optional label.

        Returns
        -------
        StartNode
        """
        n = StartNode(name)
        if parent is not None:
            n.parent = parent  # drawn inside the composite (v0.4.0)
        self.activities.append(n)
        return n

    def add_done(self, name='Done', parent=None):
        """Add an activity done / accept node (bullseye).

        Parameters
        ----------
        name : str
            Optional label.

        Returns
        -------
        DoneNode
        """
        n = DoneNode(name)
        if parent is not None:
            n.parent = parent  # drawn inside the composite (v0.4.0)
        self.activities.append(n)
        return n

    def add_terminate(self, name='Terminate', parent=None):
        """Add an activity terminate node (circle with X).

        Parameters
        ----------
        name : str
            Optional label.

        Returns
        -------
        TerminateNode
        """
        n = TerminateNode(name)
        if parent is not None:
            n.parent = parent  # drawn inside the composite (v0.4.0)
        self.activities.append(n)
        return n

    def add_fork(self, name='', w=36, h=8, parent=None):
        """Add an activity fork node (synchronization bar).

        Parameters
        ----------
        name : str
            Optional label.
        w, h : int
            Bar dimensions.
        parent : Node, optional
            Composite-structure parent (v0.4.0 nesting).

        Returns
        -------
        ForkJoinNode
        """
        n = ForkJoinNode(name, w, h)
        if parent is not None:
            n.parent = parent
        self.activities.append(n)
        return n

    def add_join(self, name='', w=36, h=8, parent=None):
        """Add an activity join node (synchronization bar).

        Same visual as fork — a thick bar.

        Parameters
        ----------
        name : str
            Optional label.
        w, h : int
            Bar dimensions.
        parent : Node, optional
            Composite-structure parent (v0.4.0 nesting).

        Returns
        -------
        ForkJoinNode
        """
        n = ForkJoinNode(name, w, h)
        if parent is not None:
            n.parent = parent
        self.activities.append(n)
        return n

    def add_decision(self, name='', size=28, parent=None):
        """Add an activity decision node (diamond).

        Parameters
        ----------
        name : str
            Optional label shown inside the diamond.
        size : int
            Width/height of the diamond bounding box.
        parent : Node, optional
            Composite node to nest the diamond inside (v0.4.0 nesting).

        Returns
        -------
        DecisionNode
        """
        n = DecisionNode(name, size)
        if parent is not None:
            n.parent = parent
        self.activities.append(n)
        return n

    def add_merge(self, name='', size=28, parent=None):
        """Add an activity merge node (diamond).

        Same visual as decision — a diamond shape.

        Parameters
        ----------
        name : str
            Optional label shown inside the diamond.
        size : int
            Width/height of the diamond bounding box.
        parent : Node, optional
            Composite-structure parent (v0.4.0 nesting).

        Returns
        -------
        DecisionNode
        """
        n = DecisionNode(name, size)
        if parent is not None:
            n.parent = parent
        self.activities.append(n)
        return n

    # ── state-machine pseudostates ──

    def add_initial(self, name='initial', parent=None):
        """Add a state-machine initial pseudostate (filled black circle).

        Parameters
        ----------
        name : str
            Optional label.
        parent : Node, optional
            Composite node to nest the pseudostate inside (v0.4.0).

        Returns
        -------
        InitialPseudostate
        """
        n = InitialPseudostate(name=name)
        if parent is not None:
            n.parent = parent
        self.activities.append(n)
        return n

    def add_junction(self, name=''):
        """Add a state-machine junction pseudostate (filled black circle).

        Returns
        -------
        JunctionPseudostate
        """
        n = JunctionPseudostate(name=name)
        self.activities.append(n)
        return n

    def add_choice(self, name=''):
        """Add a state-machine choice pseudostate (diamond).

        Returns
        -------
        ChoicePseudostate
        """
        n = ChoicePseudostate(name=name)
        self.activities.append(n)
        return n

    def add_fork_pseudostate(self, name='', w=36, h=8):
        """Add a state-machine fork pseudostate (synchronization bar).

        Distinct name from :meth:`add_fork` to mark state-machine intent;
        shape is identical.

        Returns
        -------
        ForkPseudostate
        """
        n = ForkPseudostate(name=name, w=w, h=h)
        self.activities.append(n)
        return n

    def add_join_pseudostate(self, name='', w=36, h=8):
        """Add a state-machine join pseudostate (synchronization bar).

        Returns
        -------
        JoinPseudostate
        """
        n = JoinPseudostate(name=name, w=w, h=h)
        self.activities.append(n)
        return n

    def add_final_state(self, name='final', parent=None):
        """Add a state-machine final state (bullseye).

        Returns
        -------
        FinalState
        """
        n = FinalState(name=name)
        if parent is not None:
            n.parent = parent  # drawn inside the composite (v0.4.0)
        self.activities.append(n)
        return n

    def add_terminate(self, name='terminate', kind='state', parent=None):
        """Add a state-machine terminate pseudostate (open circle with X).

        ``kind`` is accepted for forward compatibility — activity terminate
        (``kind='activity'``) and state terminate (``kind='state'``) share
        both shape and class today.

        Returns
        -------
        TerminatePseudostate
        """
        n = TerminatePseudostate(name=name)
        if parent is not None:
            n.parent = parent  # drawn inside the composite (v0.4.0)
        self.activities.append(n)
        return n

    def add_history(self, name='', deep=False, r=8):
        """Add a state-machine history pseudostate (open circle with H / H*).

        Returns
        -------
        HistoryPseudostate
        """
        n = HistoryPseudostate(name=name, deep=deep, r=r)
        self.activities.append(n)
        return n

    def add_state(self, name, stereotypes=None, attributes=None,
                  substates=None, dashed=False):
        """Add a state node with rounded corners and default ``«state»``.

        Returns
        -------
        StateNode
        """
        n = StateNode(name, stereotypes=stereotypes, attributes=attributes,
                      substates=substates, dashed=dashed)
        self.nodes.append(n)
        return n

    def add_entry_point(self, state, label, side='left', offset=None,
                        direction=None):
        """Attach an :class:`EntryPoint` (hollow boundary circle) to *state*.

        Returns
        -------
        EntryPoint
        """
        p = EntryPoint(label, side=side, offset=offset, direction=direction)
        p.parent = state
        state.ports.append(p)
        return p

    def add_exit_point(self, state, label, side='right', offset=None,
                       direction=None):
        """Attach an :class:`ExitPoint` (hollow boundary circle) to *state*.

        Returns
        -------
        ExitPoint
        """
        p = ExitPoint(label, side=side, offset=offset, direction=direction)
        p.parent = state
        state.ports.append(p)
        return p

    def _update_port_positions(self):
        for n in self.nodes:
            if not n.ports:
                continue

            groups = defaultdict(list)
            for p in n.ports:
                groups[p.side].append(p)

            for side, ports in groups.items():
                n_ports = len(ports)

                if n_ports >= 1 and any(p.offset is None for p in ports):
                    # Auto-distribute all ports on this side with minimum spacing
                    if side in ('left', 'right'):
                        px = n.x - PORT_W if side == 'left' else n.x + n.w
                        total_h = n_ports * PORT_H + (n_ports - 1) * _MIN_PORT_SPACING
                        start_y = n.y + max(0, (n.h - total_h) // 2)
                        for i, p in enumerate(ports):
                            p.x = px
                            p.y = start_y + i * (PORT_H + _MIN_PORT_SPACING)
                    else:  # top / bottom
                        py = n.y - PORT_H if side == 'top' else n.y + n.h
                        total_w = n_ports * PORT_W + (n_ports - 1) * _MIN_PORT_SPACING
                        start_x = n.x + max(0, (n.w - total_w) // 2)
                        for i, p in enumerate(ports):
                            p.x = start_x + i * (PORT_W + _MIN_PORT_SPACING)
                            p.y = py
                else:
                    for p in ports:
                        p.update_pos()

    def add_edge(self, source, target, **kw):
        """Create a new edge and register it with the diagram.

        Parameters
        ----------
        source, target : Node
            Endpoint nodes.
        **kw
            Passed to ``Edge``: ``line_style``, ``source_style``,
            ``target_style``, ``label``, ``source_port``, ``target_port``.

        Returns
        -------
        Edge
            The newly created edge.
        """
        e = Edge(source, target, **kw)
        self.edges.append(e)
        return e

    def compose(self, whole, part, **kw):
        """Convenience: composition edge (filled diamond at whole, no arrow).

        Parameters
        ----------
        whole, part : Node
        **kw
            Passed through to ``add_edge``.  Overrides ``source_style``
            and ``target_style`` if provided.

        Returns
        -------
        Edge
        """
        kw.setdefault('source_style', FILLED)
        kw.setdefault('target_style', NONE)
        return self.add_edge(whole, part, **kw)

    def aggregate(self, whole, part, **kw):
        """Convenience: aggregation edge (empty diamond at whole, no arrow)."""
        kw.setdefault('source_style', DIAMOND)
        kw.setdefault('target_style', NONE)
        return self.add_edge(whole, part, **kw)

    def depend(self, client, supplier, **kw):
        """Convenience: dependency edge (dashed, open arrow at supplier)."""
        kw.setdefault('line_style', DASHED)
        kw.setdefault('target_style', OPEN)
        kw.setdefault('source_style', NONE)
        return self.add_edge(client, supplier, **kw)

    def annotate(self, client, supplier, **kw):
        """Convenience: SysMLv2 annotation edge (same style as dependency).

        An annotation in SysMLv2 is a dashed line with an open arrow at the
        element being annotated — identical styling to ``depend()``.
        """
        return self.depend(client, supplier, **kw)

    def contain(self, container, element, **kw):
        """Convenience: containment edge (circle at container end).

        In UML/SysML, a containment relationship uses an open circle
        at the container end to indicate namespace membership.

        Parameters
        ----------
        container : Node or View
            The owning namespace / container.
        element : Node
            The contained element.
        **kw
            Passed through to ``add_edge``.

        Returns
        -------
        Edge
        """
        kw.setdefault('source_style', CIRCLE)
        kw.setdefault('target_style', NONE)
        return self.add_edge(container, element, **kw)

    def uncontain(self, container, element, **kw):
        """Convenience: unowned-membership edge (open circle at container end).

        In SysML, unowned membership is shown with an open circle (no cross)
        at the container end, indicating membership without ownership.

        Parameters
        ----------
        container : Node or View
            The owning namespace / container.
        element : Node
            The contained element.
        **kw
            Passed through to ``add_edge``.

        Returns
        -------
        Edge
        """
        kw.setdefault('source_style', UNOWNED)
        kw.setdefault('target_style', NONE)
        return self.add_edge(container, element, **kw)

    def generalize(self, child, parent, **kw):
        """Convenience: UML generalization / inheritance (open triangle at parent).

        Parameters
        ----------
        child, parent : Node
        **kw
            Passed through to ``add_edge``.

        Returns
        -------
        Edge
        """
        kw.setdefault('source_style', NONE)
        kw.setdefault('target_style', TRIANGLE)
        return self.add_edge(child, parent, **kw)

    def _child_nodes(self):
        """Return set of all nodes that are children of a View or nested
        inside a composite Node (v0.4.0)."""
        children = set()
        for v in self.views:
            children.update(v.children)
        children.update(self._node_descendants())
        return children

    def _node_descendants(self):
        """All nodes nested inside composite nodes (transitive, v0.4.0)."""
        desc = set()

        def walk(n):
            for c in n.children:
                desc.add(c)
                walk(c)

        for n in self.nodes:
            walk(n)
        return desc

    # ── composite-node (nested) layout ──────────────────────────

    _NEST_PAD = 4        # inner padding around the children area
    _NEST_GAP = 4        # horizontal gap between children in a row
    _NEST_ROW_GAP = 6    # vertical gap between rows of children
    _NEST_MAX_ROW = 64   # wrap row when it exceeds this width

    @classmethod
    def _pack_rows(cls, items):
        """Greedy row packing: items wider than the row budget wrap."""
        rows, cur, cur_w = [], [], 0
        for it in items:
            if cur and cur_w + cls._NEST_GAP + it.w > cls._NEST_MAX_ROW:
                rows.append(cur)
                cur, cur_w = [], 0
            cur.append(it)
            cur_w += it.w if len(cur) == 1 else cls._NEST_GAP + it.w
        if cur:
            rows.append(cur)
        return rows or [[]]

    def _size_nested_tree(self, node=None):
        """Post-order: inflate composite nodes to contain their children.

        Leaf sizes come from ``_calc_size()``; composites store their
        original text area in ``_text_w``/``_text_h`` and the packed rows
        in ``_rows`` so ``_place_nested_tree`` can position children.
        Parented activities (pseudostates inside a composite) participate
        in the same row packing as child nodes.
        """
        if node is None:
            for n in self.nodes:
                if n.parent is None:
                    self._size_nested_tree(n)
            return
        for c in node.children:
            self._size_nested_tree(c)
        items = list(node.children) + [
            a for a in self.activities if getattr(a, 'parent', None) is node]
        # Normalize to the pure text size first — makes repeated sizing
        # idempotent (the previous inflation is discarded each pass).
        node._calc_size()
        # Opt-in: nodes with inside-labeled boundary ports get vertical
        # room so the port marker and its label clear the text rows.
        if any(getattr(p, 'label_inside', False) for p in node.ports):
            lr = sum(1 for p in node.ports
                     if p.side in ('left', 'right'))
            node.h = max(node.h, node.h + lr * (PORT_H + 4) + 10)
            # Horizontal room: inside labels hug their own border, so
            # the centered text must clear label widths on both sides.
            left_max = max((len(p.label or '') for p in node.ports
                            if p.side == 'left'), default=0)
            right_max = max((len(p.label or '') for p in node.ports
                             if p.side == 'right'), default=0)
            if left_max or right_max:
                node.w = max(node.w, node.w + 2 * (PORT_W + 2 + left_max)
                             + 2 * (PORT_W + 2 + right_max) + 8)
        if not items:
            node._rows = []
            node._text_w, node._text_h = node.w, node.h
            return
        node._text_w, node._text_h = node.w, node.h
        rows = self._pack_rows(items)
        node._rows = rows
        row_ws = [sum(c.w for c in r) + self._NEST_GAP * (len(r) - 1)
                  for r in rows]
        inner_w = max(row_ws)
        inner_h = sum(max(c.h for c in r) for r in rows) \
            + self._NEST_ROW_GAP * (len(rows) - 1)
        node.w = max(node._text_w, inner_w + 2 * self._NEST_PAD)
        node.h = node._text_h + self._NEST_PAD + 2 + inner_h \
            + self._NEST_PAD

    def _place_nested_tree(self, node=None):
        """Position children rows inside their composite parent (top-down)."""
        if node is None:
            for n in self.nodes:
                if n.parent is None:
                    self._place_nested_tree(n)
            return
        rows = getattr(node, '_rows', None)
        if not rows:
            return
        top = node.y + node._text_h + self._NEST_PAD + 2
        for r in rows:
            rh = max(c.h for c in r)
            rw = sum(c.w for c in r) + self._NEST_GAP * (len(r) - 1)
            x = node.x + (node.w - rw) // 2
            for c in r:
                c.x = x
                c.y = top + (rh - c.h) // 2
                x += c.w + self._NEST_GAP
            top += rh + self._NEST_ROW_GAP
        for c in node.children:
            self._place_nested_tree(c)

    @staticmethod
    def _top_ancestor(n):
        """Outermost composite ancestor of ``n`` (itself if top-level)."""
        while getattr(n, 'parent', None) is not None:
            n = n.parent
        return n

    @staticmethod
    def _boundary_point(node, tx, ty):
        """Point on ``node``'s border on the segment toward (tx, ty)."""
        dx, dy = tx - node.cx, ty - node.cy
        if dx == 0 and dy == 0:
            return (node.x + node.w, node.cy)
        t = min(node.w / 2 / abs(dx) if dx else float('inf'),
                node.h / 2 / abs(dy) if dy else float('inf'))
        return (round(node.cx + dx * t), round(node.cy + dy * t))

    def _reanchor_nested_edges(self):
        """Pre-pass: adjust edge endpoints for composite nesting (v0.4.0).

        - Both endpoints under the same outermost ancestor: the edge is
          internal — routed as a straight boundary-to-boundary segment
          (clipped at each child box) and marked ``_nested_internal``.
        - Endpoints under different ancestors: the edge is re-anchored to
          the two outermost ancestors (original endpoints kept in
          ``_nested_orig``) so the engine routes across the parent
          boundary, per UML composite-structure convention.
        """
        desc = self._node_descendants()
        for e in self.edges:
            s, t = e.source, e.target
            s_nested = s in desc or getattr(s, 'parent', None) is not None
            t_nested = t in desc or getattr(t, 'parent', None) is not None
            if not s_nested and not t_nested:
                continue
            sa, ta = self._top_ancestor(s), self._top_ancestor(t)
            if sa is ta:
                sx, sy = self._boundary_point(s, t.cx, t.cy)
                tx, ty = self._boundary_point(t, s.cx, s.cy)
                e.route((sx, sy), (tx, ty))
                e._nested_internal = True
            elif sa is not s or ta is not t:
                e._nested_orig = (s, t)
                e.source, e.target = sa, ta

    def _refresh_internal_edges(self):
        """Recompute internal (same-composite) edge waypoints after children
        have been placed (v0.4.0)."""
        for e in self.edges:
            if getattr(e, '_nested_internal', False):
                s, t = e.source, e.target
                sx, sy = self._boundary_point(s, t.cx, t.cy)
                tx, ty = self._boundary_point(t, s.cx, s.cy)
                e.route((sx, sy), (tx, ty))

    def _is_visual_containment(self, edge):
        """Check if edge is a containment edge that's visually redundant.

        Returns True if the edge has a containment marker (CIRCLE or UNOWNED)
        and the target is a child of the source View, making the arrow redundant
        since the visual enclosure already indicates containment.
        """
        if edge.source_style not in (CIRCLE, UNOWNED):
            return False
        if not isinstance(edge.source, View):
            return False
        return edge.target in edge.source.children

    def _assign_layers(self):
        child_nodes = self._child_nodes()
        eligible = ([n for n in self.nodes if n not in child_nodes]
                    + [a for a in self.activities
                       if not getattr(a, 'parent', None)])
        incoming = {n: set() for n in eligible}
        for e in self.edges:
            if getattr(e, '_nested_internal', False):
                continue  # internal to a composite — not a layer constraint
            if isinstance(e.source, (Comment, View)) or isinstance(e.target, (Comment, View)):
                continue
            if e.source in child_nodes or e.target in child_nodes:
                continue
            incoming[e.target].add(e.source)

        roots = [n for n in eligible if not incoming[n]]
        if not roots and eligible:
            roots = [eligible[0]]

        layer_of = {}
        queue = [(n, 0) for n in roots]
        for n, l in queue:
            if n in layer_of:
                continue
            layer_of[n] = l
            for e in self.edges:
                if isinstance(e.target, (Comment, View)):
                    continue
                if e.target in child_nodes or e.source in child_nodes:
                    continue
                if e.source == n:
                    queue.append((e.target, l + 1))

        for n in eligible:
            if n not in layer_of:
                layer_of[n] = 0

        layers = []
        for n, l in layer_of.items():
            while len(layers) <= l:
                layers.append([])
            layers[l].append(n)
        return layers, layer_of

    # ── straight-line routing ──

    def _route_straight(self, e, layer_of):
        if e.source_port and e.target_port:
            self._port_route(e)
            return
        sl = layer_of.get(e.source, 0)
        tl = layer_of.get(e.target, 0)
        if sl < tl and abs(sl - tl) == 1:
            same_src = [e2 for e2 in self.edges
                        if e2.source == e.source and layer_of.get(e2.target) == tl]
            same_tgt = [e2 for e2 in self.edges
                        if e2.target == e.target and layer_of.get(e2.source) == sl]
            try:
                src_i = same_src.index(e)
            except ValueError:
                src_i = 0
            try:
                tgt_i = same_tgt.index(e)
            except ValueError:
                tgt_i = 0
            n_src = max(len(same_src), 1)
            n_tgt = max(len(same_tgt), 1)
            src_ports = self._distribute_ports(n_src, e.source.w)
            tgt_ports = self._distribute_ports(n_tgt, e.target.w)
            sx = e.source.x + src_ports[min(src_i, len(src_ports) - 1)]
            sy = e.source.y + e.source.h
            tx = e.target.x + tgt_ports[min(tgt_i, len(tgt_ports) - 1)]
            ty = e.target.y
            e.route((sx, sy), (tx, ty))
        else:
            e.route((e.source.cx, e.source.cy), (e.target.cx, e.target.cy))

    # ── orthogonal (Manhattan) routing ──

    def _distribute_ports(self, n, w):
        """Distribute n ports across width w with minimum spacing."""
        if n <= 0:
            return []
        spacing = w / (n + 1)
        if spacing < _MIN_PORT_SPACING and n > 1:
            spacing = _MIN_PORT_SPACING
            total = (n - 1) * spacing
            start = max(0, (w - total) / 2)
            return [int(start + spacing * i + spacing / 2) for i in range(n)]
        return [int(w * (i + 1) / (n + 1)) for i in range(n)]

    def _get_port(self, node, edge, is_source, layer_of):
        """Compute a distributed port position for an edge on a node."""
        if isinstance(node, DecisionNode):
            half = node.size // 2
            if is_source:
                target = edge.target
                dx = target.cx - node.cx
                dy = target.cy - node.cy
            else:
                source = edge.source
                dx = source.cx - node.cx
                dy = source.cy - node.cy
            if abs(dx) > half and abs(dx) > abs(dy) * 0.5:
                if dx >= 0:
                    return (node.cx + half, node.cy)  # right tip
                else:
                    return (node.cx - half, node.cy)  # left tip
            else:
                if dy >= 0:
                    return (node.cx, node.cy + half)  # bottom tip
                else:
                    return (node.cx, node.cy - half)  # top tip

        tl = layer_of.get(edge.target)
        sl = layer_of.get(edge.source)
        if is_source:
            peers = [e for e in self.edges if e.source == node and layer_of.get(e.target) == tl]
            try:
                i = peers.index(edge)
            except ValueError:
                i = 0
            n = max(len(peers), 1)
            ports = self._distribute_ports(n, node.w)
            x = node.x + ports[min(i, len(ports) - 1)]
            y = node.y + node.h
        else:
            peers = [e for e in self.edges if e.target == node and layer_of.get(e.source) == sl]
            try:
                i = peers.index(edge)
            except ValueError:
                i = 0
            n = max(len(peers), 1)
            ports = self._distribute_ports(n, node.w)
            x = node.x + ports[min(i, len(ports) - 1)]
            y = node.y
        return (x, y)

    def _segment_hits(self, x1, y1, x2, y2, obstacles):
        """Check if any obstacle box intersects the segment (x1,y1)-(x2,y2)."""
        for node in obstacles:
            nx1, ny1, nx2, ny2 = node.box()
            pad = 1
            if x1 == x2:  # vertical
                if not (nx1 - pad <= x1 <= nx2 + pad):
                    continue
                lo, hi = (y1, y2) if y1 < y2 else (y2, y1)
                if lo <= ny2 + pad and hi >= ny1 - pad:
                    return True, node
            else:  # horizontal
                if not (ny1 - pad <= y1 <= ny2 + pad):
                    continue
                lo, hi = (x1, x2) if x1 < x2 else (x2, x1)
                if lo <= nx2 + pad and hi >= nx1 - pad:
                    return True, node
        return False, None

    def _port_boundary(self, p):
        """Return (x, y) at the outer edge of a port box for edge connection."""
        if p.side == 'left':
            return (p.x, p.cy)
        elif p.side == 'right':
            return (p.x + PORT_W, p.cy)
        elif p.side == 'top':
            return (p.cx, p.y)
        else:  # bottom
            return (p.cx, p.y + PORT_H)

    def _route_clear(self, pts, e):
        """True if every axis-aligned segment of ``pts`` avoids foreign boxes.

        Obstacles are node bodies and port boxes of nodes other than the
        edge endpoints.  The first segment may graze the source node and
        the last the target node (each departs from / lands on its own
        port face); all other segments must clear both endpoints too.
        """
        foreign = [n for n in self.nodes if n not in (e.source, e.target)]
        foreign_ports = [(p, p.box()) for n in foreign for p in n.ports]

        def _hits(seg, box, pad=1):
            (x1, y1), (x2, y2) = seg
            bx1, by1, bx2, by2 = box
            if x1 == x2:
                if not (bx1 - pad <= x1 <= bx2 + pad):
                    return False
                lo, hi = (y1, y2) if y1 < y2 else (y2, y1)
                return lo <= by2 + pad and hi >= by1 - pad
            if y1 == y2:
                if not (by1 - pad <= y1 <= by2 + pad):
                    return False
                lo, hi = (x1, x2) if x1 < x2 else (x2, x1)
                return lo <= bx2 + pad and hi >= bx1 - pad
            return False  # only axis-aligned segments supported

        nseg = len(pts) - 1
        for i in range(nseg):
            seg = (pts[i], pts[i + 1])
            skip = set()
            if i == 0:
                skip.add(id(e.source))
            if i == nseg - 1:
                skip.add(id(e.target))
            for n in foreign:
                if id(n) in skip:
                    continue
                if _hits(seg, n.box()):
                    return False
            for _p, pbox in foreign_ports:
                if _hits(seg, pbox):
                    return False
        return True

    def _bypass_candidates(self, sx, sy, ax, ay, e):
        """Y-sequence candidates for a wrap-around bypass leg.

        The bypass horizontal must clear the target node's y-range, so
        candidates come from the band between the two nodes' boxes and
        from just beyond the target box on either side.
        """
        src_bottom = e.source.y + e.source.h
        tgt_top = e.target.y
        tgt_bottom = e.target.y + e.target.h
        cands = []

        # Band between the two boxes (when they don't overlap vertically)
        lo, hi = min(src_bottom, tgt_top), max(src_bottom, tgt_top)
        if hi - lo > 12:
            step = max(8, (hi - lo) // 8)
            cands.extend(range(lo + 6, hi - 6, step))

        # Just beyond the target box (above and below)
        for base in (tgt_top - 6, tgt_top - 14, tgt_top - 24,
                     tgt_bottom + 6, tgt_bottom + 14, tgt_bottom + 24):
            cands.append(base)
        return [y for y in cands if y > 0]

    def _port_route(self, e):
        """Obstacle-aware port-to-port routing.

        Anchors each end at the port's outer face and keeps the final
        segment perpendicular to the target port face.  Candidate routes
        are tried in order and the first that clears all foreign node
        bodies and port boxes wins:

        1. the direct Z-shape (source leg, horizontal leg, perpendicular
           approach) — used unchanged whenever it is already clear;
        2. wrap-around bypasses for side-facing ports: leave the source
           port, run a horizontal bypass through a free band between or
           beyond the nodes, and descend (ascend) outside the target box
           to approach the port from its own side — this is what keeps
           sugiyama layering from slicing a left/right port edge through
           intermediate boxes;
        3. horizontal-leg scans for top/bottom ports (same band logic,
           shifting the leg y);
        4. direct L-shaped fallbacks for hook geometries.

        Falls back to the plain Z-shape when nothing clears, preserving
        the pre-existing behaviour.
        """
        sp, tp = e.source_port, e.target_port
        if not sp or not tp:
            return False
        sx, sy = self._port_boundary(sp)
        tx, ty = self._port_boundary(tp)
        gap = 4

        # Perpendicular approach point for the target port face.
        if tp.side == 'left':
            ax, ay = tx - gap, ty
        elif tp.side == 'right':
            ax, ay = tx + gap, ty
        elif tp.side == 'top':
            ax, ay = tx, ty - gap
        else:  # bottom
            ax, ay = tx, ty + gap

        cands = []

        # 1. Plain Z-shape (historical behaviour) as the first candidate.
        if tp.side in ('left', 'right'):
            if (sx - tx) * (ax - tx) < 0:
                # Hook geometry — source is on the far side of the port:
                # direct L-shape (validated below, after the wraps).
                pass
            else:
                cands.append([(sx, sy), (sx, ay), (ax, ay), (tx, ty)])
        else:
            if (sy - ty) * (ay - ty) < 0:
                pass
            else:
                cands.append([(sx, sy), (ax, sy), (ax, ay), (tx, ty)])

        # 2. Wrap-around bypasses for side-facing target ports.
        if tp.side in ('left', 'right'):
            for by in self._bypass_candidates(sx, sy, ax, ay, e):
                if by == ay:
                    continue
                # Descend/ascend outside the target box on the port side.
                cands.append([(sx, sy), (sx, by), (ax, by),
                              (ax, ay), (tx, ty)])

        # 3. Horizontal-leg scans for top/bottom target ports.
        else:
            for my in self._bypass_candidates(sx, sy, ax, ay, e):
                if my == sy:
                    continue
                cands.append([(sx, sy), (ax, my), (ax, ay), (tx, ty)])

        # 4. Direct L-shaped fallbacks (hook geometries).
        if tp.side in ('left', 'right') and (sx - tx) * (ax - tx) < 0:
            if abs(ty - sy) > abs(tx - sx):
                cands.append([(sx, sy), (sx, ty), (tx, ty)])
            else:
                cands.append([(sx, sy), (tx, sy), (tx, ty)])
        elif tp.side in ('top', 'bottom') and (sy - ty) * (ay - ty) < 0:
            if abs(ty - sy) > abs(tx - sx):
                cands.append([(sx, sy), (sx, ty), (tx, ty)])
            else:
                cands.append([(sx, sy), (tx, sy), (tx, ty)])

        for pts in cands:
            # drop consecutive duplicate points
            dedup = [pts[0]]
            for p in pts[1:]:
                if p != dedup[-1]:
                    dedup.append(p)
            if len(dedup) < 2:
                continue
            if self._route_clear(dedup, e):
                e.route(*dedup)
                return True

        # Fallback: historical Z-shape (unchanged when nothing clears).
        if tp.side in ('left', 'right'):
            if abs(ty - sy) > abs(tx - sx):
                e.route((sx, sy), (sx, ty), (tx, ty))
            else:
                e.route((sx, sy), (tx, sy), (tx, ty))
        else:
            e.route((sx, sy), (ax, sy), (ax, ay), (tx, ty))
        return True

    def _route_single_port(self, e):
        """Route an edge with exactly one port-anchored end (sugiyama).

        The ported end anchors at its boundary face; the other end lands
        on the facing face centre of the plain node.  Candidates scan
        the band between the nodes, exactly like the two-port router.
        """
        if e.source_port and not e.target_port:
            sx, sy = self._port_boundary(e.source_port)
            tx, ty = e.target.cx, e.target.y
            tface = 'top' if ty >= sy else 'bottom'
            if ty < sy:
                ty = e.target.y + e.target.h
        else:
            tx, ty = self._port_boundary(e.target_port)
            sx, sy = e.source.cx, e.source.y + e.source.h
            if e.target.y < e.source.y:
                sx, sy = e.source.cx, e.source.y
        mid = (sy + ty) // 2
        cands = [[(sx, sy), (sx, mid), (tx, mid), (tx, ty)],
                 [(sx, sy), (sx, ty), (tx, ty)],
                 [(sx, sy), (tx, sy), (tx, ty)]]
        for off in (10, 20, -10, -20):
            cands.append([(sx, sy), (sx, mid + off), (tx, mid + off),
                          (tx, ty)])
        for pts in cands:
            dedup = [pts[0]]
            for p in pts[1:]:
                if p != dedup[-1]:
                    dedup.append(p)
            if self._route_clear(dedup, e):
                e.route(*dedup)
                return True
        e.waypoints = [(sx, sy), (tx, ty)]
        return True

    def _route_orthogonal(self, e, layer_of, layers, gap_used=None):
        if e.source_port and e.target_port:
            self._port_route(e)
            return

        sl = layer_of.get(e.source, 0)
        tl = layer_of.get(e.target, 0)
        obstacles = [n for n in self.nodes if n not in (e.source, e.target)]

        if sl < tl:
            sx, sy = self._get_port(e.source, e, True, layer_of)
            tx, ty = self._get_port(e.target, e, False, layer_of)

            # Collect eligible gap y-levels between source and target layers
            gap_key = (sl, tl)
            if gap_used is not None and gap_key not in gap_used:
                gap_used[gap_key] = 0
            used = gap_used[gap_key] if gap_used is not None else 0

            candidates = []
            for l in range(sl, tl):
                gap_top = max(n.y + n.h for n in layers[l]) if layers[l] else 0
                gap_bot = min(n.y for n in layers[l + 1]) if layers[l + 1] else gap_top + 40
                if gap_top < gap_bot:
                    base = (gap_top + gap_bot) // 2
                    candidates.append(base)
            if not candidates:
                candidates.append((sy + ty) // 2)
            # Spread edges across the gap with per-edge offset
            base = candidates[0]
            offset = used * 3
            my = base + offset

            for my_candidate in [base + i * 3 for i in range(len(candidates) * 2 + 1)]:
                if my_candidate == base + offset:
                    my = my_candidate
                    break
                hits, _ = self._segment_hits(sx, my_candidate, tx, my_candidate, obstacles)
                if not hits:
                    my = my_candidate
                    break

            if gap_used is not None:
                gap_used[gap_key] = used + 1

            e.route((sx, sy), (sx, my), (tx, my), (tx, ty))
        elif sl > tl:
            # Reverse: source below target — route upward
            sx, sy = e.source.cx, e.source.y
            tx, ty = e.target.cx, e.target.y + e.target.h
            gap_key = (tl, sl)
            if gap_used is not None and gap_key not in gap_used:
                gap_used[gap_key] = 0
            used = gap_used[gap_key] if gap_used is not None else 0

            candidates = []
            for l in range(tl, sl):
                gap_top = max(n.y + n.h for n in layers[l]) if layers[l] else 0
                gap_bot = min(n.y for n in layers[l + 1]) if layers[l + 1] else gap_top + 40
                if gap_top < gap_bot:
                    candidates.append((gap_top + gap_bot) // 2)
            if not candidates:
                candidates.append((sy + ty) // 2)
            base = candidates[0]
            my = base + used * 3
            if gap_used is not None:
                gap_used[gap_key] = used + 1
            e.route((sx, sy), (sx, my), (tx, my), (tx, ty))
        else:
            self._route_straight(e, layer_of)

    # ── special-node edge routing (Comment / View) ──

    def _route_special_edge(self, e, orthogonal=False):
        special = e.source if isinstance(e.source, _SPECIAL_TYPES) else e.target
        other = e.target if isinstance(e.source, _SPECIAL_TYPES) else e.source
        is_source_special = isinstance(e.source, _SPECIAL_TYPES)

        dx = other.cx - special.cx
        dy = other.cy - special.cy
        dist = max(1, (dx * dx + dy * dy) ** 0.5)

        if hasattr(special, 'r'):
            sx = round(special.cx + dx / dist * special.r)
            sy = round(special.cy + dy / dist * special.r)
        elif abs(dx) >= abs(dy):
            if dx >= 0:
                sx, sy = special.x + special.w, special.cy
            else:
                sx, sy = special.x, special.cy
        else:
            if dy >= 0:
                sx, sy = special.cx, special.y + special.h
            else:
                sx, sy = special.cx, special.y

        if hasattr(other, 'r'):
            nx = round(other.cx - dx / dist * other.r)
            ny = round(other.cy - dy / dist * other.r)
        elif abs(dx) >= abs(dy):
            if dx >= 0:
                nx, ny = other.x, other.cy
            else:
                nx, ny = other.x + other.w, other.cy
        else:
            if dy >= 0:
                nx, ny = other.cx, other.y
            else:
                nx, ny = other.cx, other.y + other.h

        if orthogonal:
            if abs(dx) >= abs(dy):
                mid_y = (sy + ny) // 2
                pts = [(sx, sy), (sx, mid_y), (nx, mid_y), (nx, ny)]
            else:
                mid_x = (sx + nx) // 2
                pts = [(sx, sy), (mid_x, sy), (mid_x, ny), (nx, ny)]
            if is_source_special:
                e.route(*pts)
            else:
                e.route(*reversed(pts))
        else:
            if is_source_special:
                e.route((sx, sy), (nx, ny))
            else:
                e.route((nx, ny), (sx, sy))

    # ── Sugiyama routing ──

    def _route_sugiyama(self, node_gap, margin):
        edge_list = [(e.source.name, e.target.name) for e in self.edges
                     if not getattr(e, '_nested_internal', False)]
        node_sizes = {n.name: (n.w, n.h) for n in self.nodes}
        # Use layer_gap from our own layout attrs or default
        layer_spacing = getattr(self, '_layer_gap', 50)

        positions, routes, _ = sugiyama_layout(
            edge_list, node_sizes,
            node_gap=node_gap, margin=margin,
            layer_spacing=layer_spacing,
        )

        # Update node positions from sugiyama's layer assignment.
        for n in self.nodes:
            if n.name in positions:
                n.x, n.y, n.w, n.h = positions[n.name]

        # Port outer-faces depend on the node box positions computed above, so
        # refresh them before any port-to-port routing runs.
        self._update_port_positions()

        # Map routes back to edges (preserving order)
        route_map = {}
        for src, tgt, pts in routes:
            route_map[(src, tgt)] = pts
        for e in self.edges:
            # Explicit port-to-port edges use the same Z-shaped routing as the
            # orthogonal engine — this anchors each end at the port's outer
            # face instead of the bare centre of the node body, so arrowheads
            # (filled diamonds in particular) sit beside the port box rather
            # than crashing into a port placed on the side the sugiyama
            # router drops arrows in from.
            if e.source_port and e.target_port:
                self._port_route(e)
                continue
            if e.source_port or e.target_port:
                self._route_single_port(e)
                continue
            if getattr(e, '_nested_internal', False):
                continue  # already routed (inside its composite)
            key = (e.source.name, e.target.name)
            if key in route_map:
                e.waypoints = route_map[key]
            else:
                e.waypoints = [(e.source.cx, e.source.cy), (e.target.cx, e.target.cy)]

    # ── layout entry point ──

    def layout(self, routing='orthogonal', layer_gap=50, node_gap=12, margin=8):
        """Compute node positions and edge waypoints.

        After calling ``layout()``, nodes have ``.x``, ``.y``, ``.w``,
        ``.h`` set and edges have ``.waypoints`` populated.  The method
        is called automatically by ``render()`` and ``render_svg()``.

        Parameters
        ----------
        routing : {'straight', 'orthogonal', 'sugiyama', 'elk', 'pyelk'}
            Routing engine to use.  ``'elk'`` requires Node.js + elkjs
            (``npm install elkjs``); ``'pyelk'`` requires the pure-Python
            ``pyelk`` package (``pip install pyelk``).
        layer_gap : int
            Vertical gap between layers (pixels).
        node_gap : int
            Horizontal gap between nodes in the same layer (pixels).
        margin : int
            Left/top margin (pixels).
        """
        self._layer_gap = layer_gap

        # Composite-node nesting (v0.4.0): inflate sizes and re-anchor
        # edges to composite boundaries before any engine runs.
        self._size_nested_tree()
        self._reanchor_nested_edges()

        if routing == 'sugiyama':
            self._route_sugiyama(node_gap, margin)
            self._place_nested_tree()
            self._refresh_internal_edges()
            self._update_port_positions()
            return

        if routing == 'elk':
            from diagramboxes.elk import layout_with_elk
            # Composite internal edges are pre-routed; hide them from the
            # engine (they'd become self-edges on the composite node).
            internal = [e for e in self.edges
                        if getattr(e, '_nested_internal', False)]
            self.edges = [e for e in self.edges if e not in internal]
            layout_with_elk(self)
            self.edges.extend(internal)
            self._place_nested_tree()
            self._refresh_internal_edges()
            self._update_port_positions()
            return

        if routing == 'pyelk':
            from diagramboxes.pyelk_layout import layout_with_pyelk
            internal = [e for e in self.edges
                        if getattr(e, '_nested_internal', False)]
            self.edges = [e for e in self.edges if e not in internal]
            layout_with_pyelk(self)
            self.edges.extend(internal)
            self._place_nested_tree()
            self._refresh_internal_edges()
            self._update_port_positions()
            return

        layers, layer_of = self._assign_layers()
        y = margin
        for lyr in layers:
            x = margin
            max_h = 0
            for n in lyr:
                n.x = x
                n.y = y
                x += n.w + node_gap
                max_h = max(max_h, n.h)
            y += max_h + layer_gap

        self._update_port_positions()

        # Place extras (comments, views) below the last layer
        child_nodes = self._child_nodes()
        extras = self.comments + self.views
        if extras:
            eligible = [n for n in self.nodes if n not in child_nodes]
            max_y = max((n.y + n.h for n in eligible), default=y)
            gap = layer_gap
            x = margin
            for item in extras:
                item.x = x
                item.y = max_y + gap
                x += item.w + node_gap

        # Position children inside their parent views
        for v in self.views:
            if v.children:
                cy = v.content_y + 8
                for child in v.children:
                    cx = v.x + (v.w - child.w) // 2
                    child.x = cx
                    child.y = cy
                    cy += child.h + 4

        # Position children inside composite nodes (v0.4.0), then refresh
        # internal-edge waypoints (children are now positioned).
        self._place_nested_tree()
        self._refresh_internal_edges()

        gap_used = {}
        for e in self.edges:
            if self._is_visual_containment(e):
                continue
            if getattr(e, '_nested_internal', False):
                continue  # routed already (inside its composite)
            if isinstance(e.source, (Comment, View)) or isinstance(e.target, (Comment, View)):
                self._route_special_edge(e, orthogonal=(routing == 'orthogonal'))
            elif routing == 'orthogonal':
                self._route_orthogonal(e, layer_of, layers, gap_used)
            else:
                self._route_straight(e, layer_of)

    def render(self, c=None, routing='orthogonal', layer_gap=50, node_gap=12, margin=8):
        if c is None:
            c = Canvas()
        self.layout(routing=routing, layer_gap=layer_gap, node_gap=node_gap, margin=margin)
        self._update_port_positions()
        used_labels = set()
        all_path_px = set()
        for e in self.edges:
            if self._is_visual_containment(e):
                continue
            pts = e.waypoints
            for i in range(len(pts) - 1):
                x1, y1 = pts[i]
                x2, y2 = pts[i + 1]
                if x1 == x2:
                    lo, hi = (y1, y2) if y1 < y2 else (y2, y1)
                    for y in range(lo, hi + 1, 4):
                        all_path_px.add((x1, y))
                else:
                    lo, hi = (x1, x2) if x1 < x2 else (x2, x1)
                    for x in range(lo, hi + 1, 4):
                        all_path_px.add((x, y1))
        for e in self.edges:
            if self._is_visual_containment(e):
                continue
            if getattr(e, '_nested_internal', False):
                continue
            own = set(e.waypoints)
            for i in range(len(e.waypoints) - 1):
                x1, y1 = e.waypoints[i]
                x2, y2 = e.waypoints[i + 1]
                if x1 == x2:
                    lo, hi = (y1, y2) if y1 < y2 else (y2, y1)
                    for y in range(lo, hi + 1, 4):
                        own.add((x1, y))
                else:
                    lo, hi = (x1, x2) if x1 < x2 else (x2, x1)
                    for x in range(lo, hi + 1, 4):
                        own.add((x, y1))
            keep_away = all_path_px - own
            if len(e.waypoints) >= 2:
                draw_polyline(c, e.waypoints,
                              line_style=e.line_style,
                              source=e.source_style,
                              target=e.target_style,
                              label=e.label,
                              used_labels=used_labels,
                              keep_away=keep_away,
                              source_node=e.source,
                              target_node=e.target)
            else:
                draw_relation(c, e.source.cx, e.source.cy, e.target.cx, e.target.cy,
                              line_style=e.line_style,
                              source=e.source_style,
                              target=e.target_style,
                              label=e.label,
                              source_node=e.source,
                              target_node=e.target)
        child_nodes = self._child_nodes()

        def _draw_node_tree(node):
            draw_class_box(c, node.x, node.y, node.x + node.w, node.y + node.h,
                           node.name, node.stereotypes, node.attributes,
                           rounded=node.rounded, dashed=node.dashed)
            for p in node.ports:
                if isinstance(p, (EntryPoint, ExitPoint)):
                    draw_entry_exit_point(c, p.cx, p.cy, PORT_W // 2, label=p.label, kind=getattr(p, 'kind', 'entry'))
                else:
                    draw_port_box(c, p.x, p.y, p.label, side=p.side,
                                  direction=p.direction,
                                  label_inside=getattr(p, 'label_inside', False))
            for ch in node.children:
                _draw_node_tree(ch)
            for a in self.activities:
                if getattr(a, 'parent', None) is node:
                    _draw_activity(a)

        def _draw_activity(a):
            if isinstance(a, StartNode):
                draw_start_node(c, a.cx, a.cy, a.r)
            elif isinstance(a, DoneNode):
                draw_done_node(c, a.cx, a.cy, a.r)
            elif isinstance(a, TerminateNode):
                draw_terminate_node(c, a.cx, a.cy, a.r)
            elif isinstance(a, ForkJoinNode):
                draw_fork_join_node(c, a.x, a.y, a.x + a.w, a.y + a.h)
            elif isinstance(a, DecisionNode):
                draw_decision_node(c, a.cx, a.cy, a.size // 2, a.name)
            elif isinstance(a, HistoryPseudostate):
                draw_history_node(c, a.cx, a.cy, a.r, deep=a.deep)

        for n in self.nodes:
            if n in child_nodes:
                continue
            _draw_node_tree(n)
        for com in self.comments:
            draw_comment_box(c, com.x, com.y, com.x + com.w, com.y + com.h, com.text)
        for v in self.views:
            draw_view_box(c, v.x, v.y, v.x + v.w, v.y + v.h, v.name, v.stereotypes, v.attributes, dashed=v.dashed)
            for child in v.children:
                draw_class_box(c, child.x, child.y, child.x + child.w, child.y + child.h,
                               child.name, child.stereotypes, child.attributes, rounded=child.rounded, dashed=child.dashed)
                for p in child.ports:
                    if isinstance(p, (EntryPoint, ExitPoint)):
                        draw_entry_exit_point(c, p.cx, p.cy, PORT_W // 2, label=p.label, kind=getattr(p, 'kind', 'entry'))
                    else:
                        draw_port_box(c, p.x, p.y, p.label, side=p.side,
                                  direction=p.direction,
                                  label_inside=getattr(p, 'label_inside', False))
        for a in self.activities:
            if getattr(a, 'parent', None) is not None:
                continue  # drawn inside its composite node
            if isinstance(a, StartNode):
                draw_start_node(c, a.cx, a.cy, a.r)
            elif isinstance(a, DoneNode):
                draw_done_node(c, a.cx, a.cy, a.r)
            elif isinstance(a, TerminateNode):
                draw_terminate_node(c, a.cx, a.cy, a.r)
            elif isinstance(a, ForkJoinNode):
                draw_fork_join_node(c, a.x, a.y, a.x + a.w, a.y + a.h)
            elif isinstance(a, DecisionNode):
                draw_decision_node(c, a.cx, a.cy, a.size // 2, a.name)
            elif isinstance(a, HistoryPseudostate):
                draw_history_node(c, a.cx, a.cy, a.r, deep=a.deep)
        # Composite-internal edges (v0.4.0) — after boxes, so they land in
        # the open interior between sibling child boxes.
        for e in self.edges:
            if getattr(e, '_nested_internal', False):
                draw_polyline(c, e.waypoints,
                              line_style=e.line_style,
                              source=e.source_style,
                              target=e.target_style,
                              label=e.label,
                              used_labels=used_labels,
                              source_node=e.source,
                              target_node=e.target)
        return c.frame()

    def render_svg(self, routing='orthogonal', layer_gap=50, node_gap=12, margin=8, scale=1.5):
        self.layout(routing=routing, layer_gap=layer_gap, node_gap=node_gap, margin=margin)
        self._update_port_positions()

        # Compute bounds
        xs = [margin]
        ys = [margin]
        for n in self.nodes:
            xs.extend([n.x, n.x + n.w])
            ys.extend([n.y, n.y + n.h])
            for p in n.ports:
                xs.extend([p.x, p.x + p.w])
                ys.extend([p.y, p.y + p.h])
        for com in self.comments:
            xs.extend([com.x, com.x + com.w])
            ys.extend([com.y, com.y + com.h])
        for v in self.views:
            xs.extend([v.x, v.x + v.w])
            ys.extend([v.y, v.y + v.h])
        for a in self.activities:
            xs.extend([a.x, a.x + a.w])
            ys.extend([a.y, a.y + a.h])
        for e in self.edges:
            for px, py in e.waypoints:
                xs.append(px)
                ys.append(py)

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        pad = 10
        w = int((max_x - min_x + pad * 2) * scale)
        h = int((max_y - min_y + pad * 2) * scale)

        c = SvgCanvas(scale=scale)

        # Build keep-away sets for label collision avoidance
        all_path_px = set()
        for e in self.edges:
            if self._is_visual_containment(e):
                continue
            pts = e.waypoints
            for i in range(len(pts) - 1):
                x1, y1 = pts[i]
                x2, y2 = pts[i + 1]
                if x1 == x2:
                    lo, hi = (y1, y2) if y1 < y2 else (y2, y1)
                    for y in range(lo, hi + 1, 4):
                        all_path_px.add((x1, y))
                else:
                    lo, hi = (x1, x2) if x1 < x2 else (x2, x1)
                    for x in range(lo, hi + 1, 4):
                        all_path_px.add((x, y1))

        for e in self.edges:
            if self._is_visual_containment(e):
                continue
            own = set(e.waypoints)
            for i in range(len(e.waypoints) - 1):
                x1, y1 = e.waypoints[i]
                x2, y2 = e.waypoints[i + 1]
                if x1 == x2:
                    lo, hi = (y1, y2) if y1 < y2 else (y2, y1)
                    for y in range(lo, hi + 1, 4):
                        own.add((x1, y))
                else:
                    lo, hi = (x1, x2) if x1 < x2 else (x2, x1)
                    for x in range(lo, hi + 1, 4):
                        own.add((x, y1))
            keep_away = all_path_px - own
        child_nodes = self._child_nodes()

        def _svg_node_tree(node):
            svg_draw_node(c, node)
            for p in node.ports:
                if isinstance(p, (EntryPoint, ExitPoint)):
                    svg_draw_entry_exit_point(c, p.cx, p.cy, PORT_W // 2, label=p.label, kind=getattr(p, 'kind', 'entry'))
                else:
                    svg_draw_port(c, p)
            for ch in node.children:
                _svg_node_tree(ch)
            for a in self.activities:
                if getattr(a, 'parent', None) is node:
                    _svg_activity(a)

        def _svg_activity(a):
            if isinstance(a, StartNode):
                svg_draw_start_node(c, a.cx, a.cy, a.r)
            elif isinstance(a, DoneNode):
                svg_draw_done_node(c, a.cx, a.cy, a.r)
            elif isinstance(a, TerminateNode):
                svg_draw_terminate_node(c, a.cx, a.cy, a.r)
            elif isinstance(a, ForkJoinNode):
                svg_draw_fork_join_node(c, a.x, a.y, a.x + a.w, a.y + a.h)
            elif isinstance(a, DecisionNode):
                svg_draw_decision_node(c, a.cx, a.cy, a.size // 2, a.name)
            elif isinstance(a, HistoryPseudostate):
                svg_draw_history_node(c, a.cx, a.cy, a.r, deep=a.deep)

        for n in self.nodes:
            if n in child_nodes:
                continue
            _svg_node_tree(n)
        for com in self.comments:
            svg_draw_comment(c, com)
        for v in self.views:
            svg_draw_view(c, v)
            for child in v.children:
                svg_draw_node(c, child)
                for p in child.ports:
                    if isinstance(p, (EntryPoint, ExitPoint)):
                        svg_draw_entry_exit_point(c, p.cx, p.cy, PORT_W // 2, label=p.label, kind=getattr(p, 'kind', 'entry'))
                    else:
                        svg_draw_port(c, p)
        for e in self.edges:
            if self._is_visual_containment(e):
                continue
            svg_draw_edge(c, e, keep_away=all_path_px - set(e.waypoints))
        for a in self.activities:
            if getattr(a, 'parent', None) is not None:
                continue  # drawn inside its composite node
            if isinstance(a, StartNode):
                svg_draw_start_node(c, a.cx, a.cy, a.r)
            elif isinstance(a, DoneNode):
                svg_draw_done_node(c, a.cx, a.cy, a.r)
            elif isinstance(a, TerminateNode):
                svg_draw_terminate_node(c, a.cx, a.cy, a.r)
            elif isinstance(a, ForkJoinNode):
                svg_draw_fork_join_node(c, a.x, a.y, a.x + a.w, a.y + a.h)
            elif isinstance(a, DecisionNode):
                svg_draw_decision_node(c, a.cx, a.cy, a.size // 2, a.name)
            elif isinstance(a, HistoryPseudostate):
                svg_draw_history_node(c, a.cx, a.cy, a.r, deep=a.deep)
        return c.output(width=w, height=h, padding=pad * scale)
