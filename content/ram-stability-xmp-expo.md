---
title: RAM stability, XMP and EXPO explained
category: hardware
tags: [ram, memory, xmp, expo, ddr5, ddr4, overclocking, timings, stability, crash]
difficulty: moderate
os_version: Windows 10/11
featured: true
---

Most people who think their RAM is faulty actually have memory running at
settings that are slightly too aggressive. The modules are fine. The profile is
not.

This guide explains what those profiles do, why an unstable one causes crashes
that a memory test cannot detect, and how to turn the problem off without
guessing.

## The short version

1. Check whether a profile is even enabled, using the script below
2. If it is, turn it off and use the computer normally for several days
3. If the crashes stop, your memory is fine and the timings were not
4. If they do not stop, test the memory with MemTest86 as described in
   [test-ram-memory-errors](/articles/test-ram-memory-errors)

## What JEDEC speed actually means

Every memory module has two speed figures, and confusing them is the source of
most of this confusion.

**JEDEC speed** is the default the module guarantees to run at. It is the speed
the factory tested to a published standard, and it is what your motherboard uses
when no profile is enabled. For a kit sold as "DDR5 6000", the JEDEC default is
usually something like DDR5 4800.

**Rated speed** is the number on the box, the one you paid for. Reaching it needs
extra settings: a specific frequency, specific timings, and often extra voltage.
A module cannot do this by itself, which is why it needs a profile.

> [!TIP]
> A DDR5 6000 kit running at 4800 is not broken. It is a 6000 kit running at its
> guaranteed speed. Many people never notice, because most applications do not
> benefit much from the extra bandwidth.

## What XMP and EXPO do

XMP and EXPO are the two competing standards for storing those extra settings
on the module itself.

| Profile | Made by | Common on |
| --- | --- | --- |
| XMP | Intel | Both Intel and AMD boards |
| EXPO | AMD | Mostly AMD boards |
| DOCP | ASUS naming for XMP | ASUS boards |

The important thing is that they are the same idea under different names. When
you enable one, the motherboard reads a set of tested timings out of the module
and applies all of them at once, instead of leaving the memory on slow, safe
default timings.

That is convenient and it is also the source of the problem. The profile was
tested by the memory manufacturer, not by the board and CPU combination you
happen to own. It usually works. When it does not, the margin is very thin.

> [!WARNING]
> Enabling a profile is a documented, supported feature. It is not a hardware
> risk. What is risky is the reaction people have when it misbehaves, which is
> turning the voltage up. See below.

## Why a memory test will not catch it

This is the part that confuses people most, so it is worth being precise.

When your memory timing is too tight, the module sometimes returns the wrong
value. But it returns a *plausible* wrong value. The bit pattern is a valid
address, pointing somewhere that exists. No error is raised, because from the
computer's point of view nothing went wrong.

MemTest86 writes a value to an address and reads it back to see if it matches.
When timings are unstable, that read usually *does* come back correct. The
read-back is exactly the easy case. The failure shows up under the complex,
interleaved access patterns of a running operating system, which is not what a
memory test does.

So the result looks like this, and it confuses everybody:

- MemTest86 reports zero errors
- The computer crashes anyway, sometimes hours apart

That combination does not mean the memory test lied. It means the timings are
unstable, and a memory test is the wrong instrument for the job.

## Symptoms of an unstable profile

- Crashes that happen under load but never when idle
- Random restarts with no blue screen
- Freezes for a few seconds, then recovery
- Blue screens naming an unrelated driver
- File corruption, which is the frightening one
- A machine that worked fine before you touched the BIOS
- [CLOCK_WATCHDOG_TIMEOUT](/bsod), which specifically suggests unstable
  overclocked settings

If your machine worked reliably for months and started crashing after a BIOS
update, a new memory kit, or a Windows update that changed a driver, suspect the
profile before you buy replacement hardware.

## Check whether a profile is active

Our read-only RAM diagnostics script reports this without entering the BIOS.

1. Download the script from the [scripts page](/scripts)
2. Open PowerShell as Administrator and run it
3. Read the section on XMP or EXPO profile status

It compares the module's **rated speed** against its **configured speed**, which
is the running speed. When a profile is off, Windows reports no configured speed
at all, while still showing the much higher rated figure. That difference is the
answer.

> [!TIP]
> The script also checks whether your modules are paired across two channels.
> Dual channel needs a matched pair in the correct two slots. Two sticks in the
> slots nearest the CPU run single channel and halve memory bandwidth, which
> feels like a slow machine but has nothing to do with faults.

## Turn the profile off

This is the diagnostic step, and it is safe.

1. Restart your computer
2. Press Del or F2 repeatedly during startup to enter the BIOS
3. Look for a screen named Overclocking, Tuning, OC Profile or AI Tweaker
4. Find the XMP, EXPO, DOCP or Memory Profile setting
5. Set it to Disabled
6. Save and exit

> [!WARNING]
> Change nothing else while you are in the BIOS. Setting a memory profile to
> disabled is safe on its own. Manually changing frequency, timings or voltage
> is a different activity with a real chance of not booting.

Your memory now runs at its JEDEC default, which is slower. That is expected.

Use the computer normally for several days. Not an hour, because instability is
intermittent.

- **Crashes stopped:** your memory is fine and the timings were not
- **Crashes continued:** the profile was not the cause, and you can re-enable it

## If you want the speed back anyway

Once you know the profile was the problem, there are three options, in order of
how much I would recommend them.

**Option one: leave it off.** Your memory runs at its guaranteed speed and your
computer is stable. For most people doing ordinary work, the difference is small.

**Option two: lower the frequency, keep the timings on Auto.** In the BIOS, set
the memory frequency down one step from your kit's rating, and leave everything
else on automatic. A DDR5 6000 kit set to 5600 with Auto timings is usually
stable, because the board picks timings it can actually achieve. You keep most of
the performance and drop the overclock.

**Option three: raise the voltage.** This works, and I am listing it last because
it is the option that damages hardware.

> [!DANGER]
> Do not raise memory voltage to stabilise a profile. Above the rated voltage,
> which is usually printed on the module or in the BIOS as its default, memory
> generates heat that shortens the life of the modules. Many people damage a
> perfectly good kit this way trying to keep an overclock they did not need.

If you do check voltage at all, check that it is *at* the rated value rather than
above it, and confirm with the RAM report script afterwards.

## When the profile is not the problem

If disabling the profile changed nothing, test the memory itself:

- [Test RAM and fix memory errors](/articles/test-ram-memory-errors) covers
  MemTest86 and how to isolate which module is faulty
- Run MemTest86 for at least two full passes. One error is a failure
- Also check the drive, since a failing drive corrupts files and looks identical
  to unstable timings. See
  [disk health](/articles/check-disk-health-ssd-hdd)
- Check for WHEA hardware events in your RAM report, which point at the CPU,
  board or power supply rather than the memory
- Update the motherboard BIOS, since many WHEA errors are firmware bugs

> [!WARNING]
> Do not test a memory module while a drive is failing. A test restart is one
> more opportunity for the drive to stop working.

## Mixed kits

Two different kits in one machine run at the slower of their two speeds, and
sometimes a board refuses to run them in dual channel at all.

If your modules have different part numbers, treat them as a mismatch:

- The whole group runs at the slowest common speed
- On some boards, mixing disables dual channel entirely
- The instability this causes looks exactly like a bad profile

Our RAM diagnostics script prints each module's part number, so you can check
this without opening the case. See
[upgrade or add RAM](/articles/upgrade-ram-laptop-desktop) for how to pair
modules correctly.

## Quick reference

| What you see | Most likely cause |
| --- | --- |
| Crashes under load only, MemTest86 clean | Unstable XMP or EXPO profile |
| Crashes began after a BIOS update | Profile reset to a different setting |
| Configured speed missing, rated speed shown | No profile enabled |
| Modules report different part numbers | Mixed kit, running at reduced speed |
| One error in MemTest86 | Genuinely faulty module, replace it |
| WHEA events present | CPU, board or power supply |
| Everything slow together, plenty of RAM used | Not a fault, see capacity |

## Related

- [Test RAM and fix memory errors](/articles/test-ram-memory-errors)
- [Upgrade or add RAM](/articles/upgrade-ram-laptop-desktop)
- [Check disk health for SSD and HDD](/articles/check-disk-health-ssd-hdd)