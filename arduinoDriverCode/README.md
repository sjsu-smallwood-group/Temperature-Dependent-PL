# Jankomotor 8812 Arduino Controller

Simple, production-ready Arduino controller for New Focus Picomotor 8812 actuators.

## ⚠️ Safety Features

- **Emergency Stop Button** (Pin 2) - Immediately stops all movement
- **Limit Switches** (Pins 3,4,7,8) - Prevents over-travel damage
- **Current Monitoring** (Pin A0) - Protects against electrical overload
- **Watchdog Timer** - Resets system if it freezes
- **Software Limits** - Configurable position boundaries

## Hardware Connections

### Motor Control
- **Pin 5** → X_PH (X axis direction)
- **Pin 9** → X_EN (X axis enable/pulse)
- **Pin 6** → Y_PH (Y axis direction)
- **Pin 10** → Y_EN (Y axis enable/pulse)

### Safety Systems
- **Pin 2** → Emergency Stop Button (to GND)
- **Pin 3** → X Min Limit Switch (to GND)
- **Pin 4** → X Max Limit Switch (to GND)
- **Pin 7** → Y Min Limit Switch (to GND)
- **Pin 8** → Y Max Limit Switch (to GND)
- **Pin A0** → Current Sense (from motor driver)

### Status
- **Pin 12** → Trigger Output (for spectrometer)
- **Pin 13** → Status LED

## Commands

### Basic Control
- `ENABLE` - Enable motor system
- `DISABLE` - Disable motor system
- `MOVE X <steps>` - Move X axis relative
- `MOVE Y <steps>` - Move Y axis relative
- `MOVE XY <x> <y>` - Move both axes
- `POSITION` - Get current position
- `STATUS` - Get system status
- `STOP` - Emergency stop
- `HOME` - Home both axes

### Safety
- `SAFETY` - Get safety status
- `SET_LIMITS <xmin> <xmax> <ymin> <ymax>` - Set software limits

### Help
- `HELP` - Show command list

## Usage

1. Upload `Jankomotor8812.ino` to your Arduino
2. Connect safety hardware (limit switches, emergency stop)
3. Open Serial Monitor at 9600 baud
4. Send commands to control the motors

## Example

```
ENABLE
MOVE X 1000
MOVE Y -500
POSITION
STATUS
DISABLE
```

## Safety Notes

- **Always connect limit switches** before first use
- **Test emergency stop** before running motors
- **Set appropriate software limits** for your setup
- **Monitor current readings** to ensure proper operation
- **Start with small movements** to verify operation

## Troubleshooting

- **"ERROR: System not enabled"** → Send `ENABLE` command
- **"ERROR: Emergency stop active"** → Release emergency stop button
- **"ERROR: Position would exceed limits"** → Check software limits
- **"ERROR: Current overload"** → Check motor connections and power
