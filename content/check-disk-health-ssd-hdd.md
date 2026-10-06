---
title: Check SSD and hard drive health
category: hardware
tags: [ssd, hdd, disk, smart, chkdsk, data loss, drive]
difficulty: easy
os_version: Windows 10/11
featured: true
---

A failing drive produces blue screens, random restarts and corrupted files that
look like software problems. Check it before you spend hours reinstalling
Windows.

## Signs the drive may be failing

- Clicking, grinding or buzzing from the drive
- The drive disappears from Explorer or BIOS intermittently
- Files fail to open or are unexpectedly corrupted
- Windows asks to format a healthy-looking drive
- Stop codes such as [KERNEL_DATA_INPAGE_ERROR](/bsod),
  [STORAGE_DEVICE_ABNORMALITY_DETECTED](/bsod) or
  [UNMOUNTABLE_BOOT_VOLUME](/bsod)
- Very slow reads even when the drive should be fast

## Check SMART data

SMART records the drive's own view of its health, including reallocated sectors,
pending sectors and wear.

**With our script:** run [fixit-disk-health](/scripts/disk-health) as
Administrator. It reads SMART counters and writes a report to your Desktop.

**With Windows tools:**

```text
Get-PhysicalDisk
```

```text
Get-PhysicalDisk | Get-StorageReliabilityCounter
```

**With your vendor's tool:** Samsung Magician, Crucial Storage Executive,
Western Digital Dashboard, Seagate SeaTools or Kingston SSD Manager all give
more detail than Windows.

> [!IMPORTANT]
> Run your vendor's tool as well as Windows'. Some problems appear in one but not
> the other.

## Reading SMART counters

| Counter | Healthy | Concerning |
| --- | --- | --- |
| Reallocated sectors (SSD and HDD) | 0 | Anything above 0 and climbing |
| Pending sectors | 0 | Anything above 0 |
| Uncorrectable errors | 0 | Anything above 0 |
| Percentage used (SSD) | Under 90 percent | Over 90 percent |
| Power-on hours (HDD) | Under about 20,000 | Over 30,000 for a consumer drive |
| Reallocated event count (SSD) | 0 | Rising steadily |

A single reallocated sector on an SSD is normal. On a mechanical drive it is
worth investigating. Rising counts are the real signal.

## Check the filesystem without changing anything

Run a read-only scan, which reports errors but repairs nothing:

```text
chkdsk C: /scan
```

You can also run our [disk health script](/scripts/disk-health), which uses
PowerShell's `Repair-Volume -Scan`.

> [!DANGER]
> Do not run `chkdsk C: /f` on a drive whose SMART data shows failures. The `/f`
> flag writes to the drive, which can destroy data that is still recoverable.
> Check SMART first, always.

## Repairing when the drive is healthy

If SMART is clean and chkdsk finds errors:

1. Back up your files first
2. Run from an elevated Command Prompt:

```text
chkdsk C: /f /r /x
```

`/f` repairs filesystem errors, `/r` scans for bad sectors, and `/x` forces the
volume to dismount so the repair can run.

> [!WARNING]
> `/r` reads the entire drive. On a 4 TB mechanical drive this can take many
> hours. Do not interrupt it, since that can leave the filesystem worse.

## When to replace the drive

Replace it, do not repair it, if:

- SMART reports failures in any category
- The drive is over six years old and mechanical
- Errors recur after a successful chkdsk repair
- It is slow to respond even when idle
- An SSD has passed its rated write life

A failing drive can stop working at any moment, and taking the data with it.

## Recovering data first

If the drive holds something irreplaceable:

1. Stop using the drive immediately
2. Do not format it, even if Windows suggests it
3. Try TestDisk or PhotoRec, which read raw devices without writing
4. If the drive clicks or drops off, use professional recovery. Every attempt
   stresses it further

> [!DANGER]
> Never keep re-plugging a failing drive. Each connection can destroy more
> recoverable data.

## Check all your drives

Users often check only the system drive. Check every drive, including external
ones and any drive with irreplaceable files on it.

## Use an SSD

Once you have recovered your data, consider replacing a mechanical drive with an
SSD. See [HDD to SSD upgrade](/articles/hdd-to-ssd-upgrade-guide).

## Related stop codes

- [KERNEL_DATA_INPAGE_ERROR](/bsod)
- [UNMOUNTABLE_BOOT_VOLUME](/bsod)
- [NTFS_FILE_SYSTEM](/bsod)
- [STORAGE_MINIPORT_ERROR](/bsod)
- [POOL_CORRUPTION_IN_FILE_AREA](/bsod)
- [STORAGE_DEVICE_ABNORMALITY_DETECTED](/bsod)

## Related

- [UNMOUNTABLE_BOOT_VOLUME](/articles/fix-unmountable-boot-volume)
- [Fix boot loop](/articles/fix-boot-recovery-loop)
- [Collect system info report](/articles/collect-system-info-report)
