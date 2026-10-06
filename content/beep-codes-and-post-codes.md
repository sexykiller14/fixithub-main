---
title: Beep codes and POST error codes explained
category: hardware
tags: [beep codes, post, boot, motherboard, diagnostics, hardware]
difficulty: moderate
os_version: Windows 10/11
---

When a computer will not start, the motherboard tells you what is wrong with
beeps or a numeric code on a small LED display. This is the fastest diagnostic
tool you have.

## Classic beep codes

These are AMI BIOS codes, found on most desktop motherboards.

| Pattern | Meaning | What to do |
| --- | --- | --- |
| 1 long, 2 short | Video card failure | Reseat the card, test with another slot |
| 1 long, 3 short | Memory failure | Reseat RAM, test one stick at a time |
| 1 long, 8 short | Display failure | Check the monitor, cable and GPU |
| 3 long | Memory not detected | Test each stick in each slot |
| 3 short | Memory failure | Test each stick in each slot |
| 4 short | Processor or video failure | Check cooler mounting, reseat CPU |
| 5 short | Processor failure | Reseat CPU, check cooler |
| 6 short | Chipset failure | Board fault, usually needs replacement |
| 7 short | Virtual mode error | Check CPU and RAM |
| 8 short | Parity memory error | Test each stick |
| Continuous short | Power or memory | Check PSU, test one stick |
| Continuous long | Display adapter | Reseat or replace the card |

> [!IMPORTANT]
> Codes vary between manufacturers. Your motherboard manual has the exact table
> for your board. These are the most common AMI patterns.

## Award BIOS codes

Older and budget boards sometimes use Award codes:

| Pattern | Meaning |
| --- | --- |
| 1 long, 2 short | Video error |
| 1 long, 1 short | DRAM error |
| 1 long, 3 short | Video or DRAM error |
| Repeating short beeps | Power supply or CPU failure |
| Long, short, short, short | Video adapter failure |
| Long, short, short, long | Video or keyboard failure |

## POST codes on the LED display

Many modern boards have a two-digit diagnostic LED. The first digit identifies
the stage:

| Digit | Stage |
| --- | --- |
| 00 | No error detected, passed POST |
| 01 | CPU failure |
| 02 | Memory failure |
| 03 | Chipset or GPU failure |
| 04 | Memory failure |
| 05 | CPU failure |
| 06 | GPU failure |
| 07 | CPU or memory failure |
| 31 | Power supply failure |
| 54 | Storage device failure |

Your board's manual lists the full table. Record the code before doing anything
else, since it disappears when the power goes off.

## Diagnostic LEDs on the board

Most modern motherboards have labelled LEDs for CPU, DRAM, VGA and BOOT. They
light up during POST and stay lit on the component that failed.

| Light stays on | Meaning |
| --- | --- |
| CPU | Processor not detected, or cooler not mounted |
| DRAM | Memory not detected or faulty |
| VGA | Graphics output problem |
| BOOT | Storage device not found or unreadable |

These are more reliable than beeps and are worth learning for your board.

## Work through in this order

1. **Record the code** before powering off
2. **Check power**: PSU switch, wall socket, cables fully seated
3. **Check the CPU cooler**: an unmounted cooler stops POST immediately
4. **Reseat RAM**: one stick at a time, each slot
5. **Reseat the graphics card**: with the PCIe latch open, never forced
6. **Check the display path**: cable, monitor input, correct port
7. **Reseat the CPU**: only if you are confident, check for bent pins
8. **Clear CMOS**: removes BIOS settings and can clear obscure faults

## Clearing CMOS

This resets BIOS settings to factory defaults, which fixes many obscure boot
problems.

1. Write down any BIOS settings you have changed
2. Turn off and unplug the PC
3. Hold the power button 10 seconds
4. On the motherboard, find the clear-CMOS jumper or button and use it as
   documented
5. Or remove the CR2032 coin cell for five minutes and put it back
6. Power on and enter BIOS to check settings

> [!WARNING]
> Removing the CMOS battery resets BIOS settings including boot order, XMP
> profiles and any custom fan or power settings. Note them down first.

## CPU errors are often cooler errors

An unmounted or badly mounted cooler, or one not plugged into the CPU fan
header, stops POST with a CPU code. This is very common after a cooler change.

## When to see a technician

See a professional if:

- The code points to the CPU or chipset and reseating did not help
- The CPU fan runs but there is no display on any output
- The board lights nothing at all with a known-good PSU
- POST codes appear on a board that worked before any change you made

## Related

- [PC will not turn on](/articles/fix-pc-wont-boot-power-on)
- [Black screen or no display](/articles/fix-black-screen-no-display)
- [Test RAM](/articles/test-ram-memory-errors)
