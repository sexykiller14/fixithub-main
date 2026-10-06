---
title: Fix Windows Update failing
category: windows
tags: [windows update, update errors, 0x80070002, restart, install]
difficulty: moderate
os_version: Windows 10/11
---

Update failures are usually a cache problem, a conflicting driver, or a
component store that needs repairing.

## Identify the error first

Settings > Windows Update > Update history shows the error code. The common
ones:

| Code | Meaning |
| --- | --- |
| `0x80070002` | A file is missing, usually from a failed previous update |
| `0x80070003` | A path is wrong, often leftover from an old install |
| `0x80070005` | Access denied, needs administrator rights |
| `0x80073712` | The component store is corrupt |
| `0x80073715` | Some files are missing |
| `0x800704c7` | Operation cancelled by a request |

## Fix 1: Restart the update components

This resets the Windows Update service, which clears most stuck states. Open
Command Prompt as Administrator:

```text
net stop wuauserv
```

```text
net stop bits
```

```text
net stop cryptsvc
```

```text
net stop msiserver
```

```text
ren C:\Windows\SoftwareDistribution SoftwareDistribution.old
```

```text
ren C:\Windows\System32\catroot2 catroot2.old
```

Now start them again:

```text
net start cryptsvc
```

```text
net start bits
```

```text
net start wuauserv
```

```text
net start msiserver
```

Restart the PC and try the update again.

> [!WARNING]
> Renaming these folders deletes the update cache. It is safe, since Windows
> rebuilds it, but the `.old` folders can be deleted afterwards once the update
> works.

## Fix 2: Repair the component store

```text
DISM /Online /Cleanup-Image /RestoreHealth
```

```text
sfc /scannow
```

Error `0x80073712` almost always needs this. See our
[system file repair guide](/articles/repair-windows-system-files).

## Fix 3: Use the troubleshooter

Settings > System > Other > Run troubleshooter, or:

1. Settings > System > Troubleshooting > Other troubleshooters
2. Run Windows Update
3. Also run the Microsoft Store troubleshooter

## Fix 4: Turn off driver updates

Windows Update can install driver versions that break hardware, and a bad one
blocks further updates.

1. Settings > Windows Update > Advanced options > Optional updates
2. Under Driver updates choose Pause updates for 5 weeks

This is worth doing permanently if you install drivers from your PC vendor, as
ours recommend.

## Fix 5: Uninstall the update that caused the problem

Settings > Windows Update > Update history > Uninstall updates.

Pick the most recent update, which is often a preview or optional update rather
than a security one.

> [!WARNING]
> Do not uninstall security updates unless you have a specific reason. Leaving
> Windows unpatched is the main route for ransomware. If a security update keeps
> failing, it is usually worth fixing the underlying problem properly.

## Fix 6: Check for conflicting software

These commonly block or break updates:

- Antivirus suites, especially third-party ones
- VPN clients
- Driver update utilities
- System "tuning" tools
- Registry cleaners

Uninstall one at a time and test.

## Fix 7: Free up space first

Updates need 20 to 30 GB free. If the system drive is nearly full, updates fail
with unhelpful errors.

Check Settings > System > Storage, then run Disk Cleanup with Windows Update
Cleanup ticked.

## Fix 8: Check the system date

An incorrect clock breaks certificate validation, so updates fail to download.

Settings > Time & language > Date & time, then turn on Set time automatically
and Time zone automatically.

## Fix 9: Feature updates need more help

A major version upgrade, such as Windows 10 to 11, sometimes needs the Update
Assistant rather than Windows Update. Microsoft's official Update Assistant is at
[support.microsoft.com](https://support.microsoft.com/windows).

## If nothing works

1. Run an in-place repair by mounting the Windows ISO and running setup.exe from
   it. Choose Keep files and apps.
2. Use Reset this PC keeping your files as a last resort

> [!DANGER]
> In-place repair keeps your files but reinstalls Windows. Back up anything
> irreplaceable first. Reset this PC removes installed applications.

## Related

- [Repair Windows system files](/articles/repair-windows-system-files)
- [CRITICAL_PROCESS_DIED](/articles/critical-process-died), which often follows a
  bad update
- [Fix boot loop](/articles/fix-boot-recovery-loop)
