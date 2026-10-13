# Liebherr LTM 1060

- Title: LIEBHERR 1060
- Creator: bacakmar
- Source: https://sketchfab.com/3d-models/liebherr-1060-bb7adad7dacd464b8fa77868710af906
- License: Creative Commons Attribution 4.0 International (CC BY 4.0)
- License URL: https://creativecommons.org/licenses/by/4.0/
- Changes: Original source retained. A derived OBJ is centered at ground level,
  scaled from metres to centimetres, and rotated from Y-up to Z-up, including
    normals. Imported solid-color materials use the source diffuse colors.
    The derived model is split into chassis, upper assembly, hook block, and six
    wheels. Twelve fixed cable-strip faces are replaced with six adjustable lines.

Retain credit, the source and license links, and an indication of subsequent
changes when distributing this asset or a project containing it.

## Controls & Multi-Crane Features

- **W / S:** Drive Mobile Crane Forward / Backward (swept kinematic motion with clearance over flat terrain)
- **A / D:** Steer Mobile Crane Left / Right (wheels physically rotate and steer)
- **Q / E:** Boom Elevation / Pitch Angle (raises/lowers boom diagonal angle to ground from $-74^\circ$ down in resting saddle up to $+15^\circ$ / $\approx 77.6^\circ$ near vertical)
- **R / F:** Telescopic Boom Length (smoothly telescopes all 5 nested boom stages in and out from fully retracted $\approx 8.96\text{ m}$ resting length up to original modeled $\approx 40.58\text{ m}$ length with zero gaps)
- **Up / Down Arrows:** Lift / Lower Hook Block (hoist cables dynamically track boom tip and hook block across all boom angles and lengths)
- **Left / Right Arrows:** Rotate Turntable / Upper Assembly
- **C:** Switch Controls & Camera between Mobile Crane and Stationary Tower Crane
- **Right Mouse Button + Drag:** Orbit Camera (both Mobile Crane and Tower Crane have full high-angle orbital cameras)
- **Mouse Wheel:** Zoom Camera In / Out

The movement functions passed focused Unreal runtime checks for hook travel,
hoist lines, upper rotation, driving, steering, wheel spin, camera limits, and
collision stopping. Tests run on transient actors and verify that the placed
crane's pose, state, and level actor set remain unchanged after cleanup.

Source preparation uses prepare_model.py and rig_model.py. The mesh analysis
dependencies are installed locally under Saved/LiebherrTools. Original source
files are retained under model; articulated exports are under model/Parts.