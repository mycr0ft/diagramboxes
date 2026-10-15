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
    # owner=None → the diagram frame itself (§9.6)
    p = d.par_param('r1', 'km', side='left', offset=0.75)
    d.render()
    assert p.placed
    fr = d._frame_rect()
    assert p.x == fr[0]            # flush at the frame's inner left border
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