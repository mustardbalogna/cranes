import json
import math

import unreal


def close(actual, expected, label, tolerance=0.05):
    if not math.isclose(actual, expected, abs_tol=tolerance):
        raise AssertionError(f"{label}: expected {expected}, received {actual}")


def copy_vector(value):
    return unreal.Vector(value.x, value.y, value.z)


def copy_rotator(value):
    return unreal.Rotator(pitch=value.pitch, yaw=value.yaw, roll=value.roll)


def component_poses(actor):
    return {
        component.get_name(): (
            copy_vector(component.get_editor_property("relative_location")),
            copy_rotator(component.get_editor_property("relative_rotation")),
            copy_vector(component.get_editor_property("relative_scale3d")),
        )
        for component in actor.get_components_by_class(unreal.SceneComponent)
    }


def check_pose(before, after, label):
    for index, axes in enumerate((("x", "y", "z"), ("pitch", "yaw", "roll"), ("x", "y", "z"))):
        for axis in axes:
            close(getattr(after[index], axis), getattr(before[index], axis), f"{label}: {axis}")


def test_controls():
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    placed_actor = next(
        item for item in subsystem.get_all_level_actors()
        if item.get_actor_label() == "Liebherr1060_Mobile"
    )
    placed_pose = (
        copy_vector(placed_actor.get_actor_location()),
        copy_rotator(placed_actor.get_actor_rotation()),
        copy_vector(placed_actor.get_actor_scale3d()),
    )
    poses = component_poses(placed_actor)
    variable_names = ["HookDrop", "WheelAngle", "SteeringAngle", "CameraPitch", "CameraYaw", "CameraDistance"]
    variables = {name: placed_actor.get_editor_property(name) for name in variable_names}
    level_actors = {item.get_path_name() for item in subsystem.get_all_level_actors()}
    actor = None
    obstacle = None
    results = []
    try:
        actor = subsystem.spawn_actor_from_class(
            placed_actor.get_class(), unreal.Vector(5000, 1000, 150), transient=True
        )
        if not actor:
            raise RuntimeError("Unable to create the temporary control-test crane")
        actor.set_actor_label("Liebherr_ControlTest_Crane")
        components = {
            component.get_name(): component
            for component in actor.get_components_by_class(unreal.SceneComponent)
        }
        if not isinstance(actor.get_editor_property("root_component"), unreal.BoxComponent):
            raise AssertionError("Driving root must be a BoxComponent")
        hook = components["Hook"]
        upper = components["UpperPivot"]
        chassis = components["Chassis"]
        actor.call_method("LiftHook", (1.0, 1.0))
        close(hook.get_editor_property("relative_location").z, 3515.0, "Hook lowers 120 cm")
        for index in range(1, 7):
            cable = components[f"Cable{index:02d}"]
            location = cable.get_editor_property("relative_location")
            scale = cable.get_editor_property("relative_scale3d")
            close(location.z + scale.z * 50, 3857.5, "Hoist anchor remains fixed")
            close(location.z - scale.z * 50, 3546.0, "Hoist bottom follows load block")
        results.append("hook and all six hoist lines")

        chassis_rotation = chassis.get_editor_property("relative_rotation")
        actor.call_method("RotateUpper", (1.0, 1.0))
        close(upper.get_editor_property("relative_rotation").yaw, 15.0, "Upper turns 15 degrees")
        close(chassis.get_editor_property("relative_rotation").yaw, chassis_rotation.yaw, "Chassis stays fixed")
        actor.call_method("RotateUpper", (1.0, -1.0))
        results.append("upper rotation independent of chassis")

        actor.call_method("LiftHook", (100.0, 1.0))
        close(actor.get_editor_property("HookDrop"), 3650.0, "Lower hook limit")
        actor.call_method("LiftHook", (100.0, -1.0))
        close(actor.get_editor_property("HookDrop"), -120.0, "Upper hook limit")
        actor.call_method("LiftHook", (1.0, 1.0))
        results.append("hook travel limits")

        before = actor.get_actor_location()
        actor.call_method("DriveTruck", (1.0, 1.0))
        after = actor.get_actor_location()
        distance = math.dist((before.x, before.y, before.z), (after.x, after.y, after.z))
        close(distance, 400.0, "Truck drives 400 cm")
        expected_angle = -distance / 77.01125 * 57.295779513
        close(actor.get_editor_property("WheelAngle"), expected_angle, "Wheels match travel")
        actor.call_method("SteerTruck", (1.0, 1.0, 1.0))
        close(actor.get_actor_rotation().yaw, 25.0, "Truck steers")
        close(components["Wheel05"].get_editor_property("relative_rotation").yaw, 20.0, "Front wheel steers")
        results.append("driving, steering, and wheel travel")

        actor.call_method("ZoomCamera", (-10000.0,))
        close(actor.get_editor_property("CameraDistance"), 600.0, "Near zoom limit")
        actor.call_method("ZoomCamera", (20000.0,))
        close(actor.get_editor_property("CameraDistance"), 7000.0, "Far zoom limit")
        actor.call_method("OrbitCamera", (0.0, 10000.0))
        close(actor.get_editor_property("CameraPitch"), -5.0, "Camera upper pitch limit")
        actor.call_method("OrbitCamera", (0.0, -10000.0))
        close(actor.get_editor_property("CameraPitch"), -65.0, "Camera lower pitch limit")
        results.append("camera orbit and zoom limits")

        actor.set_actor_location(unreal.Vector(5000, 1000, 150), False, True)
        actor.set_actor_rotation(unreal.Rotator(), True)
        before = actor.get_actor_location()
        obstacle = subsystem.spawn_actor_from_class(
            unreal.StaticMeshActor, unreal.Vector(before.x + 800, before.y, before.z), transient=True
        )
        obstacle.set_actor_label("Liebherr_ControlTest_Obstacle")
        obstacle_mesh = obstacle.get_components_by_class(unreal.StaticMeshComponent)[0]
        obstacle_mesh.set_static_mesh(unreal.load_asset("/Engine/BasicShapes/Cube"))
        obstacle_mesh.set_collision_profile_name("BlockAll")
        obstacle.set_actor_scale3d(unreal.Vector(2, 5, 5))
        actor.call_method("DriveTruck", (5.0, 1.0))
        after = actor.get_actor_location()
        traveled = after.x - before.x
        if not 0 <= traveled <= 252:
            raise AssertionError(f"Truck passed through obstacle: {traveled} cm")
        settling_distance = math.inf
        for attempt in range(4):
            position = actor.get_actor_location()
            angle = actor.get_editor_property("WheelAngle")
            actor.call_method("DriveTruck", (1.0, 1.0))
            settled = actor.get_actor_location()
            settling_distance = math.dist(
                (position.x, position.y, position.z), (settled.x, settled.y, settled.z)
            )
            expected_change = -settling_distance / 77.01125 * 57.295779513
            close(actor.get_editor_property("WheelAngle") - angle, expected_change, "Wheel spin follows collision settling")
            if settling_distance < 0.1:
                break
        if settling_distance >= 0.1:
            raise AssertionError(f"Blocked truck did not stop: {settling_distance} cm")
        results.append("collision sweep and blocked wheel stop")
    finally:
        cleanup_errors = []
        for temporary in (obstacle, actor):
            if temporary and not subsystem.destroy_actor(temporary):
                cleanup_errors.append(temporary.get_path_name())
        if cleanup_errors:
            raise RuntimeError(f"Unable to remove temporary test actors: {cleanup_errors}")
        check_pose(placed_pose, (
            placed_actor.get_actor_location(),
            placed_actor.get_actor_rotation(),
            placed_actor.get_actor_scale3d(),
        ), "Placed crane transform unchanged")
        current_poses = component_poses(placed_actor)
        if current_poses.keys() != poses.keys():
            raise AssertionError("The placed crane's component hierarchy changed")
        for name, pose in poses.items():
            check_pose(pose, current_poses[name], f"Placed {name} pose unchanged")
        for name, value in variables.items():
            close(placed_actor.get_editor_property(name), value, f"Placed {name} state unchanged")
        current_actors = {item.get_path_name() for item in subsystem.get_all_level_actors()}
        if current_actors != level_actors:
            raise AssertionError("The level actor set changed during the control test")
    results.append("isolated test cleanup and placed crane unchanged")
    unreal.log("LIEBHERR_CONTROL_TESTS_PASSED: " + json.dumps(results))


test_controls()