# Power service

Measures how much energy the bot spends answering a single question.

## What it is

`ina219-host.py` reads an INA219 power monitor over I2C, samples it 20 times a
second, and serves energy totals on TCP port 8424. The chatbot notes the time a
question starts, then asks this service how many joules went by before the
answer finished.

It follows the same shape as the PiSugar battery service that
`src/device/battery.ts` already talks to on port 8423.

## Setup on the Pi

Enable I2C:

```bash
sudo raspi-config          # Interface Options, I2C, Yes
sudo reboot
i2cdetect -y 1             # 40 should appear in the grid
```

Install the library. Recent Raspberry Pi OS refuses a system-wide pip install,
so use a virtual environment:

```bash
python3 -m venv ~/power-venv
~/power-venv/bin/pip install pi-ina219
```

## Check the wiring, and find out if the shunt is big enough

```bash
~/power-venv/bin/python ~/solarbot/python/power-service/ina219-host.py --test
```

This prints live readings. Ask the bot a few questions while it runs, then stop
it with Ctrl+C. It reports the peak current it saw.

Two things to look at:

1. **Did the peak get near the ceiling?** With the stock 0.1 ohm shunt that is
   3.2 A. If you stayed comfortably below it, nothing needs changing.
2. **Did the Pi complain about undervoltage?** Run `vcgencmd get_throttled` on
   the Pi. `throttled=0x0` means fine. Anything else means the shunt is
   stealing too much voltage.

If either one is a problem, replace the shunt resistor with a 0.02 ohm part
(marked R020) and set `SHUNT_OHMS = 0.02` at the top of the script. That raises
the ceiling to 16 A and cuts the voltage drop to a fifth. Or use an INA260,
which has the right resistor built in and needs no soldering.

## Run it as a service

Keep it separate from the chatbot. The chatbot restarts often and you would
lose the measurement history, and you want it sampling while the bot is idle so
there is a baseline to compare a question against.

```bash
sudo tee /etc/systemd/system/power-monitor.service > /dev/null <<EOF
[Unit]
Description=INA219 power monitor
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$HOME/solarbot
ExecStart=$HOME/power-venv/bin/python $HOME/solarbot/python/power-service/ina219-host.py
StandardOutput=append:$HOME/solarbot/power-monitor.log
StandardError=append:$HOME/solarbot/power-monitor.log
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now power-monitor.service
systemctl status power-monitor --no-pager
```

## Talking to it

```bash
printf 'get power\n' | nc 127.0.0.1 8424
printf 'energy 1757000000000\n' | nc 127.0.0.1 8424
```

| Command | Reply |
| --- | --- |
| `ping` | `pong` |
| `get power` | `power: <volts> <amps> <watts>` |
| `get idle` | `idle: <watts>` |
| `get errors` | `errors: <count of over range events>` |
| `energy <epoch_ms>` | `energy: <joules> <seconds> <avg_watts> <joules_above_idle>` |

`joules_above_idle` is the marginal cost of the question, so what it took on
top of simply being switched on. The plain `joules` figure is what the battery
actually gave up. Both are worth showing, they say different things.

## Wiring it into the bot

`src/core/chat-flow/states.ts` has the states `sleep`, `listening`, `asr` and
`answer`, and `ctx.answerId` increments once per question. Record `Date.now()`
on each transition, keyed by that id. At the end of `answer`, ask this service
for the energy since the start of `listening`.

That gives you a breakdown as well as a total: listening is nearly free,
transcribing costs something, the thinking is almost all of it.

## Turning joules into something people understand

Joules mean nothing to anyone. Two conversions worth showing:

- **Seconds of sunshine.** Joules divided by the panel's watts. A 96 J answer
  on a 5 W panel is about 19 seconds of sun. Note that this is a calculation
  from the panel's rating, not a measurement, unless you put a second sensor on
  the solar input.
- **Share of the battery.** A 1200 mAh cell at 3.7 V holds roughly 16000 J, so
  96 J is about 0.6 percent of a full charge.

## A second sensor

The INA219 has solder pads marked A0 and A1. Bridging A0 changes the address
from 0x40 to 0x41, so a second board can share the same two data wires. Set
`I2C_ADDRESS` accordingly and run a second copy on a different port.

With one on the solar input and one on the battery lead you can separate what
comes in from what goes out, even when both happen at once. With a single
sensor on the battery you only ever see the net result.
