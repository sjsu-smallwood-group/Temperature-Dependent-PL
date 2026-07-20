#!/usr/bin/env python3
"""
WARNING: Do not make step size/position past the mechanical limits. It will
break the motor. It is safe to move small increments but if it stops moving
but is making noise, stop the script IMMEDIATELY.

There is no internal position saved on the hardware. You must return to
0, 0, 0 before ending the script, or the next run will treat wherever the
laser is last pointed as the new home (0, 0, 0).

------------------------------------------------------------------------------
arduino_controlled_picomotor.py
------------------------------------------------------------------------------
Interactive terminal controller for a New Focus / Newport Picomotor mount
driven through an Arduino with PicomotorControl/arduinoDriverCode/jankoMotor8812.ino

Features
--------
- Should work on Windows, macOS, and Linux
- Auto-detects the Arduino
- Tracks absolute A/B/C position relative to the current home
- Terminal commands: set home, return home, go to, status, stop, help
- "A B C" or "A, B, C" lines are treated as relative step moves

"""

from __future__ import annotations

import argparse
import logging
import platform
import re
import sys
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("ERROR: pyserial is required. Install with: pip install pyserial")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Constants matching the .ino
# ---------------------------------------------------------------------------
BAUD_RATE = 9600
SERIAL_TIMEOUT_S = 1.0
CONNECT_SETTLE_S = 2.0          # Arduino resets on open; wait for READY
CONNECT_ATTEMPTS = 3           # Full open+handshake retries (fresh reset each)
COMMAND_TIMEOUT_S = 120.0       # Long moves can take a while
COMMAND_GUARD_S = 0.20          # Quiet time before each serial command
INTER_BYTE_DELAY_S = 0.003      # Pace bytes for the Arduino serial parser
DEFAULT_LOG_LEVEL = logging.INFO

# Hints used when scanning USB serial devices for an Arduino
ARDUINO_HINTS = (
    "arduino",
    "usbmodem",       # common macOS CDC ACM name for Uno/Leonardo/etc.
    "usbserial",
    "ch340",
    "ch341",
    "cp210",
    "ftdi",
    "wch",
    "acm",
)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log = logging.getLogger("picomotor")


def setup_logging(verbose: bool = False) -> None:
    """Configure console logging for connection debugging."""
    level = logging.DEBUG if verbose else DEFAULT_LOG_LEVEL
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


# ---------------------------------------------------------------------------
# Port discovery
# ---------------------------------------------------------------------------
@dataclass
class PortInfo:
    """One USB/serial device found on the system."""
    device: str
    description: str
    manufacturer: str
    hwid: str

    def matches_arduino(self) -> bool:
        blob = " ".join(
            [self.device, self.description, self.manufacturer, self.hwid]
        ).lower()
        return any(hint in blob for hint in ARDUINO_HINTS)


def get_os_name() -> str:
    """Return the host OS name (Windows / Linux / Darwin / ...)."""
    return platform.system()


def list_serial_ports() -> List[PortInfo]:
    """Enumerate all serial ports currently visible to the OS."""
    ports: List[PortInfo] = []
    for p in list_ports.comports():
        ports.append(
            PortInfo(
                device=p.device,
                description=p.description or "",
                manufacturer=p.manufacturer or "",
                hwid=p.hwid or "",
            )
        )
    return ports


def print_ports(ports: List[PortInfo]) -> None:
    """Pretty-print discovered serial ports for debugging."""
    if not ports:
        print("No serial ports found.")
        return
    print(f"Found {len(ports)} serial port(s) on {get_os_name()}:")
    for i, p in enumerate(ports, 1):
        tag = " [arduino candidate]" if p.matches_arduino() else ""
        print(f"  {i}. {p.device}{tag}")
        print(f"      desc={p.description!r}  mfr={p.manufacturer!r}")


def find_arduino_port(preferred: Optional[str] = None) -> Optional[str]:
    """
    Pick the serial port that is most likely the Arduino.

    Priority:
      1. Explicit --port / preferred path if it exists
      2. Ports whose name/description/manufacturer look like Arduino
      3. None (caller should fail clearly)
    """
    ports = list_serial_ports()
    log.debug("OS=%s, scanning %d serial port(s)", get_os_name(), len(ports))
    for p in ports:
        log.debug(
            "  port=%s desc=%r mfr=%r hwid=%r arduino=%s",
            p.device,
            p.description,
            p.manufacturer,
            p.hwid,
            p.matches_arduino(),
        )

    if preferred:
        devices = {p.device for p in ports}
        if preferred in devices:
            log.info("Using user-specified port: %s", preferred)
            return preferred
        # On some systems the path exists but is briefly missing from the list;
        # still try it if the user asked for it explicitly.
        log.warning(
            "Specified port %s not in enumerated list; will still try to open it",
            preferred,
        )
        return preferred

    candidates = [p for p in ports if p.matches_arduino()]
    if len(candidates) == 1:
        log.info("Auto-detected Arduino on %s", candidates[0].device)
        return candidates[0].device

    if len(candidates) > 1:
        # Prefer the strongest Arduino match (manufacturer/description contain
        # "arduino") over generic USB-serial chips.
        strong = [
            p for p in candidates
            if "arduino" in (p.manufacturer + " " + p.description).lower()
        ]
        chosen = strong[0] if strong else candidates[0]
        log.warning(
            "Multiple Arduino candidates found; using %s. "
            "Pass --port to override. Candidates: %s",
            chosen.device,
            ", ".join(p.device for p in candidates),
        )
        return chosen.device

    log.error("No Arduino-like serial port found. Use --list-ports / --port.")
    return None


# ---------------------------------------------------------------------------
# Picomotor serial client
# ---------------------------------------------------------------------------
class PicomotorController:
    """
    Thin serial client for the Arduino Picomotor firmware.

    Absolute A/B/C positions are tracked in this process only. The Arduino
    also keeps counters (ZERO / POSITION), but they are not persisted across
    power cycles or script restarts.
    """

    def __init__(self, port: str, baudrate: int = BAUD_RATE):
        self.port = port
        self.baudrate = baudrate
        self.ser: Optional[serial.Serial] = None
        # Software absolute position relative to the current home
        self.pos_a = 0
        self.pos_b = 0
        self.pos_c = 0

    # -- connection --------------------------------------------------------

    def connect(self) -> bool:
        """
        Open the serial port and complete the READY/PING/ZERO handshake.

        Opening the port resets the Arduino (DTR toggle), and occasionally the
        first boot lands in a bad window where every command is swallowed. To be
        robust, the whole open+handshake is retried a few times; each retry
        closes and reopens the port, giving the Arduino a fresh reset.

        Returns True on success.
        """
        for attempt in range(1, CONNECT_ATTEMPTS + 1):
            log.info("Connecting to Picomotor controller on %s @ %d baud "
                     "(attempt %d/%d)",
                     self.port, self.baudrate, attempt, CONNECT_ATTEMPTS)
            if self._open_and_handshake():
                self.pos_a = self.pos_b = self.pos_c = 0
                log.info("Picomotor controller connected on %s", self.port)
                return True
            self.disconnect()
            if attempt < CONNECT_ATTEMPTS:
                log.warning("Handshake failed; retrying with a fresh reset...")
                time.sleep(1.0)

        log.error("Failed to connect after %d attempt(s)", CONNECT_ATTEMPTS)
        return False

    def _open_and_handshake(self) -> bool:
        """Open the port and run the READY/PING/ZERO handshake once."""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=SERIAL_TIMEOUT_S,
                write_timeout=SERIAL_TIMEOUT_S,
            )
        except serial.SerialException as exc:
            log.error("Failed to open serial port %s: %s", self.port, exc)
            return False

        # The Uno bootloader runs for ~1-2s after the reset before handing off
        # to the sketch. Commands sent during that window get swallowed or
        # fragmented (e.g. the sketch sees "NG" instead of "PING") and come back
        # as "ERROR: Unknown command". Wait for the READY banner (confirms the
        # sketch is up and drains boot output), then retry the handshake commands
        # so any straggling fragment gets flushed out.
        log.debug("Waiting %.1fs for Arduino reset...", CONNECT_SETTLE_S)
        time.sleep(CONNECT_SETTLE_S)

        if not self._wait_for_ready(timeout_s=6.0):
            log.warning("Did not see READY banner; will still try handshake")
        self._flush_input()

        if not self._ping(retries=8):
            log.error("PING failed after retries")
            return False

        # Verify the board accepts the exact motion protocol used below.
        # A zero-step move is safe: the firmware parses MOVE A <steps> and
        # returns OK without pulsing the motor.
        if not self._send_expect_ok("MOVE A 0", retries=2):
            log.error(
                "Arduino firmware does not accept the required "
                "'MOVE A <steps>' command protocol"
            )
            return False

        # Align software + firmware counters to a known home
        if not self._send_expect_ok("ZERO", retries=8):
            log.error("ZERO failed during connect handshake")
            return False

        return True

    def disconnect(self) -> None:
        """Close the serial port if open."""
        if self.ser is not None and self.ser.is_open:
            try:
                self.ser.close()
            except serial.SerialException as exc:
                log.debug("Error closing serial port: %s", exc)
        self.ser = None
        log.debug("Disconnected from Picomotor controller")

    def _require_open(self) -> serial.Serial:
        if self.ser is None or not self.ser.is_open:
            raise ConnectionError("Not connected to Picomotor controller")
        return self.ser

    def _flush_input(self) -> None:
        ser = self._require_open()
        time.sleep(0.05)
        ser.reset_input_buffer()

    def _wait_for_ready(self, timeout_s: float = 3.0) -> bool:
        """Read lines until READY appears or timeout."""
        ser = self._require_open()
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            line = ser.readline().decode("ascii", errors="replace").strip()
            if not line:
                continue
            log.debug("Arduino boot line: %r", line)
            if "READY" in line.upper():
                # Drain any follow-up banner lines quickly
                drain_deadline = time.time() + 0.3
                while time.time() < drain_deadline:
                    extra = ser.readline().decode("ascii", errors="replace").strip()
                    if not extra:
                        break
                    log.debug("Arduino boot line: %r", extra)
                return True
        return False

    def _readline(self, timeout_s: float = COMMAND_TIMEOUT_S) -> str:
        """Read one non-empty response line, respecting a deadline."""
        ser = self._require_open()
        old_timeout = ser.timeout
        ser.timeout = min(1.0, timeout_s)
        deadline = time.time() + timeout_s
        try:
            while time.time() < deadline:
                raw = ser.readline()
                if not raw:
                    continue
                log.debug("RX bytes: %s", raw.hex(" "))
                line = raw.decode("ascii", errors="replace").strip()
                if line:
                    log.debug("RX: %r", line)
                    return line
        finally:
            ser.timeout = old_timeout
        return ""

    def _send(self, command: str) -> str:
        """Send one newline-terminated command and read one response line.

        Leave a short quiet period, clear stale input, and pace individual
        bytes. The protocol remains one complete command followed by exactly
        one response. Byte pacing is intentionally conservative for the
        Arduino's timeout-based String parser.
        """
        ser = self._require_open()
        payload = (command + "\n").encode("ascii")
        time.sleep(COMMAND_GUARD_S)
        ser.reset_input_buffer()
        log.debug("TX: %r", command)
        for byte in payload:
            ser.write(bytes((byte,)))
            ser.flush()
            time.sleep(INTER_BYTE_DELAY_S)
        return self._readline()

    def _send_expect_ok(self, command: str, retries: int = 0) -> bool:
        """Send a command and expect "OK", retrying to ride out boot fragments."""
        response = ""
        for attempt in range(retries + 1):
            response = self._send(command)
            if response == "OK":
                if attempt:
                    log.debug("%s -> OK (attempt %d)", command, attempt + 1)
                return True
            log.debug("%s attempt %d/%d got %r",
                      command, attempt + 1, retries + 1, response)
            time.sleep(0.2)
        # Some firmwares may emit ERROR lines; surface the last one
        log.error("Command %r failed: %r", command, response)
        return False

    def _ping(self, retries: int = 0) -> bool:
        """Send PING and expect PONG, retrying to ride out a slow/late boot."""
        for attempt in range(retries + 1):
            response = self._send("PING")
            if response.upper() == "PONG":
                log.debug("PING -> PONG (attempt %d)", attempt + 1)
                return True
            log.debug("PING attempt %d/%d got %r",
                      attempt + 1, retries + 1, response)
            time.sleep(0.3)
        return False

    # -- motion ------------------------------------------------------------

    def move_relative(self, da: int, db: int, dc: int) -> bool:
        """
        Move each corner by a relative step count (can be negative / zero).
        Updates the software absolute position on success.
        """
        moves = (("A", da), ("B", db), ("C", dc))
        for corner, steps in moves:
            if steps == 0:
                continue
            command = f"MOVE {corner} {steps}"
            response = self._send(command)

            # "Unknown command" means the firmware never entered its MOVE
            # handler, so no steps were issued. It is therefore safe to resend
            # after a brief pause. Never retry timeouts or motion/safety errors:
            # in those cases the motor may already have moved.
            for attempt in range(2):
                if response.strip().upper() != "ERROR: UNKNOWN COMMAND":
                    break
                log.warning(
                    "%s was not parsed; retrying (%d/2)",
                    command,
                    attempt + 1,
                )
                time.sleep(0.5)
                response = self._send(command)

            if response != "OK":
                log.error("MOVE %s %s failed: %r", corner, steps, response)
                return False
            if corner == "A":
                self.pos_a += steps
            elif corner == "B":
                self.pos_b += steps
            else:
                self.pos_c += steps
        return True

    def go_to(self, a: int, b: int, c: int) -> bool:
        """Move to an absolute coordinate relative to the current home."""
        return self.move_relative(a - self.pos_a, b - self.pos_b, c - self.pos_c)

    def return_home(self) -> bool:
        """Return to absolute (0, 0, 0) relative to the current home."""
        return self.go_to(0, 0, 0)

    def set_home(self) -> bool:
        """
        Declare the current physical pose as the new home (0, 0, 0).
        Does not move the motors — only resets counters.
        """
        if not self._send_expect_ok("ZERO"):
            return False
        self.pos_a = self.pos_b = self.pos_c = 0
        return True

    def position_tuple(self) -> Tuple[int, int, int]:
        return (self.pos_a, self.pos_b, self.pos_c)

    def position_str(self) -> str:
        return f"{self.pos_a}, {self.pos_b}, {self.pos_c}"

    def sync_position_from_arduino(self) -> Optional[Tuple[int, int, int]]:
        """
        Optional: read POSITION from firmware and adopt those counters.
        Useful for debugging; normal interactive use trusts software tracking.
        """
        response = self._send("POSITION")
        # Expected: "POS A=<a> B=<b> C=<c>"
        match = re.search(
            r"A\s*=\s*(-?\d+)\s+B\s*=\s*(-?\d+)\s+C\s*=\s*(-?\d+)",
            response,
            re.IGNORECASE,
        )
        if not match:
            log.error("Could not parse POSITION response: %r", response)
            return None
        self.pos_a, self.pos_b, self.pos_c = map(int, match.groups())
        return self.position_tuple()


# ---------------------------------------------------------------------------
# Interactive command parsing
# ---------------------------------------------------------------------------
HELP_TEXT = """
Notes
-----
  - Positions are steps from the last "set home" / startup home.
  - Always return home before quitting if you care about the next session.
  - If a motor stalls / buzzes without moving, run stop immediately.
  - Any position is accepted with commas as well:
      ex  go to -1000, 0, 2000  and  go to -1000 0 2000  works

Commands
--------
  set home             Set current position as home (0, 0, 0) — does not move motors
  return home          Move back to home (0, 0, 0)
  A B C                Move by # of steps  ex: -100 0 100  (no keyword needed)
  go to A B C          Go to a specific coordinate relative to home
  status               Print current coordinate position
  stop                 Disconnect and exit the script
""".strip()


def parse_three_ints(text: str) -> Optional[Tuple[int, int, int]]:
    """
    Parse three integers from a string that may use spaces and/or commas.
    Returns None if the text is not exactly three integers.
    """
    # Normalize commas to spaces, collapse whitespace
    cleaned = text.replace(",", " ")
    parts = cleaned.split()
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def handle_line(controller: PicomotorController, line: str) -> bool:
    """
    Handle one interactive input line.

    Returns False if the REPL should exit (stop), True to keep going.
    """
    raw = line.strip()
    if not raw:
        return True

    lowered = raw.lower()

    if lowered in ("help", "h", "?"):
        print(HELP_TEXT)
        return True

    if lowered in ("stop", "exit", "quit", "q"):
        print("disconnected")
        return False

    if lowered == "status":
        print(f"Current position: {controller.position_str()}")
        return True

    if lowered in ("set home", "sethome", "zero"):
        if controller.set_home():
            print("Home set")
            print(f"Location: {controller.position_str()}")
        else:
            print("ERROR: set home failed")
        return True

    if lowered in ("return home", "returnhome", "home"):
        print("Returning home...")
        if controller.return_home():
            print(f"Current position: {controller.position_str()}")
        else:
            print("ERROR: return home failed")
        return True

    if lowered.startswith("go to") or lowered.startswith("goto"):
        # Accept "go to ...", "goto ..."
        rest = raw.split(None, 2)
        # rest examples: ["go", "to", "-1000 0 2000"] or ["goto", "-1000,0,2000"]
        if lowered.startswith("go to"):
            coords_text = raw[len("go to"):].strip()
        else:
            coords_text = raw[len("goto"):].strip()
        coords = parse_three_ints(coords_text)
        if coords is None:
            print("ERROR: go to needs three integers, e.g.  go to -1000 0 2000")
            return True
        a, b, c = coords
        print(f"Going to {a}, {b}, {c} ...")
        if controller.go_to(a, b, c):
            print(f"Current position: {controller.position_str()}")
        else:
            print("ERROR: go to failed")
        return True

    # Bare relative move: "100 0 -100" or "100, 0, -100"
    rel = parse_three_ints(raw)
    if rel is not None:
        da, db, dc = rel
        print(f"Moving relative A={da:+d}, B={db:+d}, C={dc:+d} ...")
        if controller.move_relative(da, db, dc):
            print(f"Current position: {controller.position_str()}")
        else:
            print("ERROR: relative move failed")
        return True

    print("Unknown input. Type 'help' for commands, or enter A B C steps.")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Interactive Arduino Picomotor controller (A/B/C corners).",
    )
    parser.add_argument(
        "--port",
        default="COM4",
        help="Serial port path (skip auto-detect). "
             "Defaults to COM4 (the Arduino Uno on this machine). "
             "Examples: COM4, /dev/ttyUSB0, /dev/cu.usbmodem14101",
    )
    parser.add_argument(
        "--list-ports",
        action="store_true",
        help="List serial ports and exit (useful for debugging detection).",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging for connection / serial traffic.",
    )
    return parser


def run_repl(controller: PicomotorController) -> int:
    """Interactive command loop after a successful connection."""
    print("connected")
    print("home set")
    print(f"Location: {controller.position_str()}")
    print("Enter a position or help for more.")

    try:
        while True:
            try:
                line = input("> ")
            except EOFError:
                print("disconnected")
                break
            if not handle_line(controller, line):
                break
    except KeyboardInterrupt:
        print("\ndisconnected")
    finally:
        controller.disconnect()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    setup_logging(verbose=args.verbose)

    log.debug("Host OS: %s (%s)", get_os_name(), platform.platform())

    ports = list_serial_ports()
    if args.list_ports:
        print_ports(ports)
        return 0

    port = find_arduino_port(preferred=args.port)
    if not port:
        print("ERROR: Could not find an Arduino serial port.")
        print("Tip: unplug other USB-serial devices, or pass --port explicitly.")
        print("     Use --list-ports to see what the OS currently reports.")
        return 1

    controller = PicomotorController(port)
    if not controller.connect():
        print(f"ERROR: Failed to connect on {port}")
        print("Tip: confirm .ino is uploaded and the cable is data-capable.")
        print("     Re-run with -v --list-ports for more detail.")
        return 1

    return run_repl(controller)


if __name__ == "__main__":
    sys.exit(main())
