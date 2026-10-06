---
title: "UNMOUNTABLE_BOOT_VOLUME: fix a drive that will not mount"
category: bsod
tags: [bsod, unmountable boot volume, chkdsk, boot, drive]
difficulty: hard
os_version: Windows 10/11
featured: true
---

This stop code means Windows cannot mount the drive it boots from because the
filesystem is damaged. It is usually caused by a power cut or forced shutdown
during a large write, but a failing drive produces the same symptom.

## First, check whether the drive is healthy

This matters more than any repair. If the drive is failing, repairing the
filesystem can destroy the data you have not yet recovered.

Run our [disk health check](/scripts/disk-health) script. It reports SMART data
and runs a read-only scan without changing anything.

- **SMART reports failures**: back up what you can read, then replace the drive
- **SMART is clean**: the filesystem is damaged and repairable, continue below

## Repair the filesystem

Boot into the Recovery Environment. Either wait for automatic repair to fail
three times, or press and hold Shift while clicking Restart, then choose
Troubleshoot > Advanced > Command Prompt.

First find the Windows partition:

```text
diskpart
list volume
```

Note the letter of the Windows volume, then exit diskpart with `exit`. Usually
it is `C`, but it is sometimes another letter on dual-boot machines.

Now repair it:

```text
chkdsk C: /f /r /x
```

`/f` fixes filesystem errors, `/r` finds bad sectors and marks them unusable,
and `/x` forces the volume to dismount first so the repair can run. Confirm with
Y when prompted.

> [!WARNING]
> `/r` reads the entire drive, which on a large failing disk can take many hours.
> If SMART shows failures, do not run `/r`. Back up first.

## If chkdsk reports unrecoverable errors

If chkdsk says it cannot fix the errors, the drive is failing. Your options:

1. Boot from Windows installation media and try chkdsk again from there, since
   the running system has the volume open
2. Use a Linux live USB with `TestDisk` or `ntfsfix`, which can sometimes recover
   a volume Windows cannot
3. Replace the drive and restore from backup

> [!DANGER]
> Do not keep running a drive that reports uncorrectable errors. Every write
> reduces the chance of recovering what remains. Back up readable files first.

## Rebuild the boot files

If chkdsk succeeds but Windows still will not boot, repair the boot records:

```text
bootrec /fixmbr
bootrec /fixboot
bootrec /rebuildbcd
```

If `bootrec /fixboot` fails with "Access is denied", rebuild the boot
configuration data:

```text
bcdboot C:\Windows /s C: /f UEFI
```

## When the drive is not in the PC's drive list at all

If the drive does not appear in BIOS or in Disk Management, no software fix
applies. Check:

- SATA and power cables are fully seated, including at the drive end
- The M.2 retention screw is tightened
- The drive is visible in BIOS

If it appears in BIOS but not in Windows, the drive's firmware or the
controller is at fault, which means a repair shop or a new drive.

## Prevent it happening again

- Never force a shutdown while Windows is writing files
- Use a UPS if your area has unreliable power
- Keep 15 to 20 percent of the system drive free
- Check SMART health every few months, since it predicts failure
- Make sure you have a real backup, not just a sync folder
