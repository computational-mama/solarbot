#!/usr/bin/env python3
"""
ina219-host.py

Samples an INA219 power monitor and serves energy totals over a TCP socket,
so the chatbot can ask "how much energy did that question cost".

It mirrors the pattern of the PiSugar battery service that
src/device/battery.ts already talks to on port 8423.

Run it as its OWN systemd service, not as part of the chatbot. Two reasons:
the chatbot restarts often and you would lose your measurement history, and
you need it sampling while the bot is idle so you have a baseline to compare
a question against.

Protocol: plain text, newline terminated.

  ping                 -> pong
  get power            -> power: <volts> <amps> <watts>
  get idle             -> idle: <watts>
  energy <epoch_ms>    -> energy: <joules> <seconds> <avg_watts> <above_idle_joules>

Typical use from the bot: note the epoch ms when a question starts, then
send "energy <that number>" when the answer finishes.

Test the wiring first, without any of the socket stuff:

  python3 ina219-host.py --test
"""

import argparse
import bisect
import socket
import socketserver
import statistics
import sys
import threading
import time
from collections import deque

from ina219 import INA219, DeviceRangeError

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

# The shunt resistor on the board, in ohms.
# The stock Adafruit / generic breakout has 0.1, marked R100 on the part.
# If you swap it for R020 or R010, change this number or every reading will
# be wrong by exactly the factor you changed.
SHUNT_OHMS = 0.1

# Roughly the highest current you expect. Lets the library pick the best
# resolution. It still reads above this, just less precisely.
MAX_EXPECTED_AMPS = 3.0

I2C_ADDRESS = 0x40      # 0x41 if you bridged the A0 pad for a second board
I2C_BUSNUM = 1

SAMPLE_HZ = 20          # 20 a second is plenty, a question lasts seconds
HISTORY_SECONDS = 900   # keep 15 minutes of samples in memory
IDLE_WINDOW_SECONDS = 300
IDLE_PERCENTILE = 0.05  # the quietest 5 percent of recent samples is "idle"

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 8424      # 8423 is taken by the PiSugar battery service

# ---------------------------------------------------------------------------


class PowerSampler(threading.Thread):
    """Reads the sensor in the background and keeps a short history."""

    daemon = True

    def __init__(self):
        super().__init__(name="power-sampler")
        self._ina = INA219(
            SHUNT_OHMS,
            MAX_EXPECTED_AMPS,
            busnum=I2C_BUSNUM,
            address=I2C_ADDRESS,
        )
        self._ina.configure(self._ina.RANGE_16V)

        maxlen = int(SAMPLE_HZ * HISTORY_SECONDS)
        self._times = deque(maxlen=maxlen)    # epoch seconds, ascending
        self._watts = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._latest = (0.0, 0.0, 0.0)        # volts, amps, watts
        self._range_errors = 0

    # -- reading ------------------------------------------------------------

    def read_once(self):
        """One sample. Returns volts, amps, watts."""
        volts = self._ina.voltage()
        try:
            amps = self._ina.current() / 1000.0
            watts = self._ina.power() / 1000.0
        except DeviceRangeError:
            # Current went past what this shunt can measure. The reading is
            # not usable, so report the ceiling and count it. If this keeps
            # happening you need a smaller shunt resistor.
            self._range_errors += 1
            amps = 0.32 / SHUNT_OHMS
            watts = volts * amps
        return volts, amps, watts

    def run(self):
        interval = 1.0 / SAMPLE_HZ
        while True:
            started = time.time()
            try:
                volts, amps, watts = self.read_once()
            except OSError as exc:
                # I2C hiccup. Do not die, the bot may still be running.
                print(f"[power] i2c read failed: {exc}", file=sys.stderr)
                time.sleep(1.0)
                continue

            with self._lock:
                self._latest = (volts, amps, watts)
                self._times.append(started)
                self._watts.append(watts)

            time.sleep(max(0.0, interval - (time.time() - started)))

    # -- queries ------------------------------------------------------------

    def latest(self):
        with self._lock:
            return self._latest

    def range_errors(self):
        return self._range_errors

    def idle_watts(self):
        """
        Baseline power. Taken as a low percentile of recent samples rather
        than the minimum, so one odd reading does not define it.
        """
        cutoff = time.time() - IDLE_WINDOW_SECONDS
        with self._lock:
            recent = [
                w for t, w in zip(self._times, self._watts) if t >= cutoff
            ]
        if not recent:
            return 0.0
        recent.sort()
        index = int(len(recent) * IDLE_PERCENTILE)
        return recent[min(index, len(recent) - 1)]

    def energy_since(self, start_epoch):
        """
        Integrate power over time from start_epoch until now.

        Returns joules, seconds, average watts, and joules above the idle
        baseline. That last one is the marginal cost of whatever happened,
        as opposed to the total the battery actually gave up.
        """
        with self._lock:
            times = list(self._times)
            watts = list(self._watts)

        if len(times) < 2:
            return 0.0, 0.0, 0.0, 0.0

        first = bisect.bisect_left(times, start_epoch)
        if first >= len(times) - 1:
            return 0.0, 0.0, 0.0, 0.0

        joules = 0.0
        for i in range(first + 1, len(times)):
            dt = times[i] - times[i - 1]
            if dt <= 0:
                continue
            # Trapezoid: average the two samples across the gap.
            joules += (watts[i] + watts[i - 1]) / 2.0 * dt

        seconds = times[-1] - times[first]
        average = joules / seconds if seconds > 0 else 0.0
        above_idle = max(0.0, joules - self.idle_watts() * seconds)
        return joules, seconds, average, above_idle


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        for raw in self.rfile:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                reply = self.dispatch(line)
            except Exception as exc:  # keep the socket alive whatever happens
                reply = f"error: {exc}"
            self.wfile.write((reply + "\n").encode("utf-8"))

    def dispatch(self, line):
        sampler = self.server.sampler
        parts = line.split()
        command = parts[0].lower()

        if command == "ping":
            return "pong"

        if command == "get" and len(parts) > 1:
            if parts[1] == "power":
                volts, amps, watts = sampler.latest()
                return f"power: {volts:.3f} {amps:.4f} {watts:.4f}"
            if parts[1] == "idle":
                return f"idle: {sampler.idle_watts():.4f}"
            if parts[1] == "errors":
                return f"errors: {sampler.range_errors()}"

        if command == "energy" and len(parts) > 1:
            start = float(parts[1]) / 1000.0
            joules, seconds, average, above = sampler.energy_since(start)
            return (
                f"energy: {joules:.3f} {seconds:.3f} "
                f"{average:.4f} {above:.3f}"
            )

        return f"error: unknown command {line!r}"


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def run_test():
    """Print readings so you can check the wiring and see the real numbers."""
    sampler = PowerSampler()
    print(f"shunt {SHUNT_OHMS} ohm, ceiling "
          f"{0.32 / SHUNT_OHMS:.2f} A, address {hex(I2C_ADDRESS)}")
    print("volts    amps     watts")
    peak = 0.0
    try:
        while True:
            volts, amps, watts = sampler.read_once()
            peak = max(peak, amps)
            flag = "  <-- OVER RANGE" if sampler.range_errors() else ""
            print(f"{volts:6.3f}  {amps:7.4f}  {watts:7.3f}{flag}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print(f"\npeak current seen: {peak:.3f} A")
        print(f"over range events: {sampler.range_errors()}")
        if sampler.range_errors():
            print("You went past what this shunt can measure. "
                  "Fit a smaller one (R020) and set SHUNT_OHMS to match.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true",
                        help="print live readings instead of serving")
    args = parser.parse_args()

    if args.test:
        run_test()
        return

    sampler = PowerSampler()
    sampler.start()
    time.sleep(1.0)  # let a little history build up before answering queries

    server = Server((LISTEN_HOST, LISTEN_PORT), Handler)
    server.sampler = sampler
    print(f"[power] listening on {LISTEN_HOST}:{LISTEN_PORT}, "
          f"shunt {SHUNT_OHMS} ohm")
    server.serve_forever()


if __name__ == "__main__":
    main()
