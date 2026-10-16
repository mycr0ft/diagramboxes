"""RED: UML 2.5.1 chapter 19 deployment notation (Delligatti's corpus
stops at SysML v1.3; these criteria are quoted verbatim from the UML
2.5.1 formal spec text layer, ch19 Notation sections).

Criteria ('formal/2017-12-05'):
- 19.2.4 'DeployedTargets are shown as a perspective view of cube
  labeled with the name ... System elements deployed on a
  DeployedTarget, and Deployments that connect them, may be drawn
  inside the perspective cube.'
- 19.3.4 'An Artifact is presented using an ordinary Class rectangle
  with the keyword artifact.'
- 19.2.8+ 'Deployments are depicted using the same dashed line notation
  as Dependency' with the 'deploy' keyword.
- 19.3.x 'A Manifestation is notated ... as a dashed line with the
  keyword manifest.'
- 19.4.4 'CommunicationPaths between Nodes are depicted using the same
  as normal Association links.'
"""
import os
import unittest

import diagramboxes as db
from diagramboxes import Diagram, DASHED, OPEN


def _svg():
    d = Diagram()
    return d, d.render_svg()


class TestNodeCube(unittest.TestCase):
    def criteria_node_is_perspective_cube(self):
        return 'perspective view of cube'

    def test_node_cube_draws_offset_3d_facets(self):
        d = Diagram()
        n = d.node(':app-server')          # an instance-level Node
        svg = d.render_svg()
        self.assertTrue('nodecube' in svg, 'cube glyph marker missing')
        # the cube = the box + the top and right facet polylines: the
        # group class marks all three facet edges
        self.assertEqual(svg.count('polyline'), 3)

    def test_node_keywords(self):
        d = Diagram()
        d.node('server', kinds=('device',))
        svg = d.render_svg()
        self.assertIn('\u00abdevice\u00bb', svg)

    def test_deployed_elements_draw_inside_the_cube(self):
        d = Diagram()
        n = d.node(':app-server')
        art = d.artifact('order-handler.war')
        n.add_child(art)
        svg = d.render_svg()
        self.assertIn('order-handler.war', svg)
        txt = d.render()
        self.assertIn('order-handler.war', txt)


class TestArtifact(unittest.TestCase):
    def test_artifact_is_class_rectangle_with_keyword(self):
        d = Diagram()
        d.artifact('order-handler.war')
        svg = d.render_svg()
        self.assertIn('\u00abartifact\u00bb', svg)


class TestDeployment(unittest.TestCase):
    def test_deploy_is_dashed_dependency_with_keyword(self):
        d = Diagram()
        art = d.artifact('order-handler.war')
        tgt = d.node(':app-server')
        e = d.deploy(art, tgt)
        self.assertEqual(e.line_style, DASHED)
        svg = d.render_svg()
        self.assertIn('\u00abdeploy\u00bb', svg)

    def test_manifest_is_dashed_with_keyword(self):
        d = Diagram()
        art = d.artifact('order-handler.war')
        comp = d.add_node('Order Entry')
        d.manifest(art, comp)
        svg = d.render_svg()
        self.assertIn('\u00abmanifest\u00bb', svg)

    def test_communication_path_is_plain_association(self):
        d = Diagram()
        a = d.node('server1')
        b = d.node('server2')
        d.add_edge(a, b)
        e = d.edges[0]
        self.assertEqual(e.line_style, db.SOLID)


if __name__ == '__main__':
    unittest.main()