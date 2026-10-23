"""Estimate a color pixel's 3D position using aligned RealSense depth."""

import numpy as np
from viam.media.video import CameraMimeType


def measure_plate_center(images, properties, plate, color_shape):
    depth_image = next(
        (image for image in images if image.name == "depth"
         and image.mime_type == CameraMimeType.VIAM_RAW_DEPTH), None
    )
    if depth_image is None:
        raise ValueError("No raw depth image: configure both color and depth streams.")
    depth = np.asarray(depth_image.bytes_to_depth_array())
    if depth.shape != color_shape[:2]:
        raise ValueError("Color/depth sizes differ. Check align_color_depth=true.")
    intrinsics = properties.intrinsic_parameters
    height, width = depth.shape
    if (intrinsics.width_px, intrinsics.height_px) != (width, height):
        raise ValueError("Camera intrinsics do not match the color image dimensions.")
    if intrinsics.focal_x_px <= 0 or intrinsics.focal_y_px <= 0:
        raise ValueError("Camera returned invalid focal lengths.")
    u, v = plate[:2]
    if not (0 <= u < width and 0 <= v < height):
        raise ValueError("Detected plate center is outside the image.")

    # Median of an 11x11 patch rejects missing depth and individual noisy pixels.
    patch = depth[max(0, v-5):min(height, v+6), max(0, u-5):min(width, u+6)]
    valid = patch[(patch > 0) & (patch < 65535)]
    if valid.size < patch.size / 2:
        raise ValueError("Too little valid depth at the plate center; no 3D estimate.")
    spread = float(np.percentile(valid, 90) - np.percentile(valid, 10))
    if spread > 20:
        raise ValueError(f"Center depth is inconsistent ({spread:.1f} mm spread).")
    z = float(np.median(valid))
    x = (u - intrinsics.center_x_px) * z / intrinsics.focal_x_px
    y = (v - intrinsics.center_y_px) * z / intrinsics.focal_y_px
    # Pinhole approximation; lens distortion is not corrected in this first check.
    return {
        "frame": "camera_optical",
        "pixel": [int(u), int(v)],
        "x_mm": float(x), "y_mm": float(y), "z_mm": z,
        "valid_depth_samples": int(valid.size),
        "depth_spread_mm": spread,
        "method": "aligned_depth_pinhole_approximation",
    }
