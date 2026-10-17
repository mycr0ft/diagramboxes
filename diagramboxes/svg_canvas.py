"""SVG canvas — vector-graphics renderer for diagrams.

Provides a ``SvgCanvas`` builder class and three high-level drawing
functions (``svg_draw_edge``, ``svg_draw_node``, ``svg_draw_port``)
that mirror the structure of ``primitives.py`` but produce SVG 1.1 XML
instead of braille pixels.

Usage
-----
::

    c = SvgCanvas(scale=1.5)
    svg_draw_node(c, my_node)
    svg_draw_edge(c, my_edge)
    print(c.output())   # <svg xmlns=...>...</svg>

Coordinate system
-----------------
All input coordinates are in drawille pixel units (same as ``layout.py``
uses).  ``SvgCanvas.s()`` scales them by the ``scale`` factor so the
output is readable in a browser.  Default scale 1.5 gives reasonable
sizes for typical diagrams.

Arrowheads
----------
Filled/polygon arrowheads (TRIANGLE, DIAMOND, FILLED, DEFINITION,
REDEFINITION) are computed as ``<polygon>`` vectors via
``_arrow_polygon()``.  OPEN arrowheads are rendered as two ``<line>``
elements.  Arrow size matches ``ARROW_SIZE`` (7 px in diagram coords),
same as the braille renderer.

See also
--------
primitives.py  : drawille-based equivalent (terminal output)
layout.py      : Diagram.render_svg() calls these functions
"""

from math import atan2, cos, sin, pi

from diagramboxes.primitives import _orthogonal_departs
from xml.sax.saxutils import escape

# proportional font stack for SVG text (drawille-compatible char metrics
# ≈ 0.6× font-size, matching the 2px/char layout assumption)
FONT_FAMILY = 'Helvetica, DejaVu Sans, sans-serif'

from diagramboxes.primitives import SOLID, DASHED, NONE, OPEN, TRIANGLE, DIAMOND, FILLED, \
    DEFINITION, REDEFINITION, REFERENCE_SUBSETTING, PORTION, CIRCLE, UNOWNED, ARROW_SIZE, COMMENT_FOLD, \
    ROUNDED_RADIUS, _port_arrow, _arrow_backoff, _node_outward_angle, _class_box_sections, \
    edge_end_label_positions, route_point_at, clear_label_pos, \
    CIRCLED_PLUS, FOLDER_KINDS, _is_folder


def _arrow_polygon(x, y, angle, style) -> tuple:
    """Return polygon/fill for an arrowhead, or (lines, None) for OPEN."""
    if style == NONE or style is None or style in (PORTION, CIRCLE, UNOWNED, CIRCLED_PLUS):
        return None, style if style in (PORTION, CIRCLE, UNOWNED, CIRCLED_PLUS) else None
    size = ARROW_SIZE
    if style == OPEN:
        lines = []
        for sign in (-1, 1):
            a = angle + sign * 5 * pi / 6
            lines.append((x, y, x + cos(a) * size, y + sin(a) * size))
        return lines, 'open'
    if style == TRIANGLE:
        tip = (x, y)
        hp = angle + pi / 2
        hw = size * 0.4
        bx = x - cos(angle) * size
        by = y - sin(angle) * size
        pts = [
            tip,
            (bx + cos(hp) * hw, by + sin(hp) * hw),
            (bx - cos(hp) * hw, by - sin(hp) * hw),
        ]
        return pts, TRIANGLE
    elif style == DEFINITION or style == REDEFINITION or style == REFERENCE_SUBSETTING:
        # Same triangle polygon; extras drawn by _svg_arrow_extras
        hp = angle + pi / 2
        hw = size * 0.4
        bx = x - cos(angle) * size
        by = y - sin(angle) * size
        pts = [
            (x, y),
            (bx + cos(hp) * hw, by + sin(hp) * hw),
            (bx - cos(hp) * hw, by - sin(hp) * hw),
        ]
        return pts, style
    elif style == DIAMOND or style == FILLED:
        s = size * 0.7
        hp = angle + pi / 2
        hw = s * 0.5
        pts = [
            (x, y),                                           # tip
            (x - cos(angle) * s + cos(hp) * hw,
             y - sin(angle) * s + sin(hp) * hw),             # right wing
            (x - 2 * cos(angle) * s,
             y - 2 * sin(angle) * s),                         # back
            (x - cos(angle) * s - cos(hp) * hw,
             y - sin(angle) * s - sin(hp) * hw),             # left wing
        ]
        fill = 'black' if style == FILLED else 'white'
        return pts, fill


def _svg_draw_circle(c, x, y, angle):
    r = max(3, ARROW_SIZE * 0.5)
    cx = x - cos(angle) * r
    cy = y - sin(angle) * r
    c.add_circle(cx, cy, r, fill='none')
    h = r * 0.7
    for sign in (-1, 1):
        a = angle + sign * pi / 4
        c.add_line(cx, cy, cx + cos(a) * h, cy + sin(a) * h)
        c.add_line(cx, cy, cx + cos(a + pi) * h, cy + sin(a + pi) * h)


def _svg_draw_circled_plus(c, x, y, angle):
    """Crosshair namespace containment (SysML v1 §10.4): circled plus on
    the namespace end of a solid containment line."""
    r = max(3, ARROW_SIZE * 0.5)
    cx = x - cos(angle) * r
    cy = y - sin(angle) * r
    c.add_group({'class': 'crosshair'})
    c.add_circle(cx, cy, r, fill='none')
    c.add_line(cx - r, cy, cx + r, cy)
    c.add_line(cx, cy - r, cx, cy + r)
    c.close_group()


def _svg_draw_unowned(c, x, y, angle):
    """Open circle only — no cross — for unowned membership."""
    r = max(3, ARROW_SIZE * 0.5)
    cx = x - cos(angle) * r
    cy = y - sin(angle) * r
    c.add_circle(cx, cy, r, fill='none')


def _svg_draw_portion(c, x, y, angle):
    r = ARROW_SIZE * 0.6
    cx = x - cos(angle) * r
    cy = y - sin(angle) * r
    mouth_half = pi / 4
    start_a = angle + pi + mouth_half
    end_a = angle + pi - mouth_half
    sx = cx + r * cos(start_a)
    sy = cy + r * sin(start_a)
    ex = cx + r * cos(end_a)
    ey = cy + r * sin(end_a)
    scx, scy = c.s(cx, cy)
    ssx, ssy = c.s(sx, sy)
    sex, sey = c.s(ex, ey)
    sr = c.s(r)
    d = f"M {scx:.1f},{scy:.1f} L {ssx:.1f},{ssy:.1f} A {sr:.1f},{sr:.1f} 0 1 1 {sex:.1f},{sey:.1f} Z"
    c.elements.append(
        f'<path d="{d}" fill="{c.STROKE}" stroke="{c.STROKE}" />'
    )


def _svg_arrow_extras(c, x, y, angle, style):
    """Draw auxiliary elements for DEFINITION, REDEFINITION, or REFERENCE_SUBSETTING."""
    size = ARROW_SIZE
    if style == DEFINITION:
        d = size + 3
        cx = x - cos(angle) * d
        cy = y - sin(angle) * d
        hp = angle + pi / 2
        ox = cos(hp) * 4
        oy = sin(hp) * 4
        c.add_circle(round(cx + ox), round(cy + oy), r=1.5, fill=c.STROKE)
        c.add_circle(round(cx - ox), round(cy - oy), r=1.5, fill=c.STROKE)
    elif style == REDEFINITION:
        dist = size + 2
        bx = x - cos(angle) * dist
        by = y - sin(angle) * dist
        hp = angle + pi / 2
        hw = size * 0.4
        c.add_line(bx + cos(hp) * hw, by + sin(hp) * hw,
                   bx - cos(hp) * hw, by - sin(hp) * hw)
    elif style == REFERENCE_SUBSETTING:
        hp = angle + pi / 2
        ox = cos(hp) * 4
        oy = sin(hp) * 4
        for d in (size + 3, size + 8):
            cx = x - cos(angle) * d
            cy = y - sin(angle) * d
            c.add_circle(round(cx + ox), round(cy + oy), r=1.5, fill=c.STROKE)
            c.add_circle(round(cx - ox), round(cy - oy), r=1.5, fill=c.STROKE)


class SvgCanvas:
    """SVG drawing surface, producing an SVG string on output()."""

    # Colors
    STROKE = '#1a1a1a'
    FILL = '#f0f0f0'

    def __init__(self, scale=1.5):
        self.scale = scale
        self.elements = []
        self.stroke_width = 1.5

    def s(self, *args):
        """Scale one or more values by the canvas scale factor."""
        if len(args) == 1:
            return args[0] * self.scale
        return tuple(a * self.scale for a in args)

    def add_line(self, x1, y1, x2, y2, stroke=None, width=None, dashed=False):
        stroke = stroke or self.STROKE
        width = width or self.stroke_width
        x1, y1, x2, y2 = self.s(x1, y1, x2, y2)
        parts = [
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"',
            f' stroke="{stroke}" stroke-width="{width}" fill="none"',
        ]
        if dashed:
            parts.append(f' stroke-dasharray="{width * 6},{width * 4}"')
        parts.append(' />')
        self.elements.append(''.join(parts))

    def add_rect(self, x, y, w, h, fill=None, stroke=None, width=None, rx=None, ry=None, dashed=False):
        fill = fill or self.FILL
        stroke = stroke or self.STROKE
        width = width or self.stroke_width
        x, y, w, h = self.s(x, y, w, h)
        extras = ''
        if rx is not None:
            extras += f' rx="{self.s(rx):.1f}"'
        if ry is not None:
            extras += f' ry="{self.s(ry):.1f}"'
        if dashed:
            extras += f' stroke-dasharray="{width * 6},{width * 4}"'
        self.elements.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"'
            f'{extras} fill="{fill}" stroke="{stroke}" stroke-width="{width}" />'
        )

    def add_text(self, x, y, text, color=None, size=None, anchor='middle',
                 font_family=None, font_style=None, font_weight=None):
        color = color or self.STROKE
        # font-size matches drawille's 2px/char width
        # (proportional char-width ≈ 0.6× font-size; 2/0.6 ≈ 3.33)
        size = size or self.s(10 / 3)
        x, y = self.s(x, y)
        t = escape(text)
        fam = font_family or FONT_FAMILY
        style = f' font-style="{font_style}"' if font_style else ''
        weight = f' font-weight="{font_weight}"' if font_weight else ''
        self.elements.append(
            f'<text x="{x:.1f}" y="{y:.1f}" fill="{color}"'
            f' font-size="{size:.1f}" font-family="{fam}"{style}{weight}'
            f' text-anchor="{anchor}">{t}</text>'
        )

    def add_label(self, x, y, text, anchor='middle', italic=False):
        """Text with a white halo rectangle, for labels that sit near or
        on top of lines — the halo erases the line segment beneath the
        text (readability, Figure 3.1 review). Rendered as a <g> with
        the rect followed by the text."""
        size = 10 / 3                       # diagram units
        pad = 1.2
        self.add_group()
        w = len(text) * size * 0.6 + pad * 2
        h = size * 1.5 + pad
        if anchor == 'middle':
            rx = x - w / 2
        elif anchor == 'start':
            rx = x - pad
        else:
            rx = x - w + pad
        ry = y - size * 1.25
        # halo coords must be scaled like the text (s()) — unscaled halos
        # drift away from their text for content far from the origin
        # (Figure 4.6 vision review: labels unreadable, frame border
        # erased in the wrong spans)
        self.elements.append(
            f'<rect class="halo" x="{self.s(rx):.1f}" y="{self.s(ry):.1f}"'
            f' width="{self.s(w):.1f}" height="{self.s(h):.1f}" fill="white" />')
        self.add_text(x, y, text, size=self.s(size), anchor=anchor,
                      font_style='italic' if italic else None)
        self.close_group()

    def add_polygon(self, points, fill=None, stroke=None, width=None, dashed=False):
        fill = fill or 'black'
        stroke = stroke or self.STROKE
        width = width or self.stroke_width
        pts = ' '.join(f'{self.s(x):.1f},{self.s(y):.1f}' for x, y in points)
        extra = ''
        if dashed:
            extra = f' stroke-dasharray="{width * 6},{width * 4}"'
        self.elements.append(
            f'<polygon points="{pts}" fill="{fill}"'
            f' stroke="{stroke}" stroke-width="{width}"{extra} />'
        )

    def add_circle(self, x, y, r=1, fill=None, stroke=None):
        fill = fill or self.STROKE
        stroke = stroke or self.STROKE
        x, y = self.s(x, y)
        r = self.s(r)
        self.elements.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}"'
            f' fill="{fill}" stroke="{stroke}" />'
        )

    def add_ellipse(self, cx, cy, rx, ry, fill='white', stroke=None):
        stroke = stroke or self.STROKE
        self.elements.append(
            '<ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f"'
            ' fill="%s" stroke="%s" stroke-width="%g" />'
            % (self.s(cx), self.s(cy), self.s(rx), self.s(ry),
               fill, stroke, self.stroke_width))

    def add_polyline(self, points, stroke=None, width=None, dashed=False):
        stroke = stroke or self.STROKE
        width = width or self.stroke_width
        pts = ' '.join(f'{self.s(x):.1f},{self.s(y):.1f}' for x, y in points)
        parts = [f'<polyline points="{pts}"']
        parts.append(f' stroke="{stroke}" stroke-width="{width}" fill="none"')
        if dashed:
            parts.append(f' stroke-dasharray="{width * 6},{width * 4}"')
        parts.append(' />')
        self.elements.append(''.join(parts))

    def add_group(self, attrs=None):
        """Open a <g> element. Must be followed by close_group()."""
        attr_str = ''
        if attrs:
            attr_str = ' ' + ' '.join(f'{k}="{v}"' for k, v in attrs.items())
        self.elements.append(f'<g{attr_str}>')

    def close_group(self):
        self.elements.append('</g>')

    def output(self, width=None, height=None, padding=10.0, origin=(0.0, 0.0)):
        """Return SVG string. Bounds auto-computed if not provided.

        ``origin`` is the (x, y) of the content's top-left in output
        units; the viewBox is anchored one ``padding`` beyond it so
        content at negative coordinates is never clipped.
        """
        ox, oy = origin
        if width is not None and height is not None:
            w, h = width, height
        else:
            # Compute from element positions (crude: collect all coords)
            xs, ys = [], []
            for el in self.elements:
                import re
                for m in re.finditer(r'x1="([\d.-]+)"|x2="([\d.-]+)"|x="([\d.-]+)"'
                                     r'|cx="([\d.-]+)"|points="([\d.,\s-]+)"', el):
                    pass  # complex; just use large default
            # Simple fallback: use padding boundaries from last elements
            w = 800
            h = 600

        header = (
            f'<svg xmlns="http://www.w3.org/2000/svg"'
            f' viewBox="{ox - padding} {oy - padding} {w + padding * 2} {h + padding * 2}"'
            f' width="{w + padding * 2}pt" height="{h + padding * 2}pt">'
        )
        body = '\n'.join(self.elements)
        return f'{header}\n{body}\n</svg>'


# ── sequence diagram drawing (§7.4–7.7) ──

def svg_seq_head(c, x, top, label, width=None, head_h=12):
    """Lifeline head rectangle + name text."""
    w = width or (len(label) * 2 + 10)
    c.add_rect(x - w / 2, top, w, head_h, fill='white')
    c.add_text(x, top + head_h / 2 + 2, label, anchor='middle')


def svg_seq_destruction(c, x, y, r=4):
    """Destruction occurrence X."""
    c.add_line(x - r, y - r, x + r, y + r)
    c.add_line(x - r, y + r, x + r, y - r)


def svg_seq_exec(c, x, y1, y2, shaded=False, width=8):
    """Thin vertical execution-specification rectangle."""
    c.add_rect(x - width / 2, y1, width, y2 - y1,
               fill='#e8e8e8' if shaded else 'white')


def svg_seq_message(c, x1, x2, y, kind, label):
    """Message line + arrowhead + floating name label (halo)."""
    dashed = kind in ('reply', 'create', 'delete')
    c.add_line(x1, y, x2, y, dashed=dashed)
    a_angle = 0.0 if x2 >= x1 else pi
    # synchronous messages take a FILLED-IN TRIANGLE (§7.5.2); TRIANGLE
    # yields the hollow triangle polygon — fill it black
    poly, fill = _arrow_polygon(x2, y, a_angle,
                                TRIANGLE if kind == 'sync' else OPEN)
    lines = poly if isinstance(poly, (list, tuple)) else []
    if fill == 'open':
        for lx1, ly1, lx2, ly2 in lines:
            c.add_line(lx1, ly1, lx2, ly2)
    elif poly:
        fill_color = 'black' if kind == 'sync' else 'white'
        c.add_polygon(poly, fill=fill_color, stroke=c.STROKE)
    if label:
        c.add_label((x1 + x2) / 2, y - 4, label, anchor='middle')


def svg_seq_self_message(c, x, y, kind, label):
    """Self-message (§7.5): a small loop out and back, arrowhead landing
    back on the lifeline below the departure."""
    pts = [(x, y), (x + 30, y), (x + 30, y + 8), (x + 8, y + 8)]
    dashed = kind in ('reply', 'create', 'delete')
    c.add_polyline(pts, dashed=dashed)
    style = FILLED if kind == 'sync' else OPEN
    poly, fill = _arrow_polygon(x + 8, y + 8, pi, style)
    lines = poly if isinstance(poly, (list, tuple)) else []
    if fill == 'open':
        for lx1, ly1, lx2, ly2 in lines:
            c.add_line(lx1, ly1, lx2, ly2)
    elif poly:
        c.add_polygon(poly, fill='black' if fill == FILLED else fill,
                      stroke=c.STROKE)
    if label:
        c.add_label(x + 33, y + 3, label, anchor='start')


# ── combined fragments / interaction uses (§7.9–7.10) ──

def svg_par_param(c, p):
    """Constraint-parameter square (§9.6): a small square docked on the
    inside of its owner's boundary (or STRADDLING the frame border for
    frame-attached sockets, Fig 9.3). Drawn AFTER the nodes (squares on
    top of the box interior, not buried) and BEFORE the edges (halos
    never erase connector or border ink, vision round 2). Socket labels
    print with their baseline ON the square's top edge — just above the
    connector leg (the book's spacing)."""
    c.add_rect(p.x, p.y, p.w, p.h, fill='white')
    if p.owner is None and p.side in ('left', 'right'):
        # the book keeps socket labels INSIDE the frame, off the border
        # column, just above the connector leg — centered-on-border
        # halos wipe the border and the header band (Fig 9.3 round 3)
        if p.side == 'left':
            c.add_label(p.x + p.w + 2, p.y - 4, p.name, anchor='start')
        else:
            c.add_label(p.x - 2, p.y - 4, p.name, anchor='end')
        return
    ly = p.y + p.h / 2 + 2
    if p.side == 'right':
        c.add_label(p.x - 2, ly, p.name, anchor='end')
    else:
        c.add_label(p.x + p.w + 2, ly, p.name, anchor='start')


def svg_usecase_node(c, n):
    """Use case ellipse (§5.5, Figure 5.1) + the verb-phrase name
    centered inside."""
    cx = n.x + n.w / 2.0
    cy = n.y + n.h / 2.0
    c.add_group()
    c.add_ellipse(cx, cy, n.w / 2.0, n.h / 2.0)
    c.add_text(cx, cy + 2, n.name, anchor='middle')
    c.close_group()


def svg_actor_stick(c, n):
    """Actor stick figure (§5.7, Figure 5.1): head circle, body, arms,
    legs. The name does NOT draw here — association lines route to the
    figure after the nodes, so the label defers (with a halo) to after
    the edges (render_svg's deferred_actor_labels)."""
    cx = n.x + n.w / 2.0
    hy = n.y + 3.0
    c.add_group()
    c.add_circle(cx, hy + 1.0, 3.5, fill='white')
    c.add_polyline([(cx, hy + 4), (cx, hy + 11)])
    c.add_polyline([(cx - 6, hy + 7), (cx, hy + 5.5), (cx + 6, hy + 7)])
    c.add_polyline([(cx, hy + 11), (cx - 4.5, hy + 17)])
    c.add_polyline([(cx, hy + 11), (cx + 4.5, hy + 17)])
    c.close_group()


def svg_seq_fragment(c, f, span_x):
    """Rectangle over the participating lifelines (§7.9); a pentagon in
    the upper-left corner holds the interaction operator (+ range for
    loops). Interaction uses (operator 'ref') paint the rectangle
    opaque — the lifelines disappear behind it — and center the
    referenced interaction's name inside. Operand separator rows draw
    as dashed lines with that operand's guard below them."""
    lo, hi = span_x
    if f.is_ref:
        c.add_rect(lo, f.y1, hi - lo, f.y2 - f.y1, fill='white')
    else:
        # transparent: the fragment must NOT cover the enclosed messages
        # (the add_rect default gray fill blanked the interior)
        c.add_rect(lo, f.y1, hi - lo, f.y2 - f.y1, fill='none')
    pent = f.operator + ((' %s' % f.frag_range) if f.frag_range else '')
    pw = len(pent) * 2 + 6
    if f.guard:
        # guard label FIRST — the pentagon (drawn last) repaints its own
        # white fill over the halo's upper edge instead of the reverse
        g = '[%s]' % f.guard
        c.add_label(lo + 4, f.y1 + 9, g, anchor='start')
    for row, guard in f.operands:
        if guard:
            g = '[%s]' % guard
            c.add_label(lo + 4, row + 9, g, anchor='start')
    # the operator pentagon last: opaque, so overlapping halos can never
    # deface its border (vision round 3: guard halo bit the pentagon)
    c.add_polygon([
        (lo, f.y1), (lo + pw + 3, f.y1), (lo + pw, f.y1 + 3),
        (lo + pw, f.y1 + 7), (lo, f.y1 + 7),
    ], fill='white', stroke=c.STROKE)
    c.add_text(lo + 2, f.y1 + 6, pent, anchor='start')
    if f.is_ref and f.name:
        c.add_text((lo + hi) / 2, (f.y1 + f.y2) / 2 + 2, f.name,
                   anchor='middle')
    for row, guard in f.operands:
        c.add_line(lo, row, hi, row, dashed=True)


# ── sequence constraints / state invariants (§7.8) ──

def svg_seq_constraint(c, li, con):
    """Braced floating text (or a round-cornered state-notation box)."""
    x = li.x + con.dx
    if con.rounded:
        w = len(con.text) * 2 + 10
        c.add_rect(x - w / 2, con.y, w, 10, fill='white', rx=3, ry=3)
        c.add_text(x, con.y + 6, con.text, anchor='middle')
    else:
        c.add_label(x, con.y, '{%s}' % con.text, anchor='middle')


# ── High-level drawing functions for diagrams ──

def svg_draw_edge(c, e, keep_away=None, used_labels=None, forbidden=None):
    """Draw an edge (with or without waypoints) onto an SvgCanvas.
    
    keep_away : set of (x, y) tuples — points to avoid for label placement.
    """
    if len(e.waypoints) >= 2:
        pts = list(e.waypoints)
        dashed = e.line_style == DASHED

        # Build polyline points, shortened at arrowhead ends
        draw_pts = list(pts)
        if e.target_style and e.target_style != NONE:
            bo = _arrow_backoff(e.target_style)
            if bo:
                x1, y1 = draw_pts[-2]
                x2, y2 = draw_pts[-1]
                if x1 == x2:
                    draw_pts[-1] = (x2, y2 - bo if y2 > y1 else y2 + bo)
                else:
                    draw_pts[-1] = (x2 - bo if x2 > x1 else x2 + bo, y2)
        if e.source_style and e.source_style != NONE:
            bo = _arrow_backoff(e.source_style)
            if bo:
                x1, y1 = draw_pts[0]
                x2, y2 = draw_pts[1]
                if x1 == x2:
                    draw_pts[0] = (x1, y1 + bo if y2 > y1 else y1 - bo)
                else:
                    draw_pts[0] = (x1 + bo if x2 > x1 else x1 - bo, y1)

        c.add_polyline(draw_pts, dashed=dashed)

        # Arrowheads at the ends
        if e.target_style and e.target_style != NONE and len(pts) >= 2:
            dx = pts[-1][0] - pts[-2][0]
            dy = pts[-1][1] - pts[-2][1]
            angle = atan2(dy, dx)
            target_angle = angle
            if e.target_style in (CIRCLE, UNOWNED, CIRCLED_PLUS):
                node_angle = _node_outward_angle(pts[-1][0], pts[-1][1], e.target)
                if node_angle is not None:
                    target_angle = node_angle
            poly, fill = _arrow_polygon(pts[-1][0], pts[-1][1], target_angle, e.target_style)
            if fill == CIRCLE:
                _svg_draw_circle(c, pts[-1][0], pts[-1][1], target_angle)
            elif fill == UNOWNED:
                _svg_draw_unowned(c, pts[-1][0], pts[-1][1], target_angle)
            elif fill == CIRCLED_PLUS:
                _svg_draw_circled_plus(c, pts[-1][0], pts[-1][1], target_angle)
            elif fill == PORTION:
                _svg_draw_portion(c, pts[-1][0], pts[-1][1], target_angle)
            elif poly:
                if fill == 'open':
                    for x1, y1, x2, y2 in poly:
                        c.add_line(x1, y1, x2, y2)
                else:
                    color = 'white' if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING, TRIANGLE) else fill
                    c.add_polygon(poly, fill=color, stroke=c.STROKE if color in ('white', 'open') else color)
            if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING):
                _svg_arrow_extras(c, pts[-1][0], pts[-1][1], target_angle, fill)

        if e.source_style and e.source_style != NONE and len(pts) >= 2:
            dx = pts[1][0] - pts[0][0]
            dy = pts[1][1] - pts[0][1]
            angle = atan2(dy, dx)
            source_angle = angle + pi
            if e.source_style in (CIRCLE, UNOWNED, CIRCLED_PLUS):
                node_angle = _node_outward_angle(pts[0][0], pts[0][1], e.source)
                if node_angle is not None:
                    source_angle = node_angle
            poly, fill = _arrow_polygon(pts[0][0], pts[0][1], source_angle, e.source_style)
            if fill == CIRCLE:
                _svg_draw_circle(c, pts[0][0], pts[0][1], source_angle)
            elif fill == UNOWNED:
                _svg_draw_unowned(c, pts[0][0], pts[0][1], source_angle)
            elif fill == CIRCLED_PLUS:
                _svg_draw_circled_plus(c, pts[0][0], pts[0][1], source_angle)
            elif fill == PORTION:
                _svg_draw_portion(c, pts[0][0], pts[0][1], source_angle)
            elif poly:
                if fill == 'open':
                    for x1, y1, x2, y2 in poly:
                        c.add_line(x1, y1, x2, y2)
                else:
                    color = 'white' if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING, TRIANGLE) else fill
                    c.add_polygon(poly, fill=color, stroke=c.STROKE if color in ('white', 'open') else color)
            if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING):
                _svg_arrow_extras(c, pts[0][0], pts[0][1], source_angle, fill)

        # Label at midpoint
        if e.label:
            keep_away = keep_away or set()
            placed = False
            if len(pts) == 2:
                # STRAIGHT edge: geometric midpoint + a PERPENDICULAR
                # offset so the label hugs its line (a Manhattan-length
                # midpoint on a long diagonal drifts along the line,
                # and the axis-aligned keep-away cascade slides a fanned
                # family of labels into one distant band — the fig10_3
                # defect: five «import» labels all ~40 units high)
                x1, y1 = pts[0]
                x2, y2 = pts[1]
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                L = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** .5 or 1
                nx, ny = -(y2 - y1) / L, (x2 - x1) / L   # unit perpendicular
                cands = [(mx + nx * 9, my + ny * 9),
                         (mx - nx * 9, my - ny * 9),
                         (mx + nx * 18, my + ny * 18),
                         (mx - nx * 18, my - ny * 18)]
                for pos in cands:
                    if not any(abs(pos[0] - p[0]) < 12 and
                               abs(pos[1] - p[1]) < 12 for p in keep_away):
                        lx, ly = pos
                        placed = True
                        break
                if not placed:
                    lx, ly = cands[0]
                c.add_label(lx, ly, e.label, anchor='middle')
                if used_labels is not None:
                    used_labels.add((lx - len(e.label), ly, len(e.label) * 2))
            total = sum(abs(pts[i + 1][0] - pts[i][0]) +
                        abs(pts[i + 1][1] - pts[i][1])
                        for i in range(len(pts) - 1))
            target = total // 2
            acc = 0
            for i in range(len(pts) - 1) if not placed else ():
                x1, y1 = pts[i]
                x2, y2 = pts[i + 1]
                seg = abs(x2 - x1) + abs(y2 - y1)
                if acc + seg >= target:
                    rem = target - acc
                    if seg > 0:
                        if x1 == x2:
                            mx = x1
                            my = y1 + (rem if y2 > y1 else -rem)
                            lx, ly = mx + 12, my
                            offsets = [(0, 0), (0, -12), (-24, 0), (0, 8)]
                        else:
                            mx = x1 + (rem if x2 > x1 else -rem)
                            my = y1
                            lx, ly = mx, my - 6
                            offsets = [(0, 0), (12, 0), (0, -8), (-12, 0), (0, 8)]
                    else:
                        lx, ly = x1, y1 - 4
                        offsets = [(0, 0)]
                    for ox, oy in offsets:
                        pos = (lx + ox, ly + oy)
                        if not any(abs(pos[0] - p[0]) < 12 and abs(pos[1] - p[1]) < 12
                                   for p in keep_away):
                            lx, ly = pos
                            break
                    c.add_label(lx, ly, e.label, anchor='middle')
                    if used_labels is not None:
                        used_labels.add((lx - len(e.label), ly, len(e.label) * 2))
                    break
                acc += seg

        # Per-end labels (SysML v1 §3.5) — collision-aware placement;
        # '\n'-joined labels render as stacked halo rows (v2 metamodel)
        # and anchor OUTSIDE the endpoint so the stack never sits on the
        # box it names (Fig 15: the inward anchor erases the box's text)
        spos, tpos = edge_end_label_positions(pts)
        for lab, pos, vert, outward, endpoint in (
                (e.source_label, spos, pts[0][0] == pts[1][0],
                 (pts[0], pts[1]), e.source),
                (e.target_label, tpos, pts[-1][0] == pts[-2][0],
                 (pts[-1], pts[-2]), e.target)):
            if not lab or pos is None:
                continue
            rows = str(lab).split('\n')
            if len(rows) > 1:
                dx, dy = (outward[0][0] - outward[1][0],
                          outward[0][1] - outward[1][1])
                L = (dx * dx + dy * dy) ** 0.5 or 1
                pos = (pos[0] - dx / L * 22, pos[1] - dy / L * 22)
            elif endpoint is not None and getattr(endpoint, 'w', 0) > 0:
                # single-row label: an anchor landing inside the
                # endpoint's box prints ON the block (fig3_1: the
                # 'primaryComputer 1' collision with the Flight
                # Computer title) — push out through the nearest border
                nx, ny = endpoint.x, endpoint.y
                nw, nh = endpoint.w, endpoint.h
                lx, ly = pos
                if nx - 6 <= lx <= nx + nw + 6 and ny - 9 <= ly <= ny + nh + 9:
                    dists = ((lx - nx, -8 - (lx - nx), 0),
                             (nx + nw - lx, 8 + (nx + nw - lx), 0),
                             (ly - ny, 0, -9 - (ly - ny)),
                             (ny + nh - ly, 0, 9 + (ny + nh - ly)))
                    _, ox, oy = min(dists, key=lambda t: t[0])
                    pos = (lx + ox, ly + oy)

            def _place(p):
                return clear_label_pos(p, max(len(r) for r in rows),
                                       keep_away, used_labels,
                                       anchor='start' if vert else 'middle',
                                       forbidden=forbidden)
            pos = _place(pos)
            base = pos[1] - (len(rows) - 1) * 6
            for i, row in enumerate(rows):
                c.add_label(pos[0], base + i * 6, row,
                            anchor='start' if vert else 'middle')
                if used_labels is not None:
                    wrow = max(len(r) for r in rows)
                    used_labels.add((pos[0] if vert else pos[0] - wrow,
                                     base + i * 6, wrow * 2))

        # Item flow (SysML v1 §4.9): filled triangular arrowhead along the
        # connector with the item type as a halo label near it.  The halo
        # is drawn FIRST so it erases the connector but not the arrowhead.
        if getattr(e, 'item_flow', None):
            r = route_point_at(pts, getattr(e, 'item_position', 0.5))
            if r:
                fx, fy, fangle = r
                vx, vy = cos(fangle), sin(fangle)
                if abs(vx) > 0.7:   # horizontal → label upstream of the arrow
                    lx = fx - vx * (len(e.item_flow) * 2 + 10)
                    lx, ly = clear_label_pos((lx, fy), len(e.item_flow) * 2,
                                             keep_away, used_labels, anchor='middle')
                    c.add_label(lx, ly, e.item_flow, anchor='middle')
                else:               # vertical → label right of the arrow
                    lx, ly = clear_label_pos((fx + 2, fy), len(e.item_flow) * 2,
                                             keep_away, used_labels, anchor='start')
                    c.add_label(lx, ly, e.item_flow, anchor='start')
                size = ARROW_SIZE
                hp = fangle + pi / 2
                hw = size * 0.4
                bx, by = fx - cos(fangle) * size, fy - sin(fangle) * size
                c.add_polygon([
                    (fx, fy),
                    (bx + cos(hp) * hw, by + sin(hp) * hw),
                    (bx - cos(hp) * hw, by - sin(hp) * hw),
                ], fill='black')
    else:
        # Fallback straight line — anchored orthogonally: the edge
        # departs perpendicular to a side, runs the diagonal, arrives
        # perpendicular to a side (never slides out of a corner)
        (sx, sy), (xs, ys), (xt, yt), (tx, ty) = _orthogonal_departs(
            e.source, e.target)
        dx_total, dy_total = tx - xt, ty - yt
        length = max(1, (dx_total * dx_total + dy_total * dy_total) ** 0.5)

        lsx, lsy, ltx, lty = sx, sy, xt, yt
        if e.source_style and e.source_style != NONE:
            bo = _arrow_backoff(e.source_style)
            if bo:
                lsx = sx + (xs - sx) / 14.0 * bo
                lsy = sy + (ys - sy) / 14.0 * bo

        if e.target_style and e.target_style != NONE:
            bo = _arrow_backoff(e.target_style)
            if bo:
                ltx = xt - (xt - tx) / 14.0 * bo
                lty = yt - (yt - ty) / 14.0 * bo

        dashed = e.line_style == DASHED
        c.add_line(lsx, lsy, xs, ys, dashed=dashed)
        if (xs, ys) != (xt, yt):
            c.add_line(xs, ys, xt, yt, dashed=dashed)
        c.add_line(xt, yt, ltx, lty, dashed=dashed)

        angle = atan2(ty - yt, tx - xt)
        target_angle = angle
        if e.target_style in (CIRCLE, UNOWNED, CIRCLED_PLUS):
            node_angle = _node_outward_angle(tx, ty, e.target)
            if node_angle is not None:
                target_angle = node_angle
        poly, fill = _arrow_polygon(tx, ty, target_angle, e.target_style)
        if fill == CIRCLE:
            _svg_draw_circle(c, tx, ty, target_angle)
        elif fill == UNOWNED:
            _svg_draw_unowned(c, tx, ty, target_angle)
        elif fill == CIRCLED_PLUS:
            _svg_draw_circled_plus(c, tx, ty, target_angle)
        elif fill == PORTION:
            _svg_draw_portion(c, tx, ty, target_angle)
        elif poly:
            color = 'white' if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING, TRIANGLE) else fill
            c.add_polygon(poly, fill=color, stroke=c.STROKE if color in ('white', 'open') else color)
        if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING):
            _svg_arrow_extras(c, tx, ty, target_angle, fill)
        source_angle = angle + pi
        if e.source_style in (CIRCLE, UNOWNED, CIRCLED_PLUS):
            node_angle = _node_outward_angle(sx, sy, e.source)
            if node_angle is not None:
                source_angle = node_angle
        poly, fill = _arrow_polygon(sx, sy, source_angle, e.source_style)
        if fill == CIRCLE:
            _svg_draw_circle(c, sx, sy, source_angle)
        elif fill == UNOWNED:
            _svg_draw_unowned(c, sx, sy, source_angle)
        elif fill == CIRCLED_PLUS:
            _svg_draw_circled_plus(c, sx, sy, source_angle)
        elif fill == PORTION:
            _svg_draw_portion(c, sx, sy, source_angle)
        elif poly:
            color = 'white' if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING, TRIANGLE) else fill
            c.add_polygon(poly, fill=color, stroke=c.STROKE if color in ('white', 'open') else color)
        if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING):
            _svg_arrow_extras(c, sx, sy, source_angle, fill)

        if e.label:
            mx, my = (sx + tx) // 2, (sy + ty) // 2
            if sx == tx:
                c.add_label(mx + 12, my, e.label, anchor='middle')
            else:
                c.add_label(mx, my - 6, e.label, anchor='middle')
        if e.source_label or e.target_label:
            spos, tpos = edge_end_label_positions([(sx, sy), (tx, ty)])

            def _out_of_box(pos, endpoint):
                """Push an end-label anchor OUT of the endpoint's box
                (same rule as the routed path: the 'primaryComputer 1'
                collision — an anchor landing inside the box prints on
                the block's title)."""
                if (pos is None or endpoint is None
                        or getattr(endpoint, 'w', 0) <= 0):
                    return pos
                nx, ny = endpoint.x, endpoint.y
                nw, nh = endpoint.w, endpoint.h
                lx, ly = pos
                if nx - 6 <= lx <= nx + nw + 6 and ny - 9 <= ly <= ny + nh + 9:
                    dists = ((lx - nx, -8 - (lx - nx), 0),
                             (nx + nw - lx, 8 + (nx + nw - lx), 0),
                             (ly - ny, 0, -9 - (ly - ny)),
                             (ny + nh - ly, 0, 9 + (ny + nh - ly)))
                    _, ox, oy = min(dists, key=lambda t: t[0])
                    return (lx + ox, ly + oy)
                return pos

            spos = _out_of_box(spos, e.source)
            tpos = _out_of_box(tpos, e.target)
            if spos is not None and tpos is not None and (sx != tx or sy != ty):
                vert = sx == tx

                def _stacked(label, pos):
                    """Support '\n'-joined end labels (SysML v2 metamodel
                    figures stack '+/name', multiplicity, '{subsets ...}'
                    at one end): render as stacked halo rows anchored at
                    the same x; EVERY row registers a claim so later
                    labels cannot sit on the stack and erase it."""
                    rows = str(label).split('\n')
                    base = pos[1] - (len(rows) - 1) * 6
                    for i, row in enumerate(rows):
                        c.add_label(pos[0], base + i * 6, row,
                                    anchor='start' if vert else 'middle')
                    if used_labels is not None:
                        wrow = max(len(r) for r in rows)
                        for i in range(len(rows)):
                            used_labels.add((pos[0] if vert
                                             else pos[0] - wrow,
                                             base + i * 6, wrow * 2))

                def _clear(p, lab, vert_):
                    return clear_label_pos(p, len(str(lab)),
                                           keep_away, used_labels,
                                           anchor='start' if vert_
                                           else 'middle', forbidden=forbidden)
                if e.source_label:
                    _stacked(e.source_label, _clear(spos, e.source_label, vert))
                if e.target_label:
                    _stacked(e.target_label, _clear(tpos, e.target_label, vert))
        if getattr(e, 'item_flow', None):
            r = route_point_at([(sx, sy), (tx, ty)],
                               getattr(e, 'item_position', 0.5))
            if r:
                fx, fy, fangle = r
                vx = cos(fangle)
                if abs(vx) > 0.7:
                    lx = fx - vx * (len(e.item_flow) * 2 + 10)
                    lx, ly = clear_label_pos((lx, fy), len(e.item_flow) * 2,
                                             keep_away, used_labels)
                    c.add_label(lx, ly, e.item_flow, anchor='middle')
                else:
                    lx, ly = clear_label_pos((fx + 2, fy), len(e.item_flow) * 2,
                                             keep_away, used_labels)
                    c.add_label(lx, ly, e.item_flow, anchor='start')
                size = ARROW_SIZE
                hp = fangle + pi / 2
                hw = size * 0.4
                bx, by = fx - cos(fangle) * size, fy - sin(fangle) * size
                c.add_polygon([
                    (fx, fy),
                    (bx + cos(hp) * hw, by + sin(hp) * hw),
                    (bx - cos(hp) * hw, by - sin(hp) * hw),
                ], fill='black')


# ── activity node SVG drawing ──

def svg_draw_start_node(c, cx, cy, r):
    """Filled circle — activity start."""
    c.add_circle(cx, cy, r, fill=c.STROKE)


def svg_draw_done_node(c, cx, cy, r):
    """Bullseye (outer ring + inner filled) — activity done."""
    c.add_circle(cx, cy, r, fill='none')
    inner_r = max(2, r // 2)
    c.add_circle(cx, cy, inner_r, fill=c.STROKE)


def svg_draw_terminate_node(c, cx, cy, r):
    """Open circle with X — activity terminate."""
    c.add_circle(cx, cy, r, fill='none')
    h = r * 0.7
    for sign in (-1, 1):
        a = pi / 4 * sign
        c.add_line(cx, cy, cx + cos(a) * h, cy + sin(a) * h)
        c.add_line(cx, cy, cx + cos(a + pi) * h, cy + sin(a + pi) * h)


def svg_draw_fork_join_node(c, x1, y1, x2, y2):
    """Filled rectangle — activity fork/join synchronization bar."""
    c.add_rect(x1, y1, x2 - x1, y2 - y1, fill=c.STROKE)


def svg_draw_decision_node(c, cx, cy, size, name='', filled=False):
    """Diamond polygon — decision/merge (``filled``: the v2 start node)."""
    pts = [(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)]
    c.add_polygon(pts, fill='black' if filled else 'white')
    if name:
        c.add_text(cx, cy + 4, name, anchor='middle')


def svg_draw_send_signal_node(c, n):
    """Convex signpost pentagon — send signal action (§6.8.3)."""
    p = n.POINT
    pts = [(n.x, n.y), (n.x + n.w - p, n.y), (n.x + n.w, n.cy),
           (n.x + n.w - p, n.y + n.h), (n.x, n.y + n.h)]
    c.add_polygon(pts, fill='white')
    if n.name:
        c.add_text(n.x + 4, n.cy + 4, n.name, anchor='start')


def svg_draw_accept_event_node(c, n):
    """Concave pentagon (notched arrival side) — accept event action
    (§6.8.4)."""
    q = n.NOTCH
    pts = [(n.x, n.y), (n.x + n.w, n.y), (n.x + n.w, n.y + n.h),
           (n.x, n.y + n.h), (n.x + q, n.cy)]
    c.add_polygon(pts, fill='white')
    if n.name:
        c.add_text(n.x + q + 3, n.cy + 4, n.name, anchor='start')


def svg_draw_wait_time_node(c, n):
    """Hourglass (two triangles) + the time expression beneath — wait
    time action (§6.8.5)."""
    gh = n.glyph_h
    cx = n.x + n.w // 2
    mid = n.y + gh // 2
    bot = n.y + gh
    c.add_polygon([(n.x, n.y), (n.x + n.w, n.y), (cx, mid)], fill='white')
    c.add_polygon([(cx, mid), (n.x, bot), (n.x + n.w, bot)], fill='white')
    # waist crossbar
    c.add_line(cx - 2, mid, cx + 2, mid)
    if n.name:
        c.add_text(cx, bot + 7, n.name, anchor='middle')


def svg_draw_rake(c, x1, y1):
    """Call behavior rake glyph (§6.8.2): two short parallel diagonals
    in the lower-right corner; drawn AFTER the node's rect so the halo
    rule never bites."""
    for dx in (0, 3):
        c.add_line(x1 - 8 + dx, y1, x1 - 4 + dx, y1 - 7)
        c.add_line(x1 - 8 + dx, y1 - 1, x1 - 4 + dx, y1 - 8)


def svg_draw_region_box(c, r):
    """State-machine region (§8.7): dashed rectangle, name floating
    inside the top-right corner."""
    x1, y1, x2, y2 = r.x, r.y, r.x + r.w, r.y + r.h
    c.add_polygon([(x1, y1), (x2, y1), (x2, y2), (x1, y2)],
                  fill='white', dashed=True)
    if r.name:
        c.add_text(x2 - 2 - len(r.name) * 2, y1 + 10, r.name)


def svg_draw_history_node(c, cx, cy, r, deep=False):
    """Shallow- or deep-history pseudostate.

    Shallow history shows ``H`` inside an open circle; deep history shows
    ``H*``.  Drawn as a ring with the label centred inside it.
    """
    c.add_circle(cx, cy, r, fill='white')
    label = 'H*' if deep else 'H'
    c.add_text(cx, cy + 4, label, anchor='middle')


def svg_draw_entry_exit_point(c, cx, cy, r, label=None, kind='entry'):
    """Entry/exit point — hollow circle (optionally labelled)."""
    c.add_circle(cx, cy, r, fill='white')
    if label:
        c.add_text(cx, cy + r + 8, label, anchor='middle')


def svg_draw_node(c, n):
    """Draw a node box with stereotypes, name, and compartments."""
    chamfer = getattr(n, 'chamfer', 0)
    if chamfer:
        # 45-degree chamfered octagon — the v2 action usage shape
        ch = min(chamfer, n.w // 4, n.h // 4)
        pts = [(n.x + ch, n.y), (n.x + n.w - ch, n.y),
               (n.x + n.w, n.y + ch), (n.x + n.w, n.y + n.h - ch),
               (n.x + n.w - ch, n.y + n.h), (n.x + ch, n.y + n.h),
               (n.x, n.y + n.h - ch), (n.x, n.y + ch)]
        c.add_polygon(pts, **({'dashed': True} if n.dashed
                              else {'fill': 'white'}))
    else:
        kw = {}
        if n.rounded:
            kw['rx'] = kw['ry'] = min(ROUNDED_RADIUS, n.w // 4, n.h // 4)
        if n.dashed:
            kw['dashed'] = True
        c.add_rect(n.x, n.y, n.w, n.h, **kw)
    if getattr(n, 'cube', False):
        # UML 2.5.1 ch19 Node: perspective-view cube facets (§19.2.4)
        dx, dy = 7, 6
        c.add_group({'class': 'nodecube'})
        c.add_polyline([(n.x, n.y), (n.x + dx, n.y - dy),
                        (n.x + n.w + dx, n.y - dy),
                        (n.x + n.w + dx, n.y + n.h - dy)])
        c.add_polyline([(n.x + n.w + dx, n.y + n.h - dy), (n.x + n.w, n.y + n.h)])
        c.add_polyline([(n.x + n.w, n.y), (n.x + n.w + dx, n.y - dy)])
        c.close_group()
    if _is_folder(getattr(n, 'stereotypes', None)):
        # Package folder tab (§10.4): rectangle on the upper-left side
        tw = min(10, n.w // 4) if n.w > 26 else max(4, n.w // 4)
        c.add_group({'class': 'pkg-tab'})
        c.add_polyline([(n.x, n.y - 3), (n.x + tw, n.y - 3), (n.x + tw, n.y)])
        c.close_group()
    box_cx = n.x + n.w // 2
    sections = _class_box_sections(getattr(n, 'stereotypes', None), n.name,
                                   getattr(n, 'attributes', None),
                                   getattr(n, 'compartments', None))
    for i, (kind, txt) in enumerate(sections):
        y = n.y + 4 + i * 5
        if kind == 'sep':
            c.add_line(n.x + 2, y, n.x + n.w - 2, y)
        elif kind == 'title':
            # compartment titles are italic titles (§3.4, Figure 3.1)
            c.add_text(box_cx, y + 4, txt, anchor='middle', font_style='italic')
        else:
            c.add_text(box_cx, y + 4, txt, anchor='middle')


def svg_draw_frame(c, x1, y1, x2, y2, header):
    """Enclosing SysML v1 diagram-kind frame: plain border rectangle with
    a dog-eared headline tag holding the header string at the top-left
    (Delligatti §2.4/§3.3). SVG-only nicety — the braille renderer keeps
    the header strip."""
    c.add_rect(x1, y1, x2 - x1, y2 - y1)
    if header:
        fold = min(4, (x2 - x1) / 8)
        tag_h = 10
        # the headline band runs to the book's ~94% of the frame width
        # with the dog-leg cut at its far-right end (Fig 9.3)
        tag_w = (x2 - x1) * 0.94
        pts = [
            (x1, y1),
            (x1 + tag_w - fold, y1),
            (x1 + tag_w, y1 + fold),
            (x1 + tag_w, y1 + tag_h),
            (x1, y1 + tag_h),
        ]
        c.add_group()
        c.add_polygon(pts, fill='white')
        c.add_text(x1 + 3, y1 + 7, header, anchor='start')
        c.close_group()


def svg_draw_interface(c, iface):
    """UML interface symbol in SVG (§3.4.1.5): provided = stick + filled
    ball (lollipop); required = stick + open semicircle (socket, drawn as
    a class="arc" polyline); name as a halo label near the symbol."""
    sx, sy = iface.face
    OUT = {'right': (1, 0), 'left': (-1, 0), 'top': (0, -1), 'bottom': (0, 1)}
    dx, dy = OUT[iface.side]
    cx, cy = iface.center()
    c.add_line(sx, sy, cx, cy)
    r = 3
    if iface.kind == 'provided':
        c.add_circle(cx, cy, r, fill='black')
    else:
        px, py = -dy, dx
        pts = [(cx + dx * cos(a) * r + px * sin(a) * r,
                cy + dy * cos(a) * r + py * sin(a) * r)
               for a in (-pi / 2 + t / 8 * pi for t in range(9))]
        pts_svg = ' '.join('%.1f,%.1f' % (c.s(x), c.s(y)) for x, y in pts)
        c.elements.append(
            '<polyline class="arc" points="%s" stroke="%s"'
            ' stroke-width="%s" fill="none" />'
            % (pts_svg, c.STROKE, c.stroke_width))
    if iface.name:
        if dx:
            nx = cx + dx * (r + 2)
            c.add_label(nx, cy, iface.name, anchor='start')
        else:
            c.add_label(cx + 2, cy - dy * (r + 4), iface.name, anchor='start')


def svg_draw_comment(c, com):
    fold = min(COMMENT_FOLD, com.w // 3, com.h // 3)
    x1, y1 = com.x, com.y
    x2, y2 = com.x + com.w, com.y + com.h
    pts = [
        (x1, y1),
        (x2 - fold, y1),
        (x2, y1 + fold),
        (x2, y2),
        (x1, y2),
    ]
    c.add_polygon(pts, fill='white')
    c.add_text(com.x + com.w // 2, com.y + com.h // 2 + 2, com.text, anchor='middle')


def svg_draw_view(c, v):
    tw = []
    if v.stereotypes:
        tw.extend(len(f'\u00ab{s}\u00bb') for s in v.stereotypes)
    tw.append(len(v.name))
    max_tw = max(tw) if tw else 0
    tab_w = min(max_tw * 2 + 6, v.w)
    n_lines = 1 + (len(v.stereotypes) if v.stereotypes else 0)
    tab_h = n_lines * 5 + 4

    x1, y1 = v.x, v.y
    x2, y2 = v.x + v.w, v.y + v.h
    pts = [
        (x1, y1),
        (x1 + tab_w, y1),
        (x1 + tab_w, y1 + tab_h),
        (x2, y1 + tab_h),
        (x2, y2),
        (x1, y2),
    ]
    c.add_polygon(pts, fill='white', dashed=v.dashed)

    lines = []
    if v.stereotypes:
        for s in v.stereotypes:
            lines.append(f'\u00ab{s}\u00bb')
    lines.append(v.name)
    for i, txt in enumerate(lines):
        y = y1 + 2 + i * 5
        c.add_text(x1 + tab_w // 2, y + 4, txt, anchor='middle')

    if v.attributes:
        sep_y = y1 + tab_h + 2
        c.add_line(x1 + 2, sep_y, x2 - 2, sep_y)
        for i, attr in enumerate(v.attributes):
            y = sep_y + 2 + i * 5
            c.add_text((x1 + x2) // 2, y + 4, attr, anchor='middle')


def svg_draw_port(c, p, with_label=True):
    """Draw a port box with optional direction arrow inside. Labels are
    halo-backed and drawn via ``svg_port_label`` (frame ports flip their
    label to the frame's interior side); layout defers them until after
    the edges so the halo erases connector ink, not the reverse."""
    c.add_rect(p.x, p.y, p.w, p.h, fill='white')
    arrow = _port_arrow(p.side, p.direction)
    if arrow:
        c.add_text(p.x + p.w // 2, p.y + p.h // 2 + 2, arrow, anchor='middle')
    if with_label:
        svg_port_label(c, p)


def svg_port_label(c, p):
    """Halo-backed port label; frame ports flip to the interior side.
    ``label_above`` ports (book convention, Figure 4.6) print the label
    above the port box so it never sits on the connector's row."""
    if not getattr(p, 'label', None):
        return
    if getattr(p, 'label_above', False):
        c.add_label(p.x + p.w // 2, p.y - 8, p.label, anchor='middle')
        return
    side = p.side
    if getattr(p, 'is_frame_port', False):
        side = {'left': 'right', 'right': 'left',
                'top': 'bottom', 'bottom': 'top'}[side]
    if side == 'left' and getattr(p, 'label_inside', False):
        c.add_label(p.x + p.w + 4, p.y + p.h // 2 + 2, p.label, anchor='start')
    elif side == 'right' and getattr(p, 'label_inside', False):
        c.add_label(p.x - 4, p.y + p.h // 2 + 2, p.label, anchor='end')
    elif side == 'left':
        c.add_label(p.x - 4, p.y + p.h // 2 + 2, p.label, anchor='end')
    elif side == 'right':
        c.add_label(p.x + p.w + 4, p.y + p.h // 2 + 2, p.label, anchor='start')
    elif side == 'top':
        c.add_label(p.x + p.w // 2, p.y - 4, p.label, anchor='middle')
    elif side == 'bottom':
        c.add_label(p.x + p.w // 2, p.y + p.h + 8, p.label, anchor='middle')
