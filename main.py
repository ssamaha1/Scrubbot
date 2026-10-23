"""Scrubbot entry point: connect to Viam, then run the project pipeline."""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from viam.components.arm import Arm
from viam.components.camera import Camera
from viam.robot.client import RobotClient


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
    arm_name = required_env("VIAM_ARM_NAME")

    machine = await RobotClient.at_address(address, options)
    try:
        print("Connected to Viam. Available resources:")
        for resource in machine.resource_names:
            print(f"  {resource.name}")

        camera = Camera.from_robot(machine, camera_name)
        arm = Arm.from_robot(machine, arm_name)
        print(f"Ready: camera={camera.name}, arm={arm.name}")

        # TODO: Vision — capture an image and find dirt in plate coordinates.
        # Shared target format: {"x_mm": 25.0, "y_mm": -10.0, "z_mm": 0.0}
        # Plate origin: surface center; +Z points outward from the plate.
        # Agree on plate X/Y directions together before implementing motion.

        # TODO: Arm — transform a plate target to a gripper hover pose and move.
        # No motion is commanded by this starter.
    finally:
        await machine.close()


if __name__ == "__main__":
    asyncio.run(main())
