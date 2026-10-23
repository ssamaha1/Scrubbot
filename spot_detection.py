"""Basic dark-residue detection on a plain, light-colored plate."""

import cv2
import numpy as np

INNER_RADIUS_FRACTION = 0.82
MAX_SPOTS = 6
MIN_SPACING_RADIUS_FRACTION = 0.30
DARKNESS_THRESHOLD = 35
MIN_SPOT_AREA_PX = 20


def detect_spots(image, plate):
    x, y, radius = plate
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    interior = np.zeros(gray.shape, dtype=np.uint8)
    cv2.circle(interior, (x, y), int(radius * INNER_RADIUS_FRACTION), 255, -1)
    background = float(np.median(gray[interior > 0]))
    mask = np.where((gray < background - DARKNESS_THRESHOLD) & (interior > 0),
                    255, 0).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    mask = cv2.bitwise_and(mask, interior)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    spots = []
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if not MIN_SPOT_AREA_PX <= area <= np.count_nonzero(interior) * 0.15:
            continue
        component = np.uint8(labels == label)
        # Pick an interior point rather than a centroid that could lie outside a smear.
        distances = cv2.distanceTransform(component, cv2.DIST_L2, 5)
        v, u = np.unravel_index(np.argmax(distances), distances.shape)
        spots.append({"pixel": [int(u), int(v)], "area_px": area})
    return sorted(spots, key=lambda spot: spot["area_px"], reverse=True), mask


def draw_spots(image, plate, spots):
    result = image.copy()
    cv2.circle(result, tuple(plate[:2]), int(plate[2] * INNER_RADIUS_FRACTION), (0, 255, 255), 2)
    for index, spot in enumerate(spots):
        pixel = tuple(spot["pixel"])
        cv2.circle(result, pixel, 8, (0, 0, 255), 2)
        cv2.putText(result, str(index + 1), (pixel[0] + 10, pixel[1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    return result


def select_spots(spots, plate):
    """Largest spot first, then distant candidates; never invent missing spots."""
    if not spots:
        return []
    remaining = sorted(spots, key=lambda spot: spot["area_px"], reverse=True)
    selected = [remaining.pop(0)]
    min_spacing = plate[2] * MIN_SPACING_RADIUS_FRACTION
    while remaining and len(selected) < MAX_SPOTS:
        def separation(spot):
            return min(float(np.linalg.norm(np.array(spot["pixel"]) - other["pixel"]))
                       for other in selected)
        candidate = max(remaining, key=lambda spot: (separation(spot), spot["area_px"]))
        if separation(candidate) < min_spacing:
            break
        selected.append(candidate)
        remaining.remove(candidate)
    return selected
