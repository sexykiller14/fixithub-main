---
title: Fix random restarts on Windows
category: windows
tags: [restarts, bsod, overheating, psu, updates, reliability monitor]
difficulty: moderate
os_version: Windows 10/11
featured: true
---

Random restarts have four real causes: blue screen crashes, overheating, power
supply faults, and scheduled update restarts. Work out which one you have first.

## Step 1: Find out what Windows recorded

1. Press Windows key plus R
2. Type `perfmon /rel` and press Enter
3. Look at the red X markers on the days the machine restarted

| What you see | What it means |
| --- | --- |
| "Stop error" with a blue screen | A crash, go to step 2 |
| "Hardware error" | Hardware fault, usually power or heat |
| A service or app failure | Software, see below |
| Nothing at all | No crash, go to step 3 |

## Step 2: If a blue screen appeared

The stop code tells you what to fix. Look it up in our
[BSOD lookup](/bsod), or upload a minidump to our
[analyzer](/bsod/analyze) to get the code and parameters explained.

The most common causes in order:

1. Faulty RAM
2. A corrupt or mismatched driver, usually graphics or network
3. A failing drive
4. Overheating
5. A failing power supply

## Step 3: If it restarts without a blue screen

Answer these:

**Does it get hot first?** If yes, it is thermal. See
[high temperatures](/articles/fix-high-cpu-temperature).

**Does it restart under heavy load while staying cool?** That points to power
delivery. See [PSU failure symptoms](/articles/psu-failure-symptoms).

**Does it restart at a similar time each day?** That is a Windows Update
schedule. See [Windows Update failing](/articles/fix-windows-update-failing)
for how to set active hours.

**Did you upgrade anything recently?** Added hardware that exceeds the power
supply's rating causes load-related restarts with no error message.

## Fix 1: Check the power supply

The most under-diagnosed cause. Check:

- Total wattage against your GPU and CPU draw
- That every modular cable came with that power supply
- Whether a known-good PSU fixes the problem, which is the only reliable test

> [!DANGER]
> Never open a power supply. The capacitors inside hold a lethal charge even when
> unplugged. Only use modular cables from the same PSU model.

## Fix 2: Check temperatures

Load the machine and watch temperatures using our
[hardware monitoring guide](/articles/fix-high-cpu-temperature). CPU above 90C
under sustained load, or GPU above 85C, causes thermal shutdowns.

## Fix 3: Test memory

Run MemTest86 for two full passes. Any error at all means faulty RAM. Test one
stick at a time in each slot. See
[testing RAM](/articles/test-ram-memory-errors).

## Fix 4: Check the drive

Run our [disk health script](/scripts/disk-health). A failing drive causes
restarts with no blue screen, and it is easy to mistake for a power problem.

## Fix 5: Update drivers

In this order, because chipset drivers underpin everything else:

1. Chipset
2. Graphics
3. Network
4. Storage controller

For graphics, do a clean install with DDU. See
[clean GPU driver uninstall](/articles/clean-gpu-driver-uninstall-ddu).

## Fix 6: Disable Fast Startup

Fast Startup saves and restores kernel state, which turns a one-off crash into a
permanent problem. See
[disable Fast Startup](/articles/disable-fast-startup-hibernation).

## Fix 7: Check for a failing USB device

A shorted USB device can pull the whole system down. Disconnect everything and
test:

1. Disconnect all USB devices
2. Test the machine
3. Add them back one at a time

If a specific device causes the restarts, replace it.

## Fix 8: Check event logs for the pattern

Our [system report script](/scripts/system-report) captures the last three days
of critical and error events, which usually makes the pattern obvious.

## Capture the exact moment

If restarts are rare and unexplained:

1. Set Windows to write a small memory dump:
   Windows key plus R, `sysdm.cpl`, Advanced tab, Startup and Recovery
2. Tick Write debugging information to: Small memory dump
3. Upload the resulting file to our [minidump analyzer](/bsod/analyze)

## When to see a technician

See a professional if:

- Restarts continue with a known-good PSU, clean memory tests and stock settings
- The machine resets with no blue screen and no heat
- You hear clicking, see burn marks, or smell burning
- Restarts happen only when the graphics card is under load

These point to motherboard or power supply failure.

## Related stop codes

- [THREAD_STUCK_IN_DEVICE_DRIVER](/bsod) is the classic driver-hang restart
- [CLOCK_WATCHDOG_TIMEOUT](/bsod) and
  [DPC_WATCHDOG_TIMEOUT](/bsod) both cause resets
- [WHEA_UNCORRECTABLE_ERROR](/bsod) is a hardware-level warning
