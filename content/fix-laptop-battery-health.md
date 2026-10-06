---
title: Check and improve laptop battery health
category: hardware
tags: [laptop, battery, charge cycle, health, power, capacity]
difficulty: easy
os_version: Windows 10/11
---

Laptop batteries wear out. Understanding where they are in their life tells you
whether to keep using one or start planning a replacement.

## Generate a battery report

Windows has a built-in command:

1. Open Command Prompt or PowerShell
2. Run:

```text
powercfg /batteryreport /output battery.html
```

3. Open the generated `battery.html` file from the folder you were in

> [!IMPORTANT]
> Run this from an ordinary command prompt or PowerShell window. It needs no
> administrator rights. Older versions of Windows used `powercfg /energy` for a
> different report.

## Read the report

Look at these fields under Battery usage:

| Field | Meaning |
| --- | --- |
| Design capacity | What the battery held when new |
| Full charge capacity | What it holds now |
| Cycle count | How many full charges it has had |
| Active | Time on battery since the last full charge |

## Work out the health percentage

```text
health = full charge capacity / design capacity × 100
```

Example: design 45000 mWh, full charge 36000 mWh, so health is 80 percent.

| Health | What to expect |
| --- | --- |
| Above 85 percent | Normal, no action needed |
| 75 to 85 percent | Reduced runtime, keep an eye on it |
| 60 to 75 percent | Noticeably shorter runtime |
| Below 60 percent | Replace it soon |

> [!IMPORTANT]
> A battery that is several years old losing 20 percent capacity is normal.
> Losing 30 percent or more in under two years suggests heat, overcharging or a
> poor quality cell.

## Improve battery life

**Reduce heat**, which is the biggest factor:

- Keep the laptop off soft surfaces such as beds and cushions
- Use a hard surface for long sessions
- Clean the vents
- Avoid heavy gaming while plugged in, since heat is the same either way

**Avoid staying at 100 percent**, which stresses the cells:

- Charge only to 80 percent where the battery supports it
- Windows 11 offers battery charge limits in Settings > System > Power & battery
- Some laptop vendors provide their own charge limit utility in their software
- Leave it unplugged when working near a socket for long stretches

**Reduce drain per hour:**

- Lower screen brightness
- Use battery saver mode
- Turn off Wi-Fi and Bluetooth when not needed
- Reduce sleep timeout
- Close background applications, especially browsers

## Calibrate the battery occasionally

If the reported capacity seems wrong, calibration helps:

1. Charge to 100 percent and leave it plugged in for two hours
2. Use the laptop until it shuts down from low battery
3. Leave it switched off and discharging to about 5 percent
4. Charge it fully without interruption

> [!WARNING]
> Do this once or twice a year, not regularly. Deliberately draining a battery to
> zero stresses the cells.

## Repair swollen batteries

> [!DANGER]
> A swollen battery is dangerous. Stop using the laptop on mains power and do not
> puncture, squeeze or open the cell. Take it to a repair shop.

Signs of swelling:

- The trackpad or case bulges
- The keyboard sits unevenly
- The screen no longer closes flush
- The battery case is curved

A swollen battery can rupture and, in rare cases, ignite. Do not press on it.

## Replace it

Replace the battery when:

- Health is below 60 percent and runtime is unacceptable
- It charges but discharges much faster than expected
- The laptop will not charge it any more
- It swells

Always buy a battery that matches the exact model number, and check that it is
genuine or from a reputable supplier. Very cheap replacement cells are the
leading cause of laptop fires.

## Charging myths

| Claim | Reality |
| --- | --- |
| Leaving it plugged in destroys it | Heat does, not the charger |
| You must drain to zero | Modern batteries have no such memory |
| 0 to 100 percent is best | Partial cycles are gentler |
| Leaving it full overnight is fine | Heat matters more than the level |
| Fast charging is bad | Mild, but sustained high heat is worse |

## Related stop codes

- [POWER_STATE_FAILURE](/bsod), which is very common on ageing laptops
- [DRIVER_POWER_STATE_FAILURE](/bsod)
- [INTERNAL_POWER_ERROR](/bsod)
- [ACPI_BIOS_ERROR](/bsod)

## Related

- [Laptop sleep and wake problems](/articles/laptop-sleep-wake-issues)
- [Disable Fast Startup](/articles/disable-fast-startup-hibernation)
- [PSU failure symptoms](/articles/psu-failure-symptoms)
