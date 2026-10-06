---
title: Replace an HDD with an SSD
category: hardware
tags: [ssd, hdd, upgrade, clone, nvme, sata, performance]
difficulty: moderate
os_version: Windows 10/11
featured: true
---

Replacing a mechanical hard drive with an SSD is the single biggest speed
improvement you can make. It is usually straightforward, and most of the risk is
in the cloning step.

## What to expect

| Operation | Mechanical HDD | SSD |
| --- | --- | --- |
| Boot to desktop | 45 to 90 seconds | 10 to 20 seconds |
| Open a 100 MB file | 3 to 10 seconds | Under 1 second |
| Windows updates | Very slow | Fast |
| Shock risk | High | Negligible |

## Choose the right SSD

**Check what you have first:**

- A 2.5 inch SATA SSD fits almost every laptop and desktop
- An M.2 NVMe SSD needs an M.2 slot on your motherboard
- An M.2 SATA SSD needs an M.2 slot but uses the SATA interface, so it is only
  worth it if you have no SATA ports left

Confirm by looking in Task Manager > Performance > Disk, or by checking the
motherboard manual for M.2 support.

> [!WARNING]
> Some M.2 slots only support SATA, not NVMe, and some older laptops have an M.2
> slot that physically accepts the drive but does not support it at all. Check
> your manual before buying.

**Capacity:** buy more than you need. Drives get cheaper in larger sizes, and
you will fill it anyway.

**Brand:** any reputable brand works. There is no meaningful difference in
reliability between the major manufacturers at the same capacity.

## Clone, do not reinstall

Cloning copies everything, including your applications, and takes 20 to 60
minutes. A clean reinstall is cleaner but takes a whole afternoon.

Cloning tools:

- **Macrium Reflect** (free personal edition, now the official recommendation)
- **Samsung Data Migration**, if you bought a Samsung drive
- **Clonezilla**, free and good but the interface is dated
- **Acronis True Image**, often bundled with Crucial and Kingston drives

## Step 1: Prepare

1. Back up your important files. This step is not optional.
2. Note which drive is which by capacity, so you clone in the right direction
3. Defragment your mechanical drive first, which makes the clone faster and more
   reliable
4. Note which drive boots Windows

## Step 2: Connect the new SSD

- If it is a 2.5 inch SATA drive, connect it with a SATA data cable and a power
  cable while your old drive is still connected
- If it is M.2, it is already connected when you insert it, so remove your old
  drive only after cloning

> [!WARNING]
> Keep the old drive connected during the clone. Removing it first is how people
> end up with a computer that cannot boot.

## Step 3: Clone

1. Install the cloning tool
2. Select the source, which is your mechanical drive
3. Select the destination, which is the SSD
4. Verify the direction carefully
5. Start the clone and let it finish

> [!DANGER]
> The clone erases the destination completely. Double-check the source and
> destination before continuing. Cloning onto your old boot drive destroys
> Windows.

## Step 4: Make it boot

Some systems need the boot order changed:

1. Enter BIOS with Del or F2 at power-on
2. Look for the boot device list
3. Put the SSD first
4. Save and exit

If your BIOS is in Legacy or CSM mode and you installed an NVMe drive, it may
not appear. Switch to UEFI mode, which requires reinstalling Windows.

> [!WARNING]
> Switching from Legacy to UEFI needs a clean Windows install. Plan for this
> before you start if you are currently in Legacy mode.

## Step 5: Test before removing the old drive

1. Boot into Windows from the SSD
2. Confirm everything works: applications, files, drivers
3. Check Disk Management shows the right letter and healthy status
4. Run a chkdsk scan on the new drive to confirm it is healthy

Only then remove the old drive.

## Keep the old drive

Do not discard it immediately. Keep it externally connected or in an enclosure
for two weeks as a backup. If the new drive has problems, you still have your
system.

## Migrate an existing SSD to a larger one

You can clone an SSD to a larger SSD directly. This is the standard way to move
to more capacity without reinstalling.

## Do not do this

- Do not use a 4K random access method on a mechanical drive with important files
- Do not partition the new drive more than necessary
- Do not defrag an SSD. Windows runs TRIM automatically, which is the correct
  tool
- Do not clone from an external enclosure back to the same disk

## Related

- [Speed up a slow PC](/articles/speed-up-slow-windows-pc)
- [Why my PC is slow after an upgrade](/articles/fix-slow-pc-after-upgrade)
- [Check disk health](/articles/check-disk-health-ssd-hdd)
