# USB Ports & Connected Devices — Temperature-Dependent-PL Setup

_Last checked: 2026-07-14_

This documents the USB devices connected to the lab computer and the serial (COM) ports in use. All devices below report `Status: OK`.

## Summary

| Device | Identity | VID / PID | Port |
|---|---|---|---|
| **Arduino** | Arduino Uno R3 (`USB Serial Device`) | `2341 / 0043` | **COM4** |
| **Thorlabs camera** | Thorlabs Camera Zelux | `1313 / 4002` | — (USB) |
| **Keyboard** | Dell wired keyboard (KB216-class) | `413C / 2113` | — (USB) |
| **Mouse** | Logitech mouse | `046D / C040` | — (USB) |

## COM / Serial Ports

| Port | Device | Type |
|---|---|---|
| **COM4** | `USB Serial Device` → **Arduino Uno R3** | USB (this is the one to use for the Arduino) |
| COM1 | Communications Port | Onboard standard port (not USB) |
| COM3 | Intel(R) Active Management Technology - SOL | Virtual (Intel AMT serial-over-LAN, not USB) |

## Device Details

### Arduino — COM4
- Vendor ID `2341` = Arduino LLC (official Arduino vendor ID)
- Product ID `0043` = Arduino Uno R3
- Enumerated as `USB Serial Device (COM4)` → **use `COM4`** in code/IDE to connect to the Arduino.

### Thorlabs Camera Zelux
- Vendor ID `1313` = Thorlabs
- Product ID `4002` = Zelux camera
- Driver loaded and device ready (`Status: OK`).

### Keyboard
- Vendor ID `413C` = Dell
- Product ID `2113` = Dell KB216-class wired keyboard
- Presents as a `USB Composite Device` plus `HID Keyboard Device` interfaces (main keyboard + consumer/media control).

### Mouse
- Vendor ID `046D` = Logitech
- Product ID `C040` = Logitech HID-compliant mouse

## Notes
- Ignore virtual/built-in entries when looking for physical peripherals: `Remote Desktop Keyboard/Mouse` and Intel AMT `SOL (COM3)`. These are not physical USB devices (the machine is accessed over Remote Desktop).
- `COM1` is a standard onboard communications port, not a USB device.

## How this was gathered (for re-checking later)
Run in PowerShell:

```powershell
# List present USB devices
Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match '^USB' } |
    Select-Object Status, Class, FriendlyName | Sort-Object Class | Format-Table -AutoSize

# Get VID/PID for each USB device
Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match '^USB' } | ForEach-Object {
    $null = $_.InstanceId -match 'VID_([0-9A-Fa-f]{4})'; $v = $Matches[1]
    $null = $_.InstanceId -match 'PID_([0-9A-Fa-f]{4})'; $p = $Matches[1]
    [PSCustomObject]@{ Name = $_.FriendlyName; VID = $v; PID = $p }
} | Format-Table -AutoSize

# List COM ports
Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match 'COM\d+' } |
    Select-Object Name, Manufacturer | Format-Table -AutoSize
```
