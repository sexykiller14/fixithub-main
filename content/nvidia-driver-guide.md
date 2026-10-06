---
title: NVIDIA driver install and troubleshooting
category: drivers
tags: [nvidia, geforce, driver, ddU, code 43, graphics]
difficulty: easy
os_version: Windows 10/11
featured: true
---

## Game Ready or Studio?

NVIDIA publishes two driver families:

| Driver | Best for |
| --- | --- |
| Game Ready | Gaming, prioritising new game releases |
| Studio | Video editing, 3D rendering, photo work, streaming |

Both are supported and both get security updates. Choose Studio if you do
creative work, Game Ready if you mostly play.

> [!IMPORTANT]
> Some very new games are optimised for Game Ready drivers on release day.
> Studio drivers catch up within a few weeks.

## Install a driver

1. Get it from NVIDIA directly:
   [nvidia.com/Download/index.aspx](https://www.nvidia.com/Download/index.aspx)
2. Select your product, operating system, and download type
3. Download the driver before installing anything else
4. Run the installer
5. Choose Custom and tick Perform a clean installation if you have previously
   had driver trouble

> [!WARNING]
> Do not use "Driver Update" from GeForce Experience on a machine with problems.
> It can install a different version behind your back. Download from NVIDIA's
> site instead.

## Fix NVIDIA Control Panel missing

After some driver installations the control panel disappears.

1. Download the driver again and run it
2. Choose Custom install
3. Tick Perform a clean installation
4. Reboot and check Settings > Apps for NVIDIA Control Panel

## Disable automatic driver downloads

GeForce Experience reinstalls drivers by itself, which can undo your fix.

1. Open GeForce Experience
2. Settings > Account
3. Turn off Driver Downloads

Also turn off the in-game overlay in Settings > In-game overlay, since it hooks
the display driver and causes some crashes.

## Code 43: Windows has stopped this device

The most common NVIDIA-specific fault.

**Causes:**

- An overclock or undervolt
- A driver corruption
- GPU overheating
- Insufficient power
- Hardware failure

**Fix, in order:**

1. Open MSI Afterburner or the NVIDIA app and reset all overclock and undervolt
   settings to default, including profiles that load automatically
2. Clean reinstall the driver with
   [DDU](/articles/clean-gpu-driver-uninstall-ddu)
3. Update chipset drivers
4. Check GPU temperature under load with our
   [temperature guide](/articles/fix-high-cpu-temperature)
5. Check the power connectors are fully seated and the PSU is adequate

> [!IMPORTANT]
> If Code 43 appears immediately after installing a driver and survives a clean
   install at stock clocks, the card itself may be failing.

## No display after a driver update

Boot into Safe Mode and roll back or reinstall.

1. Interrupt the boot three times and choose Safe mode
2. Device Manager > Display adapters > right-click > Properties > Driver
3. Choose Roll Back Driver if available
4. If not, uninstall the device and install an older known-good version

Our [black screen guide](/articles/fix-black-screen-no-display) covers this in
more detail.

## GeForce Experience errors

**"NVIDIA Graphics Driver is not compatible"**
An old package. Download the current driver from NVIDIA.

**"Cannot install" or "access denied"**
Uninstall the existing driver, restart, then install again as administrator.

**Experience will not launch**
Uninstall GeForce Experience and install the driver only. You do not need
Experience to use your card.

## Black screen while gaming or in a video call

This is usually [VIDEO_TDR_FAILURE](/bsod) without the blue screen. See that
guide, plus:

- Reset all overclocks
- Clean reinstall the driver
- Disable the overlay
- Turn off hardware-accelerated GPU scheduling in Settings > System > Display >
  Graphics

## Low frame rates or stuttering

- Reset any overclock
- Update the driver
- Check GPU temperature, since thermal throttling looks exactly like a slow GPU
- Check whether the power plan is in Balanced rather than High Performance
- Verify the frame rate is not being limited by V-Sync or the frame limiter

## Verify the driver actually loaded

1. Open NVIDIA Control Panel
2. Click System Information at the top left
3. Confirm the driver version matches what you installed

If it does not, something replaced it. Check Windows Update optional updates and
disable driver replacement.

## Related stop codes

- [VIDEO_TDR_FAILURE](/bsod)
- [VIDEO_TDR_TIMEOUT_DETECTED](/bsod)
- [VIDEO_DXGKRNL_FATAL_ERROR](/bsod)
- [VIDEO_DRIVER_INIT_FAILURE](/bsod)
- [VIDEO_MEMORY_MANAGEMENT_INTERNAL](/bsod)

## Related

- [Clean GPU driver uninstall with DDU](/articles/clean-gpu-driver-uninstall-ddu)
- [High CPU and GPU temperatures](/articles/fix-high-cpu-temperature)
- [PSU failure symptoms](/articles/psu-failure-symptoms)
