"""Position the arm for image analysis."""

from viam.proto.common import Pose, PoseInFrame
from viam.proto.service.motion import Constraints, LinearConstraint
from viam.services.motion import MotionClient

ANALYSIS_HEIGHT_MM = 575.0  # Arm end-frame Z relative to the arm base.
MIN_HOVER_Z_MM = 208.46  # Minimum commanded Z, from manual teaching.
LOW_HOVER_Z_MM = MIN_HOVER_Z_MM + 1.0  # Margin for the 1 mm path tolerance.
BETWEEN_SPOTS_LIFT_MM = 20.0
# Empirical arm-base correction, taught with the same downward tool orientation.
HOVER_OFFSET_X_MM = 14.00
HOVER_OFFSET_Y_MM = -17.00
# Set to (x, y) in arm-base millimeters, NOT image pixels.


async def set_analysis_height(machine, arm):
    # Rounded analysis position in arm-base mm, with the tool pointing down.
    pose = Pose(
        x=472.0,
        y=-251.0,
        z=ANALYSIS_HEIGHT_MM,
        o_x=0.0,
        o_y=0.0,
        o_z=-1.0,
        theta=0.0,
    )
    print("Returning to analysis pose: X=472, Y=-251, Z=575 mm", flush=True)
    await move_to_pose(machine, arm, pose, straight_line=False)


async def move_to_pose(machine, arm, pose, straight_line=True):
    if pose.z < MIN_HOVER_Z_MM:
        raise ValueError(f"Target Z must be at least {MIN_HOVER_Z_MM} mm.")
    motion = MotionClient.from_robot(machine, "builtin")
    constraints = None
    if straight_line:
        constraints = Constraints(linear_constraint=[LinearConstraint(
            line_tolerance_mm=1.0, orientation_tolerance_degs=1.0,
        )])
    success = await motion.move(
        component_name=arm.name,
        destination=PoseInFrame(reference_frame=f"{arm.name}_origin", pose=pose),
        constraints=constraints,
        timeout=60,
    )
    if not success:
        raise RuntimeError("Could not reach hover position.")


async def lower_to_plate(machine, arm, center_x_mm, center_y_mm):
    pose = await arm.get_end_position()
    if abs(pose.x - center_x_mm) > 2 or abs(pose.y - center_y_mm) > 2:
        raise RuntimeError("Arm has not reached the plate center; descent cancelled.")
    if pose.z < LOW_HOVER_Z_MM:
        raise RuntimeError("Arm is already below the low hover target; descent cancelled.")
    pose.z = LOW_HOVER_Z_MM
    await move_to_pose(machine, arm, pose, straight_line=True)
    print(f"Low hover complete: target Z={LOW_HOVER_Z_MM:.2f} mm.")


async def imitate_scrubbing(machine, arm, x_mm, y_mm, stroke_length_mm=10.0):
    """Two back-and-forth strokes, above the plate; finish over the spot."""
    if not 2.0 <= stroke_length_mm <= 10.0:
        raise ValueError("Stroke length must be between 2 and 10 mm.")
    pose = await arm.get_end_position()
    if abs(pose.x - x_mm) > 2 or abs(pose.y - y_mm) > 2 or abs(pose.z - LOW_HOVER_Z_MM) > 2:
        raise RuntimeError("Arm did not reach the spot hover; scrubbing cancelled.")
    pose.z = LOW_HOVER_Z_MM
    pose.y = y_mm
    half = stroke_length_mm / 2
    for offset in (-half, half, -half, half, 0.0):
        pose.x = x_mm + offset
        await move_to_pose(machine, arm, pose, straight_line=True)
    print(f"Scrubbing imitation finished ({stroke_length_mm:.2f} mm stroke); no contact commanded.")
