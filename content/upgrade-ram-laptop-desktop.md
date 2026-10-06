---
title: Upgrade or add RAM
category: hardware
tags: [ram, memory, ddr4, ddr5, sodimm, xmp, upgrade]
difficulty: moderate
os_version: Windows 10/11
featured: true
---

Adding RAM is usually the easiest hardware upgrade, and the most likely to cause
problems if you get the details wrong.

## How much do you need?

| Use | Comfortable | Minimum |
| --- | --- | --- |
| Browsing, email, documents | 8 GB | 8 GB |
| Office work, many browser tabs | 16 GB | 16 GB |
| Video editing, photo work | 32 GB | 16 GB |
| Modern games | 16 GB | 16 GB |
| Development, virtual machines | 32 GB | 16 GB |
| Large language models, video 4K | 64 GB | 32 GB |

Windows 11 officially supports 4 GB, but in practice that leaves nothing spare.

## Check what you have

1. Settings > System > About, and look at Installed RAM
2. Task Manager > Performance > Memory, which shows slots used and slots available
3. The slot type and speed are shown in the same panel

## Check what your board supports

Your motherboard manual has the supported type, speeds and maximum capacity.
Check:

- **DDR4 or DDR5.** These are not interchangeable.
- **SODIMM or DIMM.** Laptops and small form factor PCs use the shorter SODIMM.
  Desktops use full-length DIMM.
- **Maximum capacity.** Some older boards cap at 32 GB or 64 GB regardless of
  what the modules support.
- **Supported speeds.** A faster module runs at the slower supported speed, which
  is fine.

> [!DANGER]
> DDR4 and DDR5 are physically and electrically different. Forcing the wrong type
> into a slot can damage the slot, the memory and sometimes the motherboard.
> Check before inserting.

## Matched kits versus single sticks

A matched kit of two identical sticks:

- Runs as a dual channel pair, which roughly doubles memory bandwidth
- Achieves the full rated speed

Two different sticks:

- Run at the slower of the two speeds
- May not enable dual channel at all

For most purposes a matched pair is worth the small extra cost.

## Correct slots for dual channel

Motherboards interleave memory across slots. The correct pair is usually not the
two slots nearest the CPU. Check your manual.

Common layouts:

- Four slots: use slots 2 and 4
- Two slots: use both
- Laptop with four SODIMM slots: check the manual, which varies

## Install desktop RAM

1. Shut down and unplug, then hold the power button 10 seconds
2. Touch bare metal on the case to ground yourself
3. Open the side panel
4. Open the retention clips on the slots
5. Align the notch in the module with the notch in the slot
6. Press down firmly on both ends until the clips click shut
7. Check the clips are locked

> [!WARNING]
> RAM modules must be seated firmly. A stick that sits loose can damage the slot
> over time.

## Install laptop RAM

Most laptops use one or two SODIMM slots, often under a cover.

1. Shut down and unplug, and disconnect the battery if possible
2. Remove the bottom cover
3. Release the retention clips
4. Insert at an angle of about 30 degrees, then press flat until it clicks

Some very thin laptops have soldered memory that cannot be upgraded. Check the
manual or the manufacturer's specification first.

> [!WARNING]
> Check whether the laptop has soldered memory before buying anything. Many
> thin laptops cannot be upgraded at all.

## Enable XMP or EXPO afterwards

Rated speeds are conservative; XMP and EXPO are overclocked profiles.

1. Enter BIOS with Del or F2
2. Find the memory or overclock settings
3. Enable XMP, EXPO or DOCP for your kit
4. Save and reboot

> [!WARNING]
> These are overclocked timings. If your kit is not fully stable you will get
> random crashes, freezing and sometimes file corruption, not just instability
> you notice immediately. Test thoroughly before relying on it.
>
> If anything odd happens, disable the profile and run at the default speed.

Test stability by running MemTest86 for two passes. See
[test RAM](/articles/test-ram-memory-errors).

## Confirm the upgrade worked

1. Task Manager > Performance > Memory
2. Confirm total capacity and speed
3. Confirm the number of slots in use matches what you installed
4. If dual channel is enabled, confirm the label says Dual Channel

## Common mistakes

| Mistake | Result |
| --- | --- |
| Mixing DDR4 and DDR5 | Won't fit or damages hardware |
| Mixing a kit with a single stick | No dual channel |
| Using the wrong slots | Half the bandwidth |
| Not enabling XMP | Running slower than advertised |
| Enabling an unstable XMP | Random crashes |
| Mixing modules of different capacities | Can reduce speed to the slowest |

## Related

- [Test RAM errors](/articles/test-ram-memory-errors)
- [Why my PC is slow after an upgrade](/articles/fix-slow-pc-after-upgrade)
- [MEMORY_MANAGEMENT](/bsod), usually caused by unstable timings
