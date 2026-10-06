---
title: "VIDEO_TDR_FAILURE and other graphics driver crashes"
category: bsod
tags: [bsod, tdr, graphics, gpu, nvidia, amd, black screen]
difficulty: moderate
os_version: Windows 10/11
featured: true
---

`VIDEO_TDR_FAILURE` means the graphics driver stopped responding and Windows
could not reset it. It belongs to a family of codes that all point at the same
place.

## The TDR family

| Code | Name | Notes |
| --- | --- | --- |
| `0x116` | VIDEO_TDR_FAILURE | The classic one |
| `0x117` | VIDEO_TDR_TIMEOUT_DETECTED | Display driver timeout |
| `0x119` | VIDEO_SCHEDULER_INTERNAL_ERROR | Often after wake from sleep |
| `0x10E` | VIDEO_MEMORY_MANAGEMENT_INTERNAL | Video memory problems |
| `0x113` | VIDEO_DXGKRNL_FATAL_ERROR | DirectX graphics kernel fault |
| `0xB4` | VIDEO_DRIVER_INIT_FAILURE | Driver failed at startup |

## What it looks like

- Black screen with sound still playing
- Screen goes black during a game or a video call
- The screen recovers after a few seconds
- Repeated restarts, or the stop code after a freeze
- Desktop sometimes recovers without a crash

## Cause 1: A bad driver version

The most common. Windows Update and vendor auto-updaters both install drivers
that cause faults.

1. Boot into Safe Mode
2. Uninstall the graphics driver with Delete the driver software ticked
3. Restart and install a known-good driver

For a thorough clean removal, use
[DDU in Safe Mode](/articles/clean-gpu-driver-uninstall-ddu).

> [!WARNING]
> Roll Back Driver is faster if it is available. It is greyed out when you have
> never updated that driver.

## Cause 2: Overclock or undervolt

Very common on cards that were fine until someone tuned them.

1. Open MSI Afterburner, NVIDIA App or AMD Adrenalin
2. Reset every overclock and undervolt to default
3. Delete any saved profiles that load automatically
4. Test again

> [!IMPORTANT]
> Do this before anything else. It takes two minutes and fixes a large share of
> cases.

## Cause 3: Overheating

1. Monitor GPU temperature while you reproduce the fault
2. Sustained above 85C causes throttling and driver faults
3. Clear dust from the cooler and fans
4. Check the fan curve in your GPU utility

See [high temperatures](/articles/fix-high-cpu-temperature).

## Cause 4: Insufficient or faulty memory

- Run MemTest86 for two full passes
- Disable XMP/EXPO while testing
- Check the drive's health, since a failing drive also faults video

[VIDEO_MEMORY_MANAGEMENT_INTERNAL](/bsod) points more directly at video memory
than at system RAM.

## Cause 5: Power supply

Cards that draw heavily under load cause restarts and driver faults when the
supply cannot keep up.

- Check total wattage against the card's requirement, with headroom
- Reseat every power connector until it clicks
- Test with a known-good PSU

> [!DANGER]
> Only use modular cables that came with the same power supply model. Mixing
> cables from different units destroys hardware.

## Cause 6: Overlays and capture software

These hook the display driver and are a frequent cause of TDR crashes.

- GeForce Experience in-game overlay
- AMD Adrenalin overlay
- Discord overlay
- Xbox Game Bar
- OBS and other capture tools
- Wallpaper Engine and similar

Disable them one at a time and test.

## The order that works

1. Reset all overclocks and undervolts
2. Clean reinstall the driver with
   [DDU](/articles/clean-gpu-driver-uninstall-ddu)
3. Install the newest stable driver
4. Disable Windows Update driver replacement
5. Update chipset drivers
6. Disable overlays and hardware-accelerated GPU scheduling
7. Test memory, then disk health
8. Check GPU temperature
9. Check the power supply

## Disable hardware-accelerated GPU scheduling

Settings > System > Display > Graphics > Default graphics settings > Hardware
accelerated GPU scheduling. Turn it off, then reboot.

## Disable Windows Update driver replacement

Otherwise your working driver gets swapped out silently and the crash returns.

Settings > Windows Update > Advanced options > Optional updates > Driver
updates > Pause updates.

## Multi-monitor problems

`VIDEO_TDR_TIMEOUT_DETECTED` often appears after changing monitors or cables.

- Reconnect every display cable
- Test with a single monitor
- Try different HDMI or DisplayPort inputs
- Remove custom resolutions and refresh rates

## Related

- [NVIDIA driver guide](/articles/nvidia-driver-guide)
- [AMD driver guide](/articles/amd-driver-guide)
- [Black screen or no display](/articles/fix-black-screen-no-display)
- [High CPU and GPU temperatures](/articles/fix-high-cpu-temperature)

## When to see a technician

See a professional if the crash persists at stock clocks, with a clean driver
install, clean memory and disk tests, healthy temperatures and a known-good
power supply. At that point it is failing graphics hardware.
