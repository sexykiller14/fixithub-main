---
title: Speed up a slow Windows PC
category: windows
tags: [performance, startup, ssd, disk cleanup, sfc, dism]
difficulty: easy
os_version: Windows 10/11
featured: true
---

Work through these in order of how much they help. The first two change
everything; the rest are worth doing but rarely transformative.

## Fix 1: Check whether you have a mechanical drive

This matters more than anything else. Task Manager > Performance > Disk shows the
media type.

If it says HDD, replacing it with an SSD is a 5 to 10 times improvement on
almost everything. No software setting can compete. See our
[HDD to SSD guide](/articles/hdd-to-ssd-upgrade-guide).

## Fix 2: Have enough memory

Check Settings > System > About > Installed RAM.

- **4 GB or less**: too little for Windows 11 in practice
- **8 GB**: workable for office use
- **16 GB**: comfortable for most people
- **32 GB or more**: only needed for video editing, large games or heavy
  development

If memory sits above 85 percent while you work, adding RAM gives a real
improvement. See [upgrading RAM](/articles/upgrade-ram-laptop-desktop).

## Fix 3: Trim startup programs

1. Press Ctrl plus Shift plus Esc for Task Manager
2. Open the Startup apps tab
3. Disable chat clients, game launchers, cloud sync, printer tools and anything
   else you do not use daily

Also check Settings > Apps > Startup, which covers some programs Task Manager
does not show.

> [!WARNING]
> Never disable antivirus, chipset drivers, storage drivers, or Windows Update
> components. Disabling a driver can stop hardware from working.

## Fix 4: Free up disk space

Keep at least 15 to 20 percent of the system drive free. A nearly full drive is
slow and causes updates to fail.

1. Search for Disk Cleanup and open it
2. Select your drive and click Clean up system files
3. Tick Previous Windows installation(s) if you do not need to roll back
4. Tick Windows Update Cleanup, which can free several GB
5. Confirm and run

> [!DANGER]
> "Previous Windows installation" contains your ability to go back to your
> earlier version of Windows. Only delete it if you are certain you do not need
> it.

## Fix 5: Repair system files

Open Command Prompt as Administrator:

```text
DISM /Online /Cleanup-Image /StartComponentCleanup
```

```text
sfc /scannow
```

The first removes superseded component versions that accumulate after updates.
The second repairs protected system files.

## Fix 6: Limit Windows Search indexing

Indexing every file on a large drive uses disk and CPU constantly.

1. Settings > Privacy & security > Windows Search > Indexing options
2. Click Modify and select only your user folder and Program Files
3. Leave the Windows folder, System32 and drive roots unindexed

You can still search, just not as deeply.

## Fix 7: Disable startup animations and transparency

Settings > System > Display > Scroll down to Visual effects:

- Turn off Animate controls and windows
- Turn off Animations in Windows
- Turn off Transparency

This makes menus and windows appear instantly rather than sliding in. It is a
visible difference on a slow machine.

## Fix 8: Check for malware

Run Windows Security > Virus & threat protection > Scan options > Full scan.

Then run a Microsoft Defender Offline scan, which reboots into a separate
environment where some malware cannot hide.

> [!WARNING]
> Never install antivirus from a pop-up or an advertisement. Use Windows Security
> or a vendor's official site. Free PC "optimiser" bundles advertised this way
> are a common malware delivery method.

## What not to do

- Do not install registry cleaners. They rarely help and sometimes break Windows.
- Do not disable the page file. Windows needs it.
- Do not defrag an SSD. Windows runs TRIM automatically, which is the correct
  tool.
- Do not disable Windows Update permanently.
- Do not delete files from C:\Windows or System32 by hand.

## Measure the result

Use Task Manager's Performance tab before and after. The CPU, memory and disk
graphs tell you whether a change actually helped, rather than whether it felt
better for a day.

Our [system report script](/scripts/system-report) captures a full picture in one
go.

## Related

- [Why my PC is slow after an upgrade](/articles/fix-slow-pc-after-upgrade)
- [Fix high CPU usage](/articles/fix-high-cpu-usage)
- [Repair Windows system files](/articles/repair-windows-system-files)
