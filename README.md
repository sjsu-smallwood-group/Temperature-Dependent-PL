# Temperature-Dependent-PL

Automation code for Temperature Dependent PL in Dr. Smallwood's Research Lab.

Repo: https://github.com/sjsu-smallwood-group/Temperature-Dependent-PL

## Run the picomotor controller

**Easiest:** double-click `run_python_script.bat` in the project folder. It creates a shared project `.venv` if needed, installs `requirements.txt`, runs `arduino_controlled_picomotor.py`, and keeps the window open when the script exits.

That `.venv` lives in the project folder (on Public Desktop), so every Windows profile on this machine uses the same packages — no per-user `pip install`.

Or from PowerShell, `cd` into the project folder and run via the project venv:

```powershell
cd "<path to>\Temperature-Dependent-PL"
.\.venv\Scripts\python.exe arduino_controlled_picomotor.py
```

First-time setup (if you are not using the bat file):

```powershell
cd "C:\Users\Public\Desktop\Temperature-Dependent-PL"
& "C:\ProgramData\anaconda3\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

- Defaults to the Arduino on **COM4** (override with `--port COMx`).
- Type `help` for commands; always `return home` before quitting.
- Dependencies are listed in `requirements.txt` (currently `pyserial`).

More setup notes are in [`info/`](info/) (USB devices and git repo URL).
