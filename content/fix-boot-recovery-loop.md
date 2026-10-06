---
title: Fix a boot loop or automatic repair loop
category: windows
tags: [boot, recovery, startup repair, windows update, fixmbr]
difficulty: moderate
os_version: Windows 10/11
featured: true
---

A boot loop means Windows starts, fails, and tries again. The most common form
shows "Preparing automatic repair" repeatedly, sometimes with a countdown
number before each restart.

## Why this happens

- An interrupted Windows Update left the system half-installed
- A recent driver or software change conflicts with the system
- The boot files or Boot Configuration Data are damaged
- The drive is failing
- A third-party antivirus removed a system file

## Get to the Recovery Environment

You have three options. Use whichever is available:

- Wait for automatic repair to fail three times, which forces the Recovery
  Environment
- Press and hold Shift while clicking Restart
- Interrupt the boot by holding the power button when the Windows logo appears

Then choose **Troubleshoot > Advanced**.

## Fix 1: Startup Repair

Choose **Startup Repair** and let it run. It examines boot files, drivers and
system integrity, then repairs what it can.

If it reports that it could not repair the problem, move on. Running it twice
rarely helps further.

## Fix 2: Repair system files

Open **Command Prompt** and run these in order:

```text
DISM /Online /Cleanup-Image /RestoreHealth
```

```text
sfc /scannow
```

DISM repairs the component store using Windows Update, then SFC replaces
individual corrupted files. Run `sfc /scannow` again after a restart, because
DISM frequently needs two passes.

## Fix 3: Rebuild the boot files

```text
bootrec /fixmbr
bootrec /fixboot
bootrec /rebuildbcd
```

If `bootrec /fixboot` reports "Access is denied", the boot partition is not
marked active or is damaged. Rebuild the boot configuration data instead:

```text
bcdboot C:\Windows /s C: /f UEFI
```

Use `/f BIOS` on a machine older than Windows 8.

> [!WARNING]
> Do not format or reinstall during a boot loop until you have checked the
> drive. A failing drive causes boot loops that no reinstall will fix.

## Fix 4: Remove the update that caused it

From Command Prompt in the Recovery Environment, uninstall the latest update:

```text
wmic qfe list brief
```

Note the KB number of the newest update, then remove it:

```text
DISM /Image:C:\ /Remove-Package /PackageName:Package_for_KB5012277
```

Replace the package name with the one you found. You can also uninstall it from
Settings once the machine boots far enough to reach them.

## Fix 5: Uninstall recent drivers and software

Boot into Safe Mode, which loads on a minimal driver set:

1. Interrupt the boot three times and choose Start your PC in Safe mode
2. Open Settings > Apps > Installed apps
3. Uninstall anything added in the days before the problem started
4. Restart

Pay particular attention to antivirus, disk utilities, tuning tools and driver
packages, since these are the usual culprits.

## Fix 6: Check the drive

A failing drive produces a boot loop that looks identical to a software
problem. Run our [disk health check](/scripts/disk-health) script from another
working computer or from the Recovery Environment's command prompt.

If SMART reports failures, back up what you can and replace the drive.

> [!DANGER]
> If the drive reports failures, do not run chkdsk with `/f` on it. Repair writes
> to the drive and can destroy recoverable data.

## Fix 7: Last resort

If the loop survives everything above, reset Windows while keeping your files:

**Settings > System > Recovery > Reset this PC > Keep my files**

This rebuilds the system from scratch and keeps your documents, but removes
installed applications.

> [!DANGER]
> Back up your Desktop, Documents and Downloads first. Reset this PC deletes
> installed applications, and some software needs reinstalling afterwards.
