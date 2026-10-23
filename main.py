"""Scrubbot entry point: connect to Viam, then run the project pipeline."""

import asyncio
import os
from pathlib import Path
import cv2

from dotenv import load_dotenv
from viam.components.arm import Arm
from viam.components.camera import Camera
from viam.errors import ResourceNotFoundError
from viam.media.video import CameraMimeType
from viam.robot.client import RobotClient

from plate_detection import detect_plate, draw_plate
from set_hover import set_analysis_height

def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Set {name} in your .env file (see .env.example).")
    return value


async def main() -> None:
    load_dotenv(Path(__file__).with_name(".env"))
    address = required_env("VIAM_MACHINE_ADDRESS")
    options = RobotClient.Options.with_api_key(
        api_key=required_env("VIAM_API_KEY"),
        api_key_id=required_env("VIAM_API_KEY_ID"),
    )
    camera_name = required_env("VIAM_CAMERA_NAME")
    arm_name = os.getenv("VIAM_ARM_NAME", "").strip()

    machine = await RobotClient.at_address(address, options)
    try:
        print("Connected to Viam. Available resources:")
        for resource in machine.resource_names:
            print(f"  {resource.name}")

        camera = Camera.from_robot(machine, camera_name)
        print(f"Ready: camera={camera.name}")
        arm = None
        if arm_name:
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


        if arm is not None:
            await set_analysis_height(machine, arm)

        # Take a single image to identify plate
        images, _ = await camera.get_images()
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
        

        
        # TODO: Vision — find dirt in the captured image in plate coordinates.
        # Shared target format: {"x_mm": 25.0, "y_mm": -10.0, "z_mm": 0.0}
        # Plate origin: surface center; +Z points outward from the plate.
        # Agree on plate X/Y directions together before implementing motion.

        # TODO: Arm — transform a plate target to a gripper hover pose and move.
        # Only run arm code when arm is not None.
    finally:
        await machine.close()


if __name__ == "__main__":
    asyncio.run(main())
