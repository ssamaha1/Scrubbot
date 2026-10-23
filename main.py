"""Scrubbot entry point: connect to Viam, then run the project pipeline."""

import asyncio
import argparse
import json
import math
import time
import os
import traceback
from pathlib import Path
import cv2

from dotenv import load_dotenv
from viam.components.arm import Arm
from viam.components.camera import Camera
from viam.errors import ResourceNotFoundError
from viam.media.video import CameraMimeType
from viam.robot.client import RobotClient
from viam.proto.common import Pose, PoseInFrame

from plate_detection import detect_plate, draw_plate
from depth_measurement import measure_plate_center
from set_hover import set_analysis_height, move_to_pose, lower_to_plate
from set_hover import HOVER_OFFSET_X_MM, HOVER_OFFSET_Y_MM
from set_hover import imitate_scrubbing, LOW_HOVER_Z_MM, BETWEEN_SPOTS_LIFT_MM
from spot_detection import detect_spots, draw_spots, select_spots, INNER_RADIUS_FRACTION

def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Set {name} in your .env file (see .env.example).")
    return value


async def main() -> None:
    parser = argparse.ArgumentParser(description="Scrubbot analysis and arm positioning")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--orient-only", action="store_true",
                        help="Set downward orientation at the current X/Y/Z target, then exit")
    modes.add_argument("--measure-only", action="store_true",
                       help="Capture and estimate plate center in 3D without moving the arm")
    modes.add_argument("--hover-detected", action="store_true",
                       help="Return to the analysis pose, measure the plate, then hover over its center")
    modes.add_argument("--spot-preview", action="store_true",
                       help="Detect dark spots and save an overlay without moving the arm")
    modes.add_argument("--scrub-spot", action="store_true",
                       help="Return to analysis and imitate scrubbing over up to six spaced dark spots")
    args = parser.parse_args()
    moving_detection = args.hover_detected or args.scrub_spot
    measuring = args.measure_only or args.spot_preview or moving_detection
    load_dotenv(Path(__file__).with_name(".env"))
    address = required_env("VIAM_MACHINE_ADDRESS")
    options = RobotClient.Options.with_api_key(
        api_key=required_env("VIAM_API_KEY"),
        api_key_id=required_env("VIAM_API_KEY_ID"),
    )
    arm_name = os.getenv("VIAM_ARM_NAME", "").strip()

    machine = await RobotClient.at_address(address, options)
    try:
        print("Connected to Viam. Available resources:")
        for resource in machine.resource_names:
            print(f"  {resource.name}")

        arm = None
        if args.measure_only or args.spot_preview:
            print("Measurement only: no arm movements will be requested.")
        elif arm_name:
            try:
                arm = Arm.from_robot(machine, arm_name)
            except ResourceNotFoundError:
                print(
                    f"Arm '{arm_name}' is unavailable. Continuing with camera only. "
                    "Check the arm configuration and logs in Viam."
                )
            else:
                print(f"Ready: arm={arm.name}")
        else:
            print("VIAM_ARM_NAME is unset. Continuing with camera only.")


        if args.orient_only:
            if arm is None:
                raise RuntimeError("An available arm is required for --orient-only.")
            pose = await arm.get_end_position()
            pose.o_x, pose.o_y, pose.o_z, pose.theta = 0.0, 0.0, -1.0, 0.0
            await move_to_pose(machine, arm, pose, straight_line=False)
            print("Downward orientation set. Target X/Y/Z preserved.")
            pose = await arm.get_end_position()
            print(pose)
            return

        camera = Camera.from_robot(machine, required_env("VIAM_CAMERA_NAME"))
        print(f"Ready: camera={camera.name}")

        if moving_detection:
            if arm is None:
                raise RuntimeError("An available arm is required for this movement mode.")
            if await arm.is_moving():
                raise RuntimeError("Stop the arm before measuring the plate.")
            await set_analysis_height(machine, arm)
            analysis_ready_at = time.time()
            await asyncio.sleep(0.3)  # Allow a camera frame from the new pose.
            start_pose = await arm.get_end_position()
            if abs(start_pose.z - 575.0) > 2 or start_pose.o_z > -0.999 or abs(start_pose.theta) > 1:
                raise RuntimeError("Arm did not reach the downward analysis height; stopping.")
        elif arm is not None:
            await set_analysis_height(machine, arm)

        # Take a single image to identify plate
        images, metadata = await camera.get_images(timeout=15)
        if measuring:
            if not metadata.HasField("captured_at"):
                raise RuntimeError("Camera returned no capture timestamp; cannot verify freshness.")
            captured = metadata.captured_at.seconds + metadata.captured_at.nanos / 1e9
            if moving_detection and captured < analysis_ready_at:
                raise RuntimeError("Camera frame predates arrival at the analysis pose; no hover move sent.")
            age = time.time() - captured
            if abs(age) > 15:
                raise RuntimeError(f"Camera frame timestamp differs from now by {age:.1f}s. Check camera and clocks.")
        extensions = {CameraMimeType.JPEG: ".jpg", CameraMimeType.PNG: ".png"}
        image = next((img for img in images if img.mime_type in extensions), None)
        if image is None:
            raise RuntimeError("Camera returned no JPEG/PNG image. Check its color output configuration.")
        output_dir = Path(__file__).parent / "captures"
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / f"plate{extensions[image.mime_type]}"
        output_path.write_bytes(image.data)
        print(f"Saved camera image: {output_path.resolve()}")


        # After capturing image
        image = cv2.imread(str(output_path))
        if image is None:
            raise RuntimeError(f"Could not read {output_path}")

        # System to detect plate boundaries.
        # plate: (x, y, radius)
        plate = detect_plate(image)


        # Create image depicting plate boundaries
        if plate is None:
            print("No plate detected.")
        else:
            annotated = draw_plate(image, plate)
            cv2.imwrite(str(output_dir / "plate_boundary.jpg"), annotated)
            print(f"Plate center and radius in pixels: {plate}")
            if args.spot_preview or args.scrub_spot:
                spots, mask = detect_spots(image, plate)
                candidate_count = len(spots)
                spots = select_spots(spots, plate)
                cv2.imwrite(str(output_dir / "spot_mask.png"), mask)
                cv2.imwrite(str(output_dir / "spots.jpg"), draw_spots(image, plate, spots))
                (output_dir / "spots.json").write_text(json.dumps(spots, indent=2) + "\n")
                print(f"Found {candidate_count} dark spots; selected {len(spots)} spaced targets, numbered red in captures/spots.jpg.")
                if not spots:
                    print("No spot found; no target or scrub movement requested.")
                    return
            if measuring:
                properties = await camera.get_properties(timeout=15)
                measurement = measure_plate_center(images, properties, plate, image.shape)
                measurement["captured_at_unix"] = captured
                # Camera optical axes must match the configured camera frame.
                arm_frame = f"{required_env('VIAM_ARM_NAME')}_origin"
                robot_point = await machine.transform_pose(
                    PoseInFrame(reference_frame=camera.name, pose=Pose(
                        x=measurement["x_mm"], y=measurement["y_mm"],
                        z=measurement["z_mm"], o_z=1.0,
                    )),
                    arm_frame,
                )
                measurement["robot_estimate_unvalidated"] = {
                    "reference_frame": arm_frame,
                    "x_mm": robot_point.pose.x,
                    "y_mm": robot_point.pose.y,
                    "z_mm": robot_point.pose.z,
                }
                target_x = robot_point.pose.x + HOVER_OFFSET_X_MM
                target_y = robot_point.pose.y + HOVER_OFFSET_Y_MM
                if args.spot_preview or args.scrub_spot:
                    intrinsics = properties.intrinsic_parameters
                    inner_radius_mm = (plate[2] * INNER_RADIUS_FRACTION * measurement["z_mm"]
                                       / max(intrinsics.focal_x_px, intrinsics.focal_y_px))
                    targets = []
                    skipped_spots = []
                    for spot in spots:
                        try:
                            point = measure_plate_center(images, properties, (*spot["pixel"], 0), image.shape)
                        except ValueError as error:
                            skipped_spots.append({"pixel": spot["pixel"], "reason": str(error)})
                            print(f"Skipping spot {spot['pixel']}: {error}")
                            continue
                        spot_point = await machine.transform_pose(
                            PoseInFrame(reference_frame=camera.name, pose=Pose(
                                x=point["x_mm"], y=point["y_mm"], z=point["z_mm"], o_z=1.0)), arm_frame)
                        relative_x = spot_point.pose.x - robot_point.pose.x
                        relative_y = spot_point.pose.y - robot_point.pose.y
                        # Shorten strokes near the rim while retaining a 5 mm margin.
                        available_half_stroke = inner_radius_mm - math.hypot(relative_x, relative_y) - 5.0
                        stroke_length = min(10.0, 2 * available_half_stroke)
                        if stroke_length < 2.0:
                            skipped_spots.append({
                                "pixel": spot["pixel"],
                                "reason": "Not enough rim clearance for even a 2 mm stroke",
                                "distance_from_plate_center_mm": math.hypot(relative_x, relative_y),
                                "inner_radius_mm": inner_radius_mm,
                            })
                            print(f"Skipping spot {spot['pixel']}: not enough room for the stroke.")
                            continue
                        targets.append({
                            "pixel": spot["pixel"],
                            "plate_relative_mm": {"x": relative_x, "y": relative_y, "z": 0.0},
                            "corrected_robot_xy_mm": [spot_point.pose.x + HOVER_OFFSET_X_MM,
                                                       spot_point.pose.y + HOVER_OFFSET_Y_MM],
                            "stroke_axis": "plate_x", "stroke_length_mm": stroke_length, "cycles": 2,
                        })
                    measurement["selected_spots"] = targets
                    measurement["skipped_spots"] = skipped_spots
                    print(f"{len(targets)} targets passed depth and stroke checks; {len(skipped_spots)} skipped.")
                    if targets:
                        target_x, target_y = targets[0]["corrected_robot_xy_mm"]
                measurement["corrected_hover_xy"] = {
                    "reference_frame": arm_frame,
                    "x_mm": target_x, "y_mm": target_y,
                    "offset_x_mm": HOVER_OFFSET_X_MM,
                    "offset_y_mm": HOVER_OFFSET_Y_MM,
                }
                path = output_dir / "plate_center_3d.json"
                path.write_text(json.dumps(measurement, indent=2) + "\n")
                print(f"Measurement saved to {path}")
                print("Axes: +X right, +Y down, +Z forward from the camera.")
                print("Check this measurement physically before using it for motion.")
                if args.scrub_spot:
                    if not targets:
                        print("No spots passed the depth and stroke checks; no scrub movement requested.")
                        return
                    route = [start_pose]  # Validate all horizontal legs before starting.
                    for target in targets:
                        xy = target["corrected_robot_xy_mm"]
                        route.append(Pose(x=xy[0], y=xy[1]))
                    if any(math.hypot(b.x-a.x, b.y-a.y) > 400 for a, b in zip(route, route[1:])):
                        raise RuntimeError("A spot requires more than 400 mm horizontal travel; stopping.")
                if moving_detection:
                    pose = await arm.get_end_position()
                    if abs(time.time() - captured) > 15:
                        raise RuntimeError("Measurement is now stale; no hover move sent.")
                    if max(abs(getattr(pose, a) - getattr(start_pose, a)) for a in ("x", "y", "z", "o_x", "o_y", "o_z", "theta")) > 0.5:
                        raise RuntimeError("Arm moved during measurement; capture again.")
                    distance = math.hypot(target_x - pose.x, target_y - pose.y)
                    if distance > 400:
                        raise RuntimeError(f"Horizontal travel is {distance:.1f} mm; limit is 400 mm. No hover move sent.")
                    visit_targets = ([target["corrected_robot_xy_mm"] for target in targets]
                                     if args.scrub_spot else [(target_x, target_y)])
                    for index, (visit_x, visit_y) in enumerate(visit_targets):
                        if index:
                            # Lift vertically before moving sideways to the next spot.
                            pose = await arm.get_end_position()
                            pose.z = LOW_HOVER_Z_MM + BETWEEN_SPOTS_LIFT_MM
                            await move_to_pose(machine, arm, pose, straight_line=True)
                        pose.x, pose.y = visit_x, visit_y
                        await move_to_pose(machine, arm, pose, straight_line=True)
                        print(f"Target {index + 1}/{len(visit_targets)} reached; descending vertically.")
                        await lower_to_plate(machine, arm, visit_x, visit_y)
                        if args.scrub_spot:
                            await imitate_scrubbing(machine, arm, visit_x, visit_y,
                                                    stroke_length_mm=targets[index]["stroke_length_mm"])
                    end_pos = await arm.get_end_position()
                    print(f"Final arm position: {end_pos}")


        # TODO: Vision — find dirt in the captured image in plate coordinates.
        # Shared target format: {"x_mm": 25.0, "y_mm": -10.0, "z_mm": 0.0}
        # Plate origin: surface center; +Z points outward from the plate.
        # Agree on plate X/Y directions together before implementing motion.

        # TODO: Arm — transform a plate target to a gripper hover pose and move.
        # Only run arm code when arm is not None.

        # if arm is not None:
        #     pose = await arm.get_end_position()
        #     print(pose.x, pose.y)

        # if arm is not None and plate is not None:
        #     await hover_above_plate(machine, arm)


    finally:
        await machine.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        log_path = Path(__file__).with_name("errors.log")
        log_path.write_text(traceback.format_exc())
        print(f"Error details saved to {log_path}")
        raise
