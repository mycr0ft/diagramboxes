"""Parametric diagram notation (Delligatti §9.4-9.8, Figures 9.2-9.4):
constraint properties (rounded nodes '<name> : <type>'), constraint
parameters (small squares docked inside the owner's boundary), value
properties (plain rectangles '<name> : <type> [<mult>] = <default>'),
and binding connectors (solid, no arrowheads).
"""

from diagramboxes import Diagram, NONE, ParParam, to_di, from_di, \
    to_di_xmi, from_di_xmi


def _braille(d):
    return d.render()


def test_par_constraint_is_rounded_name_type_usage():
    d = Diagram()
    tos = d.par_constraint('tos', 'Transfer Orbit Size')
    assert tos.rounded
    assert tos.name == 'tos : Transfer Orbit Size'
    # §9.5: the type must name a constraint block — the string carries it
    assert 'Transfer Orbit Size' in tos.name
    assert 'tos : Transfer Orbit Size' in _braille(d)


def test_par_param_docks_inside_owner_boundary():
    d = Diagram()
    d.par_constraint('tos', 'Transfer Orbit Size')
    ttof = d.par_constraint('ttof', 'Transfer Time of Flight')
    p1 = d.par_param('r1', 'km', ttof, side='left', offset=0.25)
    d.render()
    assert p1.placed
    # flush INSIDE the owner's boundary: the square's outer edge sits ON
    # the boundary, positioned by offset along it
    assert p1.x == ttof.x
    assert p1.y == ttof.y + int(ttof.h * 0.25) - p1.h // 2
    # the string '<name> : <type>' renders beside the square
    assert 'r1 : km' in _braille(d)


def test_par_param_docks_on_frame_for_constraintblock_frame():
    d = Diagram()
    d.add_frame('par', element_kind='constraintBlock',
                element_name='Hohmann Transfer')
    d.par_constraint('tos', 'Transfer Orbit Size')
    # owner=None → the diagram frame itself (§9.6): sockets STRADDLE the
    # frame border like §4.8 frame ports (Fig 9.3 pixel evidence)
    p = d.par_param('r1', 'km', side='left', offset=0.75)
    d.render()
    assert p.placed
    fr = d._frame_rect()
    assert p.x + p.w // 2 == fr[0]
    assert 'r1 : km' in _braille(d)


def test_par_value_property_string_format():
    d = Diagram()
    d.add_frame('par', element_kind='block',
                element_name='Transfer Time Analysis')
    vp = d.par_value('timeOfFlight', 'min', default='452.4')
    # §9.7: '<value name> : <type> [<mult>] = <default>'
    assert vp.name == 'timeOfFlight : min = 452.4'
    vp2 = d.par_value('currentOrbitRadius', 'km', mult='0..1')
    assert vp2.name == 'currentOrbitRadius : km [0..1]'
    assert vp2.name in _braille(d)


def test_bind_is_solid_undirected_line():
    d = Diagram()
    tos = d.par_constraint('tos', 'Transfer Orbit Size')
    vp = d.par_value('orderedOrbitRadius', 'km')
    p = d.par_param('orderedOrbitRadius', 'km', tos, side='left')
    b = d.bind(p, vp)
    assert b.source_style == NONE and b.target_style == NONE
    assert b.line_style != 'dashed'   # §9.8: solid, no direction
    assert b.is_binding


def test_binding_routes_straight_between_docked_ends():
    d = Diagram()
    tos = d.par_constraint('tos', 'Transfer Orbit Size')
    vp = d.par_value('orderedOrbitRadius', 'km')
    p = d.par_param('orderedOrbitRadius', 'km', tos, side='left')
    b = d.bind(p, vp)
    d.render()
    assert b.waypoints, 'binding edge routed'
    pts = b.waypoints
    if len(pts) > 2:
        # straight-line routes may still have one bend; no three-way kinks
        assert len(pts) <= 3


def test_parametric_round_trips_di_and_xmi():
    d = Diagram()
    d.add_frame('par', element_kind='constraintBlock',
                element_name='Hohmann Transfer')
    tos = d.par_constraint('tos', 'Transfer Orbit Size')
    ttof = d.par_constraint('ttof', 'Transfer Time of Flight')
    d.par_param('r1', 'km', tos, side='left', offset=0.25)
    p_r2 = d.par_param('r2', 'km', tos, side='left', offset=0.75)
    p_fr = d.par_param('timeOfFlight', 'min', side='right', offset=0.5)
    d.bind(p_r2, ttof)
    vp = d.par_value('timeOfFlight', 'min')
    d.bind(p_fr, vp)
    for payload in (to_di(d), to_di_xmi(to_di(d))):
        d2 = (from_di(from_di_xmi(payload)) if isinstance(payload, str)
              else from_di(payload))
        assert d2.frame is not None and d2.frame.kind == 'par'
        params = list(d2.par_params)
        assert len(params) == 3
        r1 = [p for p in params if p.name.startswith('r1')][0]
        assert r1.owner is not None
        assert r1.owner.name == 'tos : Transfer Orbit Size'
        assert r1.side == 'left' and r1.offset == 0.25
        assert r1.owner.rounded
        # binding round-trips as bare solid edges
        assert any(getattr(e, 'is_binding', False) and
                   e.source_style == NONE and e.target_style == NONE
                   for e in d2.edges)
        d2.render()
        assert 'r1 : km' in _braille(d2)


def test_binding_between_facing_params_routes_orthogonal_channel():
    d = Diagram()
    d.add_frame('par', element_kind='constraintBlock', element_name='HT')
    tos = d.par_constraint('tos', 'Transfer Orbit Size')
    ttof = d.par_constraint('ttof', 'Transfer Time of Flight')
    tos.set_min_height(46)
    ttof.set_min_height(46)
    a = d.par_param('sma', 'km', tos, side='right', offset=0.9)
    b = d.par_param('sma2', 'km', ttof, side='left', offset=0.9)
    e = d.bind(a, b)
    d.render()   # facing sides, equal y → direct two-point line (Fig 9.3)
    assert len(e.waypoints) == 2
    assert e.waypoints[0][1] == e.waypoints[1][1]

    d2 = Diagram()
    d2.add_frame('par', element_kind='constraintBlock', element_name='HT')
    tos2 = d2.par_constraint('tos2', 'Transfer Orbit Size')
    tos2.set_min_height(46)
    fr_p = d2.par_param('r1', 'km', side='left', offset=0.3)   # on the frame
    box_p = d2.par_param('r1b', 'km', tos2, side='left', offset=0.9)
    eb = d2.bind(fr_p, box_p)
    d2.render()   # non-facing y's → single vertical channel, 4 points
    assert len(eb.waypoints) == 4
    wp = eb.waypoints
    assert wp[1][0] == wp[2][0], 'vertical channel between the two ends'
    assert wp[0][1] == wp[1][1] and wp[2][1] == wp[3][1]


def test_set_min_height_survives_layout():
    d = Diagram()
    tos = d.par_constraint('tos', 'Transfer Orbit Size')
    tos.set_min_height(46)
    d.render()
    assert tos.h == 46


def test_frame_pad_widens_the_border_bands():
    d = Diagram()
    d.add_frame('par', element_kind='constraintBlock', element_name='HT')
    d.par_constraint('tos', 'Transfer Orbit Size')
    d.frame_pad = 70
    d.render()
    fr = d._frame_rect()
    nodes = d.nodes
    assert nodes[0].x - fr[0] > 60, 'content insets from the border'

    d2 = Diagram()
    d2.add_frame('ibd', element_kind='block', element_name='B')
    d2.add_node('n 1')
    d2.render()   # default: frame hugs the content as before
    fr2 = d2._frame_rect()
    assert d2.nodes[0].x - fr2[0] < 12


def test_param_round_trip_keeps_docked_geometry():
    d = Diagram()
    d.add_frame('par', element_kind='constraintBlock', element_name='HT')
    tos = d.par_constraint('tos', 'Transfer Orbit Size')
    tos.set_min_height(46)
    p = d.par_param('r1', 'km', tos, side='left', offset=0.75)
    d.bind(p, tos)
    d.render()
    payload = to_di(d)
    d2 = from_di(payload)
    p2 = d2.par_params[0]
    assert (p2.x, p2.y) == (p.x, p.y)
    assert p2.owner.name == 'tos : Transfer Orbit Size'
    assert p2.offset == 0.75


def test_frame_socket_straddle_survives_render_recompute():
    """The Fig 9.3 round-2 bug: sockets docked on the placement-time
    frame, while box widening/reroute waypoints re-grew the frame at
    render time (border 111 units outside the sockets). After the fix
    (widen first, binding legs excluded from _content_bounds) the socket
    centers must sit ON the frame border even recomputed after render."""
    d = Diagram()
    d.add_frame('par', element_kind='constraintBlock', element_name='HT')
    tos = d.par_constraint('tos', 'Transfer Orbit Size')
    tos.set_min_height(46)
    fp = d.par_param('initialOrbitRadius', 'km', side='left', offset=0.35)
    bp = d.par_param('initialOrbitRadius', 'km', tos, side='left',
                     offset=0.35)
    d.bind(fp, bp)
    d.render()
    d.render_svg()
    fr = d._frame_rect()   # recomputed exactly as render_svg drew it
    assert fp.x + fp.w // 2 == fr[0]
    assert bp.x == tos.x   # owner-docked: flush inside
    # and the box param label fits inside the (widened) owner
    assert len(bp.name) * 2 + 6 <= tos.w


def test_socket_label_halo_stays_off_the_border():
    """Fig 9.3 round-3: socket labels must print INSIDE the frame, off
    the border column (centered-on-border halos wiped the frame border
    and the header band)."""
    import re as _re
    d = Diagram()
    d.add_frame('par', element_kind='constraintBlock', element_name='HT')
    tos = d.par_constraint('tos', 'Transfer Orbit Size')
    tos.set_min_height(46)
    d.par_param('initialOrbitRadius', 'km', side='left', offset=0.35)
    d.par_param('timeOfFlight', 's', side='right', offset=0.35)
    svg = d.render_svg()
    border = max(_re.findall(r'<rect x="(-?[\d.]+)" y="(-?[\d.]+)" '
                             r'width="(\d[\d.]*)" height="([\d.]+)"', svg),
                             key=lambda r: float(r[2]))
    bx1, bx2 = float(border[0]), float(border[0]) + float(border[2])
    halos = _re.findall(r'<rect class="halo" x="(-?[\d.]+)" y="[-\d.]+'
                        r'" width="([\d.]+)"', svg)
    straddle = [h for h in halos
                if float(h[0]) <= (bx1 + 1) <= float(h[0]) + float(h[1]) - 1]
    assert not straddle, 'a halo rect crosses the left border column'
    straddle = [h for h in halos
                if float(h[0]) <= (bx2 - 1) <= float(h[0]) + float(h[1]) - 1]
    assert not straddle, 'a halo rect crosses the right border column'


def test_raster_covers_strings_and_square():
    d = Diagram()
    d.add_frame('par', element_kind='block', element_name='Analysis')
    tos = d.par_constraint('tos', 'Transfer Orbit Size')
    vp = d.par_value('orderedOrbitRadius', 'km')
    p = d.par_param('orderedOrbitRadius', 'km', tos, side='left')
    d.bind(p, vp)
    txt = _braille(d)
    assert 'orderedOrbitRadius : km' in txt
    svg = d.render_svg()
    assert 'orderedOrbitRadius : km' in svg
    assert '<rect' in svg and 'tos' in svg