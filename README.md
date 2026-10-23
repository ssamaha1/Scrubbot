# Scrubbot
Better than a dishwasher

## Goal


## Ideas

# Dirt targeting
- For now, build in Plate Coords. Origin at center of plate,
- Dirt target is (x, y, 0) in plate coords, and hover target is (x, y, h). h = clearance

# Dirt classification 
- Identfiy difference between: Stain, residue, scratch,

- 

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

The starter connects and checks that the camera and arm are configured. It does not move the arm. Add vision and arm control at the TODOs in `main.py`; keep credentials in `.env`, which is ignored by Git.
