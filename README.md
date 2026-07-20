# Temperature-Dependent-PL

Automation code for Temperature Dependent PL in Dr. Smallwood's Research Lab.

Repo: https://github.com/sjsu-smallwood-group/Temperature-Dependent-PL

## Run the picomotor controller

**Easiest:** double-click `run_python_script.bat` in the project folder. It runs `arduino_controlled_picomotor.py` with Anaconda Python and keeps the window open when the script exits.

Or from PowerShell, `cd` into the project folder and run the script manually:

```powershell
cd "<path to>\Temperature-Dependent-PL"
& "C:\ProgramData\anaconda3\python.exe" arduino_controlled_picomotor.py
```

Example (this machine):

```powershell
cd "C:\Users\Public\Desktop\Temperature-Dependent-PL"

& "C:\ProgramData\anaconda3\python.exe" arduino_controlled_picomotor.py
```

- Defaults to the Arduino on **COM4** (override with `--port COMx`).
- Type `help` for commands; always `return home` before quitting.
- Requires `pyserial`: `pip install --user pyserial`

More setup notes are in [`info/`](info/) (USB devices and git repo URL).
