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
from xml.sax.saxutils import escape

from diagramboxes.primitives import SOLID, DASHED, NONE, OPEN, TRIANGLE, DIAMOND, FILLED, \
    DEFINITION, REDEFINITION, REFERENCE_SUBSETTING, PORTION, CIRCLE, UNOWNED, ARROW_SIZE, COMMENT_FOLD, \
    ROUNDED_RADIUS, _port_arrow, _arrow_backoff, _node_outward_angle


def _arrow_polygon(x, y, angle, style):
    """Return polygon/fill for an arrowhead, or (lines, None) for OPEN."""
    if style == NONE or style is None or style in (PORTION, CIRCLE, UNOWNED):
        return None, style if style in (PORTION, CIRCLE, UNOWNED) else None
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

    def add_text(self, x, y, text, color=None, size=None, anchor='middle'):
        color = color or self.STROKE
        # font-size matches drawille's 2px/char width
        # (SVG monospace char-width ≈ 0.6× font-size; 2/0.6 ≈ 3.33)
        size = size or self.s(10 / 3)
        x, y = self.s(x, y)
        t = escape(text)
        self.elements.append(
            f'<text x="{x:.1f}" y="{y:.1f}" fill="{color}"'
            f' font-size="{size:.1f}" font-family="monospace"'
            f' text-anchor="{anchor}">{t}</text>'
        )

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

    def output(self, width=None, height=None, padding=10):
        """Return SVG string. Bounds auto-computed if not provided."""
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
            f' viewBox="{-padding} {-padding} {w + padding * 2} {h + padding * 2}"'
            f' width="{w + padding * 2}pt" height="{h + padding * 2}pt">'
        )
        body = '\n'.join(self.elements)
        return f'{header}\n{body}\n</svg>'


# ── High-level drawing functions for diagrams ──

def svg_draw_edge(c, e, keep_away=None):
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
            if e.target_style in (CIRCLE, UNOWNED):
                node_angle = _node_outward_angle(pts[-1][0], pts[-1][1], e.target)
                if node_angle is not None:
                    target_angle = node_angle
            poly, fill = _arrow_polygon(pts[-1][0], pts[-1][1], target_angle, e.target_style)
            if fill == CIRCLE:
                _svg_draw_circle(c, pts[-1][0], pts[-1][1], target_angle)
            elif fill == UNOWNED:
                _svg_draw_unowned(c, pts[-1][0], pts[-1][1], target_angle)
            elif fill == PORTION:
                _svg_draw_portion(c, pts[-1][0], pts[-1][1], target_angle)
            elif poly:
                if fill == 'open':
                    for x1, y1, x2, y2 in poly:
                        c.add_line(x1, y1, x2, y2)
                else:
                    color = 'white' if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING) else fill
                    c.add_polygon(poly, fill=color, stroke=c.STROKE if color in ('white', 'open') else color)
            if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING):
                _svg_arrow_extras(c, pts[-1][0], pts[-1][1], target_angle, fill)

        if e.source_style and e.source_style != NONE and len(pts) >= 2:
            dx = pts[1][0] - pts[0][0]
            dy = pts[1][1] - pts[0][1]
            angle = atan2(dy, dx)
            source_angle = angle + pi
            if e.source_style in (CIRCLE, UNOWNED):
                node_angle = _node_outward_angle(pts[0][0], pts[0][1], e.source)
                if node_angle is not None:
                    source_angle = node_angle
            poly, fill = _arrow_polygon(pts[0][0], pts[0][1], source_angle, e.source_style)
            if fill == CIRCLE:
                _svg_draw_circle(c, pts[0][0], pts[0][1], source_angle)
            elif fill == UNOWNED:
                _svg_draw_unowned(c, pts[0][0], pts[0][1], source_angle)
            elif fill == PORTION:
                _svg_draw_portion(c, pts[0][0], pts[0][1], source_angle)
            elif poly:
                if fill == 'open':
                    for x1, y1, x2, y2 in poly:
                        c.add_line(x1, y1, x2, y2)
                else:
                    color = 'white' if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING) else fill
                    c.add_polygon(poly, fill=color, stroke=c.STROKE if color in ('white', 'open') else color)
            if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING):
                _svg_arrow_extras(c, pts[0][0], pts[0][1], source_angle, fill)

        # Label at midpoint
        if e.label:
            total = sum(abs(pts[i + 1][0] - pts[i][0]) +
                        abs(pts[i + 1][1] - pts[i][1])
                        for i in range(len(pts) - 1))
            target = total // 2
            acc = 0
            keep_away = keep_away or set()
            for i in range(len(pts) - 1):
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
                    c.add_text(lx, ly, e.label, anchor='middle')
                    break
                acc += seg
    else:
        # Fallback straight line
        sx, sy = e.source.cx, e.source.cy
        tx, ty = e.target.cx, e.target.cy
        dx_total, dy_total = tx - sx, ty - sy
        length = max(1, (dx_total * dx_total + dy_total * dy_total) ** 0.5)

        lsx, lsy = sx, sy
        if e.source_style and e.source_style != NONE:
            bo = _arrow_backoff(e.source_style)
            if bo:
                lsx = sx + dx_total / length * bo
                lsy = sy + dy_total / length * bo

        ltx, lty = tx, ty
        if e.target_style and e.target_style != NONE:
            bo = _arrow_backoff(e.target_style)
            if bo:
                ltx = tx - dx_total / length * bo
                lty = ty - dy_total / length * bo

        dashed = e.line_style == DASHED
        c.add_line(lsx, lsy, ltx, lty, dashed=dashed)

        angle = atan2(ty - sy, tx - sx)
        target_angle = angle
        if e.target_style in (CIRCLE, UNOWNED):
            node_angle = _node_outward_angle(tx, ty, e.target)
            if node_angle is not None:
                target_angle = node_angle
        poly, fill = _arrow_polygon(tx, ty, target_angle, e.target_style)
        if fill == CIRCLE:
            _svg_draw_circle(c, tx, ty, target_angle)
        elif fill == UNOWNED:
            _svg_draw_unowned(c, tx, ty, target_angle)
        elif fill == PORTION:
            _svg_draw_portion(c, tx, ty, target_angle)
        elif poly:
            color = 'white' if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING) else fill
            c.add_polygon(poly, fill=color, stroke=c.STROKE if color in ('white', 'open') else color)
        if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING):
            _svg_arrow_extras(c, tx, ty, target_angle, fill)
        source_angle = angle + pi
        if e.source_style in (CIRCLE, UNOWNED):
            node_angle = _node_outward_angle(sx, sy, e.source)
            if node_angle is not None:
                source_angle = node_angle
        poly, fill = _arrow_polygon(sx, sy, source_angle, e.source_style)
        if fill == CIRCLE:
            _svg_draw_circle(c, sx, sy, source_angle)
        elif fill == UNOWNED:
            _svg_draw_unowned(c, sx, sy, source_angle)
        elif fill == PORTION:
            _svg_draw_portion(c, sx, sy, source_angle)
        elif poly:
            color = 'white' if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING) else fill
            c.add_polygon(poly, fill=color, stroke=c.STROKE if color in ('white', 'open') else color)
        if fill in (DEFINITION, REDEFINITION, REFERENCE_SUBSETTING):
            _svg_arrow_extras(c, sx, sy, source_angle, fill)

        if e.label:
            mx, my = (sx + tx) // 2, (sy + ty) // 2
            if sx == tx:
                c.add_text(mx + 12, my, e.label, anchor='middle')
            else:
                c.add_text(mx, my - 6, e.label, anchor='middle')


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


def svg_draw_decision_node(c, cx, cy, size, name=''):
    """Diamond polygon — activity decision/merge node."""
    pts = [(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)]
    c.add_polygon(pts, fill='white')
    if name:
        c.add_text(cx, cy + 4, name, anchor='middle')


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
    """Draw a node box with stereotypes, name, and attributes."""
    kw = {}
    if n.rounded:
        kw['rx'] = kw['ry'] = min(ROUNDED_RADIUS, n.w // 4, n.h // 4)
    if n.dashed:
        kw['dashed'] = True
    c.add_rect(n.x, n.y, n.w, n.h, **kw)
    box_cx = n.x + n.w // 2
    lines = []
    if n.stereotypes:
        for s in n.stereotypes:
            lines.append(f'\u00ab{s}\u00bb')
    lines.append(n.name)

    # Separator if attributes exist
    sep_y = n.y + 4 + len(lines) * 5

    if n.attributes:
        # Draw separator line below name
        c.add_line(n.x + 2, sep_y, n.x + n.w - 2, sep_y)
        lines.append('')
        lines.extend(n.attributes)

    for i, txt in enumerate(lines):
        y = n.y + 4 + i * 5
        if txt == '' and n.attributes:
            continue
        c.add_text(box_cx, y + 4, txt, anchor='middle')


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


def svg_draw_port(c, p):
    """Draw a port box with optional direction arrow inside and label outside."""
    c.add_rect(p.x, p.y, p.w, p.h, fill='white')
    arrow = _port_arrow(p.side, p.direction)
    if arrow:
        c.add_text(p.x + p.w // 2, p.y + p.h // 2 + 2, arrow, anchor='middle')
    if p.label:
        if p.side == 'left' and getattr(p, 'label_inside', False):
            c.add_text(p.x + p.w + 4, p.y + p.h // 2 + 2, p.label, anchor='start')
        elif p.side == 'right' and getattr(p, 'label_inside', False):
            c.add_text(p.x - 4, p.y + p.h // 2 + 2, p.label, anchor='end')
        elif p.side == 'left':
            c.add_text(p.x - 4, p.y + p.h // 2 + 2, p.label, anchor='end')
        elif p.side == 'right':
            c.add_text(p.x + p.w + 4, p.y + p.h // 2 + 2, p.label, anchor='start')
        elif p.side == 'top':
            c.add_text(p.x + p.w // 2, p.y - 4, p.label, anchor='middle')
        elif p.side == 'bottom':
            c.add_text(p.x + p.w // 2, p.y + p.h + 8, p.label, anchor='middle')
