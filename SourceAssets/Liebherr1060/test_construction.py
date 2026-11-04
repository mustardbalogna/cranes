"""Run during PIE with Unreal's Python console: py "<absolute path to this file>".

The Construction Items panel offers all eight construction meshes. Its 4x4
supply bay starts at the crane's editable ConstructionSpawnOrigin and reuses
vacated slots. ConstructionTile (GameTraceChannel1) ignores other tiles only;
ground collision, pickup overlaps, physics handles, and assembly stay enabled.

Z / X rotate the hook and its held piece at 45 degrees/second in follow mode.
Pickup preserves the piece's yaw offset; release still snaps yaw to 90 degrees.
Sling endpoints follow the mesh's transformed local corners.

Physics checks finish asynchronously after several seconds of simulated time.
Temporary actors, hook/upper rotation, UI state, pausing, and ticking are restored.
"""

import json
import math
import time

import unreal


CONSTRUCTION_TEST_RESULT = None


def mesh_component(actor):
    return actor.get_components_by_class(unreal.StaticMeshComponent)[0]


def distance(a, b):
    return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))


def check_angle(actual, expected, label, tolerance=0.05):
    difference = (actual - expected + 180.0) % 360.0 - 180.0
    if abs(difference) > tolerance:
        raise AssertionError(f"{label}: expected {expected}, received {actual}")


def click_bound_button(panel, name):
    button = panel.get_editor_property(name)
    binding = str(button.get_editor_property("on_clicked"))
    function = binding.rsplit(".", 1)[-1].split("]")[0]
    if not function.startswith("BndEvt__"):
        raise AssertionError(f"{name} has no Blueprint click handler: {binding}")
    panel.call_method(function)


class ConstructionTests:
    def __init__(self):
        self.world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
        if not self.world:
            raise RuntimeError("Start Play-In-Editor before running construction tests")
        self.tile_class = unreal.load_class(None, "/Game/ConstructionTiles/BP_BuildingTile.BP_BuildingTile_C")
        crane_class = unreal.load_class(None, "/Game/Liebherr1060/BP_MobileCrane.BP_MobileCrane_C")
        cranes = unreal.GameplayStatics.get_all_actors_of_class(self.world, crane_class)
        if len(cranes) != 1:
            raise RuntimeError(f"Expected one crane, received {len(cranes)}")
        self.crane = cranes[0]
        self.panel = next(
            item for item in unreal.ObjectIterator()
            if isinstance(item, unreal.UserWidget)
            and item.get_class().get_name() == "WBP_CraneControls_C"
            and item.is_in_viewport()
        )
        self.created = []
        self.results = []
        self.callback = None
        self.paused = unreal.GameplayStatics.is_game_paused(self.world)
        self.ticking = self.crane.is_actor_tick_enabled()
        self.body = self.panel.get_editor_property("ConstructionBody")
        self.visibility = self.body.get_visibility()
        self.status = self.panel.get_editor_property("ConstructionStatus")
        self.status_text = self.status.get_text()
        self.handle = self.crane.get_editor_property("TilePhysicsHandle")
        self.hook = self.crane.get_editor_property("Hook")
        self.upper = self.crane.get_editor_property("UpperPivot")
        self.hook_rotation = self.hook.get_editor_property("relative_rotation")
        self.upper_rotation = self.upper.get_editor_property("relative_rotation")
        if self.handle.get_grabbed_component():
            raise RuntimeError("Release the crane's held piece before running construction tests")

    def actors(self):
        return unreal.GameplayStatics.get_all_actors_of_class(self.world, self.tile_class)

    def spawn(self, mesh, through_ui=False):
        before = self.actors()
        if through_ui:
            name = mesh.get_name().removeprefix("SM_Building_").replace("_", "")
            click_bound_button(self.panel, "Spawn" + name)
            added = [actor for actor in self.actors() if actor not in before]
            if len(added) != 1:
                raise AssertionError(
                    f"UI action spawned {len(added)} pieces instead of one: {self.status.get_text()}"
                )
            tile = added[0]
            message = str(self.status.get_text())
        else:
            tile, message = self.crane.call_method("SpawnConstructionTile", (mesh,))
        if not tile:
            raise AssertionError(f"Unexpected spawn failure: {message}")
        self.created.append(tile)
        if len(self.actors()) != len(before) + 1:
            raise AssertionError("A spawn action did not add exactly one tile")
        component = mesh_component(tile)
        if component.get_editor_property("static_mesh") != mesh:
            raise AssertionError("Spawned the wrong construction mesh")
        if not component.is_simulating_physics():
            raise AssertionError("Spawned tile cannot be lifted with the physics handle")
        for channel in (
            unreal.CollisionChannel.ECC_WORLD_STATIC,
            unreal.CollisionChannel.ECC_PHYSICS_BODY,
        ):
            if component.get_collision_response_to_channel(channel) != unreal.CollisionResponseType.ECR_BLOCK:
                raise AssertionError("Collision with ground or non-tile physics bodies changed")
        if "Item spawned" not in message:
            raise AssertionError(f"Successful spawn has incorrect feedback: {message}")
        return tile

    def start(self):
        unreal.GameplayStatics.set_game_paused(self.world, True)
        self.crane.set_actor_tick_enabled(False)
        self.hook.set_relative_rotation(unreal.Rotator(pitch=2, yaw=179, roll=3), False, True)
        self.crane.call_method("RotateHook", (1.0, 1.0))
        rotation = self.hook.get_editor_property("relative_rotation")
        check_angle(rotation.yaw, -136.0, "Hook yaw wraps")
        check_angle(rotation.pitch, 2.0, "Hook preserves pitch")
        check_angle(rotation.roll, 3.0, "Hook preserves roll")
        self.crane.call_method("RotateHook", (1.0, -1.0))
        check_angle(self.hook.get_editor_property("relative_rotation").yaw, 179.0, "Reverse hook rotation")
        self.crane.call_method("RotateHook", (1.0, 0.0))
        self.crane.call_method("RotateHook", (0.0, 1.0))
        check_angle(self.hook.get_editor_property("relative_rotation").yaw, 179.0, "No-input hook rotation")
        for _ in range(40):
            self.crane.call_method("RotateHook", (0.025, 1.0))
        check_angle(self.hook.get_editor_property("relative_rotation").yaw, -136.0, "Frame-independent hook rotation")
        self.hook.set_relative_rotation(unreal.Rotator(yaw=15), False, True)
        self.upper.set_relative_rotation(unreal.Rotator(), False, True)
        self.results.append("empty-hook yaw, reverse, zero input, wrap, and frame-rate independence")
        self.body.set_visibility(unreal.SlateVisibility.COLLAPSED)
        click_bound_button(self.panel, "ConstructionToggle")
        if self.body.get_visibility() != unreal.SlateVisibility.VISIBLE:
            raise AssertionError("Construction panel did not open")
        click_bound_button(self.panel, "ConstructionToggle")
        if self.body.get_visibility() != unreal.SlateVisibility.COLLAPSED:
            raise AssertionError("Construction panel did not close")
        self.results.append("construction panel opens and closes")

        meshes = sorted(
            f"{asset.package_name}.{asset.asset_name}"
            for asset in unreal.AssetRegistryHelpers.get_asset_registry().get_assets_by_path(
                "/Game/ConstructionTiles"
            )
            if str(asset.asset_name).startswith("SM_Building_")
        )
        if len(meshes) != 8:
            raise AssertionError(f"Expected eight construction meshes, received {len(meshes)}")
        positions = []
        for path in meshes:
            tile = self.spawn(unreal.load_asset(path), through_ui=True)
            position = mesh_component(tile).get_world_location()
            if any(distance(position, previous) < 399.0 for previous in positions):
                raise AssertionError("Spawned pieces share a bay slot")
            positions.append(position)
        self.results.append("all eight UI choices spawn exactly one correctly configured piece")

        floor = unreal.load_asset("/Game/ConstructionTiles/SM_Building_Floor")
        while True:
            before = self.actors()
            tile, message = self.crane.call_method("SpawnConstructionTile", (floor,))
            if not tile:
                if "full" not in message.lower() or len(self.actors()) != len(before):
                    raise AssertionError("Full supply bay did not report failure without spawning")
                break
            self.created.append(tile)
            if len(self.created) > 16:
                raise AssertionError("Supply bay did not enforce its 16-slot capacity")
        removed = self.created.pop(0)
        vacated = mesh_component(removed).get_world_location()
        removed.destroy_actor()
        if unreal.SystemLibrary.is_valid(removed):
            raise RuntimeError("Unable to remove the bay-reuse test tile")
        reused = self.spawn(floor)
        if distance(mesh_component(reused).get_world_location(), vacated) > 0.05:
            raise AssertionError("Vacated supply bay slot was not reused")
        count = len(self.actors())
        tile, message = self.crane.call_method("SpawnConstructionTile", (None,))
        if tile or len(self.actors()) != count or "missing" not in message.lower():
            raise AssertionError("Invalid mesh did not produce an explicit failure")
        self.results.append("full bay, vacated-slot reuse, and invalid-mesh feedback")

        self.probes = self.created[:2]
        self.probe_position = unreal.Vector(6000, 6000, 500)
        for tile in self.probes:
            component = mesh_component(tile)
            component.set_enable_gravity(False)
            component.set_world_location(self.probe_position, False, True)
            component.set_physics_linear_velocity(unreal.Vector())
            component.set_physics_angular_velocity_in_degrees(unreal.Vector())
        self.stage = "collision"
        self.simulation_deadline = unreal.GameplayStatics.get_time_seconds(self.world) + 0.75
        self.timeout = time.monotonic() + 30.0
        self.callback = unreal.register_slate_post_tick_callback(self.tick)
        unreal.GameplayStatics.set_game_paused(self.world, False)

    def tick(self, delta_seconds):
        global CONSTRUCTION_TEST_RESULT
        try:
            if self.stage.startswith("rotation"):
                self.crane.call_method("UpdateHeldTile")
            if (unreal.GameplayStatics.get_time_seconds(self.world) < self.simulation_deadline
                    and time.monotonic() < self.timeout):
                return
            if time.monotonic() >= self.timeout:
                raise AssertionError("Physics test timed out before the simulation advanced")
            if self.stage == "collision":
                for tile in self.probes:
                    component = mesh_component(tile)
                    if distance(component.get_world_location(), self.probe_position) > 1.0:
                        raise AssertionError("Overlapping tiles pushed each other apart")
                    if distance(component.get_physics_linear_velocity(), unreal.Vector()) > 1.0:
                        raise AssertionError("Overlapping tiles generated a collision impulse")
                for tile in self.created[2:]:
                    component = mesh_component(tile)
                    location = component.get_world_location()
                    if location.z < -2.0:
                        raise AssertionError(f"Spawned tile fell through the ground: {location.z}")
                    if location.z > 4.0:
                        return
                self.results.append("overlapping pieces do not repel; other spawned pieces settle on ground")
                self.pickup = mesh_component(self.probes[0])
                self.pickup.set_world_rotation(unreal.Rotator(yaw=23), False, True)
                sensor = self.crane.get_editor_property("TilePickupSensor")
                origin = self.pickup.get_editor_property("static_mesh").get_bounds().origin
                target = sensor.get_world_location()
                self.pickup.set_world_location(
                    unreal.Vector(target.x - origin.x, target.y - origin.y, target.z - origin.z),
                    False, True,
                )
                self.pickup.set_physics_linear_velocity(unreal.Vector())
                self.stage = "pickup"
                self.simulation_deadline = unreal.GameplayStatics.get_time_seconds(self.world) + 0.25
                return
            if self.stage == "pickup":
                sensor = self.crane.get_editor_property("TilePickupSensor")
                if not sensor.is_overlapping_component(self.pickup):
                    raise AssertionError("Pickup sensor does not overlap the new tile channel")
                self.crane.call_method("ToggleTilePickup_0")
                if self.handle.get_grabbed_component() != self.pickup:
                    raise AssertionError("Crane cannot grab a spawned construction tile")
                self.crane.call_method("UpdateHeldTile")
                _, target = self.handle.get_target_location_and_rotation()
                check_angle(target.yaw, 23.0, "Pickup preserves initial yaw")
                check_angle(self.pickup.get_world_rotation().yaw, 23.0, "Pickup does not teleport rotation")
                self.results.append("pickup captures initial alignment without snapping")
                self.rotate_and_wait(1.0, 1.0, 68.0, "rotation-forward")
                return
            if self.stage.startswith("rotation"):
                self.check_held_rotation()
                if self.stage == "rotation-forward":
                    self.rotate_and_wait(2.0, -1.0, -22.0, "rotation-reverse")
                    return
                if self.stage == "rotation-reverse":
                    self.crane.call_method("RotateUpper", (1.0, 1.0))
                    self.rotate_and_wait(0.0, 0.0, -7.0, "rotation-upper")
                    return
                if self.stage == "rotation-upper":
                    yaw = self.hook.get_editor_property("relative_rotation").yaw
                    self.crane.call_method("LiftHook", (0.1, 1.0))
                    check_angle(self.hook.get_editor_property("relative_rotation").yaw, yaw, "Hoisting preserves hook yaw")
                    self.crane.call_method("LiftHook", (0.1, -1.0))
                    self.rotate_and_wait(2.0, 1.0, 83.0, "rotation-release")
                    return
                self.results.append("held load physically follows hook, reverse, and upper rotation; hoist preserves yaw")
                self.crane.call_method("ToggleTilePickup_0")
                check_angle(self.pickup.get_world_rotation().yaw, 90.0, "Rotated release snaps to grid")
                self.pickup.set_world_location(unreal.Vector(7000, 7000, 5), False, True)
                self.pickup = mesh_component(self.probes[1])
                self.pickup.set_world_rotation(unreal.Rotator(yaw=131), False, True)
                sensor = self.crane.get_editor_property("TilePickupSensor")
                origin = self.pickup.get_editor_property("static_mesh").get_bounds().origin
                target = sensor.get_world_location()
                self.pickup.set_world_location(
                    unreal.Vector(target.x - origin.x, target.y - origin.y, target.z - origin.z),
                    False, True,
                )
                self.stage = "repickup"
                self.simulation_deadline = unreal.GameplayStatics.get_time_seconds(self.world) + 0.25
                return
            self.crane.call_method("ToggleTilePickup_0")
            if self.handle.get_grabbed_component() != self.pickup:
                raise AssertionError("Crane cannot grab the second tile")
            self.crane.call_method("UpdateHeldTile")
            _, target = self.handle.get_target_location_and_rotation()
            check_angle(target.yaw, 131.0, "Next pickup recaptures alignment")
            self.crane.call_method("ToggleTilePickup_0")
            if self.handle.get_grabbed_component():
                raise AssertionError("Crane did not release the construction tile")
            self.results.append("rotated release snaps correctly; subsequent pickup recaptures its own offset")
            self.pickup = mesh_component(self.probes[0])
            self.probes[0].call_method("AssembleTile")
            if not self.probes[0].get_editor_property("IsPlaced") or self.pickup.is_simulating_physics():
                raise AssertionError("Ground assembly no longer snaps and locks the tile")
            self.results.append("ground assembly still snaps and disables simulation")
            CONSTRUCTION_TEST_RESULT = {"passed": len(self.results), "tests": self.results}
            print(json.dumps(CONSTRUCTION_TEST_RESULT, indent=2))
        except Exception as error:
            CONSTRUCTION_TEST_RESULT = {"error": str(error)}
            unreal.log_error(f"Construction regression failed: {error}")
            raise
        finally:
            if CONSTRUCTION_TEST_RESULT is not None:
                self.cleanup()

    def rotate_and_wait(self, seconds, direction, yaw, stage):
        self.crane.call_method("RotateHook", (seconds, direction))
        self.crane.call_method("UpdateHeldTile")
        self.expected_yaw = yaw
        _, target = self.handle.get_target_location_and_rotation()
        check_angle(target.yaw, yaw, "Physics-handle target yaw")
        self.stage = stage
        self.simulation_deadline = unreal.GameplayStatics.get_time_seconds(self.world) + 4.0
        self.timeout = time.monotonic() + 30.0

    def check_held_rotation(self):
        check_angle(self.pickup.get_world_rotation().yaw, self.expected_yaw, "Physical load yaw", 3.0)
        minimum, maximum = self.pickup.get_local_bounds()
        corner = self.pickup.get_world_transform().transform_location(
            unreal.Vector(minimum.x, minimum.y, maximum.z)
        )
        sling = self.crane.get_editor_property("SlingCable01")
        scale = sling.get_world_scale()
        endpoint = sling.get_world_location() + sling.get_up_vector() * (scale.z * 50.0)
        if distance(endpoint, corner) > 1.0:
            raise AssertionError("Sling endpoint does not follow the rotated mesh corner")

    def cleanup(self):
        if self.callback is not None:
            unreal.unregister_slate_post_tick_callback(self.callback)
            self.callback = None
        if self.handle.get_grabbed_component():
            self.handle.release_component()
        for actor in self.created:
            if unreal.SystemLibrary.is_valid(actor):
                name = actor.get_name()
                actor.destroy_actor()
                if unreal.SystemLibrary.is_valid(actor):
                    raise RuntimeError(f"Unable to remove temporary tile: {name}")
        self.created.clear()
        self.hook.set_relative_rotation(self.hook_rotation, False, True)
        self.upper.set_relative_rotation(self.upper_rotation, False, True)
        self.body.set_visibility(self.visibility)
        self.status.set_text(self.status_text)
        self.crane.set_actor_tick_enabled(self.ticking)
        unreal.GameplayStatics.set_game_paused(self.world, self.paused)


construction_tests = ConstructionTests()
try:
    construction_tests.start()
except Exception:
    construction_tests.cleanup()
    raise
