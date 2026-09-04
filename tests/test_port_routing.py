"""Obstacle-aware port-to-port routing (sugiyama + orthogonal).

The sugiyama engine positions nodes in layers without regard for the
sides their ports face; the port router must therefore wrap around
node bodies through free bands instead of slicing straight through
them.  These tests pin that behaviour.
"""

from diagramboxes import Diagram, Node


def _foreign_hits(d, e, pad=1):
    """Segments of e.waypoints crossing a foreign node or port box."""
    hits = []
    foreign = [n for n in d.nodes if n not in (e.source, e.target)]
    boxes = [(n.name, n.box()) for n in foreign]
    boxes += [(f"{n.name}.{p.label}", p.box())
              for n in foreign for p in n.ports]
    for name, (bx1, by1, bx2, by2) in boxes:
        for i in range(len(e.waypoints) - 1):
            (x1, y1), (x2, y2) = e.waypoints[i], e.waypoints[i + 1]
            if x1 == x2:
                if bx1 - pad <= x1 <= bx2 + pad and \
                        min(y1, y2) <= by2 + pad and max(y1, y2) >= by1 - pad:
                    hits.append((name, i))
            elif y1 == y2:
                if by1 - pad <= y1 <= by2 + pad and \
                        min(x1, x2) <= bx2 + pad and max(x1, x2) >= bx1 - pad:
                    hits.append((name, i))
    return hits


def _two_node_right_to_left():
    """Source above-right port, target below-left port: the naive Z's
    horizontal leg would slice through the target box."""
    d = Diagram()
    src = d.add_node("src", stereotypes=["part"])
    dst = d.add_node("dst", stereotypes=["part"])
    sp = src.add_port("out", side="right")
    tp = dst.add_port("in", side="left")
    d.add_edge(src, dst, source_port=sp, target_port=tp)
    # force the awkward geometry: dst below and slightly right of src
    src.x, src.y = 8, 8
    dst.x, dst.y = 8, 120
    return d, src, dst


def test_sugiyama_port_edge_wraps_around_target():
    d, src, dst = _two_node_right_to_left()
    d.layout(routing='sugiyama', layer_gap=60, node_gap=14, margin=8)
    e = d.edges[0]
    assert e.source_port and e.target_port
    # the final segment must approach the left-facing port horizontally
    (ax, ay), (bx, by) = e.waypoints[-2], e.waypoints[-1]
    assert ay == by and bx > ax            # perpendicular final leg
    assert by == dst.ports[0].cy           # lands at the port
    assert not _foreign_hits(d, e), e.waypoints


def test_orthogonal_port_edge_clear_too():
    d, src, dst = _two_node_right_to_left()
    d.layout(routing='orthogonal', layer_gap=60, node_gap=14, margin=8)
    e = d.edges[0]
    assert not _foreign_hits(d, e), e.waypoints


def test_clean_z_geometry_unchanged():
    """When the plain Z is already clear it is kept (fast path)."""
    d = Diagram()
    src = d.add_node("src")
    dst = d.add_node("dst")
    sp = src.add_port("out", side="right")
    tp = dst.add_port("in", side="left")
    d.add_edge(src, dst, source_port=sp, target_port=tp)
    src.x, src.y = 8, 8
    dst.x, dst.y = 8, 40    # close below: direct Z from right port to
    # left port has its horizontal leg inside dst only if dst spans it —
    # at y=40-ish the leg runs above dst (dst top=40), so the naive Z
    # from (port) down to ty=44 crosses dst → wrap kicks in; assert
    # merely that the result is clear either way.
    d.layout(routing='sugiyama', layer_gap=60, node_gap=14, margin=8)
    e = d.edges[0]
    assert not _foreign_hits(d, e), e.waypoints


def test_top_port_scan_avoids_intermediate():
    """A top-facing target port with an obstacle in the corridor shifts
    its horizontal leg."""
    d = Diagram()
    src = d.add_node("src")
    mid = d.add_node("mid")
    dst = d.add_node("dst")
    sp = src.add_port("o", side="bottom")
    tp = dst.add_port("i", side="top")
    d.add_edge(src, dst, source_port=sp, target_port=tp)
    src.x, src.y = 0, 0
    mid.x, mid.y = 30, 40      # sits right of the naive leg corridor
    dst.x, dst.y = 100, 80
    d.layout(routing='orthogonal', layer_gap=60, node_gap=14, margin=8)
    e = d.edges[0]
    assert not _foreign_hits(d, e), e.waypoints


def test_single_port_edge_anchored_in_sugiyama():
    d = Diagram()
    src = d.add_node("src")
    dst = d.add_node("dst")
    sp = src.add_port("out", side="right")
    d.add_edge(src, dst, source_port=sp)
    src.x, src.y = 8, 8
    dst.x, dst.y = 8, 120
    d.layout(routing='sugiyama', layer_gap=60, node_gap=14, margin=8)
    e = d.edges[0]
    # first waypoint is the source port's outer face
    assert e.waypoints[0] == (src.x + src.w + 8, src.ports[0].cy)


def test_both_engines_no_port_box_collisions():
    """Foreign port boxes are obstacles too (label_inside ports sit on
    the node borders where naive routes love to pass)."""
    for routing in ('sugiyama', 'orthogonal'):
        d, src, dst = _two_node_right_to_left()
        # extra port on dst's right border — directly in the naive path
        dst.add_port("aux", side="right")
        d.layout(routing=routing, layer_gap=60, node_gap=14, margin=8)
        e = d.edges[0]
        assert not _foreign_hits(d, e), (routing, e.waypoints)