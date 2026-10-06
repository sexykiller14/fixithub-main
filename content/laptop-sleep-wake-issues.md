---
title: Fix laptop sleep and wake problems
category: hardware
tags: [laptop, sleep, wake, hibernation, power, fast startup]
difficulty: moderate
os_version: Windows 10/11
---

A laptop that will not sleep, or will not wake, is usually a driver, a USB
device, or an aggressive power setting.

## Symptom: it will not go to sleep

**Check what is blocking it.** Open Command Prompt as Administrator and run:

```text
powercfg /requests
```

Anything listed with a "Display" or "System" request is preventing sleep. The
output names the process.

Common blockers:

- Media players and video calls
- A USB device such as a phone charger, webcam or card reader
- Network shares keeping the system awake
- Print spooler
- A scheduled task

**Disconnect all USB devices** and try again. This fixes it surprisingly often.

**Fix the lid close action.** Settings > System > Power & battery > Screen and
sleep. Choose Sleep, Hibernate or Shut down deliberately rather than leaving it
on the default.

## Symptom: it sleeps but will not wake

**Turn off Fast Startup first.** Fast Startup saves and restores kernel state,
which is the most common cause of wake failures:

```text
powercfg /h off
```

Restart and test. See
[disable Fast Startup](/articles/disable-fast-startup-hibernation).

**Test with external devices disconnected**, particularly monitors and docks.
A display handshake failure at wake is a common cause.

**Update the chipset and graphics drivers** from your laptop vendor. Power
management lives in the chipset driver, and it matters more than most people
expect.

**Check the BIOS for a power problem.** Load BIOS defaults, and look for
settings such as Wake on LAN, Wake on PCI-E and Deep Sleep that can cause
problems. Some firmware versions have known wake bugs fixed by an update.

## Symptom: it wakes to a black screen

The system is awake but the display is not reinitialising.

1. Press Windows key plus Ctrl plus Shift plus B to reset the graphics driver
2. Connect an external monitor to test whether the internal panel is at fault
3. If the external monitor works, the internal panel cable or backlight has
   failed

Our [black screen guide](/articles/fix-black-screen-no-display) covers this in
detail.

## Symptom: it wakes to a login screen instead of resuming

Some drivers prevent sleep, so Windows hibernates instead. Once hibernation is
disabled, this cannot happen.

If you need programs to resume, hibernation is the correct mode to choose rather
than sleep.

## Symptom: it hangs on the way to sleep

- Update chipset, graphics and power management drivers
- Disable Fast Startup
- Unplug all USB devices
- Set the sleep timeout to Never while testing
- Update BIOS firmware

## Check for driver conflicts

These commonly cause sleep and wake problems:

- Intel or AMD power management drivers, especially older versions
- Bluetooth drivers, which can block sleep
- RGB and fan control software
- VPN clients with filter drivers
- Antivirus filter drivers

Update or remove them one at a time.

## Restore balanced power settings

An over-tuned power plan can cause wake problems. Reset it:

1. Settings > System > Power & battery
2. Choose Additional power settings
3. Click Restore default settings for this plan

## Check the lid switch

A faulty lid switch causes a laptop that thinks the lid is closed, so it never
sleeps. Signs: it sleeps only when you close it fully with pressure, or the
screen turns off when the lid is barely closed.

## Check for a failing CMOS battery

If the clock resets every time the laptop is shut down, the CMOS battery is
dead. That causes unreliable firmware power states and wake failures. The CR2032
cell is cheap to replace.

## When to see a technician

See a professional if:

- The laptop will not complete a sleep cycle with all drivers updated and no
  devices attached
- It wakes to a black screen with a working external monitor
- It hangs on the battery health report, suggesting a swollen battery pressing
  on internal components

## Related stop codes

- [WIN32K_POWER_WATCHDOG_TIMEOUT](/bsod), extremely common on laptop wake
- [POWER_STATE_FAILURE](/bsod)
- [DRIVER_POWER_STATE_FAILURE](/bsod)
- [INTERNAL_POWER_ERROR](/bsod)
- [CRITICAL_OBJECT_TERMINATION](/bsod)

## Related

- [Laptop battery health](/articles/fix-laptop-battery-health)
- [Disable Fast Startup](/articles/disable-fast-startup-hibernation)
- [High CPU temperature](/articles/fix-high-cpu-temperature)
