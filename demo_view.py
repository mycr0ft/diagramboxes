#!/usr/bin/env python3
"""Demo of imported packages, nesting, rounded nodes, and container styles.

Shows:
  - Imported package (Powertrain, dashed border)
  - Regular view (VehicleDynamics, solid border)
  - Square-cornered node (ECU, like a part definition)
  - Rounded-corner node (SensorCluster, like a part usage)
  - Both nested inside VehicleDynamics
  - Unowned membership (open circle) from Powertrain to ECU
  - Owned membership (crossed circle) from VWDynamics to SensorCluster
"""

from diagramboxes import Diagram, FILLED

d = Diagram()

ecu = d.add_node('ECU', ['block'],
    attributes=['+ voltage : float', '+ temp : float'])
sensor = d.add_node('SensorCluster', ['block'], rounded=True)
occ = d.add_node('OccurrenceRef', ['occurrence'], rounded=True, dashed=True)

imported = d.add_view('Powertrain', ['package'], dashed=True)
vw = d.add_view('VehicleDynamics', ['view'])
vw.add_child(sensor)

d.uncontain(imported, ecu, label='unowned')
d.contain(vw, sensor, label='owned')
d.depend(occ, ecu, label='refs')

print(d.render(routing='orthogonal', node_gap=20))
