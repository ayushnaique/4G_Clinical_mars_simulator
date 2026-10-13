# Mars Robot Simulator: how to run

A Django app that simulates a robot on a 5x5 table, with a retro top-down UI in the
browser and a command-line runner for input files.

## Requirements

- Python **3.9 or newer**. Check with `python3 --version`.
- Git.
- Nothing else. There is no database and no migrate step, and the only dependency is Django 4.2.

## 1. Get the code and install

Fork this repository on GitHub (the **Fork** button at the top right), then clone your fork.
To run it without forking, clone this repository directly instead.

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

The `.venv/` folder is listed in `.gitignore`, so it is never committed.

On Windows, use `.venv\Scripts\` instead of `.venv/bin/` in every command below. For example:
`.venv\Scripts\pip install -r requirements.txt`.

## 2. Run the web app

```bash
.venv/bin/python manage.py runserver
```

Open **http://127.0.0.1:8000/**. On your first visit, the app plays the first input file automatically, one step at a time.

| Action | How |
|---|---|
| Play an input file | Click ▶ next to a file in the **INPUT FILES** list. The robot starts at that file's first `PLACE` line. |
| Stop a running file | **STOP** button or `Esc` |
| Clear the board | **RESET**. This removes the robot and clears the log. |
| Place the robot | Pick a facing under the board, then click any tile. |
| Move / turn | The on-screen arrow pad, or the keyboard: `↑` MOVE, `←` LEFT, `→` RIGHT, `Enter` REPORT |
| Type commands | Enter one command per line in the command box, then click **RUN** (or press `Ctrl+Enter` / `Cmd+Enter`). |
| Autoplay a specific file | Open `http://127.0.0.1:8000/?run=example_c` |

The activity log under the board records every command and whether it was accepted or ignored.

If the page has no JavaScript, it still works: every button is a normal form.

Stop the server with `Ctrl+C`. If you see "That port is already in use", another server is still running. Stop it, or use a different port: `.venv/bin/python manage.py runserver 8001`.

## 3. Run input files from the command line

The `simulate` command reads a file, or stdin when no file is given. It prints one line for each `REPORT`.

```bash
.venv/bin/python manage.py simulate testdata/example_a.txt        # 0,1,NORTH
.venv/bin/python manage.py simulate testdata/edge_cases.txt
.venv/bin/python manage.py simulate --verbose testdata/invalid_input.txt   # show every step

# from stdin
printf "PLACE 0,0,NORTH\nMOVE\nREPORT\n" | .venv/bin/python manage.py simulate

# a different table size
.venv/bin/python manage.py simulate --width 3 --height 8 testdata/example_c.txt
```

### Included input files (`testdata/`)

| File | Exercises | Expected output |
|---|---|---|
| `example_a.txt` | Brief example A | `0,1,NORTH` |
| `example_b.txt` | Brief example B | `0,0,WEST` |
| `example_c.txt` | Brief example C | `3,3,NORTH` |
| `edge_cases.txt` | MOVE off every edge is refused, and the robot keeps working afterwards | `4,4,NORTH`, `4,4,EAST`, `0,0,SOUTH` |
| `invalid_input.txt` | Commands before the first PLACE, malformed and unknown lines, and an off-table PLACE are ignored | `2,2,SOUTH` |

To add a scenario, put a new `.txt` file in `testdata/`. It shows up in the web UI's file list automatically.

Input format: one command per line. Case is ignored. `#` starts a comment.

```
PLACE X,Y,F     F is NORTH, SOUTH, EAST or WEST; (0,0) is the south-west corner
MOVE
LEFT
RIGHT
REPORT
```

## 4. Run the tests

```bash
.venv/bin/python manage.py test                              # all 79 tests
.venv/bin/python manage.py test simulator.tests.test_core    # simulation rules only
```

The tests also check that each `testdata/` file produces the output its comments promise.

Optional linting:

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

## 5. Configuration (optional)

You can change these with environment variables, both for the web app and for the tests:

| Variable | Default | Meaning |
|---|---|---|
| `SIMULATION_TABLE_WIDTH` / `SIMULATION_TABLE_HEIGHT` | `5` | Table size |
| `SIMULATION_INPUT_DIR` | `testdata/` | Folder of input files listed in the UI |
| `SIMULATION_STEP_DELAY_MS` | `650` | Delay between steps when a file plays |
| `DJANGO_DEBUG` | `1` | Set to `0` for production-like behaviour |
| `DJANGO_SECRET_KEY` | dev key | Set this to a real secret outside local use |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated host names |

Example:

```bash
SIMULATION_TABLE_WIDTH=3 SIMULATION_TABLE_HEIGHT=8 .venv/bin/python manage.py runserver
```

## 6. JSON API

The UI talks to these endpoints. You can call them directly too; send a POST with a JSON body. Each one returns the full state: robot, grid, log and last report.

| Endpoint | Body |
|---|---|
| `POST /api/command/` | `{"script": "PLACE 1,2,EAST\nMOVE\nREPORT"}` |
| `POST /api/place/` | `{"x": 1, "y": 2, "facing": "NORTH"}` |
| `POST /api/reset/` | `{}` |
| `POST /api/files/<name>/start/` | `{}`: clears the board and returns that file's lines |

## Project layout

```
robot/        simulation rules, plain Python (no Django)
simulator/    Django app: views, templates, CSS/JS, `simulate` command, tests
config/       Django settings and URLs
testdata/     input files used by the UI, the CLI and the tests
```
