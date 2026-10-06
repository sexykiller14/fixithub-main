---
title: PC slow after adding a component
category: windows
tags: [performance, upgrade, startup, ssd, ram, hdd, slow]
difficulty: easy
os_version: Windows 10/11
---

Adding a component and then finding the PC is slower is almost always one of six
things.

## 1. The system drive is still a mechanical drive

The most common cause, and the biggest opportunity. Adding RAM does nothing for
disk-bound tasks.

Check Task Manager > Performance > Disk and look at the media type. If it says
HDD, replacing it with an SSD changes everything. See
[HDD to SSD upgrade](/articles/hdd-to-ssd-upgrade-guide).

## 2. Not enough RAM

Check Settings > System > About > Installed RAM.

Windows 11 officially supports 4 GB, but that is not enough for real use. If
memory sits above 85 percent while you work, Windows is constantly paging to
disk, which feels exactly like a slow drive.

See [upgrade RAM](/articles/upgrade-ram-laptop-desktop).

## 3. The system drive is nearly full

Windows needs free space to work. Above 90 percent full, updates fail and
everything slows.

- Check Settings > System > Storage
- Run Disk Cleanup with Windows Update Cleanup ticked
- Clear the Recycle Bin
- Keep 15 to 20 percent free

## 4. RAM is running below its rated speed

After adding memory, a new XMP or EXPO profile may need enabling.

1. Restart and enter BIOS with Del or F2
2. Find the memory settings
3. Enable XMP, EXPO or DOCP for your new kit
4. Save, reboot and confirm the speed in Task Manager > Performance > Memory

> [!WARNING]
> These are overclocked profiles. If your kit is not stable you will get random
> crashes and potentially file corruption. Test with MemTest86 before relying on
> it, and disable the profile if anything is odd.

## 5. Too many programs starting at login

1. Press Ctrl plus Shift plus Esc
2. Task Manager > Startup apps
3. Disable chat clients, game launchers, cloud sync and utilities you do not use

> [!WARNING]
> Never disable antivirus, chipset drivers, storage drivers, or Windows Update
> components.

## 6. New software is running a background service

Newly installed software often adds services and scheduled tasks.

1. Press Windows key plus R, type `taskschd.msc` and press Enter
2. Look in Task Scheduler Library for anything new
3. Check Settings > Apps > Startup for new entries
4. Check services.msc for new services

> [!IMPORTANT]
> Disable rather than delete. Uninstalling later can leave orphaned scheduled
> tasks behind.

## Diagnose properly

Run our [system report script](/scripts/system-report) before and after the
change. It captures what is running and the disk and memory state, so you can
compare rather than guess.

Use Task Manager's Performance tab and watch:

- **Disk at 100 percent with low CPU**: the drive is the bottleneck
- **Memory above 85 percent**: too little RAM for what you are doing
- **CPU above 80 percent**: find the process in Processes

## If it started crashing instead

A new component can cause crashes rather than slowness:

- [MEMORY_MANAGEMENT](/bsod) after adding RAM usually means unstable timings
- [INACCESSIBLE_BOOT_DEVICE](/bsod) after changing a storage mode
- [NO_SUCH_PARTITION](/bsod) after adding a drive, if you unplugged the wrong one

Run MemTest86 first, since bad RAM and unstable memory profiles cause most
component-related crashes. See [test RAM](/articles/test-ram-memory-errors).

## Related

- [Speed up a slow Windows PC](/articles/speed-up-slow-windows-pc)
- [Fix high CPU usage](/articles/fix-high-cpu-usage)
- [Upgrade RAM](/articles/upgrade-ram-laptop-desktop)
