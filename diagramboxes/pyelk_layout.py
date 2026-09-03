"""pyelk integration — pure-Python ELK layout via the ``pyelk`` package.

Bridges to the Eclipse Layout Kernel (ELK) layered algorithm without any
Node.js or JVM subprocess.  ``pyelk`` is a pure-Python port of elkjs, so the
graph format and result format are identical — this module reuses the
ELK-JSON conversion (``to_elk_json``) and result-mapping (``apply_elk_result``)
from :mod:`diagramboxes.elk` and only swaps the layout backend.

The pipeline:

1. ``to_elk_json(diagram)``  — converts Diagram -> ELK JSON  (from ``elk.py``)
2. ``ELK().layout(graph)``   — pure-Python layout via pyelk
3. ``apply_elk_result(...)`` — maps positions/waypoints back (from ``elk.py``)

Requires
--------
pip install pyelk

See also
--------
elk.py        : ELKjs subprocess variant (needs Node.js + ``npm install elkjs``)
sugiyama.py   : pure-Python Sugiyama alternative
layout.py     : homegrown orthogonal router (default)
"""

from diagramboxes.elk import to_elk_json, apply_elk_result


def layout_with_pyelk(diagram):
    """Full pipeline: convert Diagram -> ELK JSON -> run pyelk -> apply results.

    Like :func:`diagramboxes.elk.layout_with_elk` but uses the pure-Python ``pyelk``
    package instead of spawning a Node.js subprocess.  No external runtime is
    required — only ``pip install pyelk``.

    Raises
    ------
    ImportError
        If ``pyelk`` is not installed.
    """
    try:
        from pyelk import ELK
    except ImportError as exc:
        raise ImportError(
            "pyelk is required for routing='pyelk'.  Install it with:\n"
            "    pip install pyelk"
        ) from exc

    graph, id_map = to_elk_json(diagram)
    result = ELK().layout(graph)
    apply_elk_result(diagram, result, id_map=id_map)
    return diagram
