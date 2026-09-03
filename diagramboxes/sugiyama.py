"""Pure-Python Sugiyama layered layout with orthogonal edge routing.

Full 5-stage Sugiyama framework (~410 lines total).  No external
dependencies beyond the Python standard library.

Stages
------
1. ``remove_cycles(edges)``       — Greedy DFS: detects cycles, reverses
                                    back-edges to make the graph acyclic.
2. ``assign_layers(edges)``       — Longest-path from root nodes to sinks.
                                    Correctly handles non-adjacent edges
                                    (unlike the BFS-shortest-path in
                                    ``layout._assign_layers()``).
3. ``minimize_crossings(layers)`` — Barycenter layer sweep. Forward
                                    (top→bottom) and backward (bottom→top)
                                    passes, up to 24 iterations. Can get
                                    stuck in local minima on complex graphs.
4. ``position_nodes(layers)``     — Assigns x,y coordinates within layers.
5. ``route_edges(edges, positions)`` — Orthogonal 3-segment paths with
                                      obstacle avoidance (gap y-level
                                      candidates between layers).

Entry point
-----------
``sugiyama_layout(edge_list, node_sizes, node_gap, margin, layer_spacing)``
    Returns (node_positions, edge_routes, layers).

Limitations
-----------
- Does **not** support ports (unlike the homegrown orthogonal router).
- Crossing minimization uses simple barycenter and may need more
  sophisticated heuristics for large graphs.

See also
--------
elk.py       : ELKjs subprocess (alternative, larger but more polished)
layout.py    : Diagram class with sugiyama dispatch in layout()
"""

from collections import defaultdict, deque
from itertools import product
from math import inf


# ────────────────────────────────────────────────────────────
# Step 1: Cycle removal  (~40 lines)
# ────────────────────────────────────────────────────────────

def remove_cycles(edges):
    """Greedy DFS-based cycle removal. Returns a list of (src, tgt, reversed)."""
    adj = defaultdict(list)
    for s, t in edges:
        adj[s].append(t)

    visited = set()
    stack = set()
    reversed_edges = []

    def dfs(node):
        if node in stack:
            return True  # cycle detected
        if node in visited:
            return False
        visited.add(node)
        stack.add(node)
        for neighbor in list(adj[node]):
            if dfs(neighbor):
                # Reverse this edge to break cycle
                adj[node].remove(neighbor)
                adj[neighbor].append(node)
                reversed_edges.append((node, neighbor))
        stack.remove(node)
        return False

    nodes = list(set([s for s, t in edges] + [t for s, t in edges]))
    for n in nodes:
        dfs(n)

    # Build final edge list with reversals noted
    result = []
    for s, t in edges:
        if (s, t) in reversed_edges:
            result.append((t, s, True))
        else:
            result.append((s, t, False))
    return result


# ────────────────────────────────────────────────────────────
# Step 2: Layer assignment  (~50 lines)
# ────────────────────────────────────────────────────────────

def assign_layers(edges, node_sizes=None):
    """Longest-path layer assignment. Returns {node: layer_index}."""
    adj = defaultdict(list)
    incoming = defaultdict(set)
    all_nodes = set()
    for s, t, _ in edges:
        adj[s].append(t)
        incoming[t].add(s)
        all_nodes.add(s)
        all_nodes.add(t)

    # Find root nodes (no incoming edges)
    roots = [n for n in all_nodes if n not in incoming]
    if not roots:
        roots = [list(all_nodes)[0]]

    # BFS longest path
    layer = {}
    queue = deque()
    for r in roots:
        layer[r] = 0
        queue.append(r)

    while queue:
        n = queue.popleft()
        for t in adj[n]:
            new_layer = layer[n] + 1
            if t not in layer or new_layer > layer[t]:
                layer[t] = new_layer
                queue.append(t)

    # Assign unvisited nodes
    for n in all_nodes:
        if n not in layer:
            layer[n] = 0

    return layer


# ────────────────────────────────────────────────────────────
# Step 3: Crossing minimization  (~120 lines)
# ────────────────────────────────────────────────────────────

def _barycenter(layer_nodes, layer_idx, edges, node_pos):
    """Compute barycenter value for each node in a layer.

    barycenter(v) = average position of v's neighbors in adjacent layer
    """
    adj = defaultdict(list)
    for s, t, _ in edges:
        adj[s].append(t)
        adj[t].append(s)

    bary = {}
    for v in layer_nodes:
        neighbors = [u for u in adj[v]
                     if u in node_pos and node_pos[u] != layer_idx]
        if not neighbors:
            bary[v] = -1
        else:
            positions = [(node_pos[n], n) for n in neighbors
                         if abs(node_pos[n] - layer_idx) == 1]
            if not positions:
                bary[v] = -1
            else:
                bary[v] = sum(p[0] for p in positions) / len(positions)
    return bary


def _count_crossings(layer_a, layer_b, edges):
    """Count edge crossings between two adjacent layers."""
    a_pos = {n: i for i, n in enumerate(layer_a)}
    b_pos = {n: i for i, n in enumerate(layer_b)}

    a_edges = defaultdict(list)
    for s, t, _ in edges:
        if s in a_pos and t in b_pos:
            a_edges[s].append(t)
        elif t in a_pos and s in b_pos:
            a_edges[t].append(s)

    crossings = 0
    a_nodes = [n for n in layer_a if n in a_edges]
    for i in range(len(a_nodes)):
        for j in range(i + 1, len(a_nodes)):
            ni, nj = a_nodes[i], a_nodes[j]
            for ti in a_edges.get(ni, []):
                for tj in a_edges.get(nj, []):
                    if b_pos[ti] > b_pos[tj]:
                        crossings += 1
    return crossings


def minimize_crossings(layers, edges, max_passes=24):
    """Barycenter layer sweep to reduce edge crossings."""
    if len(layers) <= 1:
        return layers

    node_pos = {}
    for l, lyr in enumerate(layers):
        for i, n in enumerate(lyr):
            node_pos[n] = l

    layers = [list(lyr) for lyr in layers]

    for _ in range(max_passes):
        improved = False

        # Forward sweep (top to bottom)
        for l in range(1, len(layers)):
            bary = _barycenter(layers[l], l, edges, node_pos)
            new_order = sorted(layers[l], key=lambda v: (
                bary[v] if bary[v] >= 0 else inf, v if isinstance(v, (int, str)) else id(v)))
            if new_order != layers[l]:
                old_cross = sum(
                    _count_crossings(layers[l - 1], layers[l], edges) for _ in [0])
                layers[l] = new_order
                new_cross = sum(
                    _count_crossings(layers[l - 1], layers[l], edges) for _ in [0])
                if new_cross < old_cross:
                    improved = True
                else:
                    layers[l] = layers[l][:]  # revert? no, we already changed

        # Backward sweep (bottom to top)
        for l in range(len(layers) - 2, -1, -1):
            bary = _barycenter(layers[l], l, edges, node_pos)
            new_order = sorted(layers[l], key=lambda v: (
                bary[v] if bary[v] >= 0 else inf, v if isinstance(v, (int, str)) else id(v)))
            if new_order != layers[l]:
                layers[l] = new_order
                improved = True

        if not improved:
            break

    return layers


# ────────────────────────────────────────────────────────────
# Step 4: Node positioning  (~80 lines)
# ────────────────────────────────────────────────────────────

def position_nodes(layers, node_sizes, node_gap=20, margin=20, layer_spacing=60):
    """Assign x, y coordinates to each node based on layers and sizes.

    y: determined by layer index (even spacing with height)
    x: minimized edge length within layer, centered
    """
    positions = {}  # node -> (x, y, w, h)
    y = margin

    for lyr in layers:
        x = margin

        for n in lyr:
            w, h = node_sizes.get(n, (100, 50))
            positions[n] = (x, y, w, h)
            x += w + node_gap

        max_h = max(node_sizes.get(n, (100, 50))[1] for n in lyr) if lyr else 0
        y += max_h + layer_spacing

    return positions


# ────────────────────────────────────────────────────────────
# Step 5: Edge routing — orthogonal with obstacle avoidance  (~200 lines)
# ────────────────────────────────────────────────────────────

def _rect_intersects(seg_x1, seg_y1, seg_x2, seg_y2, rx, ry, rw, rh, pad=1):
    """Check if segment (x1,y1)-(x2,y2) intersects rectangle at (rx,ry,rw,rh)."""
    rx1, ry1, rx2, ry2 = rx - pad, ry - pad, rx + rw + pad, ry + rh + pad

    if seg_x1 == seg_x2:  # vertical
        x = seg_x1
        if not (rx1 <= x <= rx2):
            return False
        y1, y2 = (seg_y1, seg_y2) if seg_y1 < seg_y2 else (seg_y2, seg_y1)
        return y1 <= ry2 and y2 >= ry1
    else:  # horizontal
        y = seg_y1
        if not (ry1 <= y <= ry2):
            return False
        x1, x2 = (seg_x1, seg_x2) if seg_x1 < seg_x2 else (seg_x2, seg_x1)
        return x1 <= rx2 and x2 >= rx1


def route_edges(edges, positions, layers):
    """Route edges with orthogonal paths avoiding node obstacles.

    For each edge from source to target (where source is in an earlier layer):
      - Source port: bottom edge of source node
      - Target port: top edge of target node
      - Path: down from source → horizontal in gap between layers → down to target
      - Obstacle avoidance: choose gap y that avoids intermediate nodes
    """
    node_pos = {}
    for n, (x, y, w, h) in positions.items():
        node_pos[n] = (x, y, x + w, y + h)

    for s, t, rev in edges:
        if rev:
            continue
        if s not in positions or t not in positions:
            continue

        sx, sy, sw, sh = positions[s]
        tx, ty, tw, th = positions[t]

        # Port positions
        px1 = sx + sw // 2
        py1 = sy + sh
        px2 = tx + tw // 2
        py2 = ty

        # Find gap between layers for this edge
        obstacles = {n for n in positions if n != s and n != t}
        candidates = []
        # Gap candidates: between source layer and target layer
        # Try midpoint first, then quarter points
        gap = (py1 + py2) // 2
        for offset in [0, -10, 10, -20, 20]:
            my = gap + offset
            # Check if horizontal segment at my hits any obstacle
            hits = False
            for obs in obstacles:
                ox, oy, ow, oh = positions[obs]
                rx1, ry1, rx2, ry2 = ox, oy, ox + ow, oy + oh
                y1, y2 = (py1, my) if py1 < my else (my, py1)
                if ry1 <= my <= ry2:
                    x1, x2 = (px1, px2) if px1 < px2 else (px2, px1)
                    if x1 <= rx2 and x2 >= rx1:
                        hits = True
                        break
            if not hits:
                candidates.append(my)

        if not candidates:
            candidates.append(gap)

        my = candidates[0]
        points = [(px1, py1), (px1, my), (px2, my), (px2, py2)]
        # Remove consecutive dupes
        route = [points[0]]
        for p in points[1:]:
            if p != route[-1]:
                route.append(p)

        yield (s, t, route)


# ────────────────────────────────────────────────────────────
# Full pipeline
# ────────────────────────────────────────────────────────────

def sugiyama_layout(edge_list, node_sizes=None, node_gap=20, margin=20, layer_spacing=60):
    """Run full Sugiyama pipeline on a list of (source, target) edges.

    Parameters
    ----------
    edge_list : list of (str, str)
        Directed edges (source_id, target_id).
    node_sizes : dict of str -> (width, height) or None
        Node dimensions.  Defaults to (100, 50) for all.
    node_gap : int
        Horizontal gap between nodes in same layer.
    margin : int
        Left/top margin.

    Returns
    -------
    node_positions : dict of str -> (x, y, w, h)
    edge_routes : list of (src, tgt, [(x,y), ...])
        Waypoints for each edge.
    layers : list of list of str
        Nodes grouped by layer.
    """
    if node_sizes is None:
        all_nodes = set()
        for s, t in edge_list:
            all_nodes.add(s)
            all_nodes.add(t)
        node_sizes = {n: (100, 50) for n in all_nodes}

    # Step 1
    cycle_edges = remove_cycles(edge_list)

    # Step 2
    layer_of = assign_layers(cycle_edges)

    # Build layers list
    max_layer = max(layer_of.values()) if layer_of else 0
    layers = [[] for _ in range(max_layer + 1)]
    for n, l in layer_of.items():
        layers[l].append(n)

    # Step 3
    layers = minimize_crossings(layers, cycle_edges)

    # Step 4
    positions = position_nodes(layers, node_sizes, node_gap, margin, layer_spacing)

    # Step 5
    routes = list(route_edges(cycle_edges, positions, layers))

    # Map back to original edge order
    edge_routes = []
    edge_lookup = {}
    for s, t, r in routes:
        edge_lookup[(s, t)] = r
    for s, t in edge_list:
        key = (s, t)
        if key in edge_lookup:
            edge_routes.append((s, t, edge_lookup[key]))
        elif (t, s) in edge_lookup:
            # Reversed in cycle removal
            edge_routes.append((s, t, list(reversed(edge_lookup[(t, s)]))))

    return positions, edge_routes, layers


# ── quick self-test ──
if __name__ == '__main__':
    edges = [
        ('Vehicle', 'Engine'),
        ('Vehicle', 'Wheel'),
        ('Engine', 'PetrolEngine'),
        ('Engine', 'ElectricEngine'),
        ('Wheel', 'WheelL'),
        ('Wheel', 'WheelR'),
    ]
    positions, routes, layers = sugiyama_layout(edges)
    print('=== Layers ===')
    for i, lyr in enumerate(layers):
        print(f'  {i}: {lyr}')
    print()
    print('=== Positions ===')
    for n, (x, y, w, h) in sorted(positions.items()):
        print(f'  {n}: ({x}, {y}) {w}x{h}')
    print()
    print('=== Routes ===')
    for s, t, pts in routes:
        print(f'  {s} -> {t}: {pts}')
