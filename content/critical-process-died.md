---
title: "CRITICAL_PROCESS_DIED: fix the boot loop"
category: bsod
tags: [bsod, boot loop, critical process died, startup repair, windows]
difficulty: moderate
os_version: Windows 10/11
featured: true
---

`CRITICAL_PROCESS_DIED` means a process Windows cannot run without has stopped.
It almost always appears during boot, frequently alongside the automatic repair
screen, and often leaves you stuck in a restart loop.

## What causes it

- An interrupted or failed Windows Update that left a half-installed file
- Antivirus software that removed or corrupted a system file
- A failing system drive
- A corrupt user profile or registry
- A third-party privacy or "tuning" tool

## Fix 1: Boot into Safe Mode and remove recent software

Safe Mode loads only essential drivers, so it starts when Windows will not.

1. Wait for automatic repair to fail three times. Windows will then offer
   "Start your PC in Safe mode", which you should choose.
2. Once at the desktop, open Settings > Apps > Installed apps
3. Uninstall anything installed in the days before the problem, especially
   antivirus, disk tools, tuning utilities and driver packages
4. Restart normally and see whether the crash is gone

> [!WARNING]
> If Safe Mode will not start either, skip to fix 3. Do not uninstall software
> blindly while the machine cannot boot.

## Fix 2: Repair the system files

Once you can get to a command prompt, repair the damaged files. Open
Command Prompt as Administrator from Safe Mode or the Recovery Environment:

```text
DISM /Online /Cleanup-Image /RestoreHealth
```

Wait for it to finish, then run:

```text
sfc /scannow
```

Reboot and run `sfc /scannow` a second time. DISM often needs two passes before
SFC has good source files to compare against.

> [!IMPORTANT]
> `DISM /RestoreHealth` needs an internet connection. If you are offline, use
> `sfc /scannow` alone, but it will fail to repair anything that depends on a
> file DISM could have replaced.

## Fix 3: Use the Recovery Environment

Press and hold Shift while clicking Restart, then choose:

- **Troubleshoot > Advanced > Startup Repair** and let it run
- If that fails, choose **Advanced > Command Prompt** and run `bootrec` commands:

```text
bootrec /fixmbr
bootrec /fixboot
bootrec /rebuildbcd
```

If `bootrec /fixboot` reports "Access is denied", the boot partition needs
rebuilding. Run this instead:

```text
bcdboot C:\Windows /s C: /f UEFI
```

Use `/f BIOS` instead of `/f UEFI` on a very old machine.

## Fix 4: Roll back the update that caused it

If the crash started right after an update, remove it:

1. Settings > Windows Update > Update history
2. Uninstall updates > select the most recent update
3. Restart

Feature updates can also be rolled back within ten days of installation using
Settings > System > Recovery > Go back, provided you have not run
`Disk Cleanup` on Windows.old.

## Fix 5: Check your drive first

Before reinstalling anything, check whether the drive is healthy. A failing
drive causes this stop code and will cause it again after any repair.

Run our [disk health check](/scripts/disk-health) script. It reads SMART data and
runs a read-only filesystem scan, so it changes nothing.

> [!WARNING]
> If SMART reports failures, back up your files before running any repair.
> Repair writes to the drive and can destroy data that is still recoverable.

## Fix 6: Last resort - reset Windows keeping your files

If nothing else works, rebuild the system without touching your data:

1. Settings > System > Recovery > Reset this PC
2. Choose Keep my files
3. Choose Cloud download or Local reinstall, then Continue

This reinstalls Windows but keeps your applications, files and most settings.

> [!DANGER]
> Reset this PC removes applications. Back up anything you cannot reinstall,
> including files on the Desktop and in Documents, before you start. Some drivers
> and highly custom software may need reinstalling afterwards.
