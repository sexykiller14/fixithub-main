---
title: Test RAM and fix memory errors
category: hardware
tags: [ram, memory, memtest86, memtest, blue screen, crash, xmp, expo]
difficulty: easy
os_version: Windows 10/11
featured: true
---

Bad RAM causes more stop codes and mysterious crashes than any other single
piece of hardware. It is also cheap to test.

## Symptoms that suggest a memory fault

- Stop codes such as [MEMORY_MANAGEMENT](/bsod),
  [PAGE_FAULT_IN_NONPAGED_AREA](/bsod) or [BAD_POOL_HEADER](/bsod)
- Crashes in unrelated applications that move around
- Random restarts with no blue screen
- Filesystem errors like [NTFS_FILE_SYSTEM](/bsod)
- Blue screens that name a driver which should be fine
- [FAULTY_HARDWARE_CORRUPTED_PAGE](/bsod), which is a direct hardware signal
- A machine that works for hours then suddenly fails

## Test 1: Windows Memory Diagnostic

The built-in tool is easy but limited.

1. Press Windows key plus R
2. Type `mdsched.exe` and press Enter
3. Choose Restart now, or Schedule for later
4. The machine restarts and tests memory
5. Results appear when Windows starts again

> [!WARNING]
> Windows Memory Diagnostic is not thorough. It often misses errors that
> MemTest86 finds, so a clean result here is not proof your RAM is fine.

## Test 2: MemTest86, which you should actually use

MemTest86 boots from a USB drive and tests memory outside Windows, which finds
errors that an operating system test cannot.

1. Download MemTest86 from
   [memtest86.com](https://www.memtest86.com)
2. Write it to a USB drive
3. Boot from that USB drive
4. Run at least two full passes

**One error means faulty RAM.** Not a suspicious number of errors, not one error
in a while. One error is enough. Memory either passes or it does not.

A full pass on 8 GB takes 1 to 2 hours. Run it overnight.

> [!TIP]
> Enable the "Show all reports" and "Hammer test" options in the advanced
> settings if you suspect a specific address, since the hammer test hammers the
> same location repeatedly.

## Test 3: Isolate the module

If MemTest86 reports errors:

1. Test one stick at a time
2. Move each stick through each slot
3. Record which combinations fail

This distinguishes three cases:

| Result | Meaning |
| --- | --- |
| One stick fails in every slot | That stick is faulty |
| One slot fails with every stick | That slot is faulty |
| Errors change between runs | Often the motherboard or power supply |

## Fix: Reseat and clean

Reseating fixes more than people expect.

1. Power off and unplug
2. Hold the power button for 10 seconds to drain residual power
3. Ground yourself by touching bare metal
4. Remove every stick
5. Clean the slots with a soft brush or compressed air
6. Look for bent or dirty contacts and clean them with a dry eraser on a cloth
7. Reseat firmly until both side clips click shut

> [!WARNING]
> Handle RAM by the edges only. Touching the gold contacts can damage them, and
> static without grounding can too.

## Fix: Disable XMP or EXPO

XMP and EXPO are overclocked memory profiles. They often work but sometimes
barely.

1. Restart and enter BIOS with Del or F2
2. Find the memory settings
3. Disable XMP, EXPO, or DOCP
4. Save and test again

If the crashes stop, the profile was unstable rather than your RAM being broken.

> [!WARNING]
> An unstable memory profile causes random crashes, freezing and sometimes file
> corruption, not just BSODs. Do not leave it enabled without testing thoroughly.

> [!IMPORTANT]
> Do not raise the memory voltage to make an unstable profile work. It does
> shorten the life of the modules. Our
> [RAM stability guide](/articles/ram-stability-xmp-expo) covers what these
> profiles do, why a memory test cannot detect an unstable one, and how to get
> the speed back safely.

## Fix: Mix of matched kits

Two different sticks run at the slower of the two speeds. That is safe but limits
performance. Two matched sticks in the correct slots run as a dual channel pair,
which is worth the cost.

Check the correct slots in your motherboard manual. They are usually slots 2 and
4, or A2 and B2, and not the slots closest to the CPU.

## Fix: Wrong memory type

DDR4 and DDR5 are not interchangeable. Confirm the type in
Task Manager > Performance > Memory.

> [!DANGER]
> Forcing the wrong type into a slot can damage the slot or the memory. Check
> carefully before inserting.

## When memory is not the fault

If MemTest86 is clean but crashes continue:

- Check the drive, since a failing drive corrupts files. See
  [disk health](/articles/check-disk-health-ssd-hdd)
- Test each drive slot carefully
- Check CPU and chipset drivers
- Load BIOS defaults
- Check the power supply, since unstable voltage mimics memory faults

## Related stop codes

- [MEMORY_MANAGEMENT](/bsod)
- [PAGE_FAULT_IN_NONPAGED_AREA](/bsod)
- [PFN_LIST_CORRUPT](/bsod)
- [BAD_POOL_HEADER](/bsod)
- [FAULTY_HARDWARE_CORRUPTED_PAGE](/bsod)
- [CLOCK_WATCHDOG_TIMEOUT](/bsod), if XMP is enabled

## Related

- [RAM stability, XMP and EXPO explained](/articles/ram-stability-xmp-expo)
- [Upgrade RAM](/articles/upgrade-ram-laptop-desktop)
- [Why my PC is slow after an upgrade](/articles/fix-slow-pc-after-upgrade)
- [Repair Windows system files](/articles/repair-windows-system-files)
