"""ELKjs integration — spawns Node.js subprocess for production layouts.

Bridges to the Eclipse Layout Kernel (ELK) layered algorithm via elkjs.
The pipeline:

1. ``to_elk_json(diagram)`` — converts Diagram → ELK JSON
2. ``elk_layout(graph)`` — spawns ``node -e``, pipes JSON via stdin
3. ``apply_elk_result(diagram, result)`` — maps positions/waypoints back

Layout options configured (see layout_with_elk for defaults):
- elk.algorithm: layered, elk.direction: DOWN
- elk.edgeRouting: ORTHOGONAL
- Port constraints: FIXED_SIDE, alignment: CENTER

Requires
--------
npm install elkjs
node --version >= 16

See also
--------
sugiyama.py  : pure-Python alternative (~400 lines, no dependencies)
layout.py    : homegrown orthogonal router (used by default)
"""

import json
import subprocess
import os
from collections import defaultdict
from pathlib import Path

_ELK_BOOTSTRAP = """
const ELK = require('elkjs');
const elk = new ELK();
let data = '';
process.stdin.on('data', d => data += d);
process.stdin.on('end', () => {
  elk.layout(JSON.parse(data))
    .then(r => { process.stdout.write(JSON.stringify(r)); process.exit(0); })
    .catch(e => { process.stderr.write(e.message); process.exit(1); });
});
"""


def elk_layout(graph_dict, node_modules=None, timeout=30):
    """Send a graph JSON dict to elkjs, return the result dict.

    graph_dict should follow ELK input format:
      { "id": "root", "children": [...], "edges": [...], "layoutOptions": {...} }
    """
    if node_modules:
        env = os.environ.copy()
        env['NODE_PATH'] = str(Path(node_modules).resolve())
    else:
        env = os.environ.copy()

    proc = subprocess.run(
        ['node', '-e', _ELK_BOOTSTRAP],
        input=json.dumps(graph_dict),
        capture_output=True, text=True, timeout=timeout,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f'elkjs failed: {proc.stderr}')
    return json.loads(proc.stdout)


def _elk_id(obj):
    """Return a stable, unique ELK node id for a Node, View, or Comment.

    Node and View expose ``.name`` (assumed unique); Comment exposes only
    ``.text`` and has no name, so a unique id is derived from ``id()``.
    """
    name = getattr(obj, 'name', None)
    if name:
        return name
    return f'comment_{id(obj)}'


def _elk_label(obj):
    """Return the label text for a Node, View, or Comment."""
    if not hasattr(obj, 'name'):
        # Comment — just its text
        return getattr(obj, 'text', '')
    label_parts = []
    for s in getattr(obj, 'stereotypes', []) or []:
        label_parts.append(f'\u00ab{s}\u00bb')
    label_parts.append(obj.name)
    return '\n'.join(label_parts)


_SIDE_TO_ELK = {
    'left': 'WEST',
    'right': 'EAST',
    'top': 'NORTH',
    'bottom': 'SOUTH',
}


def _user_port_pos(side, offset, nw, nh):
    """ELK port (x, y) relative to a node so the routed edge endpoint lands on
    the same place the renderer draws the port box (see ``Port.update_pos``).

    Port boxes are 8x8 and sit *outside* the node boundary on the chosen side;
    the port centre is offset 4 px inwards from the port's outer edge.

    A ``None`` offset falls back to 0.5 (middle of the side).
    """
    off = 0.5 if offset is None else float(offset)
    if side == 'left':
        return -8, int(nh * off) - 4
    if side == 'right':
        return nw, int(nh * off) - 4
    if side == 'top':
        return int(nw * off) - 4, -8
    if side == 'bottom':
        return int(nw * off) - 4, nh
    return 0, 0


def _distribute_sides(count, primary, avoid=None):
    """Distribute `count` ports across sides, starting with `primary`.
    
    Returns a list of side names, one per port.
    """
    sides = ['SOUTH', 'EAST', 'WEST', 'NORTH']
    if primary in sides:
        sides.remove(primary)
        sides.insert(0, primary)
    if avoid and avoid in sides:
        sides.remove(avoid)
    
    result = []
    for i in range(count):
        result.append(sides[i % len(sides)])
    return result


def to_elk_json(diagram):
    """Convert a drawille Diagram to ELK JSON.

    Maps every addressable element — regular nodes, comments, and views —
    to ELK child nodes, and edges (including those anchored on a Comment
    or View) to ELK edges with port references.  Arrow styles are passed
    through as custom properties for post-processing.

    Returns
    -------
    (graph_dict, id_map) : tuple
        ``graph_dict`` is the ELK input JSON; ``id_map`` maps each ELK
        child id back to the originating Diagram object so that
        :func:`apply_elk_result` can reposition it.
    """
    children = []
    edges = []
    port_index = {}
    id_map = {}     # elk_id -> Diagram object (Node / Comment / View)

    # Every element that can be an edge endpoint or needs positioning.
    elements = list(diagram.nodes) + list(diagram.comments) + list(diagram.views)

    # Group edges per node/role.  Edges with an explicit user Port
    # (``source_port``/``target_port``) are routed through that port and
    # keep its side; edges without one fall back to the legacy
    # auto-distribution, which picks sides not already claimed by the
    # explicit ports on the same node.
    by_eid_out_auto = defaultdict(list)   # eid -> [edges with no source_port]
    by_eid_in_auto  = defaultdict(list)   # eid -> [edges with no target_port]
    explicit_ports = {}                  # id(user_port) -> (node_eid, port, [(role, edge), ...])

    for e in diagram.edges:
        sid = _elk_id(e.source)
        tid = _elk_id(e.target)
        sp = getattr(e, 'source_port', None)
        tp = getattr(e, 'target_port', None)
        if sp is not None:
            key = id(sp)
            rec = explicit_ports.get(key)
            if rec is None:
                rec = explicit_ports[key] = [sid, sp, []]
            rec[1] = sp
            rec[2].append(('source', e))
        else:
            by_eid_out_auto[sid].append(e)
        if tp is not None:
            key = id(tp)
            rec = explicit_ports.get(key)
            if rec is None:
                rec = explicit_ports[key] = [tid, tp, []]
            rec[2].append(('target', e))
        else:
            by_eid_in_auto[tid].append(e)

    for n in elements:
        eid = _elk_id(n)
        id_map[eid] = n
        node_w = n.w if n.w else 100
        node_h = n.h if n.h else 50
        node_ports = []

        # 1) Explicit user ports on this node.  Multiple ports may share a
        # side; auto-distribute them along the side if any has offset=None,
        # otherwise honour each port's proportional offset (matching what
        # ``Port.update_pos`` will render).
        explicit_by_side = defaultdict(list)  # elk_side -> [(port, [(role, edge), ...])]
        for (port_eid, port, refs) in explicit_ports.values():
            if port_eid != eid:
                continue
            elk_side = _SIDE_TO_ELK.get(port.side, 'WEST')
            explicit_by_side[elk_side].append((port, refs))

        for elk_side, items in explicit_by_side.items():
            n_items = len(items)
            auto_dist = any(p.offset is None for p, _ in items)
            for i, (port, refs) in enumerate(items):
                pid = f'{eid}_p{id(port)}'
                if auto_dist:
                    # Spread evenly along the side using the same rule as
                    # ``_update_port_positions`` so the rendered marker lands
                    # on the same spot the edge endpoint snaps to.
                    if elk_side in ('WEST', 'EAST'):
                        px = -8 if elk_side == 'WEST' else node_w
                        py = (i + 1) * node_h // (n_items + 1) - 4
                    else:  # NORTH / SOUTH
                        py = -8 if elk_side == 'NORTH' else node_h
                        px = (i + 1) * node_w // (n_items + 1) - 4
                else:
                    side_name = port.side
                    px, py = _user_port_pos(side_name, port.offset, node_w, node_h)
                port_props = {'port.side': elk_side, 'port.index': str(i)}
                node_ports.append({
                    'id': pid, 'width': 8, 'height': 8,
                    'x': px, 'y': py,
                    'properties': port_props,
                })
                for role, e in refs:
                    port_index[(eid, e, role)] = pid

        # 2) Auto ports for edges that did not specify an explicit port.
        # Avoid sides already used by explicit ports on this node.
        claimed = set(explicit_by_side.keys())
        out_needed = by_eid_out_auto.get(eid, [])
        in_needed  = by_eid_in_auto.get(eid, [])

        def _auto_geometry(side, count, idx):
            if side == 'SOUTH':
                return (idx + 1) * node_w // (count + 1) - 4, node_h
            if side == 'NORTH':
                return (idx + 1) * node_w // (count + 1) - 4, -8
            if side == 'EAST':
                return node_w, (idx + 1) * node_h // (count + 1) - 4
            if side == 'WEST':
                return -8, (idx + 1) * node_h // (count + 1) - 4
            return 0, 0

        # Local helper that names the loop variable consistently.
        def _add_auto(role, edges, primary_side, avoid_side):
            sides = _distribute_sides(
                len(edges), primary_side,
                avoid=avoid_side if avoid_side else None,
            )
            # Skip sides already used by explicit ports on this node by
            # rotating to the next available side in the default cycle.
            pick = [s for s in sides if s not in claimed] or sides
            for idx, e in enumerate(edges):
                side = pick[idx % len(pick)]
                pid = f'{eid}_{role}_{idx}'
                port_index[(eid, e, role)] = pid
                port_props = {'port.side': side, 'port.index': str(idx)}
                gx, gy = _auto_geometry(side, len(edges), idx)
                node_ports.append({
                    'id': pid, 'width': 8, 'height': 8,
                    'x': gx, 'y': gy,
                    'properties': port_props,
                })

        if out_needed:
            _add_auto('source', out_needed, 'SOUTH',
                      'NORTH' if in_needed else None)
        if in_needed:
            _add_auto('target', in_needed, 'NORTH',
                      'SOUTH' if out_needed else None)

        child = {
            'id': eid,
            'width': n.w if n.w else 100,
            'height': n.h if n.h else 50,
            'labels': [{'text': _elk_label(n), 'properties': {'label.placement': 'INSIDE'}}],
        }
        if node_ports:
            child['ports'] = node_ports
        children.append(child)

    # Build edge entries
    for e in diagram.edges:
        sid = _elk_id(e.source)
        tid = _elk_id(e.target)
        src_pid = port_index.get((sid, e, 'source'), sid)
        tgt_pid = port_index.get((tid, e, 'target'), tid)

        edge = {
            'id': f'{sid}__{tid}__{id(e)}',
            'sources': [src_pid],
            'targets': [tgt_pid],
        }

        # Pass through our styling for post-processing
        props = {}
        if e.source_style:
            props['source_style'] = e.source_style
        if e.target_style:
            props['target_style'] = e.target_style
        if e.line_style:
            props['line_style'] = e.line_style
        if e.label:
            props['edge_label'] = e.label
            edge['labels'] = [{
                'text': e.label,
                'properties': {'label.placement': 'CENTER'}
            }]
        if props:
            edge['properties'] = props

        edges.append(edge)

    # Layout options for UML/SysML-style block diagrams
    layout_options = {
        'elk.algorithm': 'layered',
        'elk.direction': 'DOWN',
        'elk.edgeRouting': 'ORTHOGONAL',
        'elk.layered.spacing.nodeNodeBetweenLayers': '60',
        'elk.spacing.nodeNode': '20',
        'elk.spacing.edgeNode': '15',
        'elk.spacing.portPort': '15',
        'elk.layered.nodePlacement.strategy': 'SIMPLE',
        'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
        'elk.portConstraints': 'FIXED_POS',
        'elk.portAlignment.default': 'CENTER',
        'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
    }

    graph = {
        'id': 'root',
        'layoutOptions': layout_options,
        'children': children,
        'edges': edges,
    }
    return graph, id_map


def _snap_to_node(wp, node):
    """Move a waypoint just outside *node* to the node's edge boundary.

    ELK places edge endpoints at the port center, which can be several
    pixels off the node boundary.  This projects the waypoint onto the
    nearest node edge so arrowheads sit flush.
    """
    x, y = wp
    nx1, ny1 = node.x, node.y
    nx2, ny2 = node.x + node.w, node.y + node.h

    if x < nx1:
        return (nx1, y)
    if x > nx2:
        return (nx2, y)
    if y < ny1:
        return (x, ny1)
    if y > ny2:
        return (x, ny2)
    return wp


def apply_elk_result(diagram, result, id_map=None):
    """Update Diagram element positions and edge waypoints from ELK result.

    Parameters
    ----------
    diagram : Diagram
    result : dict
        ELK layout output.
    id_map : dict, optional
        Mapping ``{elk_id: element}`` as returned by :func:`to_elk_json`.
        When provided, every element (nodes, comments, views) is positioned.
        When omitted, falls back to name-based lookup over ``diagram.nodes``
        only (legacy behaviour).
    """
    # Build lookup: node id → ELK result node
    elk_nodes = {}
    for child in result.get('children', []):
        elk_nodes[child['id']] = child

    if id_map is not None:
        for eid, obj in id_map.items():
            if eid in elk_nodes:
                en = elk_nodes[eid]
                obj.x = int(en['x'])
                obj.y = int(en['y'])
                obj.w = int(en['width'])
                obj.h = int(en['height'])
    else:
        for n in diagram.nodes:
            if n.name in elk_nodes:
                en = elk_nodes[n.name]
                n.x = int(en['x'])
                n.y = int(en['y'])
                n.w = int(en['width'])
                n.h = int(en['height'])

    # Re-position port markers so explicit ``source_port``/``target_port``
    # references resolve to the same spot we'll snap the edge endpoints to.
    update_ports = getattr(diagram, '_update_port_positions', None)
    if callable(update_ports):
        update_ports()

    elk_edges = {}
    for edge in result.get('edges', []):
        elk_edges[edge['id']] = edge

    edge_id_map = {}
    for e in diagram.edges:
        eid = f'{_elk_id(e.source)}__{_elk_id(e.target)}__{id(e)}'
        edge_id_map[eid] = e

    # Update edge waypoints
    for eid, ee in elk_edges.items():
        if eid not in edge_id_map:
            continue
        e = edge_id_map[eid]

        waypoints = []
        for section in ee.get('sections', []):
            sp = section.get('startPoint', {})
            waypoints.append((int(sp['x']), int(sp['y'])))
            for bp in section.get('bendPoints', []):
                waypoints.append((int(bp['x']), int(bp['y'])))
            ep = section.get('endPoint', {})
            waypoints.append((int(ep['x']), int(ep['y'])))

        if waypoints:
            # Clean consecutive duplicates
            cleaned = [waypoints[0]]
            for p in waypoints[1:]:
                if p != cleaned[-1]:
                    cleaned.append(p)

            # Snap first/last waypoint to the relevant port centre for
            # edges that explicitly named one — this is what the renderer
            # actually draws, so the arrowhead sits flush on the marker
            # instead of floating off where ELK routed the line.  For
            # port-less edges fall back to the node-boundary snap.
            sp = getattr(e, 'source_port', None)
            tp = getattr(e, 'target_port', None)
            if sp is not None:
                cleaned[0] = (sp.cx, sp.cy)
            elif len(cleaned) >= 1:
                cleaned[0] = _snap_to_node(cleaned[0], e.source)
            if tp is not None:
                cleaned[-1] = (tp.cx, tp.cy)
            else:
                cleaned[-1] = _snap_to_node(cleaned[-1], e.target)

            e.waypoints = cleaned

    # Post-process: offset overlapping arrowheads at shared source/target nodes.
    # Some layout engines (notably pyelk) may route multiple edges from the same
    # node to the same start point, causing arrowheads to overlap.
    source_starts = {}
    target_ends = {}
    for e in diagram.edges:
        if e.waypoints:
            src_key = (id(e.source), e.waypoints[0])
            source_starts.setdefault(src_key, []).append(e)
            tgt_key = (id(e.target), e.waypoints[-1])
            target_ends.setdefault(tgt_key, []).append(e)

    # Diamond width is ARROW_SIZE * 0.7; use 2x that for separation
    from diagramboxes.primitives import ARROW_SIZE
    diamond_width = ARROW_SIZE * 0.7
    offset = diamond_width * 2
    for (node_id, pt), edges in source_starts.items():
        if len(edges) > 1:
            for i, e in enumerate(edges):
                shift = (i - (len(edges) - 1) / 2) * offset
                ox, oy = e.waypoints[0]
                e.waypoints[0] = (int(ox + shift), oy)
                if len(e.waypoints) >= 2:
                    nx, ny = e.waypoints[1]
                    e.waypoints[1] = (int(nx + shift), ny)

    for (node_id, pt), edges in target_ends.items():
        if len(edges) > 1:
            for i, e in enumerate(edges):
                shift = (i - (len(edges) - 1) / 2) * offset
                ox, oy = e.waypoints[-1]
                e.waypoints[-1] = (int(ox + shift), oy)
                if len(e.waypoints) >= 2:
                    px, py = e.waypoints[-2]
                    e.waypoints[-2] = (int(px + shift), py)


def layout_with_elk(diagram, node_modules=None):
    """Full pipeline: convert Diagram → ELK JSON → run elkjs → apply results."""
    graph, id_map = to_elk_json(diagram)
    result = elk_layout(graph, node_modules=node_modules)
    apply_elk_result(diagram, result, id_map=id_map)
    return diagram
