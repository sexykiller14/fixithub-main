---
title: USB-C and dock problems
category: hardware
tags: [usb-c, dock, hub, charging, display, thunderbolt]
difficulty: easy
os_version: Windows 10/11
---

USB-C is a connector, not a standard. A USB-C port can carry power, data, video
or a combination, and not all ports support all features.

## First, understand what USB-C can do

| Function | Requires |
| --- | --- |
| Charging | Port with power delivery |
| Data transfer | Port with data lanes and an attached data connection |
| Video output | Port supporting DisplayPort Alt Mode or Thunderbolt |
| Thunderbolt 3 or 4 | Port with Thunderbolt, and a Thunderbolt dock |

A USB-C port that supports charging but not video will not output a picture to a
monitor through an adapter, no matter which adapter you buy.

> [!IMPORTANT]
> Check whether your specific port supports the feature you need. Laptop ports
> vary, and only some models support video output over USB-C.

## Symptom: charges but no data

- Try a different cable, since many are power-only
- Confirm the cable is a data cable rather than a charge-only one
- Update the chipset and USB controller drivers from your PC vendor
- Test with a known-good cable before suspecting the port

## Symptom: no display through the adapter

1. Confirm the port supports video output
2. Connect the display directly to the dock rather than through an intermediate
   adapter
3. Try a different port on the dock
4. Update chipset and graphics drivers
5. Use the Windows key plus P to select the external display

Some docks need a firmware update, which the manufacturer provides through their
own tool.

## Symptom: dock is not detected at all

1. Connect the dock's power adapter. Most docks require one.
2. Plug the host cable into a rear motherboard port, not a front panel or hub
3. Connect power before data, and wait a few seconds
4. Reduce attached devices to one and add them back

## Symptom: only some ports work

- Some docks are bus-powered and cannot run many devices. Use a powered dock.
- Some ports are not data-capable on certain docks, only for charging
- Too many bus-powered devices exceed what one port can supply

## Symptom: charges slowly or not at all

- Try a different charger and cable
- Remove intermediate hubs
- Check the charger is rated for your device's requirement
- Some laptops charge slowly from unpowered ports by design

> [!WARNING]
> Charging standards vary. A 60 W charger may not charge a laptop that needs
> 100 W, and it may not charge at all while in use.

## Symptom: display flickers

- Try a different cable, since long or poor-quality cables cause flicker
- Use the native port rather than an adapter
- Update graphics drivers
- Turn off DisplayPort's DSC or high refresh mode if your dock supports it

## Symptom: monitors drop out on wake

- Disable Fast Startup, which saves and restores an inconsistent state
- Disconnect external monitors and test
- Update the dock's firmware
- Update chipset and graphics drivers

## Symptom: Thunderbolt 4 dock not working

- Confirm the port is Thunderbolt, not just USB-C. Ports look identical.
- Install the dock manufacturer's driver utility
- Check that the laptop model officially supports the dock
- Update BIOS firmware

## Clean the port

Pocket lint is the most common cause of a port that works at certain angles.

1. Power off and unplug
2. Inspect with a torch
3. Clear gently with a wooden toothpick or plastic tray tool
4. Never use metal tools, which bend or short the contacts

> [!DANGER]
> Metal tweezers, a knife or a paperclip can permanently destroy a USB-C port.
> Only ever use non-conductive tools.

## Choosing a replacement dock

Match the dock to the port, not to the shape:

- Check whether the port is Thunderbolt 3, Thunderbolt 4, or USB-C with Display
  Alt Mode
- Check how many displays you need, since two displays usually need a
  DisplayPort or Thunderbolt dock
- Check the total power budget for attached devices
- Prefer a brand with firmware updates available

## Related stop codes

- [UCMUCSI_FAILURE](/bsod), which involves USB-C and power management
- [BUGCODE_USB3_DRIVER](/bsod)
- [BUGCODE_USB_DRIVER](/bsod)
- [POWER_STATE_FAILURE](/bsod)

## Related

- [USB device not recognized](/articles/fix-usb-device-not-recognized)
- [Laptop sleep and wake problems](/articles/laptop-sleep-wake-issues)
- [Laptop battery health](/articles/fix-laptop-battery-health)
