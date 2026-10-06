---
title: AMD driver install and troubleshooting
category: drivers
tags: [amd, radeon, adrenalin, driver, code 43, graphics, ryzen]
difficulty: easy
os_version: Windows 10/11
---

## Adrenalin Edition

AMD calls its driver package Adrenalin Edition, and it covers both Radeon
graphics and Ryzen processors.

Download from
[amd.com/en/support](https://www.amd.com/en/support). Select your exact
product, since the package differs between GPU and CPU families.

> [!IMPORTANT]
> The "auto-detect" tool works well, but verify afterwards that it selected the
> right product. It sometimes chooses the generation rather than the exact model.

## Installation options in Adrenalin

| Option | What it does | When to use |
| --- | --- | --- |
| Install | Keeps your settings | Normal updates |
| Clean Install | Resets settings and reinstalls | After a driver problem |
| Factory Reset | Removes the driver entirely | DDU failed |
| Driver Reset | Quick restart of the driver | A single app is misbehaving |

## Reset the graphics driver

AMD's software is fast to reset, and this fixes a surprising number of problems.

Press Windows key plus Control plus Shift plus B, or open AMD Software > Tools >
Reset Driver.

## Disable automatic driver updates

1. Open AMD Software
2. Settings > System
3. Turn off Check for Updates, or set it to Manual

Otherwise AMD replaces your working driver with a newer one behind your back.

Also turn off the overlay in Settings, since it hooks the display driver.

## Code 43 on Radeon

**Causes:**

- Overclock or undervolt
- Driver corruption
- Overheating
- Insufficient power
- Hardware failure

**Fix, in order:**

1. Open AMD Adrenalin > Performance and reset every overclock and undervolt,
   including saved profiles
2. Clean reinstall with
   [DDU](/articles/clean-gpu-driver-uninstall-ddu)
3. Update chipset drivers
4. Check GPU temperature under load
5. Confirm power connectors are fully seated

## Black screen while gaming

- Reset the driver with the keyboard shortcut above
- Reset all overclocks
- Clean reinstall with DDU
- Disable the overlay
- Turn off hardware-accelerated GPU scheduling in Settings > System > Display >
  Graphics

[VIDEO_TDR_FAILURE](/bsod) and
[VIDEO_DXGKRNL_FATAL_ERROR](/bsod) are the related stop codes.

## Adrenalin installation errors

**"Driver installation failed"**

1. Uninstall the current driver in Adrenalin using Factory Reset
2. Restart
3. Or use [DDU](/articles/clean-gpu-driver-uninstall-ddu) in Safe Mode
4. Install the newest driver, or step back to a previous version

**"AMD Software cannot start"**

Uninstall Adrenalin completely, reboot, then install the driver package directly
from AMD rather than the auto-detect wrapper.

**"Failed to apply changes"**

Another program is controlling the driver. Uninstall or close MSI Afterburner,
RTSS, RGB utilities and fan control software, then retry.

## Adrenalin and other tools conflict

You should not run several tools that control the same card. Pick one:

- AMD Adrenalin, or
- MSI Afterburner with RivaTuner Statistics Server

Running both, or adding RGB and fan tools from several vendors, causes
instability. Choose one and uninstall the rest.

## AMD Ryzen processors

If your problem is the CPU rather than the graphics, install from AMD's chipset
drivers page rather than the graphics package.

Update in this order:

1. Chipset driver
2. Graphics driver
3. Motherboard BIOS from the board vendor

## Verify the driver loaded

1. Open AMD Software > System
2. Confirm the driver version and date
3. If it does not match what you installed, check Windows Update optional updates
   and disable driver replacement

## Common myths

| Claim | Reality |
| --- | --- |
| AMD drivers are less stable than NVIDIA | Not generally true on modern drivers |
| You must always reinstall after Windows Update | Disable driver replacement instead |
| AMD Software is required | The driver works without it |
| Factory Reset is safe on any machine | It removes the driver, so do it deliberately |

## Related stop codes

- [VIDEO_TDR_FAILURE](/bsod)
- [VIDEO_DXGKRNL_FATAL_ERROR](/bsod)
- [VIDEO_MEMORY_MANAGEMENT_INTERNAL](/bsod)
- [THREAD_STUCK_IN_DEVICE_DRIVER](/bsod)

## Related

- [Clean GPU driver uninstall with DDU](/articles/clean-gpu-driver-uninstall-ddu)
- [NVIDIA driver guide](/articles/nvidia-driver-guide)
- [High CPU and GPU temperatures](/articles/fix-high-cpu-temperature)
