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
from math import atan2, cos, sin, pi, radians

from drawille import Canvas, line
from diagramboxes.primitives import draw_polyline, draw_relation, draw_class_box, draw_port_box, \
    draw_comment_box, draw_view_box, draw_start_node, draw_done_node, draw_terminate_node, \
    draw_fork_join_node, draw_decision_node, draw_interface, \
    draw_history_node, draw_entry_exit_point, draw_diagram_frame, \
    SOLID, DASHED, OPEN, NONE, FILLED, DIAMOND, TRIANGLE, CIRCLE, UNOWNED, CIRCLED_PLUS, PORT_W, PORT_H, \
    INT_STICK, INT_BALL_R, INT_STACK, _OUTWARD, _is_folder, \
    draw_seq_head, draw_seq_exec, draw_seq_message, draw_destruction_x, \
    draw_seq_fragment, \
    draw_seq_constraint, \
    draw_par_param, draw_usecase_node, draw_actor_stick, \
    draw_send_signal_node, draw_accept_event_node, draw_wait_time_node, \
    draw_rake, draw_region_box, draw_cube_facets, _orthogonal_departs, \
    draw_line, draw_arrowhead, edge_end_label_positions
from diagramboxes.svg_canvas import SvgCanvas, svg_draw_edge, svg_draw_node, svg_draw_port, svg_port_label, svg_draw_comment, svg_draw_view, \
    svg_draw_start_node, svg_draw_done_node, svg_draw_terminate_node, \
    svg_draw_fork_join_node, svg_draw_decision_node, \
    svg_draw_history_node, svg_draw_entry_exit_point, svg_draw_frame, \
    svg_seq_head, svg_seq_exec, svg_seq_message, svg_seq_self_message, \
    svg_par_param, \
    svg_seq_destruction, svg_seq_fragment, svg_seq_constraint, \
    svg_usecase_node, svg_actor_stick, \
    svg_draw_send_signal_node, svg_draw_accept_event_node, \
    svg_draw_wait_time_node, svg_draw_rake, svg_draw_region_box, \
    svg_draw_interface

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
        self.label_above = False  # label above the port box (Figure 4.6:
                                  # port names print above the ports, off
                                  # the connector's row) — default for
                                  # FramePort
        self.interfaces = []   # lollipop/socket symbols beyond this port
        self.parent = None
        self.x = self.y = 0

    def add_interface(self, name, kind='provided', index=None):
        """Attach an interface symbol beyond this port (§3.4.1.5)."""
        if index is None:
            index = len(self.interfaces)
        i = InterfaceSymbol(name, kind, side=self.side, parent=self, index=index)
        self.interfaces.append(i)
        return i

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


# ── interface symbols (lollipop / socket, §3.4.1.5) ──
# geometry constants come from primitives (single source of truth)


# ── sequence diagram elements (§7.4–7.7) ──

SEQ_HEAD_H = 12       # head rectangle height
SEQ_EXEC_W = 8        # execution-specification rectangle width
SEQ_GAP = 14          # default row gap for a create message


class Lifeline:
    """One participant instance in an interaction (§7.4): a head
    rectangle carrying the name string over a dashed tail line
    descending with time. Positional elements — the layout engine does
    not route them; rows are y-coordinates supplied by the modeler."""

    def __init__(self, label, x=0, created=False):
        self.label = label
        self.x = x                 # the dashed line / head centre column
        self.head_y = 0            # top of the head rectangle
        self.created = created

    @property
    def w(self):
        return len(self.label) * 2 + 10  # wider than SEQ_HEAD_H tall

    @property
    def h(self):
        return SEQ_HEAD_H

    @property
    def cx(self):
        return self.x

    @property
    def tail_start(self):
        return self.head_y + self.h

    def __repr__(self):
        return 'Lifeline(%r)' % self.label


class SeqMessage:
    """A message between two lifelines (§7.5): kind is one of 'async'
    (solid, open arrowhead), 'sync' (solid, filled arrowhead), 'reply'
    (dashed, open), 'create' (dashed, open, lands on the created
    lifeline's head), 'delete' (ends in a destruction occurrence).
    Horizontal at row ``y``."""

    def __init__(self, src, dst, kind, y, label=None,
                 from_left=True, to_right=True, attach=None):
        self.src = src
        self.dst = dst
        self.kind = kind
        self.y = y
        self.label = label
        self.from_left = from_left    # found messages: enter from the left
        self.to_right = to_right      # lost messages: leave to the right
        self.attach = attach          # None=auto (frame border when framed)
        self.x1 = 0
        self.x2 = 0

    @property
    def line_style(self):
        """'solid' for async/sync, 'dashed' for reply/create/delete
        (§7.5.2, Table of message kinds)."""
        return 'dashed' if self.kind in ('reply', 'create', 'delete') \
            else 'solid'

    def __repr__(self):
        return 'SeqMessage(%r->%r %s y=%s)' % (
            self.src.label, self.dst.label, self.kind, self.y)


class SeqExec:
    """An execution specification (§7.7): a thin vertical rectangle on
    a lifeline covering the span [y1, y2] of an active behavior."""

    def __init__(self, lifeline, y1, y2, shaded=False):
        self.lifeline = lifeline
        self.y1 = y1
        self.y2 = y2
        self.shaded = shaded


class SeqDestruction:
    """A destruction occurrence (§7.6): an X at the bottom of a
    lifeline — its last possible event occurrence."""

    def __init__(self, lifeline, y):
        self.lifeline = lifeline
        self.y = y


class SeqFragment:
    """A combined fragment or interaction use (§7.9–7.10): a rectangle
    over the participating lifelines with a pentagon in the upper-left
    holding the interaction operator. ``operator='ref'`` + ``name`` = an
    interaction use invoking a lower-level interaction. ``operands`` are
    (row, guard-string) pairs: dashed separators at each row, guard
    printed below it."""

    def __init__(self, lifelines, y1, y2, operator, guard=None,
                 operands=None, name=None, frag_range=None):
        self.lifelines = list(lifelines)
        self.y1 = y1
        self.y2 = y2
        self.operator = operator
        self.frag_range = frag_range      # e.g. '(2, *)' or None
        self.guard = guard
        self.operands = [tuple(o) for o in (operands or [])]
        self.name = name                  # interaction use's referenced name

    @property
    def is_ref(self):
        return self.operator == 'ref'

    def __repr__(self):
        return 'SeqFragment(%r y=%s..%s over %d lifelines)' % (
            self.operator, self.y1, self.y2, len(self.lifelines))


class SeqConstraint:
    """A time constraint, duration constraint, or state invariant
    (§7.8): text in curly braces floating over (or beside, via ``dx``)
    a lifeline just above the event occurrence it binds. State-
    notation invariants (§7.8.3/§7.12) render as ROUND-CORNERED
    rectangles holding the state's name instead of a braced Boolean."""

    def __init__(self, lifeline, y, text, dx=0, state_notation=False):
        self.lifeline = lifeline
        self.y = y
        self.text = text
        self.dx = dx
        self.rounded = bool(state_notation)

    def __repr__(self):
        return 'SeqConstraint(%r y=%s%s)' % (
            self.text, self.y, ' state' if self.rounded else '')


class FramePort(Port):
    """A port placed ON the diagram-kind frame's border (SysML v1 §4.8,
    Figure 4.6): an interaction point on the IBD header block's boundary.
    Positioned by ``Diagram._place_frame_ports`` once the frame geometry
    is known after layout; edges to it are routed from `_place_frame_ports`.
    """

    def __init__(self, label, side='left', offset=0.5, direction=None):
        super().__init__(label, side=side, offset=offset, direction=direction)
        self.placed = False
        self.is_frame_port = True
        self.label_above = True  # book convention: port name above the port


class InterfaceSymbol:
    """UML interface symbol attached outward from a port or node side:
    ``'provided'`` → ball on a stick (lollipop); ``'required'`` → stick
    with an open semicircle (socket). The name renders as a label near
    the symbol (Delligatti §3.4.1.5, Figures 4.5/4.6).
    """
    def __init__(self, name, kind='provided', side='right', offset=0.5,
                 parent=None, index=0):
        self.name = name
        self.kind = kind
        self.side = side
        self.offset = offset        # node-attached: position along the side
        self.parent = parent
        self.index = index
        self.face = (0, 0)          # anchor point on the parent's boundary

    def _stick_len(self):
        return INT_STICK + self.index * 6

    def _angle(self):
        a0 = atan2(_OUTWARD[self.side][1], _OUTWARD[self.side][0])
        return a0 + self.index * radians(40)

    def center(self):
        ball_off = INT_BALL_R if self.kind == 'provided' else 0
        L = self._stick_len() + ball_off
        a = self._angle()
        return (self.face[0] + cos(a) * L, self.face[1] + sin(a) * L)

    def update_pos(self):
        p = self.parent
        if p is None:
            return
        if isinstance(p, Port):
            self.face = {
                'right': (p.x + PORT_W, p.y + PORT_H // 2),
                'left': (p.x, p.y + PORT_H // 2),
                'top': (p.x + PORT_W // 2, p.y),
                'bottom': (p.x + PORT_W // 2, p.y + PORT_H),
            }[p.side]
        else:  # node boundary
            self.face = {
                'right': (p.x + p.w, p.y + int(p.h * self.offset)),
                'left': (p.x, p.y + int(p.h * self.offset)),
                'top': (p.x + int(p.w * self.offset), p.y),
                'bottom': (p.x + int(p.w * self.offset), p.y + p.h),
            }[self.side]

    def extent(self):
        """Bounding (x1, y1, x2, y2) of the symbol + its name label
        estimate — consumed by the SVG bounds math."""
        cx, cy = self.center()
        r = INT_BALL_R
        labw = (len(self.name) * 2 + 6) if self.name else 0
        if self.side == 'right':
            return (self.face[0], cy - r, cx + r + labw, cy + r)
        if self.side == 'left':
            return (cx - r - labw, cy - r, self.face[0], cy + r)
        if self.side == 'top':
            return (cx - max(4, labw / 2), cy - r,
                    cx + max(4, labw / 2), self.face[1])
        return (cx - max(4, labw / 2), self.face[1],
                cx + max(4, labw / 2), cy + r + 6)


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
        (e.g. ``['+ voltage : float', '# state : int']``) — the first,
        UNNAMED compartment.
    compartments : list of (name, lines) tuples, optional
        Additional NAMED compartments below the attributes compartment
        (SysML v1 block notation, §3.4) — e.g.
        ``[('values', ['mass : kg']), ('parts', ['p : B [2]'])]``.
        Each renders as a separator line, a centered title line, and
        its content lines.

    See also
    --------
    Diagram.add_node : Factory method for creating registered nodes.
    Port : Attachable boundary ports.
    """

    def __init__(self, name, stereotypes=None, attributes=None, rounded=False, dashed=False,
                 compartments=None, at=None, chamfer=0, cube=False):
        self.name = name
        self.stereotypes = stereotypes or []
        self.attributes = attributes or []
        self.compartments = [(t, list(ls)) for t, ls in (compartments or [])]
        self.interfaces = []   # standalone lollipop/socket symbols (no port)
        self.rounded = rounded
        self.dashed = dashed
        # 45-degree corner cut (v2 action usage octagon); 0 = off
        self.chamfer = chamfer
        # UML 2.5.1 ch19 'DeploymentTarget': perspective-view cube facets
        self.cube = cube
        # §6.8.2 call behavior action: rake glyph in the lower-right
        self.rake = False
        self.ports = []
        # Composite-structure nesting (v0.4.0): a node may own child nodes
        # drawn *inside* its box (e.g. composite states, part assemblies).
        self.parent = None
        self.children = []
        self.x = self.y = self.w = self.h = 0
        # fixed-position hint (reproduction pin): honored by layout()
        # only when EVERY top-level node carries one
        self.at = tuple(at) if at is not None else None
        self._calc_size()

    def _calc_size(self):
        tw = []
        if self.stereotypes:
            tw.extend(len(f'\u00ab{s}\u00bb') for s in self.stereotypes)
        tw.append(len(self.name))
        if self.attributes:
            tw.extend(len(a) for a in self.attributes)
        for title, lines in self.compartments:
            tw.append(len(title))
            tw.extend(len(l) for l in lines)
        max_tw = max(tw) if tw else 0
        self.w = max(max_tw * 2 + 6, 26)
        total_lines = len(self.stereotypes) + 1
        if self.attributes:
            total_lines += 1 + len(self.attributes)
        for title, lines in self.compartments:
            total_lines += 2 + len(lines)  # separator + title + content
        self.h = max(total_lines * 5 + 8, getattr(self, 'h_hint', 0))

    def add_port(self, label, side='left', offset=None, direction=None,
                 label_inside=False):
        p = Port(label, side, offset, direction, label_inside=label_inside)
        p.parent = self
        self.ports.append(p)
        return p

    def add_attribute(self, text):
        self.attributes.append(text)
        self._calc_size()

    def set_min_height(self, h):
        """Reserve room below the text rows across layout passes — a
        height hint ``_calc_size`` honors (used for constraint-property
        boxes sized to seat their parameter squares, Fig 9.3)."""
        self.h_hint = h
        self.h = max(self.h, h)

    def add_interface(self, name, kind='provided', side='right', offset=0.5,
                      index=None):
        """Attach an interface symbol (lollipop/socket) directly to this
        node's boundary — no port needed (§3.4.1.5)."""
        if index is None:
            index = len(self.interfaces)
        i = InterfaceSymbol(name, kind, side=side, offset=offset,
                            parent=self, index=index)
        self.interfaces.append(i)
        return i

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


PAR_PARAM_S = 8   # edge length of the constraint-parameter square (§9.6)


class ParParam(Node):
    """A constraint parameter (SysML v1 §9.6, Figures 9.3/9.4): a small
    square attached to the INSIDE of its owner's boundary — a constraint
    property, or the diagram frame itself when the frame represents a
    constraint block. Position and binding-edge routing are deferred to
    ``Diagram._place_par_params`` (geometry exists only after layout).
    Registered in ``Diagram.par_params`` and deliberately NOT laid out
    as a normal node.
    """

    def __init__(self, name, side='left', offset=0.5, owner=None):
        self.side = side
        self.offset = offset
        self.owner = owner
        self.is_par_param = True
        self.placed = False
        super().__init__(name)

    def _calc_size(self):
        self.w = PAR_PARAM_S
        self.h = PAR_PARAM_S


UC_BODY_H = 16   # rows of the use case ellipse's interior (§5.5)


class UseCase(Node):
    """A use case (SysML v1 §5.5, Figure 5.1): an ellipse with the
    verb-phrase name displayed INSIDE."""

    def __init__(self, name):
        self.is_use_case = True
        super().__init__(name)

    def _calc_size(self):
        self.w = max(len(self.name) * 2 + 8, 34)
        self.h = UC_BODY_H


class Actor(Node):
    """An actor (SysML v1 §5.7, Figure 5.1): a stick figure with the
    name printed BENEATH (``is_stick_figure``), or a plain rectangle
    carrying the «actor» stereotype keyword — either is legal for any
    type of actor, person or system."""

    def __init__(self, name, stick_figure=True):
        self.is_actor = True
        self.is_stick_figure = stick_figure
        super().__init__(name,
                         stereotypes=None if stick_figure else ['actor'])

    def _calc_size(self):
        if not self.is_stick_figure:
            super()._calc_size()
            return
        self.w = max(16, len(self.name) * 2 + 2)
        self.h = 16      # the figure only; the name hangs BELOW the box
                         # (its halo band must stay clear of the edges
                         # that anchor at this node's boundary)


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

    def __init__(self, name='Start', at=None):
        self.name = name
        self.r = _ACTIVITY_RADIUS
        d = self.r * 2 + 2
        self.w = self.h = d
        self.x = self.y = 0
        self.parent = None  # composite-structure parent (v0.4.0)
        self.at = tuple(at) if at is not None else None

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

    def __init__(self, name='Done', at=None):
        self.name = name
        self.r = _ACTIVITY_RADIUS
        d = self.r * 2 + 2
        self.w = self.h = d
        self.x = self.y = 0
        self.parent = None  # composite-structure parent (v0.4.0)
        self.at = tuple(at) if at is not None else None

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

    def __init__(self, name='Terminate', at=None):
        self.name = name
        self.r = _ACTIVITY_RADIUS
        d = self.r * 2 + 2
        self.w = self.h = d
        self.x = self.y = 0
        self.parent = None  # composite-structure parent (v0.4.0)
        self.at = tuple(at) if at is not None else None

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)


class _ActivityPorts:
    """Minimal port attachment for activity shapes — pins (§6.6.1):
    small squares on an action's boundary carrying the pin's name
    string.  Shared by the §6.8 action shapes."""

    def add_port(self, label, side='left', offset=None, direction=None,
                 label_inside=False):
        p = Port(label, side, offset, direction, label_inside=label_inside)
        p.parent = self
        self.ports.append(p)
        return p


class SendSignalNode(_ActivityPorts):
    """Send signal action — convex signpost pentagon (§6.8.3).

    The left edge is square; the right side converges to a point in
    the direction of the flow.  The signal name prints inside.
    """

    POINT = 14   # depth of the pointed side

    def __init__(self, name='', w=56, h=26, at=None):
        self.name = name
        self.w = w
        self.h = h
        self.x = self.y = 0
        self.parent = None
        self.ports = []
        self.at = tuple(at) if at is not None else None

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)


class AcceptEventNode(_ActivityPorts):
    """Accept event action — concave pentagon (§6.8.4).

    A rectangle with a triangular notch cut into the arrival (left)
    side; the signal/time-event name prints in the body.
    """

    NOTCH = 10   # how deep the notch bites in

    def __init__(self, name='', w=64, h=26, at=None):
        self.name = name
        self.w = w
        self.h = h
        self.x = self.y = 0
        self.parent = None
        self.ports = []
        self.at = tuple(at) if at is not None else None

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)


class WaitTimeNode:
    """Wait time action — hourglass with the time expression beneath
    (§6.8.5).  ``name`` holds the whole expression (``after (2 s)`` /
    ``at (1430 GMT)``); it prints under the glyph like an actor name.
    """

    GLYPH_H = 22   # hourglass height; the expression hangs below

    def __init__(self, name='', w=26, at=None):
        self.name = name
        self.glyph_h = self.GLYPH_H
        self.h = self.glyph_h + 12
        self.w = w
        self.x = self.y = 0
        self.parent = None
        self.at = tuple(at) if at is not None else None

    @property
    def expr_h(self):
        return self.h - self.glyph_h

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        # token anchors sit on the GLYPH, not under the expression
        return self.y + self.glyph_h // 2

    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.glyph_h)


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

    def __init__(self, name='', w=36, h=8, at=None):
        self.name = name
        self.w = w
        self.h = h
        self.x = self.y = 0
        self.parent = None  # composite-structure parent (v0.4.0)
        self.at = tuple(at) if at is not None else None

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

    def __init__(self, name='', size=28, at=None, filled=False):
        self.name = name
        self.size = size
        self.w = size
        self.h = size
        # v2 start node: a small SOLID diamond (Intro deck p56/p58)
        self.filled = filled
        self.x = self.y = 0
        self.parent = None  # composite-structure parent (v0.4.0)
        self.at = tuple(at) if at is not None else None

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

    def __init__(self, name='initial', at=None):
        super().__init__(name=name, at=at)


class JunctionPseudostate(StartNode):
    """Filled black circle — state-machine junction pseudostate.

    Visually identical to the initial pseudostate but used as an
    intermediate merge/branch point in compound transition paths.  Named
    junctions (```junction J1;```) get a label rendered alongside.  Drawn
    through the same primitive as :class:`StartNode`.
    """

    def __init__(self, name='', at=None):
        super().__init__(name=name, at=at)


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

    def __init__(self, name='terminate', at=None):
        super().__init__(name=name, at=at)


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

    def __init__(self, name='', deep=False, r=8, at=None):
        self.name = name
        self.deep = deep
        self.r = r
        d = r * 2 + 2
        self.w = self.h = d
        self.x = self.y = 0
        self.parent = None  # composite-structure parent (v0.4.0)
        self.at = tuple(at) if at is not None else None

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

    def add_internal(self, text):
        """Add an internal behavior or internal transition row (§8.4.1 /
        §8.5.1) to this state's second compartment:
        ``entry / ...``, ``exit / ...``, ``do / ...``, or an internal
        transition string like ``when (...) / purgeOldestDataFiles``."""
        self.attributes = list(self.attributes or []) + [text]
        self._calc_size()
        return self


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


class Region(View):
    """A state-machine region (§8.7): a plain dashed rectangle — no
    header tab — with the optional region name floating inside a
    corner.  Regions model orthogonal (concurrent) sub-parts of a
    state machine; a transition between vertices in different regions
    is illegal (§8.7)."""

    def __init__(self, name='', stereotypes=None, attributes=None,
                 dashed=True):
        super().__init__(name, stereotypes=stereotypes,
                         attributes=attributes, dashed=dashed)

    def _tab_height(self):
        return 0        # no header band: content starts at the top edge

    @property
    def content_y(self):
        return self.y


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
    source_label, target_label : str or None, optional
        Per-end labels (SysML v1 §3.5): role name and/or multiplicity
        pinned near each end of the line (e.g. ``source_label='eps 1'``).
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
                 target_style=OPEN, label=None, source_port=None, target_port=None,
                 source_label=None, target_label=None,
                 item_flow=None, item_position=0.5):
        self.source = source
        self.target = target
        self.source_port = source_port
        self.target_port = target_port
        self.line_style = line_style
        self.source_style = source_style
        self.target_style = target_style
        self.label = label
        # Per-end labels (SysML v1 association notation, §3.5): role name
        # and/or multiplicity pinned near each end of the line.
        self.source_label = source_label
        self.target_label = target_label
        # Item flow (SysML v1 §4.9): filled triangular arrowhead along
        # the connector at ``item_position`` (0..1), with the item's
        # type as the label near it.
        self.item_flow = item_flow
        self.item_position = item_position
        # Binding connector (§9.8): solid, arrowless, set by Diagram.bind
        self.is_binding = False
        self.waypoints = []

    def route(self, *points):
        self.waypoints = list(points)


_SPECIAL_TYPES = (Comment, View, StartNode, DoneNode, TerminateNode, ForkJoinNode, DecisionNode)


class DiagramFrame:
    """The enclosing frame of a SysML v1 diagram-kind (Delligatti §2.4, §3.3).

    A frame is an outer border around all diagram content plus a header
    line naming (1) the diagram kind, (2) the kind of model element the
    frame represents, (3) the model element name, and (4) the diagram
    name::

        bdd [package] Structure [DellSat-77 Satellite Structure and Properties]

    Element kinds valid per diagram kind are listed in §2.3/§2.4 of the
    book (e.g. a BDD frame may represent a package, model, modelLibrary,
    or view).
    """

    # vertical space reserved for the header strip above the content
    HEADER_H = 14

    def __init__(self, kind, element_kind=None, element_name=None, diagram_name=None):
        self.kind = kind
        self.element_kind = element_kind
        self.element_name = element_name
        self.diagram_name = diagram_name

    @property
    def header(self):
        h = self.kind or ''
        if self.element_kind:
            h += ' [%s]' % self.element_kind
        if self.element_name:
            h += ' %s' % self.element_name
        if self.diagram_name:
            h += ' [%s]' % self.diagram_name
        return h.strip()


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
        self.frame = None  # optional DiagramFrame (SysML v1 diagram-kind)
        self.frame_ports = []  # FramePorts straddling the frame border (§4.8)
        self.par_params = []  # constraint-parameter squares (§9.6)
        self.frame_pad = 0    # extra inset between the border and content
        # Composite re-anchoring (IBD convention): opt out for use case
        # diagrams, where an actor's association must reach the ellipse
        # (§5.8), not the boundary rectangle
        self.reanchor_nested = True
        self.lifelines = []    # sequence participants (§7.4)
        self.messages = []     # SeqMessages (§7.5)
        self.exec_specs = []   # SeqExec execution specifications (§7.7)
        self.destructions = []  # SeqDestruction occurrences (§7.6)
        self.fragments = []    # SeqFragments / interaction uses (§7.9-7.10)
        self.constraints = []  # SeqConstraint floats / state invariants (§7.8)

    # ── sequence-diagram construction (§7.4–7.7) ──

    def add_lifeline(self, label, x=None, created=False):
        """Create a lifeline (§7.4). Without an explicit ``x`` the head
        column auto-spaces after the previous lifeline (head+gap).

        Returns
        -------
        Lifeline
        """
        li = Lifeline(label, created=created)
        if x is not None:
            li.x = x
        else:
            li.x = max((l.x + l.w for l in self.lifelines), default=0) + 90
        self.lifelines.append(li)
        return li

    def _seq_message(self, src, dst, kind, y, label, from_left=True,
                     to_right=True, attach=None):
        m = SeqMessage(src, dst, kind, y, label,
                       from_left=from_left, to_right=to_right, attach=attach)
        if kind == 'create':
            dst.head_y = y   # arrowhead lands at the created lifeline's head
            dst.created = True
        self.messages.append(m)
        return m

    def seq_async(self, src, dst, y, label=None):
        """Asynchronous message (§7.5.2): solid line, open arrowhead;
        the sender proceeds immediately."""
        return self._seq_message(src, dst, 'async', y, label)

    def seq_sync(self, src, dst, y, label=None):
        """Synchronous message (§7.5.2): solid line, filled-in
        arrowhead; the sender waits for the reply."""
        return self._seq_message(src, dst, 'sync', y, label)

    def seq_reply(self, src, dst, y, label=None):
        """Reply message (§7.5.2): dashed line, open arrowhead; sent by
        the performing lifeline back to the invoker."""
        return self._seq_message(src, dst, 'reply', y, label)

    def seq_found(self, dst, y, label=None, kind='sync', from_left=True,
                  attach=None):
        """Found message (§7.5): the sender is outside the diagram. The
        arrow departs at the frame border by default (framed diagrams);
        ``attach=False`` forces a mid-air floating end (excerpt-crop
        style, e.g. Figure 7.13's cropped sender)."""
        return self._seq_message(None, dst, kind, y, label,
                                 from_left=from_left, attach=attach)

    def seq_lost(self, src, y, label=None, kind='reply', to_right=True,
                 attach=None):
        """Lost message (§7.5): the receiver is outside the diagram. The
        line ends at the frame border by default (framed diagrams);
        ``attach=False`` forces a mid-air floating end."""
        return self._seq_message(src, None, kind, y, label,
                                 to_right=to_right, attach=attach)

    def seq_create(self, src, dst, label=None, y=None):
        """Create message (§7.5.2): dashed line, open arrowhead landing
        on the created lifeline's head; the arrowhead row becomes the
        created lifeline's head row."""
        if y is None:
            y = max((m.y for m in self.messages), default=0) + SEQ_GAP
        return self._seq_message(src, dst, 'create', y, label)

    def destroy(self, lifeline, y=None):
        """Destruction occurrence (§7.6): an X at the bottom of the
        lifeline (its last possible event occurrence). Default row is
        just past its last event."""
        if y is None:
            rows = [m.y for m in self.messages
                    if m.src is lifeline or m.dst is lifeline]
            rows += [s.y2 for s in self.exec_specs if s.lifeline is lifeline]
            y = max(rows, default=lifeline.head_y) + SEQ_GAP - 2
        x = SeqDestruction(lifeline, y)
        self.destructions.append(x)
        return x

    def seq_exec(self, lifeline, y1, y2, shaded=False):
        """Execution specification (§7.7): a thin vertical rectangle
        covering the behavior-execution span [y1, y2]. Message ends at
        rows inside the span attach to the rectangle's edges."""
        s = SeqExec(lifeline, y1, y2, shaded)
        self.exec_specs.append(s)
        return s

    def seq_fragment(self, lifelines, y1, y2, operator, guard=None,
                     operands=None, range=None, frag_range=None):
        """Combined fragment (§7.9): a rectangle over ``lifelines`` with
        the interaction operator in the upper-left pentagon.
        ``range`` (e.g. '(2, *)') joins the operator for loops;
        ``guard`` = the first operand's Boolean expression; ``operands``
        = (row, guard) pairs — dashed separator lines at each row with
        that operand's guard below it. Guards display in square
        brackets; keep alt guards mutually exclusive (§7.9.2)."""
        f = SeqFragment(lifelines, y1, y2, operator, guard=guard,
                        operands=operands,
                        frag_range=range or frag_range)
        self.fragments.append(f)
        return f

    def seq_ref(self, lifelines, y1, y2, name):
        """Interaction use (§7.10): a `ref` pentagon rectangle over the
        participating lifelines invoking the named lower-level
        interaction; the lifelines disappear behind it."""
        f = SeqFragment(lifelines, y1, y2, 'ref', name=name)
        self.fragments.append(f)
        return f

    def seq_constraint(self, lifeline, y, text, dx=0, state_notation=False):
        """Time/duration constraint or state invariant (§7.8): braced
        text floating over the lifeline just above the bound event
        occurrence (``dx`` offsets it sideways, e.g. a duration
        constraint beside a spec); state invariants given in the state
        notation render as round-cornered rectangles naming the
        required state (§7.8.3, Figure 7.12)."""
        c = SeqConstraint(lifeline, y, text, dx=dx,
                          state_notation=state_notation)
        self.constraints.append(c)
        return c

    def _fragment_span_x(self, f):
        lo = min(li.x for li in f.lifelines) - 10
        hi = max(li.x for li in f.lifelines) + 10
        return lo, hi

    def _lifeline_edge_x(self, li, y):
        """Where a message end at row ``y`` attaches on ``li``: the
        execution-spec edge when a spec covers the row (§7.7 attaches
        arrowheads to the thin rectangle), else the dashed-line column."""
        for s in self.exec_specs:
            if s.lifeline is li and s.y1 <= y <= s.y2:
                return s
        return None

    def _lifeline_tail_end(self, li):
        rows = [m.y for m in self.messages
                if (m.src is li or m.dst is li)
                and m.src is not None and m.dst is not None]
        rows += [s.y2 for s in self.exec_specs if s.lifeline is li]
        rows += [x.y for x in self.destructions if x.lifeline is li]
        return max(rows, default=li.tail_start + 20)

    def _event_x(self, li, y, to_right):
        """Message-end column on ``li`` at row ``y``: the exec-spec edge
        when a spec covers the row, else the dashed-line column."""
        s = self._lifeline_edge_x(li, y)
        if s is None:
            return li.x
        return li.x + (SEQ_EXEC_W // 2 if to_right else -SEQ_EXEC_W // 2)

    def _seq_message_endpoints(self, m):
        """(x1, x2): source-end column, arrowhead-end column. Found
        messages start at the frame border (framed) or mid-air 90 units
        from the receiver (unframed); lost messages mirror that."""
        if m.src is None or m.dst is None:
            e1, e2 = self._seq_midair_endpoints(m)
            li = m.dst if m.dst is not None else m.src
            if li is None:
                return e1, e2
            if m.src is None:
                # dock the arrowhead on the exec-spec edge facing the
                # incoming direction (from the left → left edge, §7.7)
                return e1, self._event_x(li, m.y, e1 > li.x)
            return self._event_x(li, m.y, e2 > li.x), e2
        if m.src is m.dst:
            return m.src.x, m.src.x
        to_right = m.dst.x >= m.src.x
        x_src = self._event_x(m.src, m.y, to_right)
        x_dst = self._event_x(m.dst, m.y, m.src.x >= m.dst.x)
        return x_src, x_dst

    def _seq_midair_endpoints(self, m):
        """(e1, e2) for found/lost messages: flush at the frame border
        when framed and ``attach`` unset; ``attach=False`` crops the end
        JUST OUTSIDE the border (excerpt-crop style) when framed, else
        90 units out beyond the nearest lifeline."""
        framed = self.frame is not None and m.attach is not False
        floating_framed = self.frame is not None and m.attach is False
        fr = self._frame_rect() if (framed or floating_framed) else None
        crop = 12 if floating_framed else 0
        left_b = right_b = None
        if fr is not None:
            left_b, right_b = fr[0], fr[2]
        if m.src is None:
            if left_b is not None and not floating_framed:
                return (left_b, m.dst.x) if m.from_left else (right_b, m.dst.x)
            if floating_framed:
                return (((left_b or 0) - crop, m.dst.x) if m.from_left
                        else ((right_b or 0) + crop, m.dst.x))
            return ((m.dst.x - 90, m.dst.x) if m.from_left
                    else (m.dst.x + 90, m.dst.x))
        if left_b is not None and not floating_framed:
            return (m.src.x, right_b) if m.to_right else (m.src.x, left_b)
        if floating_framed:
            return ((m.src.x, (right_b or 0) + crop) if m.to_right
                    else (m.src.x, (left_b or 0) - crop))
        return ((m.src.x, m.src.x + 90) if m.to_right
                else (m.src.x, m.src.x - 90))

    def _update_seq_geometry(self):
        """Cache message endpoint columns (render-time; exec specs may
        be added after the messages)."""
        for m in self.messages:
            m.x1, m.x2 = self._seq_message_endpoints(m)

    def add_frame_port(self, label, side='left', offset=0.5, direction=None):
        """Create a port on the diagram-kind frame's border (§4.8,
        Figure 4.6) — an interaction point on the header block's boundary.
        Positioned and connected during render placement.

        Returns
        -------
        FramePort
        """
        p = FramePort(label, side=side, offset=offset, direction=direction)
        self.frame_ports.append(p)
        return p

    def add_requirement(self, name, req_id='', text='', extra_stereotypes=None):
        """Create a «requirement» node (§11.4): the stereotype keyword
        preceding the name plus the two String properties ``id`` and
        ``text`` shown as named compartments.

        Returns
        -------
        Node
        """
        st = ['requirement'] + list(extra_stereotypes or [])
        comps = []
        if req_id:
            comps.append(('id', [req_id]))
        if text:
            comps.append(('text', [text]))
        return self.add_node(name, st, compartments=comps)

    def _req_edge(self, client, supplier, keyword):
        """Dependency notation (dashed line, open arrowhead) with the
        relationship keyword as the stereotype label (§11.5)."""
        return self.add_edge(client, supplier, line_style=DASHED,
                             target_style=OPEN, label='«%s»' % keyword)

    def req_trace(self, client, supplier):
        """«trace»: modification to the supplier may require modifying
        the client (§11.5)."""
        return self._req_edge(client, supplier, 'trace')

    def req_derive(self, client, supplier):
        """«deriveReqt»: the client requirement is derived from the
        supplier requirement (§11.5)."""
        return self._req_edge(client, supplier, 'deriveReqt')

    def req_refine(self, client, supplier):
        """«refine»: the client element is more concrete than the
        supplier (§11.5)."""
        return self._req_edge(client, supplier, 'refine')

    def req_satisfy(self, client, supplier):
        """«satisfy»: an instance of the client block will fulfill the
        supplier requirement — an assertion, not proof (§11.5)."""
        return self._req_edge(client, supplier, 'satisfy')

    def req_verify(self, client, supplier):
        """«verify»: executing the client test case proves the supplier
        requirement is satisfied (§11.5)."""
        return self._req_edge(client, supplier, 'verify')

    def add_package(self, name, stereotypes=None, attributes=None):
        """Create a package node — folder symbol with the tab (§10.4);
        specialized kinds pass their keyword in ``stereotypes`` (e.g.
        ``['modelLibrary']``, ``['view']``)."""
        st = ['package'] + list(stereotypes or [])
        return self.add_node(name, st, attributes=attributes or [])

    def pkg_contain(self, namespace, contained):
        """Crosshair namespace containment (§10.4): a solid line with a
        circled plus on the *namespace* end; the contained element is at
        the other end."""
        return self.add_edge(namespace, contained, line_style=SOLID,
                             source_style=CIRCLED_PLUS)

    def pkg_import(self, client, supplier):
        """Package import relationship (§10.6): dashed line, open
        arrowhead, «import» keyword near the line."""
        return self.add_edge(client, supplier, line_style=DASHED,
                             target_style=OPEN, label='«import»')

    def pkg_conform(self, view, viewpoint):
        """«conform» special dependency from the view to its viewpoint
        (§10.7.4)."""
        return self.add_edge(view, viewpoint, line_style=DASHED,
                             target_style=OPEN, label='«conform»')

    def allocation(self, source, target):
        """«allocate» dependency (§12): allocation is a cross-cutting
        relationship, never a dedicated diagram (§12.2) — e.g. behavior
        → structure, requirement → structure."""
        return self.add_edge(source, target, line_style=DASHED,
                             target_style=OPEN, label='«allocate»')

    def add_frame(self, kind, element_kind=None, element_name=None,
                  diagram_name=None):
        """Set the diagram-kind frame (replaces any previous frame).

        Parameters
        ----------
        kind : str
            Diagram-kind tag: ``bdd``, ``ibd``, ``uc``, ``act``, ``sd``,
            ``stm``, ``par``, ``pkg``, ``req`` (§2.3).
        element_kind, element_name : str, optional
            The kind and name of the model element the frame represents
            (§2.4), e.g. ``'package'`` / ``'Structure'``.
        diagram_name : str, optional
            The unique diagram name (§2.4).

        Returns
        -------
        DiagramFrame
        """
        self.frame = DiagramFrame(kind, element_kind, element_name,
                                  diagram_name)
        return self.frame

    def par_constraint(self, name, type_):
        """Constraint property (§9.5): a usage of a constraint block in
        the context of an owning block — round-angle node with the name
        string ``<constraint name> : <type>``."""
        n = self.add_node('%s : %s' % (name, type_), rounded=True)
        return n

    def node(self, name, kinds=(), at=None, **kw):
        """UML 2.5.1 ch19 DeploymentTarget/Node: a perspective-view cube
        labeled with the name ('prepended by a colon' for instances).
        kinds: («device», «executionEnvironment», ...) keyword rows."""
        return self.add_node(name, stereotypes=list(kinds) or ['node'],
                             cube=True, at=at, **kw)

    def artifact(self, name, at=None, **kw):
        """UML 2.5.1 ch19 Artifact: an ordinary Class rectangle with the
        keyword artifact (19.3.4)."""
        return self.add_node(name, stereotypes=['artifact'], at=at, **kw)

    def deploy(self, artifact, target, label='deploy'):
        """Deployment (19.2.4): the Dependency dashed-arrow notation
        with the deploy keyword, or containment — containment is the
        caller's choice via add_child()."""
        e = self.add_edge(artifact, target, line_style=DASHED,
                          target_style=OPEN,
                          label='\u00ab%s\u00bb' % label)
        return e

    def manifest(self, artifact, element):
        """Manifestation (19.3.x): a dashed line with the manifest
        keyword (an Abstraction)."""
        e = self.add_edge(artifact, element, line_style=DASHED,
                          target_style=OPEN,
                          label='\u00abmanifest\u00bb')
        return e

    def par_value(self, name, type_, mult=None, default=None, at=None):
        """Value property (§9.7): plain-rectangle node with the string
        ``<value name> : <type> [<mult>] = <default>``. Valid only when
        the frame represents a BLOCK (constraint blocks cannot own value
        properties)."""
        parts = ('%s : %s' % (name, type_)) if type_ else name
        if mult is not None:
            parts += ' [%s]' % mult
        if default is not None:
            parts += ' = %s' % default
        n = self.add_node(parts)
        if at is not None:
            n.at = tuple(at)
        return n

    def par_param(self, name, type_='', owner=None, side='left',
                  offset=0.5):
        """Constraint parameter (§9.6): small square docked inside the
        owner's boundary; ``owner=None`` docks on the diagram frame
        itself (used when the frame represents a constraint block)."""
        p = ParParam('%s : %s' % (name, type_), side=side, offset=offset,
                     owner=owner)
        self.par_params.append(p)
        return p

    def usecase(self, name, **kw):
        """Use case (§5.5): ellipse with the verb-phrase name inside."""
        n = UseCase(name)
        if kw.get('at') is not None:
            n.at = tuple(kw['at'])
        self.nodes.append(n)
        return n

    def actor(self, name, stick_figure=True):
        """Actor (§5.7): stick figure + name beneath, or the rectangle
        notation with the «actor» keyword (``stick_figure=False``)."""
        n = Actor(name, stick_figure=stick_figure)
        self.nodes.append(n)
        return n

    def subject(self, name):
        """System boundary (§5.6): the rectangle enclosing the use
        cases; the name (a noun phrase) prints at the top inside.
        Nest use cases in it with ``node.add_child(use_case)``."""
        n = Node(name)
        self.nodes.append(n)
        return n

    def association(self, a, b, **kw):
        """Actor–use case association (§5.8): plain solid line, no
        arrowheads. Multiplicity via ``source_label``/``target_label``.
        (Composite associations between an actor and a use case are
        illegal on use case diagrams.)"""
        kw.setdefault('source_style', NONE)
        kw.setdefault('target_style', NONE)
        return self.add_edge(a, b, **kw)

    def include(self, src, dst, **kw):
        """«include» relationship (§5.10): dashed open-arrow line with
        the keyword floating beside; the TARGET end (arrowhead) is the
        included use case."""
        kw.setdefault('line_style', DASHED)
        kw.setdefault('target_style', OPEN)
        kw.setdefault('label', '\u00abinclude\u00bb')
        return self.add_edge(src, dst, **kw)

    def extend(self, src, dst, **kw):
        """«extend» relationship (§5.11): dashed open-arrow line with
        the keyword; the SOURCE end (tail) is the extending use case."""
        kw.setdefault('line_style', DASHED)
        kw.setdefault('target_style', OPEN)
        kw.setdefault('label', '\u00abextend\u00bb')
        return self.add_edge(src, dst, **kw)

    def bind(self, a, b, **kw):
        """Binding connector (§9.8): solid line with no arrowheads and no
        direction — an equality between the two bound ends. At least one
        end should be a constraint parameter (enforced only by
        convention); the routed path is the straight segment between the
        two docked boundary points."""
        kw.setdefault('source_style', NONE)
        kw.setdefault('target_style', NONE)
        e = self.add_edge(a, b, **kw)
        e.is_binding = True
        return e

    def add_node(self, name, stereotypes=None, attributes=None, rounded=False, dashed=False,
                 parent=None, compartments=None, at=None, chamfer=0, cube=False):
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
        n = Node(name, stereotypes, attributes, rounded, dashed,
                 compartments, at=at, chamfer=chamfer, cube=cube)
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

    def add_start(self, name='Start', parent=None, at=None):
        """Add an activity start node (filled circle).

        Parameters
        ----------
        name : str
            Optional label.

        Returns
        -------
        StartNode
        """
        n = StartNode(name, at=at)
        if parent is not None:
            n.parent = parent  # drawn inside the composite (v0.4.0)
        self.activities.append(n)
        return n

    def add_done(self, name='Done', parent=None, at=None):
        """Add an activity done / accept node (bullseye).

        Parameters
        ----------
        name : str
            Optional label.

        Returns
        -------
        DoneNode
        """
        n = DoneNode(name, at=at)
        if parent is not None:
            n.parent = parent  # drawn inside the composite (v0.4.0)
        self.activities.append(n)
        return n

    def add_terminate(self, name='Terminate', parent=None, at=None):
        """Add an activity terminate node (circle with X).

        Parameters
        ----------
        name : str
            Optional label.

        Returns
        -------
        TerminateNode
        """
        n = TerminateNode(name, at=at)
        if parent is not None:
            n.parent = parent  # drawn inside the composite (v0.4.0)
        self.activities.append(n)
        return n

    def add_fork(self, name='', w=36, h=8, parent=None, at=None):
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
        n = ForkJoinNode(name, w, h, at=at)
        if parent is not None:
            n.parent = parent
        self.activities.append(n)
        return n

    def add_join(self, name='', w=36, h=8, parent=None, at=None):
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
        n = ForkJoinNode(name, w, h, at=at)
        if parent is not None:
            n.parent = parent
        self.activities.append(n)
        return n

    def add_decision(self, name='', size=28, parent=None, at=None):
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
        n = DecisionNode(name, size, at=at)
        if parent is not None:
            n.parent = parent
        self.activities.append(n)
        return n

    def add_send_signal(self, name='', w=56, h=26, parent=None, at=None):
        """Add a send signal action — convex signpost (§6.8.3).

        Parameters
        ----------
        name : str
            The signal name sent by the action.
        at : (x, y), optional
            Fixed-position hint (pin mode places activities too).

        Returns
        -------
        SendSignalNode
        """
        n = SendSignalNode(name, w, h, at=at)
        if parent is not None:
            n.parent = parent
        self.activities.append(n)
        return n

    def add_accept_event(self, name='', w=64, h=26, parent=None, at=None):
        """Add an accept event action — notched pentagon (§6.8.4).

        The name is usually the signal (or time event) awaited.

        Returns
        -------
        AcceptEventNode
        """
        n = AcceptEventNode(name, w, h, at=at)
        if parent is not None:
            n.parent = parent
        self.activities.append(n)
        return n

    def add_wait_time(self, name='after (0 s)', parent=None, at=None):
        """Add a wait time action — hourglass + expression beneath
        (§6.8.5).  ``name`` is the whole time expression: ``at (...)``
        (absolute) or ``after (...)`` (relative).

        Returns
        -------
        WaitTimeNode
        """
        n = WaitTimeNode(name, at=at)
        if parent is not None:
            n.parent = parent
        self.activities.append(n)
        return n

    def call_behavior(self, name, behavior, parent=None, at=None, **kw):
        """Add a call behavior action (§6.8.2): a round-cornered node
        named ``<name> : <Behavior>`` carrying the rake glyph.

        Parameters
        ----------
        name : str
            The action's verb phrase.
        behavior : str
            The invoked behavior's name.
        """
        n = self.add_node('%s : %s' % (name, behavior), parent=parent,
                          at=at, rounded=True, **kw)
        n.rake = True
        return n

    def object_flow(self, source, target, label=None, **kw):
        """Object flow (§6.7.1): solid line, open arrowhead.  ``label``
        prints on the edge (e.g. the object node's type string).
        """
        kw.setdefault('target_style', 'open')
        return self.add_edge(source, target, label=label, **kw)

    def control_flow(self, source, target, guard=None, **kw):
        """Control flow (§6.7.2): dashed line, open arrowhead.  ``guard``
        prints in square brackets (§6.9.3 decision guards) or as a plain
        label on the control flow's leg.
        """
        kw.setdefault('target_style', 'open')
        label = kw.pop('label', None)
        if guard:
            label = '[%s]' % guard
        return self.add_edge(source, target, line_style='dashed',
                             label=label, **kw)

    def action_start(self, size=14, parent=None, at=None):
        """Add a v2 action start node: a small SOLID black diamond
        (Intro deck p56, matching the deck's own labeled 'start' node).
        """
        n = DecisionNode('', size=size, at=at, filled=True)
        if parent is not None:
            n.parent = parent
        self.activities.append(n)
        return n

    def add_merge(self, name='', size=28, parent=None, at=None):
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
        n = DecisionNode(name, size, at=at)
        if parent is not None:
            n.parent = parent
        self.activities.append(n)
        return n

    # ── state-machine pseudostates ──

    def add_initial(self, name='initial', parent=None, at=None):
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
        n = InitialPseudostate(name=name, at=at)
        if parent is not None:
            n.parent = parent  # drawn inside the composite (v0.4.0)
        self.activities.append(n)
        return n

    def add_junction(self, name='', parent=None, at=None):
        """Add a state-machine junction pseudostate (filled black circle).

        Returns
        -------
        JunctionPseudostate
        """
        n = JunctionPseudostate(name=name, at=at)
        if parent is not None:
            n.parent = parent
        self.activities.append(n)
        return n

    def add_choice(self, name='', parent=None, at=None):
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

    def add_terminate(self, name='terminate', kind='state', parent=None,
                      at=None):
        """Add a terminate node — open circle with an X (§6.9.2 flow
        final notation; the state-machine variant shares shape/class).

        ``kind`` is accepted for forward compatibility — activity terminate
        (``kind='activity'``) and state terminate (``kind='state'``) share
        both shape and class today.

        Returns
        -------
        TerminatePseudostate
        """
        n = TerminatePseudostate(name=name, at=at)
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

    def add_region(self, name='', **kw):
        """Add a state-machine region (§8.7): a dashed rectangle with
        the name floating inside a corner.  Region vertices live in the
        region (children); transitions between regions are illegal.

        Returns
        -------
        Region
        """
        r = Region(name, **kw)
        self.views.append(r)
        return r

    def add_state(self, name, stereotypes=None, attributes=None,
                  substates=None, dashed=False, at=None):
        """Add a state node with rounded corners and default ``«state»``.

        Returns
        -------
        StateNode
        """
        n = StateNode(name, stereotypes=stereotypes, attributes=attributes,
                      substates=substates, dashed=dashed)
        if at is not None:
            n.at = tuple(at)
        self.nodes.append(n)
        return n

    def composite_state(self, name, entry=None, exit=None, do=None,
                        stereotypes=None, substates=None,
                        parent=None, dashed=False):
        """Add a composite state (§8.4.2): a round-cornered state with
        the optional entry/exit/do internal compartment (§8.4.1) ready
        to hold nested substates (``add_child`` or draw them inside).

        Returns
        -------
        StateNode
        """
        internals = []
        if entry:
            internals.append('entry / %s' % entry)
        if exit:
            internals.append('exit / %s' % exit)
        if do:
            internals.append('do / %s' % do)
        return self.add_state(name, stereotypes=stereotypes,
                              attributes=internals, substates=substates,
                              dashed=dashed)

    def transition(self, source, target, trigger=None, guard=None,
                   effect=None, **kw):
        """Add a state-machine transition (§8.5): a solid line with an
        open arrowhead carrying the floating string
        ``<trigger> [<guard>] / <effect>`` — each part optional, order
        fixed.  For the keyword form pass already-formatted pieces:

        >>> d.transition(offline, online,
        ...              trigger='startUp(sensorID)',
        ...              guard='isPowerAvailable == True',
        ...              effect='calibrate')

        Returns
        -------
        Edge
        """
        parts = []
        if trigger:
            parts.append(trigger)
        if guard:
            parts.append('[%s]' % guard)
        if effect:
            parts.append('/ %s' % effect)
        kw.setdefault('target_style', 'open')
        label = kw.pop('label', None)
        if parts:
            label = ' '.join(parts)
        return self.add_edge(source, target, label=label, **kw)

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
        for act in self.activities:
            # activity pins (§6.6.1): straddle the shape's boundary
            if getattr(act, 'ports', None):
                box = act.box()
                for p in act.ports:
                    if p.side == 'left':
                        p.x, p.y = box[0] - PORT_W // 2, box[3] - PORT_H
                    elif p.side == 'right':
                        p.x, p.y = box[2] - PORT_W // 2, box[3] - PORT_H
                    elif p.side == 'top':
                        p.x, p.y = box[0] + (box[2] - box[0]) // 2 - PORT_W // 2, \
                            box[1] - PORT_H // 2
                    else:  # bottom
                        p.x, p.y = box[0] + (box[2] - box[0]) // 2 - PORT_W // 2, \
                            box[3] - PORT_H // 2
        for n in self.nodes:
            if n.ports:
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

            # interface symbols (port-attached + node-attached)
            for i in n.interfaces:
                i.update_pos()
            for p in n.ports:
                for i in p.interfaces:
                    i.update_pos()

    def add_edge(self, source, target, **kw):
        """Create a new edge and register it with the diagram.

        Parameters
        ----------
        source, target : Node
            Endpoint nodes.
        **kw
            Passed to ``Edge``: ``line_style``, ``source_style``,
            ``target_style``, ``label``, ``source_label``,
            ``target_label``, ``source_port``, ``target_port``.

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

        Disabled by ``Diagram.reanchor_nested = False`` (use case
        diagrams: associations must touch the ellipses, §5.8).

        - Both endpoints under the same outermost ancestor: the edge is
          internal — routed as a straight boundary-to-boundary segment
          (clipped at each child box) and marked ``_nested_internal``.
        - Endpoints under different ancestors: the edge is re-anchored to
          the two outermost ancestors (original endpoints kept in
          ``_nested_orig``) so the engine routes across the parent
          boundary, per UML composite-structure convention.
        """
        if not getattr(self, 'reanchor_nested', True):
            return
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
            if isinstance(e.source, FramePort) or isinstance(e.target, FramePort):
                continue  # frame-port edges route in the placement pass
            if getattr(e.source, 'is_par_param', False) or \
                    getattr(e.target, 'is_par_param', False):
                continue  # binding edges route in the placement pass (§9.8)
            if e.target not in incoming:
                continue  # edges to ParParams/etc. are not layer constraints
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
            e.route(*_orthogonal_departs(e.source, e.target))

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
        if getattr(node, 'is_stick_figure', False):
            # §5.7/Fig 5.1: associations attach on the figure's SIDE —
            # never the bottom, where the name label hangs
            other = edge.target if is_source else edge.source
            dx = other.cx - node.cx
            if dx >= 0:
                return (node.x + node.w, node.cy)
            return (node.x, node.cy)
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

    _FRAME_PORT_INNER = {'left': 'right', 'right': 'left',
                         'top': 'bottom', 'bottom': 'top'}

    def _frame_port_anchor(self, p):
        """(x, y, side) where a connector from INSIDE the frame attaches
        to a frame port: the face pointing into the frame — the opposite
        of the port's outward side (§4.8: frame ports are interaction
        points on the header block's boundary; internal connectors
        approach from the frame's contents area)."""
        side = self._FRAME_PORT_INNER[p.side]
        if side == 'left':
            return (p.x, p.cy), side
        if side == 'right':
            return (p.x + PORT_W, p.cy), side
        if side == 'top':
            return (p.cx, p.y), side
        return (p.cx, p.y + PORT_H), side

    def _edge_port_anchor(self, p):
        """(x, y, side) for routing: frame ports anchor on their inner
        face, plain ports on their outer face."""
        if isinstance(p, FramePort):
            return self._frame_port_anchor(p)
        return self._port_boundary(p), p.side

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

        # Band between the two boxes (when they don't overlap vertically).
        # Middle-out ordering: bands hugging an adjacent box's edge produce
        # wrap-arounds that graze the box (and any halo labels on them).
        lo, hi = min(src_bottom, tgt_top), max(src_bottom, tgt_top)
        if hi - lo > 12:
            step = max(8, (hi - lo) // 8)
            band = list(range(lo + 6, hi - 6, step))
            band.sort(key=lambda y: abs(y - (lo + hi) / 2))
            cands.extend(band)

        # Just beyond the target box (above and below)
        for base in (tgt_top - 6, tgt_top - 14, tgt_top - 24,
                     tgt_bottom + 6, tgt_bottom + 14, tgt_bottom + 24):
            cands.append(base)
        return [y for y in cands if y > 0]

    def _frame_port_unplaced(self, e):
        """True when an edge anchors to a FramePort that rendering has not
        placed on the frame border yet (its geometry is only known after
        layout) — such edges are routed by ``_place_frame_ports``."""
        for p in (e.source_port, e.target_port):
            if isinstance(p, FramePort) and not getattr(p, 'placed', False):
                return True
        return False

    def _port_route(self, e):
        """Obstacle-aware port-to-port routing.

        Anchors each end at the port's outer face and keeps the final
        segment perpendicular to the target port face.  Candidate routes
        are tried in order and the first that clears all foreign node
        bodies and port boxes wins: (1) the direct Z-shape; (2) wrap-around
        bypasses for side-facing ports through a free band; (3) leg-scan
        shifts for top/bottom ports; (4) direct L-shaped fallbacks for
        hook geometries.  Falls back to the plain Z-shape when nothing
        clears.  Edges anchoring unplaced FramePorts are deferred to
        ``_place_frame_ports`` (the frame geometry exists only after
        layout).
        """
        if self._frame_port_unplaced(e):
            e.frame_pending = True
            return False
        sp, tp = e.source_port, e.target_port
        if not sp or not tp:
            return False
        (sx, sy), _sside = self._edge_port_anchor(sp)
        (tx, ty), tside = self._edge_port_anchor(tp)
        gap = 4

        # Perpendicular approach point for the target port face.
        if tside == 'left':
            ax, ay = tx - gap, ty
        elif tside == 'right':
            ax, ay = tx + gap, ty
        elif tside == 'top':
            ax, ay = tx, ty - gap
        else:  # bottom
            ax, ay = tx, ty + gap

        cands = []

        # 1. Plain Z-shape (historical behaviour) as the first candidate.
        if tside in ('left', 'right'):
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
        if tside in ('left', 'right'):
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
        if tside in ('left', 'right') and (sx - tx) * (ax - tx) < 0:
            if abs(ty - sy) > abs(tx - sx):
                cands.append([(sx, sy), (sx, ty), (tx, ty)])
            else:
                cands.append([(sx, sy), (tx, sy), (tx, ty)])
        elif tside in ('top', 'bottom') and (sy - ty) * (ay - ty) < 0:
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
        if tside in ('left', 'right'):
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
        Edges anchoring unplaced FramePorts are deferred to
        ``_place_frame_ports``.
        """
        if self._frame_port_unplaced(e):
            e.frame_pending = True
            return False
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

    def _all_pinned(self):
        """True when every node AND every top-level activity carries a
        fixed-position hint — the pin mode engages only for
        fully-pinned diagrams."""
        top_acts = [a for a in self.activities
                    if getattr(a, 'parent', None) is None]
        if not self.nodes and not top_acts:
            return False
        for n in self.nodes:
            if getattr(n, 'at', None) is None:
                return False
        for a in top_acts:
            if getattr(a, 'at', None) is None:
                return False
        return True

    def _route_pinned(self):
        """Pin mode: nodes AND top-level activities sit at their hints;
        edges route as orthogonal channels between the pinned boxes,
        anchors on the facing sides of each pair (horizontal rows on the
        vertical sides, vertical ladders on the horizontal sides)."""
        for n in self.nodes:
            # hints are pin coordinates; round to ints — the braille
            # renderer loops over pixel ranges
            n.x, n.y = int(round(n.at[0])), int(round(n.at[1]))
        for a in self.activities:
            if getattr(a, 'at', None) is not None:
                a.x, a.y = int(round(a.at[0])), int(round(a.at[1]))
        self._update_port_positions()
        for e in self.edges:
            if getattr(e, '_manual_route', False):
                continue    # script-curated waypoints survive re-renders
            if self._is_visual_containment(e):
                continue
            if getattr(e, '_nested_internal', False):
                continue
            self._route_pinned_edge(e)

    def _route_pinned_edge(self, e):
        s, t = e.source, e.target
        obstacles = [n for n in self.nodes if n not in (s, t)]

        def _clear(segs):
            return all(not self._segment_hits(
                x1, y1, x2, y2, obstacles)[0] for x1, y1, x2, y2 in segs)

        if s is t:
            # self-association (e.g. a nested-usage role on itself):
            # out of the right side, down, back into the lower right
            sx, sy = s.x + s.w, s.y + s.h // 2
            ch = s.x + s.w + 18
            bx = s.x + s.w * 3 // 4
            ly = s.y + s.h
            e.route((sx, sy), (ch, sy), (ch, ly), (bx, ly))
            return
        if abs(s.cy - t.cy) < max(s.h, t.h) and abs(s.cx - t.cx) > 40:
            # same row — anchor the facing vertical sides and run a
            # 4-leg ORTHOGONAL channel: horizontal at the source row,
            # vertical at a mid-x, horizontal into the target row. The
            # old (sx,sy)->(tx,base)->(tx,ty) mixed legs into diagonals
            # whenever the dodge differed from the row (fig3_1 eps-cdhs).
            if s.cx < t.cx:
                sx, sy, tx, ty = s.x + s.w, s.cy, t.x, t.cy
            else:
                sx, sy, tx, ty = s.x, s.cy, t.x + t.w, t.cy
            if sy == ty:
                e.route((sx, sy), (tx, ty))
                return
            xlo, xhi = (sx, tx) if sx < tx else (tx, sx)
            base = (sx + tx) // 2
            channel, picked = None, False
            if _clear([(sx, sy, base, sy), (base, sy, base, ty),
                       (base, ty, tx, ty)]):
                channel, picked = base, True
            for off in range(1, int((xhi - xlo) // 3) + 2):
                for mx in (base - off * 3, base + off * 3):
                    if not (xlo < mx < xhi):
                        continue
                    if _clear([(sx, sy, mx, sy), (mx, sy, mx, ty),
                               (mx, ty, tx, ty)]):
                        channel, picked = mx, True
                        break
                if picked:
                    break
            e.route((sx, sy), (channel if picked else base, sy),
                    (channel if picked else base, ty), (tx, ty))
        else:
            # vertical ladder — anchor the facing top/bottom sides.
            # box() gives the token-anchor extent (WaitTimeNode's box()
            # stops at the glyph, above its hanging expression)
            sb = s.box()
            tb = t.box()
            if s.cy < t.cy:
                sx, sy = s.cx, sb[3] + (s.y + s.h - sb[3])
                tx, ty = t.cx, tb[1]
            else:
                sx, sy = s.cx, sb[1]
                tx, ty = t.cx, tb[3]
            if abs(sx - tx) <= 12:
                e.route((sx, sy), (tx, ty))   # aligned: direct
                return
            # Y-CHANNEL ladder: exit PERPENDICULAR from the departed box
            # (a vertical leg with clearance), cross the free band
            # horizontally, enter perpendicular. A dodge along the box's
            # wall line reads as attachment along the outline (gallery
            # review: 'leaving the box along the wall').
            ylo, yhi = (sy, ty) if sy < ty else (ty, sy)
            base = (sy + ty) // 2
            channel, picked = None, False
            for off in range(0, int((yhi - ylo) // 3) + 2):
                for my in ([base] if off == 0 else
                           [base - off * 3, base + off * 3]):
                    if not (ylo + 6 < my < yhi - 6):
                        continue
                    if _clear([(sx, sy, sx, my), (sx, my, tx, my),
                               (tx, my, tx, ty)]):
                        channel, picked = my, True
                        break
                if picked:
                    break
            if not picked:
                channel = base
            e.route((sx, sy), (sx, channel), (tx, channel), (tx, ty))

    def _route_pinned_straight(self, e):
        """Pinned diagonal pair: depart orthogonally from a side of the
        source (a border anchor + a stub), run the diagonal, arrive
        orthogonally at the target — never slide out of a corner."""
        e.route(*_orthogonal_departs(e.source, e.target))

    def _route_orthogonal(self, e, layer_of, layers, gap_used=None):
        if e.source_port and e.target_port:
            self._port_route(e)
            return

        # §8.5 self-transition: an arrow from a state back to itself —
        # out of the right side, down, back into the lower edge
        if e.source is e.target:
            s = e.source
            sx, sy = s.x + s.w, s.y + s.h // 2
            ch = s.x + s.w + 20
            bx = s.x + s.w * 3 // 4
            ly = s.y + s.h
            e.route((sx, sy), (ch, sy), (ch, ly), (bx, ly))
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

        # Fixed-position pins (v0.14.4): when every node carries an `at`
        # hint, the whole diagram is placed at those coordinates and the
        # edges route as orthogonal channels between the pinned boxes —
        # metamodel/figure reproduction mode.
        if self._all_pinned():
            self._route_pinned()
            return

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

    def _content_bounds(self):
        """Union bounding box of all rendered content (nodes+ports, comments,
        views, activities, edge waypoints) — (min_x, min_y, max_x, max_y),
        or ``None`` when the diagram is empty."""
        xs, ys = [], []
        for n in self.nodes:
            xs.extend([n.x, n.x + n.w])
            ys.extend([n.y, n.y + n.h])
            for p in n.ports:
                xs.extend([p.x, p.x + p.w])
                ys.extend([p.y, p.y + p.h])
                # outside port labels extend beyond the port box — count
                # their estimated width so the canvas never clips them
                lab = getattr(p, 'label', '')
                if lab:
                    lw = len(lab) * 2 + 6
                    if p.side == 'right':
                        xs.append(p.x + p.w + lw)
                    elif p.side == 'left':
                        xs.append(p.x - lw)
                    elif p.side == 'bottom':
                        ys.append(p.y + p.h + 10)
                    elif p.side == 'top':
                        ys.append(p.y - 10)
                for i in p.interfaces:
                    ex1, ey1, ex2, ey2 = i.extent()
                    xs.extend([ex1, ex2])
                    ys.extend([ey1, ey2])
            for i in n.interfaces:
                ex1, ey1, ex2, ey2 = i.extent()
                xs.extend([ex1, ex2])
                ys.extend([ey1, ey2])
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
            if isinstance(getattr(e, 'source_port', None), FramePort) or \
                    isinstance(getattr(e, 'target_port', None), FramePort):
                continue  # routed frame-port waypoints must not widen the
                          # frame between port placement and drawing
            if getattr(e, 'is_binding', False):
                continue  # binding legs end at sockets on/near the border
                          # — they must not widen the frame under them
            for px, py in e.waypoints:
                xs.append(px)
                ys.append(py)
        for li in self.lifelines:
            xs.extend([li.x - li.w / 2, li.x + li.w / 2])
            ys.extend([li.head_y, li.head_y + li.h,
                       self._lifeline_tail_end(li)])
        for m in self.messages:
            if getattr(m, 'src', None) is None or getattr(m, 'dst', None) is None:
                if self.frame is None:
                    # border-attached ends live ON the frame and floating
                    # crop ends hang OUTSIDE it — both must never widen
                    # the frame (canvas bounds handle those)
                    xs.extend([m.x1, m.x2])
                ys.append(m.y)
        for f in self.fragments:
            lo, hi = self._fragment_span_x(f)
            xs.extend([lo, hi])
            ys.extend([f.y1, f.y2])
        for cc in self.constraints:
            lx = cc.lifeline.x + cc.dx
            xs.extend([lx - len(cc.text) - 2, lx + len(cc.text) + 2])
            ys.extend([cc.y, cc.y + (10 if cc.rounded else 0)])
        if not xs:
            return None
        return min(xs), min(ys), max(xs), max(ys)

    def _frame_rect(self):
        """Rectangle for the diagram-kind frame around the content margin,
        widened to fit the header line — (x1, y1, x2, y2) or ``None``."""
        if self.frame is None:
            return None
        b = self._content_bounds()
        if b:
            x1, y1, x2, y2 = b
        else:
            x1 = y1 = 0
            x2 = y2 = 40
        x1 = min(x1 - 4 - getattr(self, 'frame_pad', 0), 4)
        y1 -= 4
        x2 = max(x2 + 4 + getattr(self, 'frame_pad', 0),
                 len(self.frame.header) * 2 + 12)
        y2 += 4
        return (x1, y1 - DiagramFrame.HEADER_H, x2, y2)

    def _place_frame_ports(self):
        """Position FramePorts on the frame border (straddling it) and
        route their edges — called from render/render_svg after layout,
        because the frame rectangle's geometry is only known then
        (§4.8, Figure 4.6)."""
        if not self.frame_ports:
            return
        fr = self._frame_rect()
        if fr is None:
            return
        fx1, fy1, fx2, fy2 = fr
        for p in self.frame_ports:
            if p.side == 'left':
                p.x = fx1 - PORT_W // 2
                p.y = fy1 + int((fy2 - fy1) * p.offset) - PORT_H // 2
            elif p.side == 'right':
                p.x = fx2 - PORT_W // 2
                p.y = fy1 + int((fy2 - fy1) * p.offset) - PORT_H // 2
            elif p.side == 'top':
                p.x = fx1 + int((fx2 - fx1) * p.offset) - PORT_W // 2
                p.y = fy1 - PORT_H // 2
            else:
                p.x = fx1 + int((fx2 - fx1) * p.offset) - PORT_W // 2
                p.y = fy2 - PORT_H // 2
            p.placed = True
            for i in p.interfaces:
                i.update_pos()
        for e in self.edges:
            if isinstance(getattr(e, 'source_port', None), FramePort) or \
                    isinstance(getattr(e, 'target_port', None), FramePort):
                if e.source_port and e.target_port:
                    self._port_route(e)
                else:
                    self._route_single_port(e)
                e.frame_pending = False

    def _place_par_params(self):
        """Dock ParParam squares inside their owner's boundary (or
        STRADDLING the frame border when the owner is the frame, Fig 9.3
        pixel evidence / §4.8 frame-port precedent) and route binding
        edges straight or through a single orthogonal channel (§9.8) —
        called from render/render_svg after layout.

        Order matters (Fig 9.3 round-2 feedback loop): widen owners
        FIRST (their growth feeds _frame_rect), then measure the frame
        ONCE, dock, and route — never let route waypoints widen the
        frame under already-docked sockets.
        """
        if not self.par_params:
            return
        # 1) widen owner boxes so their param labels fit INSIDE with
        # margin (Fig 9.3 ~25% inner margin) — before measuring the
        # frame, since node bounds feed it
        for p in self.par_params:
            r = p.owner
            if r is None or getattr(r, 'is_par_param', False) or \
                    getattr(r, 'is_frame_port', False):
                continue
            needed = PAR_PARAM_S + len(p.name) * 2 + 6 + 12
            if p.side in ('left', 'right') and r.w < needed:
                r.w = needed
        # 2) measure the frame ONCE and dock the squares
        fr = self._frame_rect()
        for p in self.par_params:
            r = p.owner
            if r is None and fr is not None:
                # frame socket (Fig 9.3): the square STRADDLES the frame
                # border, like a §4.8 frame port; the binding starts the
                # leg at the border side
                x1, y1, x2, y2 = fr
                if p.side == 'left':
                    p.x = x1 - p.w // 2
                    p.y = y1 + int((y2 - y1) * p.offset) - p.h // 2
                elif p.side == 'right':
                    p.x = x2 - p.w // 2
                    p.y = y1 + int((y2 - y1) * p.offset) - p.h // 2
                elif p.side == 'top':
                    p.x = x1 + int((x2 - x1) * p.offset) - p.w // 2
                    p.y = y1 - p.h // 2
                else:
                    p.x = x1 + int((x2 - x1) * p.offset) - p.w // 2
                    p.y = y2 - p.h // 2
            elif r is not None:
                if getattr(r, 'x', None) is None or (r.x == 0 and r.y == 0
                                                     and r.w == 0):
                    continue   # owner not laid out yet
                if p.side == 'left':
                    p.x = r.x
                    p.y = r.y + int(r.h * p.offset) - p.h // 2
                elif p.side == 'right':
                    p.x = r.x + r.w - p.w
                    p.y = r.y + int(r.h * p.offset) - p.h // 2
                elif p.side == 'top':
                    p.x = r.x + int(r.w * p.offset) - p.w // 2
                    p.y = r.y
                else:
                    p.x = r.x + int(r.w * p.offset) - p.w // 2
                    p.y = r.y + r.h - p.h
            p.placed = True

        def _dock_point(el, toward):
            """Point on el's boundary (or center, for a parameter square)
            facing the straight line's other end."""
            if getattr(el, 'is_par_param', False):
                return (el.x + el.w // 2, el.y + el.h // 2)
            cx, cy = el.cx, el.cy
            tx, ty = toward
            if abs(tx - cx) >= abs(ty - cy):
                # the line arrives horizontally: dock on the facing side
                mid = cy + int((ty - cy) * el.w // (2 * max(1, abs(tx - cx))))
                return (el.x, mid) if tx < cx else (el.x + el.w, mid)
            mid = cx + int((tx - cx) * el.h // (2 * max(1, abs(ty - cy))))
            return (mid, el.y) if ty < cy else (mid, el.y + el.h)

        def _out_face(p):
            """A parameter square's outward face midpoint (§9.6)."""
            return {
                'left': (p.x, p.y + p.h // 2),
                'right': (p.x + p.w, p.y + p.h // 2),
                'top': (p.x + p.w // 2, p.y),
                'bottom': (p.x + p.w // 2, p.y + p.h),
            }[p.side]

        for e in self.edges:
            if not getattr(e, 'is_binding', False):
                continue
            s, t = e.source, e.target
            s_p = getattr(s, 'is_par_param', False) and s.placed
            t_p = getattr(t, 'is_par_param', False) and t.placed
            if s_p and t_p:
                so, to_ = _out_face(s), _out_face(t)
                if so[1] == to_[1] or so[0] == to_[0]:
                    e.waypoints = [so, to_]   # direct line (Fig 9.3 #5)
                elif s.side in ('left', 'right') and t.side in ('left', 'right'):
                    mx = (so[0] + to_[0]) // 2
                    e.waypoints = [so, (mx, so[1]), (mx, to_[1]), to_]
                else:
                    my = (so[1] + to_[1]) // 2
                    e.waypoints = [so, (so[0], my), (to_[0], my), to_]
            elif t_p and not s_p:
                face = _out_face(t)
                dock = _dock_point(s, (t.cx, t.cy))
                if t.side in ('top', 'bottom'):
                    # Fig 9.4: the arrival is VERTICAL into the square's
                    # outward face. The docking row still gets a
                    # perpendicular clearance stub so the horizontal run
                    # never hugs the value's own wall (or the enclosing
                    # reference's) — the review's 'along the wall'
                    # defect. Perfectly aligned pairs stay straight.
                    if dock[0] == face[0] or dock[1] == face[1]:
                        e.waypoints = [face, dock]
                    else:
                        sy2 = face[1] + (10 if t.side == 'top' else -10)
                        fx = face[0] if s.cx > t.cx else dock[0]
                        e.waypoints = [face, (face[0], sy2),
                                       (fx, sy2), (fx, dock[1]), dock]
                else:
                    if dock[0] == face[0] or dock[1] == face[1]:
                        e.waypoints = [face, dock]
                    else:
                        sx2 = face[0] + (10 if t.side == 'right' else -10)
                        fy = face[1] if s.cy > t.cy else dock[1]
                        e.waypoints = [face, (sx2, face[1]),
                                       (sx2, fy), (dock[0], fy), dock]
            elif s_p:
                face = _out_face(s)
                dock = _dock_point(t, (s.cx, s.cy))
                if s.side in ('top', 'bottom'):
                    if dock[0] == face[0] or dock[1] == face[1]:
                        e.waypoints = [dock, face]
                    else:
                        sy2 = face[1] + (10 if s.side == 'top' else -10)
                        fx = face[0] if t.cx > s.cx else dock[0]
                        e.waypoints = [dock, (dock[0], sy2),
                                       (fx, sy2), (fx, face[1]), face]
                else:
                    if dock[0] == face[0] or dock[1] == face[1]:
                        e.waypoints = [dock, face]
                    else:
                        sx2 = face[0] + (10 if s.side == 'right' else -10)
                        fy = face[1] if t.cy > s.cy else dock[1]
                        e.waypoints = [dock, (sx2, dock[1]),
                                       (sx2, fy), (face[0], fy), face]

    def render(self, c=None, routing='orthogonal', layer_gap=50, node_gap=12, margin=8):
        if c is None:
            c = Canvas()
        self.layout(routing=routing, layer_gap=layer_gap, node_gap=node_gap, margin=margin)
        self._update_port_positions()
        self._place_frame_ports()
        self._place_par_params()
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
                              source_label=getattr(e, 'source_label', None),
                              target_label=getattr(e, 'target_label', None),
                              item_flow=getattr(e, 'item_flow', None),
                              item_position=getattr(e, 'item_position', 0.5),
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
                              source_label=getattr(e, 'source_label', None),
                              target_label=getattr(e, 'target_label', None),
                              item_flow=getattr(e, 'item_flow', None),
                              item_position=getattr(e, 'item_position', 0.5),
                              source_node=e.source,
                              target_node=e.target)
        child_nodes = self._child_nodes()

        def _draw_node_tree(node):
            if isinstance(node, UseCase):
                draw_usecase_node(c, node)
            elif isinstance(node, Actor) and node.is_stick_figure:
                draw_actor_stick(c, node)
            else:
                draw_class_box(c, node.x, node.y, node.x + node.w, node.y + node.h,
                               node.name, node.stereotypes, node.attributes,
                               rounded=node.rounded, dashed=node.dashed,
                               compartments=getattr(node, 'compartments', None),
                               folder=_is_folder(node.stereotypes),
                               chamfer=getattr(node, 'chamfer', 0))
                if getattr(node, 'cube', False):
                    draw_cube_facets(c, node.x, node.y,
                                     node.x + node.w, node.y + node.h)
                if getattr(node, 'rake', False):
                    draw_rake(c, node.x + node.w - 4, node.y + node.h - 3)
            for p in node.ports:
                if isinstance(p, (EntryPoint, ExitPoint)):
                    draw_entry_exit_point(c, p.cx, p.cy, PORT_W // 2, label=p.label, kind=getattr(p, 'kind', 'entry'))
                else:
                    draw_port_box(c, p.x, p.y, p.label, side=p.side,
                                  direction=p.direction,
                                  label_inside=getattr(p, 'label_inside', False))
                for i in p.interfaces:
                    draw_interface(c, i)
            for i in node.interfaces:
                draw_interface(c, i)
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
                draw_decision_node(c, a.cx, a.cy, a.size // 2, a.name,
                                   filled=getattr(a, 'filled', False))
            elif isinstance(a, HistoryPseudostate):
                draw_history_node(c, a.cx, a.cy, a.r, deep=a.deep)
            elif isinstance(a, SendSignalNode):
                draw_send_signal_node(c, a)
            elif isinstance(a, AcceptEventNode):
                draw_accept_event_node(c, a)
            elif isinstance(a, WaitTimeNode):
                draw_wait_time_node(c, a)
            for p in getattr(a, 'ports', []):
                draw_port_box(c, p.x, p.y, p.label, side=p.side,
                              direction=p.direction,
                              label_inside=getattr(p, 'label_inside', False))

        for n in self.nodes:
            if n in child_nodes:
                continue
            _draw_node_tree(n)
        for com in self.comments:
            draw_comment_box(c, com.x, com.y, com.x + com.w, com.y + com.h, com.text)
        for v in self.views:
            if isinstance(v, Region):
                draw_region_box(c, v)
                for child in v.children:
                    draw_class_box(c, child.x, child.y, child.x + child.w, child.y + child.h,
                                   child.name, child.stereotypes, child.attributes,
                                   rounded=child.rounded, dashed=child.dashed,
                                   compartments=getattr(child, 'compartments', None),
                                   folder=_is_folder(child.stereotypes),
                                   chamfer=getattr(child, 'chamfer', 0))
                    for p in child.ports:
                        for i in p.interfaces:
                            draw_interface(c, i)
                    for i in child.interfaces:
                        draw_interface(c, i)
            else:
                draw_view_box(c, v.x, v.y, v.x + v.w, v.y + v.h, v.name, v.stereotypes, v.attributes, dashed=v.dashed)
                for child in v.children:
                    draw_class_box(c, child.x, child.y, child.x + child.w, child.y + child.h,
                                   child.name, child.stereotypes, child.attributes, rounded=child.rounded, dashed=child.dashed,
                                   compartments=getattr(child, 'compartments', None),
                                   folder=_is_folder(child.stereotypes))
                    for p in child.ports:
                        if isinstance(p, (EntryPoint, ExitPoint)):
                            draw_entry_exit_point(c, p.cx, p.cy, PORT_W // 2, label=p.label, kind=getattr(p, 'kind', 'entry'))
                        else:
                            draw_port_box(c, p.x, p.y, p.label, side=p.side,
                                          direction=p.direction,
                                          label_inside=getattr(p, 'label_inside', False))
                        for i in p.interfaces:
                            draw_interface(c, i)
                    for i in child.interfaces:
                        draw_interface(c, i)
        for p in self.frame_ports:
            draw_port_box(c, p.x, p.y, p.label, side=p.side,
                          direction=p.direction,
                          label_inside=getattr(p, 'label_inside', False),
                          label_side='top' if getattr(p, 'label_above', False)
                          else self._FRAME_PORT_INNER[p.side])
            for i in p.interfaces:
                draw_interface(c, i)
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
                draw_decision_node(c, a.cx, a.cy, a.size // 2, a.name,
                                   filled=getattr(a, 'filled', False))
            elif isinstance(a, HistoryPseudostate):
                draw_history_node(c, a.cx, a.cy, a.r, deep=a.deep)
            elif isinstance(a, SendSignalNode):
                draw_send_signal_node(c, a)
            elif isinstance(a, AcceptEventNode):
                draw_accept_event_node(c, a)
            elif isinstance(a, WaitTimeNode):
                draw_wait_time_node(c, a)
            for p in getattr(a, 'ports', []):
                draw_port_box(c, p.x, p.y, p.label, side=p.side,
                              direction=p.direction,
                              label_inside=getattr(p, 'label_inside', False))

        # ── sequence diagram elements (§7.4–7.7) ──
        self._update_seq_geometry()
        for li in self.lifelines:
            draw_seq_head(c, li.x, li.head_y, li.label)
            draw_line(c, li.x, li.tail_start, li.x,
                      self._lifeline_tail_end(li), DASHED)
        for s in self.exec_specs:
            draw_seq_exec(c, s.lifeline.x, s.y1, s.y2, s.shaded,
                          width=SEQ_EXEC_W)
        for m in self.messages:
            if m.src is m.dst:
                # self-message loop (§7.5: a lifeline may message itself)
                for px, py in line(m.src.x, m.y, m.src.x + 30, m.y):
                    c.set(px, py)
                for px, py in line(m.src.x + 30, m.y, m.src.x + 30, m.y + 8):
                    c.set(px, py)
                for px, py in line(m.src.x + 30, m.y + 8, m.src.x + 8, m.y + 8):
                    c.set(px, py)
                style = FILLED if m.kind == 'sync' else OPEN
                draw_arrowhead(c, m.src.x + 8, m.y + 8, pi, style)
                if m.label:
                    c.set_text(m.src.x + 33, m.y + 3, m.label)
            else:
                draw_seq_message(c, m.x1, m.x2, m.y, m.kind, m.label)
        for x in self.destructions:
            draw_destruction_x(c, x.lifeline.x, x.y)
        for cc in self.constraints:
            draw_seq_constraint(c, cc.lifeline, cc)
        for f in self.fragments:
            draw_seq_fragment(c, f, self._fragment_span_x(f))
        # Composite-internal edges (v0.4.0) — after boxes, so they land in
        # the open interior between sibling child boxes.
        for e in self.edges:
            if getattr(e, '_nested_internal', False):
                draw_polyline(c, e.waypoints,
                              line_style=e.line_style,
                              source=e.source_style,
                              target=e.target_style,
                              label=e.label,
                              source_label=getattr(e, 'source_label', None),
                              target_label=getattr(e, 'target_label', None),
                              item_flow=getattr(e, 'item_flow', None),
                              item_position=getattr(e, 'item_position', 0.5),
                              used_labels=used_labels,
                              source_node=e.source,
                              target_node=e.target)
        fr = self._frame_rect()
        if fr is not None and self.frame is not None:
            draw_diagram_frame(c, fr[0], fr[1], fr[2], fr[3], self.frame.header)
        # parameter squares + labels AFTER the frame/edges: square
        # outlines straddle the border cleanly, text pixels win last
        for p in self.par_params:
            draw_par_param(c, p)
        return c.frame()

    def render_svg(self, routing='orthogonal', layer_gap=50, node_gap=12, margin=8, scale=1.5):
        self.layout(routing=routing, layer_gap=layer_gap, node_gap=node_gap, margin=margin)
        self._update_port_positions()
        self._place_frame_ports()
        self._place_par_params()

        # Compute bounds
        xs = [margin]
        ys = [margin]
        for n in self.nodes:
            xs.extend([n.x, n.x + n.w])
            ys.extend([n.y, n.y + n.h])
            for p in n.ports:
                xs.extend([p.x, p.x + p.w])
                ys.extend([p.y, p.y + p.h])
                # outside port labels extend beyond the port box — count
                # their estimated width so the canvas never clips them
                lab = getattr(p, 'label', '')
                if lab:
                    lw = len(lab) * 2 + 6
                    if p.side == 'right':
                        xs.append(p.x + p.w + lw)
                    elif p.side == 'left':
                        xs.append(p.x - lw)
                    elif p.side == 'bottom':
                        ys.append(p.y + p.h + 10)
                    elif p.side == 'top':
                        ys.append(p.y - 10)
                for i in p.interfaces:
                    ex1, ey1, ex2, ey2 = i.extent()
                    xs.extend([ex1, ex2])
                    ys.extend([ey1, ey2])
            for i in n.interfaces:
                ex1, ey1, ex2, ey2 = i.extent()
                xs.extend([ex1, ex2])
                ys.extend([ey1, ey2])
        for com in self.comments:
            xs.extend([com.x, com.x + com.w])
            ys.extend([com.y, com.y + com.h])
        for v in self.views:
            xs.extend([v.x, v.x + v.w])
            ys.extend([v.y, v.y + v.h])
        for p in self.frame_ports:
            xs.extend([p.x, p.x + p.w])
            ys.extend([p.y, p.y + p.h])
            lab = getattr(p, 'label', '')
            if lab:
                lw = len(lab) * 2 + 6
                if p.side == 'right':
                    xs.append(p.x + p.w + lw)
                elif p.side == 'left':
                    xs.append(p.x - lw)
                elif p.side == 'bottom':
                    ys.append(p.y + p.h + 10)
                elif p.side == 'top':
                    ys.append(p.y - 10)
            for i in p.interfaces:
                ex1, ey1, ex2, ey2 = i.extent()
                xs.extend([ex1, ex2])
                ys.extend([ey1, ey2])
        for a in self.activities:
            xs.extend([a.x, a.x + a.w])
            ys.extend([a.y, a.y + a.h])
        for e in self.edges:
            for px, py in e.waypoints:
                xs.append(px)
                ys.append(py)
        for li in self.lifelines:
            xs.extend([li.x - li.w / 2, li.x + li.w / 2])
            ys.extend([li.head_y - 6, li.head_y + li.h,
                       self._lifeline_tail_end(li)])
        for m in self.messages:
            if getattr(m, 'src', None) is None or getattr(m, 'dst', None) is None:
                # pad for the arrowhead ticks beyond a floating crop end
                xs.extend([m.x1 - 8, m.x2 + 8])
                ys.append(m.y)
        for f in self.fragments:
            lo, hi = self._fragment_span_x(f)
            xs.extend([lo, hi])
            ys.extend([f.y1, f.y2])
        for cc in self.constraints:
            lx = cc.lifeline.x + cc.dx
            xs.extend([lx - len(cc.text) - 2, lx + len(cc.text) + 2])
            ys.extend([cc.y, cc.y + (10 if cc.rounded else 0)])

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        fr = self._frame_rect()
        if fr is not None:
            min_x = min(min_x, fr[0])
            max_x = max(max_x, fr[2])
            min_y = min(min_y, fr[1])
            max_y = max(max_y, fr[3])

        # Placed frame ports, their outside labels and interface arcs
        # widen only the CANVAS — never the frame rectangle itself, or
        # the port would stop straddling the border (it sits on it).
        for p in self.frame_ports:
            if getattr(p, 'placed', False):
                min_x = min(min_x, p.x)
                max_x = max(max_x, p.x + p.w)
                min_y = min(min_y, p.y)
                max_y = max(max_y, p.y + p.h)
        # Placed parametric sockets/param labels widen only the canvas —
        # their legs already end near the border (never feed _frame_rect)
        for p in self.par_params:
            if getattr(p, 'placed', False):
                min_x = min(min_x, p.x - 2)
                max_x = max(max_x, p.x + p.w + 2)
                min_y = min(min_y, p.y - 12 if p.owner is None else p.y)
                max_y = max(max_y, p.y + p.h)
                lab = getattr(p, 'label', '')
                if lab:
                    lw = len(lab) * 2 + 6
                    if getattr(p, 'label_above', False):
                        min_y = min(min_y, p.y - 16)
                    elif p.side == 'right':
                        max_x = max(max_x, p.x + p.w + lw)
                    elif p.side == 'left':
                        min_x = min(min_x, p.x - lw)
                    elif p.side == 'bottom':
                        max_y = max(max_y, p.y + p.h + 10)
                    elif p.side == 'top':
                        min_y = min(min_y, p.y - 10)
                for i in p.interfaces:
                    ex1, ey1, ex2, ey2 = i.extent()
                    min_x = min(min_x, ex1)
                    max_x = max(max_x, ex2)
                    min_y = min(min_y, ey1)
                    max_y = max(max_y, ey2)
        # End-label text rows must never clip: count each stacked row's
        # extent (widest row × 2 units/char, anchor-aware) — the
        # {subsets ...} stacks of the v2 metamodel figures run wide
        for e in self.edges:
            for lab, is_src in ((getattr(e, 'source_label', None), True),
                                (getattr(e, 'target_label', None), False)):
                if not lab or len(e.waypoints) < 2:
                    continue
                spos, tpos = edge_end_label_positions(e.waypoints)
                pos = spos if is_src else tpos
                if pos is None:
                    continue
                rows = str(lab).split('\n')
                wr = max(len(r) for r in rows) * 2
                if e.waypoints[0][0] == e.waypoints[1][0]:
                    min_x = min(min_x, pos[0] - 2)
                    max_x = max(max_x, pos[0] + wr + 2)
                else:
                    min_x = min(min_x, pos[0] - wr)
                    max_x = max(max_x, pos[0] + wr)
                min_y = min(min_y, pos[1] - 4 - (len(rows) - 1) * 6)
                max_y = max(max_y, pos[1] + 4)
        # Canvas: stick-actor name labels hang BELOW the node box — count
        # them (the box is the figure only)
        for n in self.nodes:
            if getattr(n, 'is_stick_figure', False):
                max_y = max(max_y, n.y + n.h + 12)
                lab_ext = len(n.name)  # half on each side of cx
                min_x = min(min_x, n.x + n.w / 2 - lab_ext)
                max_x = max(max_x, n.x + n.w / 2 + lab_ext)
        pad = 10
        w = int((max_x - min_x + pad * 2) * scale)
        h = int((max_y - min_y + pad * 2) * scale)

        c = SvgCanvas(scale=scale)
        if fr is not None and self.frame is not None:
            svg_draw_frame(c, fr[0], fr[1], fr[2], fr[3], self.frame.header)

        # Build keep-away sets for label collision avoidance
        all_path_px = set()
        svg_used_labels = set()
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
        deferred_port_labels = []
        deferred_actor_labels = []

        def _svg_node_tree(node):
            if isinstance(node, UseCase):
                svg_usecase_node(c, node)
            elif isinstance(node, Actor) and node.is_stick_figure:
                svg_actor_stick(c, node)
                deferred_actor_labels.append(node)
            else:
                svg_draw_node(c, node)
                if getattr(node, 'rake', False):
                    svg_draw_rake(c, node.x + node.w - 2,
                                  node.y + node.h - 2)
            for p in node.ports:
                if isinstance(p, (EntryPoint, ExitPoint)):
                    svg_draw_entry_exit_point(c, p.cx, p.cy, PORT_W // 2, label=p.label, kind=getattr(p, 'kind', 'entry'))
                else:
                    svg_draw_port(c, p, with_label=False)
                    deferred_port_labels.append(p)
                for i in p.interfaces:
                    svg_draw_interface(c, i)
            for i in node.interfaces:
                svg_draw_interface(c, i)
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
                svg_draw_decision_node(c, a.cx, a.cy, a.size // 2, a.name,
                                       filled=getattr(a, 'filled', False))
            elif isinstance(a, HistoryPseudostate):
                svg_draw_history_node(c, a.cx, a.cy, a.r, deep=a.deep)
            elif isinstance(a, SendSignalNode):
                svg_draw_send_signal_node(c, a)
            elif isinstance(a, AcceptEventNode):
                svg_draw_accept_event_node(c, a)
            elif isinstance(a, WaitTimeNode):
                svg_draw_wait_time_node(c, a)
            for p in getattr(a, 'ports', []):
                svg_draw_port(c, p, with_label=False)
                if p.label:
                    svg_port_label(c, p)

        for n in self.nodes:
            if n in child_nodes:
                continue
            _svg_node_tree(n)
        for com in self.comments:
            svg_draw_comment(c, com)
        for v in self.views:
            if isinstance(v, Region):
                svg_draw_region_box(c, v)
            else:
                svg_draw_view(c, v)
            for child in v.children:
                svg_draw_node(c, child)
                for p in child.ports:
                    if isinstance(p, (EntryPoint, ExitPoint)):
                        svg_draw_entry_exit_point(c, p.cx, p.cy, PORT_W // 2, label=p.label, kind=getattr(p, 'kind', 'entry'))
                    else:
                        svg_draw_port(c, p, with_label=False)
                        deferred_port_labels.append(p)
                    for i in p.interfaces:
                        svg_draw_interface(c, i)
        # Parametric squares AFTER the nodes (squares sit on top of the
        # box interior, never buried) and BEFORE the edges (halos never
        # erase connector or border ink — Fig 9.3 rounds 1-2)
        for p in self.par_params:
            svg_par_param(c, p)
        # NOTE: port labels and frame ports are drawn AFTER the edges so
        # their halo labels erase the connector ink, not the reverse.
        for e in self.edges:
            if self._is_visual_containment(e):
                continue
            svg_draw_edge(c, e, keep_away=all_path_px - set(e.waypoints),
                          used_labels=svg_used_labels,
                          forbidden=[(n.x, n.y, n.w, n.h)
                                     for n in self.nodes])
        for p in self.frame_ports:
            for i in p.interfaces:
                svg_draw_interface(c, i)
        for p in self.frame_ports:
            svg_draw_port(c, p, with_label=False)
            deferred_port_labels.append(p)
        for p in deferred_port_labels:
            svg_port_label(c, p)
        # stick-actor names draw with halos AFTER the edges, so the
        # association lines into the figure never strike the text
        for a in deferred_actor_labels:
            c.add_label(a.x + a.w / 2.0, a.y + 19, a.name,
                        anchor='middle')
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
                svg_draw_decision_node(c, a.cx, a.cy, a.size // 2, a.name,
                                       filled=getattr(a, 'filled', False))
            elif isinstance(a, HistoryPseudostate):
                svg_draw_history_node(c, a.cx, a.cy, a.r, deep=a.deep)
            elif isinstance(a, SendSignalNode):
                svg_draw_send_signal_node(c, a)
            elif isinstance(a, AcceptEventNode):
                svg_draw_accept_event_node(c, a)
            elif isinstance(a, WaitTimeNode):
                svg_draw_wait_time_node(c, a)
            for p in getattr(a, 'ports', []):
                svg_draw_port(c, p, with_label=False)
                if p.label:
                    svg_port_label(c, p)
        # ── sequence diagram elements (§7.4–7.7) ──
        self._update_seq_geometry()
        for s in self.exec_specs:
            svg_seq_exec(c, s.lifeline.x, s.y1, s.y2, s.shaded,
                         width=SEQ_EXEC_W)
        for li in self.lifelines:
            svg_seq_head(c, li.x, li.head_y, li.label)
            c.add_polyline([(li.x, li.tail_start),
                            (li.x, self._lifeline_tail_end(li))], dashed=True)
        for m in self.messages:
            if m.src is m.dst:
                svg_seq_self_message(c, m.src.x, m.y, m.kind, m.label)
            else:
                svg_seq_message(c, m.x1, m.x2, m.y, m.kind, m.label)
        for x in self.destructions:
            svg_seq_destruction(c, x.lifeline.x, x.y)
        for cc in self.constraints:
            svg_seq_constraint(c, cc.lifeline, cc)
        for f in self.fragments:
            svg_seq_fragment(c, f, self._fragment_span_x(f))

        return c.output(width=w, height=h, padding=pad * scale,
                        origin=(min_x * scale, min_y * scale))
