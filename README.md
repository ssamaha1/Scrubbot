# Scrubbot

Better than a dishwasher

## Goal

## Ideas

# Dirt targeting

- For now, build in Plate Coords. Origin at center of plate,
- Dirt target is (x, y, 0) in plate coords, and hover target is (x, y, h). h = clearance

# Dirt classification

- Identfiy difference between: Stain, residue, scratch,

# Plate identification

- Started by using an arbitrary anlysis height to view the table.
- Take image -> grayscale -> blur -> OpenCV to detect circle
- Use depth camera and

## Steps

- [ ] Start with identifying dirt relative to plate coords

## Notes

## Run

Use Python 3.10 or newer. From the project folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env` with your Viam connection details and camera/arm component names, then run:

```sh
python main.py
```

Normal mode moves to the analysis pose, captures an image, and detects the plate. Keep credentials in `.env`, which is ignored by Git.

### Commands

| Command | Action |
| --- | --- |
| `python main.py` | Move to analysis pose and detect the plate. |
| `python main.py --orient-only` | Set downward orientation at the current X/Y/Z target. |
| `python main.py --measure-only` | Measure plate center in 3D; no arm movement. |
| `python main.py --hover-detected` | Return to analysis, detect plate center, hover above it, then descend. |
| `python main.py --spot-preview` | Detect dark spots; no arm movement. Inspect `captures/spots.jpg`. |
| `python main.py --scrub-spot` | Return to analysis, select up to six spaced spots, then hover and imitate scrubbing over each. |

### Spot demo

1. Start with the camera at the analysis pose and the plate flat and stationary.
2. Run `--spot-preview`. Up to six selected spots are numbered in red in `captures/spots.jpg`.
3. Run `--scrub-spot` when ready for movement. It captures again and selects the largest spot, then distant candidates at least 30% of the plate radius apart. It uses fewer targets if not enough pass the spacing, depth, and stroke-clearance checks.

Scrubbing uses two back-and-forth strokes at Z = 209.46 mm, above the taught minimum of 208.46 mm. Strokes are normally 10 mm and shorten near the rim, retaining a 5 mm margin; spots without room for at least a 2 mm stroke are skipped. This imitates scrubbing without contact-force control. Motion speed comes from the arm settings in Viam.

The detection mask covers 82% of the plate radius. Between spots, the arm lifts vertically by 20 mm to Z = 229.46 mm before moving sideways and descending again.

Detection assumes dark residue on a plain, light plate; guide lines, shadows, and decoration can also be detected. Tune the constants in `spot_detection.py`. Targets are recorded relative to the plate center in `captures/plate_center_3d.json`, with axes parallel to the robot base.
