---
title: Repair Windows system files with DISM and SFC
category: windows
tags: [sfc, dism, system files, repair, corruption, admin]
difficulty: easy
os_version: Windows 10/11
featured: true
---

Windows has two built-in tools for repairing damaged system files. They must be
run in the correct order, which is where most people go wrong.

## What each tool does

**DISM** repairs the component store, which is the master copy of every Windows
system file. **SFC** then compares the files in use against that store and
replaces any that do not match.

SFC cannot repair much on its own if the component store is also damaged. So
DISM runs first.

## How to run them

1. Press Windows key, search for Command Prompt
2. Right-click it and choose Run as administrator
3. Accept the User Account Control prompt

> [!WARNING]
> Without administrator rights these commands appear to do nothing and report
> that the operation could not be completed.

## Step 1: Quick check

```text
DISM /Online /Cleanup-Image /CheckHealth
```

Takes under a minute. Reports whether the component store is already flagged as
repairable.

## Step 2: Detailed scan

```text
DISM /Online /Cleanup-Image /ScanHealth
```

Takes several minutes and finds problems that CheckHealth misses. It changes
nothing.

## Step 3: Restore health

```text
DISM /Online /Cleanup-Image /RestoreHealth
```

This is the step that repairs. It downloads replacement copies of damaged files
from Windows Update and reinstalls them.

> [!IMPORTANT]
> RestoreHealth needs an internet connection. It can take 20 minutes or more on a
> slow connection. A high percentage that sits still for a while is normal and
> not a hang.

> [!WARNING]
> Do not close the window while it is running. Interrupting DISM can leave the
> component store worse than it was.

## Step 4: Repair the files

```text
sfc /scannow
```

This scans and repairs. It cannot be interrupted either.

## Step 5: Run it again

Restart, then run:

```text
sfc /scannow
```

DISM frequently needs two passes before SFC has good source files. If the first
SFC run reports that it could not fix everything, the second usually succeeds.

## Reading the results

**"did not find any integrity violations"**
Your system files were fine. Look elsewhere for the cause.

**"found corrupt files and successfully repaired them"**
Reboot and see whether the problem is gone.

**"was unable to fix some of them"**
Run the whole sequence again. If it still fails, use installation media, below.

**"found corrupt files but was unable to fix some of them"**
Usually a permissions or servicing issue. Boot into Safe Mode and try again.

## When DISM cannot repair

If DISM reports that it cannot repair the source files, Windows Update is also
supplying damaged files. Use installation media:

1. Download Windows 10 or 11 ISO from Microsoft's official site
2. Create a bootable USB with Microsoft's Media Creation Tool
3. Boot from it and choose Repair your computer > Command Prompt
4. Find your Windows drive, usually D: after booting from USB
5. Run:

```text
sfc /scannow /offbootdir=D:\Offline /offwindir=D:\Windows
```

> [!WARNING]
> Confirm the drive letter with `dir D:\Windows` before running this. Repairing
> the wrong volume does nothing useful and wastes a lot of time.

You can download the correct ISO from
[microsoft.com/windows/download](https://www.microsoft.com/windows/download).

## Repairing a single file

SFC can repair one specific file, which is useful when a single file is corrupt:

```text
sfc /scannow /offbootdir=C:\ /offwindir=C:\Windows
```

To find out which file owns an error, check
[our stop code guides](/bsod), since the file named in a crash is often the one
that needs replacing.

## Automatic repair

Windows has its own built-in repair:

1. Settings > System > Recovery > Advanced startup > Restart now
2. Choose Troubleshoot > Advanced > Startup Repair

Startup Repair focuses on boot problems. DISM and SFC are more thorough for
system file corruption.

## Related stop codes

These all often resolve with DISM plus SFC:

- [SYSTEM_ENTRY_NOT_FOUND](/bsod)
- [BAD_IMAGE](/bsod)
- [FILE_CHECKSUM](/bsod)
- [NTFS_FILE_SYSTEM](/bsod), if the drive itself is healthy

> [!WARNING]
> If your drive is failing, repairing system files will not stick. Check SMART
> first with our [disk health script](/scripts/disk-health).

## Use the script

Our [system file repair script](/scripts/system-file-repair) runs these commands
in the correct order and checks for administrator rights first. Read the full
source before running it.
