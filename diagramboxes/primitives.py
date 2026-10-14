"""Terminal rendering primitives — drawille braille output.

All drawing functions in this module take a ``drawille.Canvas`` and draw
directly to its pixel grid using Bresenham line iteration.  Coordinate
system: drawille pixel units (1 braille char = 2×4 px).  Text is placed
via ``set_text(pixel_x, pixel_y, text)`` which converts to character
rows/columns via ``x // 2, y // 4``.

Arrowhead styles:  OPEN (>), TRIANGLE (triangle), DIAMOND (diamond),
FILLED (filled diamond), DEFINITION (triangle + two trailing dots),
REDEFINITION (triangle + trailing bar).  Line styles: SOLID, DASHED.

Label collision avoidance in ``draw_polyline`` uses a spiral offset
search against a ``used_labels`` shared set.

See also
--------
svg_canvas.py : equivalent SVG vector renderer
layout.py     : Diagram / Node / Edge classes that call these primitives
"""

from math import atan2, cos, sin, pi
from drawille import Canvas, line

# ── constants ──
NONE = 'none'
OPEN = 'open'
TRIANGLE = 'triangle'
DIAMOND = 'diamond'
FILLED = 'filled'
DEFINITION = 'definition'
REDEFINITION = 'redefinition'
REFERENCE_SUBSETTING = 'reference_subsetting'
PORTION = 'portion'
CIRCLE = 'circle'
UNOWNED = 'unowned'
CIRCLED_PLUS = 'circled_plus'
SOLID = 'solid'
DASHED = 'dashed'

# Package-symbol kinds (SysML v1 §10): folder symbol with the tab
FOLDER_KINDS = ('package', 'model', 'modelLibrary', 'profile', 'view')


def _is_folder(stereotypes):
    return any(k in FOLDER_KINDS for k in (stereotypes or ()))

ARROW_SIZE = 7


def _arrow_backoff(style):
    """Pixels to shorten the edge line so it stops at the arrowhead base."""
    if style is None or style == NONE or style == FILLED:
        return 0
    if style == CIRCLE or style == UNOWNED or style == CIRCLED_PLUS:
        # The circle sits tangent to the node boundary (see _draw_circle),
        # so the limb — not the centre — touches the border.  The edge line
        # therefore should reach the boundary: no backoff is needed.
        return 0
    if style == DIAMOND:
        return round(ARROW_SIZE * 0.7 * 2)
    if style == PORTION:
        return round(ARROW_SIZE * 0.6)
    return ARROW_SIZE


def _node_outward_angle(tip_x, tip_y, node):
    """Return the angle pointing INTO the nearest side of *node*.

    The angle convention matches :func:`_draw_circle`: the centre is placed
    at ``x - cos(angle)*r`` *away* from the angle, i.e. on the side opposite
    to ``angle``.  By making ``angle`` point into the node, the resulting
    centre sits outside the node — the whole circle is tangent to the
    boundary and only the limb touches it, regardless of the edge's own
    axis.  Crucial for orthogonal routes whose terminal segment runs
    parallel to the boundary (degenerate case) where the edge axis would
    otherwise push half the circle inside the node.
    """
    if node is None:
        return None
    nx1, ny1 = node.x, node.y
    nx2, ny2 = node.x + node.w, node.y + node.h
    d_top = abs(tip_y - ny1)
    d_bottom = abs(tip_y - ny2)
    d_left = abs(tip_x - nx1)
    d_right = abs(tip_x - nx2)
    min_d = min(d_top, d_bottom, d_left, d_right)
    if min_d == d_top:
        return pi / 2          # node is below the tip → centre offset upward (out)
    if min_d == d_bottom:
        return -pi / 2         # node is above the tip → centre offset downward
    if min_d == d_left:
        return 0.0             # node is right of the tip → centre offset leftward
    return pi                  # node is left of the tip → centre offset rightward


# ── arrowhead drawing ──

def _draw_open(c, x, y, angle, size):
    for sign in (-1, 1):
        a = angle + sign * 5 * pi / 6
        for px, py in line(x, y, x + cos(a) * size, y + sin(a) * size):
            c.set(px, py)


def _draw_triangle(c, x, y, angle, size):
    hp = angle + pi / 2
    hw = size * 0.4
    bx = x - cos(angle) * size
    by = y - sin(angle) * size
    for px, py in line(x, y, bx + cos(hp) * hw, by + sin(hp) * hw): c.set(px, py)
    for px, py in line(x, y, bx - cos(hp) * hw, by - sin(hp) * hw): c.set(px, py)
    for px, py in line(bx + cos(hp) * hw, by + sin(hp) * hw, bx - cos(hp) * hw, by - sin(hp) * hw): c.set(px, py)


def _draw_diamond(c, x, y, angle, size, fill=False):
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
    for i in range(4):
        for px, py in line(*pts[i], *pts[(i + 1) % 4]): c.set(px, py)
    if fill:
        xs = [int(p[0]) for p in pts]
        ys = [int(p[1]) for p in pts]
        for fx in range(min(xs), max(xs) + 1):
            for fy in range(min(ys), max(ys) + 1):
                inside = False
                j = 3
                for i in range(4):
                    xi, yi = pts[i]
                    xj, yj = pts[j]
                    if ((yi > fy) != (yj > fy)) and fx < (xj - xi) * (fy - yi) / (yj - yi) + xi:
                        inside = not inside
                    j = i
                if inside:
                    c.set(fx, fy)


def _draw_definition(c, x, y, angle, size):
    _draw_triangle(c, x, y, angle, size)
    hp = angle + pi / 2
    d = size + 3
    cx = round(x - cos(angle) * d)
    cy = round(y - sin(angle) * d)
    ox = round(cos(hp)) * 4
    oy = round(sin(hp)) * 4
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            c.set(cx + ox + dx, cy + oy + dy)
            c.set(cx - ox + dx, cy - oy + dy)


def _draw_redefinition(c, x, y, angle, size):
    _draw_triangle(c, x, y, angle, size)
    dist = size + 2
    bx = x - cos(angle) * dist
    by = y - sin(angle) * dist
    hp = angle + pi / 2
    hw = size * 0.4
    for px, py in line(bx + cos(hp) * hw, by + sin(hp) * hw,
                       bx - cos(hp) * hw, by - sin(hp) * hw):
        c.set(px, py)


def _draw_reference_subsetting(c, x, y, angle, size):
    _draw_triangle(c, x, y, angle, size)
    hp = angle + pi / 2
    ox = round(cos(hp)) * 4
    oy = round(sin(hp)) * 4
    for d in (size + 3, size + 8):
        cx = round(x - cos(angle) * d)
        cy = round(y - sin(angle) * d)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                c.set(cx + ox + dx, cy + oy + dy)
                c.set(cx - ox + dx, cy - oy + dy)


def _draw_circle(c, x, y, angle, size):
    r = max(3, round(size * 0.5))
    cx = round(x - cos(angle) * r)
    cy = round(y - sin(angle) * r)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            d = round((dx*dx + dy*dy) ** 0.5)
            if d == r:
                c.set(cx + dx, cy + dy)
    h = r * 0.7
    for sign in (-1, 1):
        a = angle + sign * pi / 4
        for px, py in line(cx, cy, cx + cos(a) * h, cy + sin(a) * h):
            c.set(px, py)
    for sign in (-1, 1):
        a = angle + sign * pi / 4 + pi
        for px, py in line(cx, cy, cx + cos(a) * h, cy + sin(a) * h):
            c.set(px, py)


def _draw_circled_plus(c, x, y, angle, size):
    """Crosshair namespace containment (SysML v1 §10.4): a circled plus
    on the namespace end of a solid containment line."""
    r = max(3, round(size * 0.5))
    cx = round(x - cos(angle) * r)
    cy = round(y - sin(angle) * r)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            d = round((dx*dx + dy*dy) ** 0.5)
            if d == r:
                c.set(cx + dx, cy + dy)
    for px, py in line(cx - r, cy, cx + r, cy):
        c.set(px, py)
    for px, py in line(cx, cy - r, cx, cy + r):
        c.set(px, py)


def _draw_unowned(c, x, y, angle, size):
    """Open circle (no cross) — unowned membership."""
    r = max(3, round(size * 0.5))
    cx = round(x - cos(angle) * r)
    cy = round(y - sin(angle) * r)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            d = round((dx*dx + dy*dy) ** 0.5)
            if d == r:
                c.set(cx + dx, cy + dy)


def _draw_portion(c, x, y, angle, size):
    r = round(size * 0.6)
    cx = round(x - cos(angle) * r)
    cy = round(y - sin(angle) * r)
    mouth_half = pi / 4
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy > r * r:
                continue
            pa = atan2(dy, dx)
            diff = ((pa - (angle + pi) + pi) % (2 * pi)) - pi
            if abs(diff) > mouth_half:
                c.set(cx + dx, cy + dy)


_ARROW_DRAWERS = {
    OPEN: _draw_open,
    TRIANGLE: _draw_triangle,
    DIAMOND: lambda c, x, y, a, s: _draw_diamond(c, x, y, a, s, False),
    FILLED: lambda c, x, y, a, s: _draw_diamond(c, x, y, a, s, True),
    DEFINITION: _draw_definition,
    REDEFINITION: _draw_redefinition,
    REFERENCE_SUBSETTING: _draw_reference_subsetting,
    PORTION: _draw_portion,
    CIRCLE: _draw_circle,
    UNOWNED: _draw_unowned,
    CIRCLED_PLUS: _draw_circled_plus,
}


# ── line drawing ──

def draw_line(c, x1, y1, x2, y2, style=SOLID):
    """Draw a single line segment on a drawille Canvas.

    Parameters
    ----------
    c : drawille.Canvas
        Target canvas.
    x1, y1, x2, y2 : int
        Endpoint coordinates (pixel units).
    style : {'solid', 'dashed'}
        ``SOLID`` draws every pixel.  ``DASHED`` draws 5 of every 8 pixels.
    """
    if style == DASHED:
        pts = list(line(x1, y1, x2, y2))
        for i, (px, py) in enumerate(pts):
            if i % 8 < 5:
                c.set(px, py)
    else:
        for px, py in line(x1, y1, x2, y2):
            c.set(px, py)


def draw_arrowhead(c, x, y, angle, style):
    """Draw an arrowhead at position (x, y) pointing in the given direction.

    Parameters
    ----------
    c : drawille.Canvas
    x, y : int
        Tip position (pixels).
    angle : float
        Direction angle in radians.
    style : str or None
        Arrowhead style: ``OPEN``, ``TRIANGLE``, ``DIAMOND``, ``FILLED``,
        ``NONE``, or ``None`` (no arrowhead drawn).
    """
    if style and style in _ARROW_DRAWERS:
        _ARROW_DRAWERS[style](c, x, y, angle, ARROW_SIZE)


# ── straight-line relation (one segment) ──

def edge_end_label_positions(points, keep_away=None, used_labels=None):
    """Anchor positions for the source-end and target-end labels of an
    edge routed through ``points`` — ((sx, sy), (tx, ty)) or ``(None, None)``
    for routes with fewer than two points.

    The label anchor sits 12 px along the first/last segment from the
    endpoint, offset 6 px right of a vertical segment or 5 px above a
    horizontal one (SysML v1 end-notation, §3.5).
    """
    pts = list(points)
    if len(pts) < 2:
        return None, None

    def _near(pos, nxt, k=12):
        x1, y1 = pos
        x2, y2 = nxt
        if x1 == x2:
            return (x1 + 6, y1 + (k if y2 > y1 else -k))
        return (x1 + (k if x2 > x1 else -k), y1 - 5)

    spos = _near(pts[0], pts[1])
    tpos = _near(pts[-1], pts[-2])
    return spos, tpos


def draw_relation(c, x1, y1, x2, y2, line_style=SOLID, source=None, target=None, label=None,
                  source_node=None, target_node=None,
                  source_label=None, target_label=None,
                  item_flow=None, item_position=0.5):
    """Draw a straight-line relation with optional arrowheads and label.

    Parameters
    ----------
    c : drawille.Canvas
    x1, y1, x2, y2 : int
        Endpoint coordinates.
    line_style : {'solid', 'dashed'}
    source, target : str or None
        Arrowhead styles at each end.
    label : str or None
        Text placed perpendicular to the line at its midpoint.
    source_node, target_node : Node or None
        Source/target diagram nodes — used to place CIRCLE / UNOWNED
        membership markers tangent to the node boundary so the entire
        circle stays visible instead of being half-covered by the node.
    """
    sx, sy, tx, ty = x1, y1, x2, y2
    dx_total, dy_total = x2 - x1, y2 - y1
    length = max(1, (dx_total * dx_total + dy_total * dy_total) ** 0.5)

    if target and target != NONE:
        bo = _arrow_backoff(target)
        if bo:
            tx = x2 - dx_total / length * bo
            ty = y2 - dy_total / length * bo

    if source and source != NONE:
        bo = _arrow_backoff(source)
        if bo:
            sx = x1 + dx_total / length * bo
            sy = y1 + dy_total / length * bo

    draw_line(c, sx, sy, tx, ty, line_style)
    angle = atan2(dy_total, dx_total)
    # Containment markers (CIRCLE / UNOWNED) sit tangent to the boundary;
    # the rest of the arrowheads point along the edge axis.
    target_angle = angle
    source_angle = angle + pi
    if target in (CIRCLE, UNOWNED, CIRCLED_PLUS):
        node_angle = _node_outward_angle(x2, y2, target_node)
        if node_angle is not None:
            target_angle = node_angle
    if source in (CIRCLE, UNOWNED, CIRCLED_PLUS):
        node_angle = _node_outward_angle(x1, y1, source_node)
        if node_angle is not None:
            source_angle = node_angle
    draw_arrowhead(c, x2, y2, target_angle, target)
    draw_arrowhead(c, x1, y1, source_angle, source)
    if label:
        mx = (x1 + x2) // 2
        my = (y1 + y2) // 2
        dx, dy = x2 - x1, y2 - y1
        length = max(abs(dx), abs(dy))
        if length > 0:
            perp_x = -dy / length
            perp_y = dx / length
            lx = int(mx + perp_x * 8)
            ly = int(my + perp_y * 8)
            c.set_text(lx, ly, label)
    if source_label or target_label:
        spos, tpos = edge_end_label_positions([(x1, y1), (x2, y2)])
        if (spos is not None and tpos is not None
                and (x1 != x2 or y1 != y2)):
            vert = x1 == x2
            if source_label:
                c.set_text(spos[0] + (2 if vert else -len(source_label) // 2),
                           spos[1], source_label)
            if target_label:
                c.set_text(tpos[0] + (2 if vert else -len(target_label) // 2),
                           tpos[1], target_label)
    if item_flow:
        r = route_point_at([(x1, y1), (x2, y2)], item_position)
        if r:
            fx, fy, fangle = r
            draw_arrowhead(c, int(fx), int(fy), fangle, FILLED)
            vx = cos(fangle)
            if abs(vx) > 0.7:
                c.set_text(int(fx - vx * (len(item_flow) * 2 + 2)), int(fy - 2),
                           item_flow)
            else:
                c.set_text(int(fx + 2), int(fy), item_flow)


# ── multi-segment (orthogonal) polyline ──

def route_point_at(points, fraction=0.5):
    """``(x, y, angle)`` at a 0..1 fraction along the Manhattan route's
    path length — or ``None`` for routes with fewer than two points.
    ``angle`` points along the segment (source → target)."""
    pts = list(points)
    if len(pts) < 2:
        return None
    total = sum(abs(pts[i + 1][0] - pts[i][0]) + abs(pts[i + 1][1] - pts[i][1])
                for i in range(len(pts) - 1))
    if total == 0:
        return None
    dist = total * (fraction if fraction is not None else 0.5)
    acc = 0
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        seg = abs(x2 - x1) + abs(y2 - y1)
        if acc + seg >= dist:
            rem = dist - acc
            if x1 == x2:
                return (x1, y1 + (rem if y2 > y1 else -rem),
                        atan2(y2 - y1, 0))
            return (x1 + (rem if x2 > x1 else -rem), y1,
                    atan2(0, x2 - x1))
        acc += seg
    return (pts[-1][0], pts[-1][1],
            atan2(pts[-1][1] - pts[-2][1], pts[-1][0] - pts[-2][0]))


def draw_polyline(c, points, line_style=SOLID, source=None, target=None, label=None,
                  used_labels=None, keep_away=None, source_node=None, target_node=None,
                  source_label=None, target_label=None,
                  item_flow=None, item_position=0.5):
    """Draw an orthogonal polyline through waypoints with arrowheads.

    used_labels : set of (x, y) tuples — occupied label positions to avoid.
    keep_away  : set of (x, y) tuples — waypoints of other edges to avoid.
    source_node, target_node : Node or None
        Diagram nodes — used to place CIRCLE / UNOWNED membership markers
        tangent to the node boundary so the entire circle stays visible.
    """
    pts = list(points)

    # Shorten last segment so the line stops at the arrowhead base
    if target and target != NONE and len(pts) >= 2:
        bo = _arrow_backoff(target)
        if bo:
            x1, y1 = pts[-2]
            x2, y2 = pts[-1]
            if x1 == x2:
                pts[-1] = (x2, y2 - bo if y2 > y1 else y2 + bo)
            else:
                pts[-1] = (x2 - bo if x2 > x1 else x2 + bo, y2)

    # Shorten first segment so the line stops at the source arrowhead base
    if source and source != NONE and len(pts) >= 2:
        bo = _arrow_backoff(source)
        if bo:
            x1, y1 = pts[0]
            x2, y2 = pts[1]
            if x1 == x2:
                pts[0] = (x1, y1 + bo if y2 > y1 else y1 - bo)
            else:
                pts[0] = (x1 + bo if x2 > x1 else x1 - bo, y1)

    for i in range(len(pts) - 1):
        draw_line(c, *pts[i], *pts[i + 1], line_style)

    # target arrowhead on last segment
    if target and len(points) >= 2:
        dx = points[-1][0] - points[-2][0]
        dy = points[-1][1] - points[-2][1]
        target_angle = atan2(dy, dx)
        if target in (CIRCLE, UNOWNED, CIRCLED_PLUS):
            node_angle = _node_outward_angle(points[-1][0], points[-1][1], target_node)
            if node_angle is not None:
                target_angle = node_angle
        draw_arrowhead(c, points[-1][0], points[-1][1], target_angle, target)

    # source arrowhead on first segment
    if source and len(points) >= 2:
        dx = points[1][0] - points[0][0]
        dy = points[1][1] - points[0][1]
        source_angle = atan2(dy, dx) + pi
        if source in (CIRCLE, UNOWNED, CIRCLED_PLUS):
            node_angle = _node_outward_angle(points[0][0], points[0][1], source_node)
            if node_angle is not None:
                source_angle = node_angle
        draw_arrowhead(c, points[0][0], points[0][1], source_angle, source)

    # label at Manhattan midpoint
    if label and len(points) >= 2:
        total = sum(abs(points[i + 1][0] - points[i][0]) +
                    abs(points[i + 1][1] - points[i][1])
                    for i in range(len(points) - 1))
        target_dist = total // 2
        acc = 0
        label_pos = None
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            seg_len = abs(x2 - x1) + abs(y2 - y1)
            if acc + seg_len >= target_dist:
                rem = target_dist - acc
                if seg_len > 0:
                    if x1 == x2:  # vertical → offset right
                        mx = x1
                        my = y1 + (rem if y2 > y1 else -rem)
                        lx, ly = mx + 6, my - 2
                    else:  # horizontal → offset below
                        mx = x1 + (rem if x2 > x1 else -rem)
                        my = y1
                        lx, ly = mx, my + 6
                else:
                    lx, ly = x1 + 6, y1
                label_pos = (lx, ly)
                break
            acc += seg_len

        if label_pos:
            lx, ly = label_pos
            keep_away = keep_away or set()
            # Collision avoidance: try offsets if position is taken
            if used_labels is not None:
                offsets = [(0, 0), (0, 12), (12, 0), (0, -8), (-12, 0),
                           (0, 20), (20, 0), (-20, 0), (0, -16)]
                for ox, oy in offsets:
                    pos = (lx + ox, ly + oy)
                    label_coll = any(abs(pos[0] - p[0]) < 10 and abs(pos[1] - p[1]) < 5
                                     for p in used_labels)
                    path_coll = any(abs(pos[0] - p[0]) < 12 and abs(pos[1] - p[1]) < 12
                                    for p in keep_away)
                    if not label_coll and not path_coll:
                        lx, ly = pos
                        used_labels.add((pos[0], pos[1], len(label) * 2))
                        break
                else:
                    used_labels.add((lx, ly, len(label) * 2))
            c.set_text(lx, ly, label)
    if (source_label or target_label) and len(points) >= 2:
        spos, tpos = edge_end_label_positions(list(points))
        _end_offsets = [(0, 0), (0, -8), (0, 8), (10, 0), (-10, 0), (0, 16),
                        (0, -16), (-18, 0), (18, 0), (0, 24)]
        pairs = ((source_label, spos, points[0][0] == points[1][0]),
                 (target_label, tpos, points[-1][0] == points[-2][0]))
        for lab, pos, vert in pairs:
            if not lab or pos is None:
                continue
            lx, ly = pos
            w2 = len(lab) * 2
            xl = lx if vert else lx - w2 // 2
            if used_labels is not None or keep_away:
                for ox, oy in _end_offsets:
                    p2 = (lx + ox, ly + oy)
                    p2l = p2[0] if vert else p2[0] - w2 // 2
                    lcoll = any(not (p2l + w2 < q[0] - 2 or p2l > q[0] + q[2] + 2)
                                and abs(p2[1] - q[1]) < 5
                                for q in (used_labels or ()))
                    pcoll = any(abs(p2[0] - q[0]) < 12 and abs(p2[1] - q[1]) < 12
                                for q in (keep_away or ()))
                    if not lcoll and not pcoll:
                        lx, ly = p2
                        xl = p2l
                        if used_labels is not None:
                            used_labels.add((xl, ly, w2))
                        break
                else:
                    if used_labels is not None:
                        used_labels.add((xl, ly, w2))
            if vert:
                c.set_text(lx + 2, ly, lab)
            else:
                c.set_text(lx - len(lab) // 2, ly, lab)
    if item_flow and len(points) >= 2:
        r = route_point_at(list(points), item_position)
        if r:
            fx, fy, fangle = r
            draw_arrowhead(c, fx, fy, fangle, FILLED)
            vx, vy = cos(fangle), sin(fangle)
            if abs(vx) > 0.7:   # horizontal segment: label upstream of the arrow
                c.set_text(int(fx - vx * (len(item_flow) * 2 + 2)), int(fy - 2),
                           item_flow)
            else:               # vertical segment: label right of the arrow
                c.set_text(int(fx + 2), int(fy), item_flow)


# ── shared label placement ──

def clear_label_pos(pos, w_units, keep_away=None, used_labels=None, anchor='middle'):
    """Collision-aware label placement: try small offsets until ``pos``
    is clear of other edges' paths (``keep_away``) and of already-placed
    labels. ``used_labels`` holds (x_left, y, width) spans and registers
    the winning position. Figure 3.1 review: parallel edges' end labels
    must not overprint."""
    offsets = [(0, 0), (0, -8), (0, 8), (10, 0), (-10, 0),
               (0, 16), (0, -16), (-18, 0), (18, 0), (0, 24)]
    for ox, oy in offsets:
        p2 = (pos[0] + ox, pos[1] + oy)
        if any(abs(p2[0] - q[0]) < 14 and abs(p2[1] - q[1]) < 6
               for q in (keep_away or ())):
            continue
        x_left = p2[0] - (w_units / 2 if anchor == 'middle' else 0)
        if any(not (x_left + w_units < q[0] - 2 or x_left > q[0] + q[2] + 2)
               and abs(p2[1] - q[1]) < 6 for q in (used_labels or ())):
            continue
        if used_labels is not None:
            used_labels.add((x_left, p2[1], w_units))
        return p2
    return pos


# ── ports / port box ──

PORT_W = 8
PORT_H = 12

def _port_arrow(side, direction):
    """Return the Unicode arrow character for a port, or ``None`` for no arrow.

    Parameters
    ----------
    side : {'left', 'right', 'top', 'bottom'}
    direction : {'in', 'out', 'inout', None}
        ``'in'``  → arrow points toward the node interior.
        ``'out'`` → arrow points away from the node.
        ``'inout'`` → double-headed arrow (bidirectional).
        ``None``  → no arrow drawn.
    """
    if direction is None:
        return None
    arrows = dict(
        in_left='\u2192', in_right='\u2190', in_top='\u2193', in_bottom='\u2191',
        out_left='\u2190', out_right='\u2192', out_top='\u2191', out_bottom='\u2193',
        inout_left='\u2194', inout_right='\u2194', inout_top='\u2195', inout_bottom='\u2195',
        nonatomic_left='< >', nonatomic_right='< >',
        nonatomic_top='< >', nonatomic_bottom='< >',
    )
    return arrows.get(f'{direction}_{side}')


def draw_port_box(c, x, y, label=None, side='left', direction=None,
                  label_inside=False, label_side=None):
    """Draw a small port box (8×12 px) with optional direction arrow inside and label outside.

    Parameters
    ----------
    c : drawille.Canvas
    x, y : int
        Top-left corner of the port box.
    label : str or None
        Text placed outside the port (away from the node).
    side : {'left', 'right', 'top', 'bottom'}
        Which side of the node the port is on — determines where the
        external label is placed.
    direction : {'in', 'out', 'inout', None}
        ``'in'``  → arrow points toward the node interior (e.g. input port).
        ``'out'`` → arrow points away from the node (e.g. output port).
        ``'inout'`` → bidirectional (double-headed arrow).
        ``None``  → no arrow drawn (default).
    """
    x1, y1, x2, y2 = x, y, x + PORT_W, y + PORT_H
    for rx, ry in line(x1, y1, x2, y1): c.set(rx, ry)
    for rx, ry in line(x2, y1, x2, y2): c.set(rx, ry)
    for rx, ry in line(x2, y2, x1, y2): c.set(rx, ry)
    for rx, ry in line(x1, y2, x1, y1): c.set(rx, ry)

    arrow = _port_arrow(side, direction)
    if arrow:
        c.set_text(x + 3, y + 4, arrow)

    if label:
        ls = label_side or side
        ly = y + 4
        if ls == 'left':
            if label_inside:
                c.set_text(x + PORT_W + 2, ly, label)
            else:
                c.set_text(x - len(label) * 2 - 2, ly, label)
        elif ls == 'right':
            if label_inside:
                c.set_text(x - len(label) * 2 - 2, ly, label)
            else:
                c.set_text(x + PORT_W + 2, ly, label)
        elif ls == 'top':
            c.set_text(x + PORT_W // 2 - len(label), y - 4, label)
        elif ls == 'bottom':
            c.set_text(x + PORT_W // 2 - len(label), y + PORT_H + 1, label)


# ── comment box (dog-ear) ──

COMMENT_FOLD = 16

def draw_comment_box(c, x1, y1, x2, y2, text):
    fold = min(COMMENT_FOLD, (x2 - x1) // 3, (y2 - y1) // 3)
    for rx, ry in line(x1, y1, x2 - fold, y1): c.set(rx, ry)
    for rx, ry in line(x2 - fold, y1, x2, y1 + fold): c.set(rx, ry)
    for rx, ry in line(x2, y1 + fold, x2, y2): c.set(rx, ry)
    for rx, ry in line(x2, y2, x1, y2): c.set(rx, ry)
    for rx, ry in line(x1, y2, x1, y1): c.set(rx, ry)
    box_cx = (x1 + x2) // 2
    box_cy = (y1 + y2) // 2
    c.set_text(box_cx - len(text), box_cy - 2, text)


# ── view / package box (folder tab) ──

def _draw_dashed_line(c, x1, y1, x2, y2):
    """Draw a line skipping pixels — 5 on, 3 off."""
    pts = list(line(x1, y1, x2, y2))
    for i, (px, py) in enumerate(pts):
        if i % 8 < 5:
            c.set(px, py)


def draw_view_box(c, x1, y1, x2, y2, name, stereotypes=None, attributes=None, dashed=False):
    tw = []
    if stereotypes:
        tw.extend(len(f'\u00ab{s}\u00bb') for s in stereotypes)
    tw.append(len(name))
    max_tw = max(tw) if tw else 0
    tab_w = min(max_tw * 2 + 6, x2 - x1)
    n_lines = 1 + (len(stereotypes) if stereotypes else 0)
    tab_h = n_lines * 5 + 4

    dl = _draw_dashed_line if dashed else None
    if dashed:
        _draw_dashed_line(c, x1, y2, x1, y1)
        _draw_dashed_line(c, x1, y1, x1 + tab_w, y1)
        _draw_dashed_line(c, x1 + tab_w, y1, x1 + tab_w, y1 + tab_h)
        _draw_dashed_line(c, x1 + tab_w, y1 + tab_h, x2, y1 + tab_h)
        _draw_dashed_line(c, x2, y1 + tab_h, x2, y2)
        _draw_dashed_line(c, x2, y2, x1, y2)
    else:
        for rx, ry in line(x1, y2, x1, y1): c.set(rx, ry)
        for rx, ry in line(x1, y1, x1 + tab_w, y1): c.set(rx, ry)
        for rx, ry in line(x1 + tab_w, y1, x1 + tab_w, y1 + tab_h): c.set(rx, ry)
        for rx, ry in line(x1 + tab_w, y1 + tab_h, x2, y1 + tab_h): c.set(rx, ry)
        for rx, ry in line(x2, y1 + tab_h, x2, y2): c.set(rx, ry)
        for rx, ry in line(x2, y2, x1, y2): c.set(rx, ry)

    lines = []
    if stereotypes:
        for s in stereotypes:
            lines.append(f'\u00ab{s}\u00bb')
    lines.append(name)
    for i, txt in enumerate(lines):
        y = y1 + 2 + i * 5
        x = x1 + (tab_w // 2) - len(txt)
        c.set_text(x, y, txt)

    if attributes:
        sep_y = y1 + tab_h + 2
        for rx, ry in line(x1 + 2, sep_y, x2 - 2, sep_y): c.set(rx, ry)
        for i, attr in enumerate(attributes):
            y = sep_y + 2 + i * 5
            text_x = (x1 + x2) // 2 - len(attr)
            c.set_text(text_x, y, attr)


# ── arc helper for rounded corners ──

ROUNDED_RADIUS = 5

def _draw_arc(c, cx, cy, r, a1, a2, dashed=False):
    """Draw a circular arc about (cx, cy) from angle a1 to a2."""
    steps = max(2, round(r * pi / 2))
    px_prev = round(cx + cos(a1) * r)
    py_prev = round(cy + sin(a1) * r)
    pixel_offset = 0
    for i in range(1, steps + 1):
        t = a1 + (a2 - a1) * i / steps
        x = round(cx + cos(t) * r)
        y = round(cy + sin(t) * r)
        pts = list(line(px_prev, py_prev, x, y))
        for j, (px, py) in enumerate(pts):
            if not dashed or (pixel_offset + j) % 8 < 5:
                c.set(px, py)
        pixel_offset += len(pts)
        px_prev, py_prev = x, y


# ── sequence diagram drawing (§7.4–7.7) ──

def draw_seq_head(c, x, top, label, width=None, head_h=12):
    """Lifeline head (§7.4): rectangle carrying the name string, centred
    on the dashed-line column."""
    w = width or (len(label) * 2 + 10)
    x1, x2 = int(x - w / 2), int(x + w / 2)
    y1, y2 = top, top + head_h
    for rx, ry in line(x1, y1, x2, y1):
        c.set(rx, ry)
    for rx, ry in line(x2, y1, x2, y2):
        c.set(rx, ry)
    for rx, ry in line(x2, y2, x1, y2):
        c.set(rx, ry)
    for rx, ry in line(x1, y2, x1, y1):
        c.set(rx, ry)
    c.set_text(x1 + 3, y1 + 4, label)


def draw_destruction_x(c, x, y, r=4):
    """Destruction occurrence (§7.6): an X at the bottom of a lifeline."""
    for px, py in line(x - r, y - r, x + r, y + r):
        c.set(px, py)
    for px, py in line(x - r, y + r, x + r, y - r):
        c.set(px, py)


def draw_seq_exec(c, x, y1, y2, shaded=False, width=8):
    """Execution specification (§7.7): a thin vertical rectangle centred
    on the lifeline's dashed-line column."""
    x1, x2 = x - width // 2, x + width // 2
    for rx, ry in line(x1, y1, x2, y1):
        c.set(rx, ry)
    for rx, ry in line(x2, y1, x2, y2):
        c.set(rx, ry)
    for rx, ry in line(x2, y2, x1, y2):
        c.set(rx, ry)
    for rx, ry in line(x1, y2, x1, y1):
        c.set(rx, ry)
    if shaded:
        for ry in range(y1 + 1, y2):
            for rx in range(x1 + 1, x2):
                c.set(rx, ry)


def draw_seq_message(c, x1, x2, y, kind, label):
    """Sequence message (§7.5): horizontal line with the kind's line
    style (async/sync solid, reply/create/delete dashed), arrowhead
    landing on the receiver, name string floating above the line."""
    lo, hi = (int(x1), int(x2)) if x1 <= x2 else (int(x2), int(x1))
    dashed = kind in ('reply', 'create', 'delete')
    draw_line(c, lo, int(y), hi, int(y), DASHED if dashed else SOLID)
    if hi > lo:
        a_angle = 0.0 if x2 >= x1 else pi
        style = FILLED if kind == 'sync' else OPEN
        draw_arrowhead(c, int(x2), int(y), a_angle, style)
    if label:
        c.set_text((lo + hi) // 2 - len(label), int(y) - 5, label)


# ── activity node drawing ──

def draw_start_node(c, cx, cy, r):
    """Draw a filled circle — activity start node."""
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if round((dx*dx + dy*dy) ** 0.5) <= r:
                c.set(cx + dx, cy + dy)


def draw_done_node(c, cx, cy, r):
    """Draw a bullseye (inset filled circle) — activity done node."""
    inner_r = max(2, r // 2)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            d = round((dx*dx + dy*dy) ** 0.5)
            if d == r or d <= inner_r:
                c.set(cx + dx, cy + dy)


def draw_terminate_node(c, cx, cy, r):
    """Draw an open circle with an X through the center — terminate node."""
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            d = round((dx*dx + dy*dy) ** 0.5)
            if d == r:
                c.set(cx + dx, cy + dy)
    h = r * 0.7
    for sign in (-1, 1):
        a = pi / 4 * sign
        for px, py in line(cx, cy, cx + cos(a) * h, cy + sin(a) * h):
            c.set(px, py)
    for sign in (-1, 1):
        a = pi + pi / 4 * sign
        for px, py in line(cx, cy, cx + cos(a) * h, cy + sin(a) * h):
            c.set(px, py)


def draw_fork_join_node(c, x1, y1, x2, y2):
    """Draw a filled synchronization bar — fork/join node."""
    for dy in range(y1, y2 + 1):
        for dx in range(x1, x2 + 1):
            c.set(dx, dy)


def draw_decision_node(c, cx, cy, size, name=''):
    """Draw a diamond — decision/merge node."""
    pts = [(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)]
    for i in range(4):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % 4]
        for px, py in line(x1, y1, x2, y2):
            c.set(px, py)
    if name:
        c.set_text(cx - len(name), cy - 2, name)


def draw_history_node(c, cx, cy, r, deep=False):
    """Draw a shallow- or deep-history pseudostate circle with an inner label.

    Shallow history shows an ``H`` inside an open circle; deep history shows
    an ``H*`` (a small asterisk follows the H).  UML/SysML pseudo-shape,
    used for state-machine region history.  Drawn as an open circle (ring)
    with the label text centred inside it.
    """
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            d = round((dx * dx + dy * dy) ** 0.5)
            if d == r:
                c.set(cx + dx, cy + dy)
    label = 'H*' if deep else 'H'
    c.set_text(cx - len(label), cy - 2, label)


def draw_entry_exit_point(c, cx, cy, r, label=None, kind='entry'):
    """Draw a hollow circle for a state's entry or exit point.

    The shape is identical for both kinds (an open circle, optionally with
    a small label drawn outside it); ``kind`` is recorded only for
    documentation/structural purposes — the visual distinction comes from
    the connecting edges (entry points have edges pointing into the state,
    exit points have edges pointing out).
    """
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            d = round((dx * dx + dy * dy) ** 0.5)
            if d == r:
                c.set(cx + dx, cy + dy)
    if label:
        c.set_text(cx - len(label), cy + r + 1, label)


# ── box ──

def _class_box_sections(stereotypes, name, attributes, compartments):
    """Content sections of a classifier box, top to bottom.

    Returns a list of ``(kind, payload)`` tuples where ``kind`` is
    ``'text'`` (payload is the string) or ``'sep'`` (a full-width
    horizontal separator line).  Shared by the braille and SVG renderers
    so both draw the same structure: stereotypes, name, then the unnamed
    attribute compartment, then any named compartments — each named
    compartment is a separator, a centered title line, and content lines
    (SysML v1 block-notation, Delligatti §3.4).
    """
    sections = []
    for s in stereotypes or []:
        sections.append(('text', '\u00ab%s\u00bb' % s))
    sections.append(('text', name))
    if attributes:
        sections.append(('sep', ''))
        for a in attributes:
            sections.append(('text', a))
    for title, lines in compartments or []:
        sections.append(('sep', ''))
        sections.append(('title', title))
        for l in lines:
            sections.append(('text', l))
    return sections


# ── interface symbols (lollipop / socket, §3.4.1.5) ──

INT_STICK = 8        # stick length from the anchor face
INT_BALL_R = 3       # provided-interface ball radius
INT_STACK = 24       # radial spacing between stacked interfaces (must fit
                     # a braille text row + symbol; 16 collides labels)

_OUTWARD = {'right': (1, 0), 'left': (-1, 0), 'top': (0, -1), 'bottom': (0, 1)}


def draw_interface(c, iface):
    """Draw a UML interface symbol beyond its anchor face (§3.4.1.5):
    provided = stick + filled ball (lollipop); required = stick + open
    semicircle (socket); name label floats beyond the symbol."""
    sx, sy = iface.face
    dx, dy = _OUTWARD[iface.side]
    cx, cy = iface.center()
    draw_line(c, sx, sy, int(cx), int(cy), SOLID)
    r = INT_BALL_R
    if iface.kind == 'provided':
        for ox in range(-r, r + 1):
            for oy in range(-r, r + 1):
                if ox * ox + oy * oy <= r * r:
                    c.set(int(cx) + ox, int(cy) + oy)
    else:
        # open semicircle bulging outward: center + axis*cos(a)*r +
        # perp*sin(a)*r, a in [-pi/2, pi/2] (flat side toward the node)
        px, py = -dy, dx
        prev = None
        for t in range(9):
            a = -pi / 2 + t / 8 * pi
            ex = int(cx + dx * (cos(a) * r) + px * (sin(a) * r))
            ey = int(cy + dy * (cos(a) * r) + py * (sin(a) * r))
            if prev is not None:
                draw_line(c, prev[0], prev[1], ex, ey, SOLID)
            prev = (ex, ey)
    if iface.name:
        if dx:      # left/right stick: label beyond the symbol on the axis
            tx = int(cx + dx * (r + 2))
            if dx < 0:
                tx -= len(iface.name)
            c.set_text(max(0, tx), int(cy) - 2, iface.name)
        else:       # top/bottom stick: label beside the symbol
            c.set_text(int(cx) + 2, int(cy - dy * (r + 4)), iface.name)


def draw_diagram_frame(c, x1, y1, x2, y2, header):
    """Enclosing SysML v1 diagram-kind frame: border rectangle with the
    header string in a strip along the top edge (Delligatti §2.4/§3.3)."""
    for rx, ry in line(x1, y1, x2, y1): c.set(rx, ry)
    for rx, ry in line(x2, y1, x2, y2): c.set(rx, ry)
    for rx, ry in line(x2, y2, x1, y2): c.set(rx, ry)
    for rx, ry in line(x1, y2, x1, y1): c.set(rx, ry)
    c.set_text(x1 + 3, y1 + 4, header)


def draw_class_box(c, x1, y1, x2, y2, name, stereotypes=None, attributes=None, rounded=False, dashed=False, compartments=None, folder=False):
    """Draw a rectangular classifier box with centered text.

    The box has four borders. Inside it renders (top to bottom):
    1. Stereotypes (if any), each in guillemets
    2. The node name
    3. A separator line (if attributes are present)
    4. Attribute/method lines (if any)

    Parameters
    ----------
    c : drawille.Canvas
    x1, y1, x2, y2 : int
        Bounding box corners (pixels).
    name : str
        Primary label.
    stereotypes : list of str, optional
    attributes : list of str, optional
    rounded : bool, optional
        Draw rounded corners (e.g. SysMLv2 part usages).
    dashed : bool, optional
        Draw border with dashed lines.
    folder : bool, optional
        Draw the package folder tab on the upper-left side (§10.4).
    """
    dl = _draw_dashed_line if dashed else None
    if rounded:
        r = min(ROUNDED_RADIUS, (x2 - x1) // 4, (y2 - y1) // 4)
        if dashed:
            _draw_dashed_line(c, x1 + r, y1, x2 - r, y1)
        else:
            for px, py in line(x1 + r, y1, x2 - r, y1): c.set(px, py)
        _draw_arc(c, x2 - r, y1 + r, r, -pi / 2, 0, dashed)
        if dashed:
            _draw_dashed_line(c, x2, y1 + r, x2, y2 - r)
        else:
            for px, py in line(x2, y1 + r, x2, y2 - r): c.set(px, py)
        _draw_arc(c, x2 - r, y2 - r, r, 0, pi / 2, dashed)
        if dashed:
            _draw_dashed_line(c, x2 - r, y2, x1 + r, y2)
        else:
            for px, py in line(x2 - r, y2, x1 + r, y2): c.set(px, py)
        _draw_arc(c, x1 + r, y2 - r, r, pi / 2, pi, dashed)
        if dashed:
            _draw_dashed_line(c, x1, y1 + r, x1, y2 - r)
        else:
            for px, py in line(x1, y1 + r, x1, y2 - r): c.set(px, py)
        _draw_arc(c, x1 + r, y1 + r, r, pi, 3 * pi / 2, dashed)
    else:
        if dashed:
            _draw_dashed_line(c, x1, y1, x2, y1)
            _draw_dashed_line(c, x2, y1, x2, y2)
            _draw_dashed_line(c, x2, y2, x1, y2)
            _draw_dashed_line(c, x1, y2, x1, y1)
        else:
            for rx, ry in line(x1, y1, x2, y1): c.set(rx, ry)
            for rx, ry in line(x2, y1, x2, y2): c.set(rx, ry)
            for rx, ry in line(x2, y2, x1, y2): c.set(rx, ry)
            for rx, ry in line(x1, y2, x1, y1): c.set(rx, ry)
    box_cx = (x1 + x2) // 2
    if folder:
        # Package folder tab (§10.4): short horizontal cap rising 2 px
        # above the upper-left border corner, closed by a vertical stub.
        tw = min(10, (x2 - x1) // 4) if x2 > x1 + 16 else max(4, (x2 - x1) // 4)
        for px, py in line(x1, y1 - 2, x1 + tw, y1 - 2):
            c.set(px, py)
        for px, py in line(x1, y1 - 2, x1, y1):
            c.set(px, py)
    for i, (kind, txt) in enumerate(_class_box_sections(
            stereotypes, name, attributes, compartments)):
        y = y1 + 4 + i * 5
        if kind == 'sep':
            for rx, ry in line(x1 + 2, y, x2 - 2, y): c.set(rx, ry)
        else:
            x = box_cx - len(txt)
            c.set_text(x, y, txt)
