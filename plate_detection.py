import cv2
import numpy as np
from pathlib import Path


def detect_plate(img):
    """Input image. Return the (center_x, center_y, radius) of the plate in pixels, or None."""

    
    if img is None:
        return None
    
    
    # Convert to grayscale
    gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Blur image to reduce noise (but keep edges)
    blur_img = cv2.medianBlur(gray_img, 5)
    
    
    # Approx plate sizes at default height
        # diameter ~= 400px
        # radius low bound = 150px, radius upperbound = 250px
    # Identify circles in the expected plate size
    circles = cv2.HoughCircles(
        blur_img,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=300,
        param1=40,
        param2=20,
        minRadius=180,
        maxRadius=215,
    )
    
    print(f"Circles deteceted: {circles}")
    if circles is not None:
        circles_outline = blur_img.copy()
        circles = np.uint16(np.around(circles))
        for i in circles[0, :]:
            center = (i[0], i[1])
            # circle center
            cv2.circle(circles_outline, center, 1, (0, 100, 100), 3)
            # circle outline
            radius = i[2]
            cv2.circle(circles_outline, center, radius, (255, 0, 255), 3)
        
        output_dir = Path(__file__).parent / "captures"
        output_dir.mkdir(exist_ok=True)
        cv2.imwrite(str(output_dir / "circle_boundaries.jpg"), circles_outline)
            
    # If no circles found
    if circles is None:
        return None
    
    
    # Use best choice
    x, y, radius = np.round(circles[0][0]).astype(int)
    return int(x), int(y), int(radius)



def draw_plate(img, plate):
    """Returns a copy of the original image but with the plate boundary drawn."""
    copy_img = img.copy()
    
    marked_img = cv2.circle(
        img=copy_img,
        center=(plate[0], plate[1]),
        radius=plate[2],
        color=(0, 255, 0),
        thickness=2)
    
    return marked_img
