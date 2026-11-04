"""Run during PIE with Unreal's Python console: py "<absolute path to this file>".

C cycles outside, side, overhead, boom-down, and driver-windshield views.
Each remembers its mount-relative pose, including G flight and RMB adjustments.
G resumes following without snapping; C while flying saves and exits flight.
The boom camera follows extension/pitch/slew, but not the lowering hook.

The final rendered-camera checks finish asynchronously over several frames.
Temporary actor/component poses, camera memories, controls, and ticking restore.
"""

import json
import math

import unreal


CAMERA_TEST_RESULT = None
POSE_NAMES = ("Outside", "Side", "Aerial", "Boom", "Driver")
MOUNT_NAMES = ("CameraRig", "SideCameraMount", "AerialCamera", "BoomTipCameraMount", "CabCamera")


def close(actual, expected, label, tolerance=0.05):
    if not math.isclose(actual, expected, abs_tol=tolerance):
        raise AssertionError(f"{label}: expected {expected}, received {actual}")


def vector_tuple(value):
    return value.x, value.y, value.z


def rotation_tuple(value):
    return value.pitch, value.yaw, value.roll


def camera_pose(camera):
    return vector_tuple(camera.get_world_location()), rotation_tuple(camera.get_world_rotation())


def relative_pose(component):
    return (
        vector_tuple(component.get_editor_property("relative_location")),
        rotation_tuple(component.get_editor_property("relative_rotation")),
    )


def check_pose(actual, expected, label):
    for index, (actual_group, expected_group) in enumerate(zip(actual, expected)):
        for actual_value, expected_value in zip(actual_group, expected_group):
            if index == 1:
                actual_value = (actual_value - expected_value + 180.0) % 360.0 - 180.0
                expected_value = 0.0
            close(actual_value, expected_value, label)


class CameraTests:
    def __init__(self):
        self.world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
        if not self.world:
            raise RuntimeError("Start Play-In-Editor before running camera tests")
        crane_class = unreal.load_class(None, "/Game/Liebherr1060/BP_MobileCrane.BP_MobileCrane_C")
        actors = unreal.GameplayStatics.get_all_actors_of_class(self.world, crane_class)
        if len(actors) != 1:
            raise RuntimeError(f"Expected one live mobile crane, received {len(actors)}")
        self.actor = actors[0]
        self.camera = self.actor.get_editor_property("CraneCamera")
        self.poses = [
            (component, component.get_relative_transform())
            for component in self.actor.get_components_by_class(unreal.SceneComponent)
        ]
        self.transform = self.actor.get_actor_transform()
        self.actor.call_method("SaveCameraPose")
        self.memories = [
            self.actor.get_editor_property(name + "CameraPose") for name in POSE_NAMES
        ]
        names = (
            "CameraMode", "FreeCamActive", "CameraPitch", "CameraYaw", "CameraDistance",
            "BoomPitch", "BoomExtensionFraction", "HookDrop",
        )
        self.variables = {name: self.actor.get_editor_property(name) for name in names}
        self.ticking = self.actor.is_actor_tick_enabled()
        self.results = []
        self.callback = None

    def select(self, mode):
        self.actor.call_method("SelectCameraMode", (mode,))

    def run(self):
        actor, camera = self.actor, self.camera
        actor.set_actor_tick_enabled(False)
        actor.set_actor_location(unreal.Vector(50000, 50000, 5000), False, True)
        active = [
            component.get_name() for component in actor.get_components_by_class(unreal.CameraComponent)
            if component.is_active()
        ]
        if active != ["CraneCamera"]:
            raise AssertionError(f"Ambiguous active cameras: {active}")
        for mode, name in enumerate(MOUNT_NAMES):
            self.select(mode)
            if camera.get_attach_parent().get_name() != name:
                raise AssertionError(f"Camera {mode} did not attach to {name}")
            before = relative_pose(camera)
            actor.call_method("ReceiveTick", (0.016,))
            check_pose(relative_pose(camera), before, "Idle tick preserves the selected view")
        self.results.append("five distinct mounts; only the rendering camera is active")

        self.select(3)
        camera.set_relative_rotation(unreal.Rotator(), False, True)
        close(camera.get_forward_vector().z, -1.0, "Boom camera points straight down")
        mount = camera.get_attach_parent()
        before = vector_tuple(mount.get_world_location())
        actor.call_method("LiftHook", (0.1, 1.0))
        check_pose(camera_pose(mount), (before, rotation_tuple(mount.get_world_rotation())),
                   "Lowering the hook does not lower the boom camera")
        actor.call_method("LiftHook", (0.1, -1.0))
        for extension in (0.0, 0.5, 1.0):
            actor.call_method("ExtendBoom", (1000.0, -1.0))
            actor.call_method("ExtendBoom", (1.0, extension / actor.get_editor_property("BoomExtendSpeed")))
            hook = actor.get_editor_property("Hook").get_editor_property("relative_location")
            position = mount.get_editor_property("relative_location")
            close(position.x, hook.x + 80.0, "Boom camera tracks tip X")
            close(position.y, hook.y - 100.0, "Boom camera clears the sheaves")
            close(position.z, hook.z + actor.get_editor_property("HookDrop") + 405.389,
                  "Boom camera stays above the boom tip")
            close(camera.get_forward_vector().z, -1.0, "Extension preserves vertical view")
        actor.call_method("PitchBoom", (0.5, -1.0))
        actor.call_method("RotateUpper", (0.5, 1.0))
        close(camera.get_forward_vector().z, -1.0, "Pitch and slew preserve vertical view")
        self.select(4)
        before = camera_pose(camera)
        actor.call_method("PitchBoom", (0.5, 1.0))
        actor.call_method("RotateUpper", (0.5, 1.0))
        check_pose(camera_pose(camera), before, "Driver view does not inherit upper/boom rotation")
        self.results.append("boom-down follows the tip through travel; driver view follows the chassis")

        for mode in range(5):
            self.select(mode)
            actor.call_method("OrbitCamera", (2.0, -2.0))
            for _ in range(2):
                before = camera_pose(camera)
                actor.call_method("ToggleFreeCamera")
                check_pose(camera_pose(camera), before, "Entering flight preserves the view")
                actor.call_method("FlyFreeCamera", (0.4, 1.0, -0.5, 0.3))
                rotation = camera.get_world_rotation()
                actor.call_method("OrbitCamera", (10.0, 5.0))
                after = camera.get_world_rotation()
                close((after.yaw - rotation.yaw + 180) % 360 - 180, 20.0, "Free yaw gain")
                close(after.pitch, min(89.0, max(-89.0, rotation.pitch + 10.0)), "Free pitch gain")
                before = camera_pose(camera)
                actor.call_method("ToggleFreeCamera")
                if actor.get_editor_property("FreeCamActive"):
                    raise AssertionError("G did not resume following")
                check_pose(camera_pose(camera), before, "Leaving flight preserves the view")
                actor.call_method("ZoomCamera", (0.0,))
                actor.call_method("ReceiveTick", (0.016,))
                check_pose(camera_pose(camera), before, "Idle controls do not reset the view")
            saved = relative_pose(camera)
            for _ in range(5):
                actor.call_method("ToggleCraneControl")
            close(actor.get_editor_property("CameraMode"), mode, "Five-way cycle wraps")
            check_pose(relative_pose(camera), saved, "Cycling restores customized camera pose")
            actor.call_method("ToggleFreeCamera")
            actor.call_method("FlyFreeCamera", (0.1, -1.0, 0.5, 0.0))
            saved = relative_pose(camera)
            actor.call_method("ToggleCraneControl")
            if actor.get_editor_property("FreeCamActive"):
                raise AssertionError("C did not save and leave flight")
            for _ in range(4):
                actor.call_method("ToggleCraneControl")
            check_pose(relative_pose(camera), saved, "Cycling directly from flight saves its pose")
            self.results.append(f"view {mode}: free/follow, sensitivity, idle, and cycle memory")

        self.select(0)
        before = relative_pose(camera)
        original_location = actor.get_actor_location()
        actor.set_actor_location(original_location + unreal.Vector(100, 50, 0), False, True)
        rotation = actor.get_actor_rotation()
        actor.set_actor_rotation(unreal.Rotator(yaw=rotation.yaw + 25), True)
        for mode in (1, 2, 3, 4, 0):
            self.select(mode)
        check_pose(relative_pose(camera), before, "Exterior memory remains truck-relative after travel")
        self.results.append("outside view survives cycling while the truck moves and steers")

        actor.call_method("ZoomCamera", (3000.0 - actor.get_editor_property("CameraDistance"),))
        before = camera_pose(camera)
        forward = vector_tuple(camera.get_forward_vector())
        actor.call_method("ZoomCamera", (-250.0,))
        check_pose(camera_pose(camera), (
            tuple(value + axis * 250 for value, axis in zip(before[0], forward)), before[1],
        ), "Follow zoom uses the customized pose")
        actor.call_method("ZoomCamera", (250.0,))
        check_pose(camera_pose(camera), before, "Follow zoom reverses without snapping")
        pitch, yaw = actor.get_editor_property("CameraPitch"), actor.get_editor_property("CameraYaw")
        actor.call_method("OrbitCamera", (10.0, 5.0))
        close(actor.get_editor_property("CameraYaw"), yaw + 2.0, "Locked yaw gain")
        close(actor.get_editor_property("CameraPitch"), min(-5.0, pitch + 1.0), "Locked pitch gain")
        actor.call_method("ZoomCamera", (-10000.0,))
        close(actor.get_editor_property("CameraDistance"), 600.0, "Near zoom limit")
        actor.call_method("ZoomCamera", (20000.0,))
        close(actor.get_editor_property("CameraDistance"), 8000.0, "Far zoom limit")
        actor.call_method("ToggleFreeCamera")
        actor.call_method("OrbitCamera", (0.0, 10000.0))
        close(camera.get_world_rotation().pitch, 89.0, "Free upper pitch limit")
        actor.call_method("OrbitCamera", (0.0, -10000.0))
        close(camera.get_world_rotation().pitch, -89.0, "Free lower pitch limit")
        before = camera_pose(camera)
        actor.call_method("FlyFreeCamera", (0.0, 0.0, 0.0, 0.0))
        check_pose(camera_pose(camera), before, "Zero flight input cannot use a stale cached position")
        self.results.append("custom zoom, sensitivity, limits, and zero-input flight")
        self.restore()
        self.actor.set_actor_tick_enabled(False)
        self.render_mode = 0
        self.frames = 0
        self.select(0)
        self.callback = unreal.register_slate_post_tick_callback(self.tick)

    def tick(self, delta_seconds):
        global CAMERA_TEST_RESULT
        self.frames += 1
        if self.frames < 3:
            return
        try:
            manager = unreal.GameplayStatics.get_player_camera_manager(self.world, 0)
            check_pose(
                (vector_tuple(manager.get_camera_location()), rotation_tuple(manager.get_camera_rotation())),
                camera_pose(self.camera), f"Actual rendered camera {self.render_mode}",
            )
            self.render_mode += 1
            if self.render_mode < 5:
                self.select(self.render_mode)
                self.frames = 0
                return
            self.results.append("player camera manager renders the selected view in all five modes")
            CAMERA_TEST_RESULT = {"passed": len(self.results), "camera_tests": self.results}
            print(json.dumps(CAMERA_TEST_RESULT, indent=2))
        except Exception as error:
            CAMERA_TEST_RESULT = {"error": str(error)}
            unreal.log_error(f"Camera regression failed: {error}")
            raise
        finally:
            if CAMERA_TEST_RESULT is not None:
                if self.callback is not None:
                    unreal.unregister_slate_post_tick_callback(self.callback)
                    self.callback = None
                self.restore()

    def restore(self):
        actor = self.actor
        self.select(0)
        actor.call_method("ZoomCamera", (
            self.variables["CameraDistance"] - actor.get_editor_property("CameraDistance"),
        ))
        actor.call_method("OrbitCamera", (
            (self.variables["CameraYaw"] - actor.get_editor_property("CameraYaw")) / 0.2,
            (self.variables["CameraPitch"] - actor.get_editor_property("CameraPitch")) / 0.2,
        ))
        actor.call_method("PitchBoom", (
            1.0, (self.variables["BoomPitch"] - actor.get_editor_property("BoomPitch"))
            / actor.get_editor_property("BoomPitchSpeed"),
        ))
        actor.call_method("LiftHook", (
            1.0, (self.variables["HookDrop"] - actor.get_editor_property("HookDrop"))
            / actor.get_editor_property("LiftSpeed"),
        ))
        actor.call_method("ExtendBoom", (
            1.0, (self.variables["BoomExtensionFraction"] - actor.get_editor_property("BoomExtensionFraction"))
            / actor.get_editor_property("BoomExtendSpeed"),
        ))
        for mode, memory in enumerate(self.memories):
            self.select(mode)
            self.camera.set_relative_transform(memory, False, True)
            actor.call_method("SaveCameraPose")
        actor.set_actor_transform(self.transform, False, True)
        for component, pose in self.poses:
            if component != self.camera:
                component.set_relative_transform(pose, False, True)
        self.select(self.variables["CameraMode"])
        if self.variables["FreeCamActive"]:
            actor.call_method("EnterFreeCameraFrom", (self.camera,))
        actor.set_actor_tick_enabled(self.ticking)


camera_tests = CameraTests()
try:
    camera_tests.run()
except Exception:
    camera_tests.restore()
    raise
