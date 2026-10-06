---
title: PC will not turn on or has no display
category: hardware
tags: [power, no display, boot, psu, hardware, black screen]
difficulty: moderate
os_version: Windows 10/11
featured: true
---

Work from the cheapest checks to the most expensive. Most "dead" computers are
actually a cable, a power outlet, or a memory stick.

## Step 1: Confirm it is receiving power

- Try a different wall outlet, or test the current one with a phone charger
- Check the power switch at the back of the power supply is set to I
- Push the power cable firmly into the back of the PSU and the wall socket
- On a laptop, try a different charger and confirm the charging light works

If nothing happens at all, this is a power problem. Skip to step 5.

## Step 2: Count the fans and lights

- **Fans spin and stay on**: the PC has power, so the problem is display or boot
- **Fans spin briefly then stop**: often bad memory or a failed power supply
- **Nothing spins**: no power reaching the motherboard

## Step 3: Reseat the memory

This is the single most common cause of a machine that powers on but shows
nothing.

1. Switch off and unplug the PC
2. Hold the power button for 10 seconds to drain residual power
3. Touch a bare metal part of the case to discharge static
4. Open the case and remove every RAM stick
5. Reseat them one at a time, testing with a single stick in the slot closest to
   the CPU

The memory should click firmly into place with both side clips engaged. A stick
that sits loose can damage the slot over time.

> [!WARNING]
> Handle RAM by the edges. Touching the gold contacts or the chips can damage
> them, and static discharge without grounding yourself can also damage parts.

## Step 4: Check the display path

A black screen with running fans is usually not the computer at all.

- Swap the video cable for a known-good one
- Try a different port on the monitor, and select it in the monitor's own menu
- Test the monitor with another device, such as a laptop
- On a desktop, confirm the cable is plugged into the graphics card, not the
  motherboard
- If the CPU has integrated graphics, move the cable to the motherboard's video
  output to test without the card

Our [black screen guide](/articles/fix-black-screen-no-display) covers this in
more detail.

## Step 5: Isolate the hardware

Disconnect everything optional, leaving only the motherboard, CPU, one memory
stick and the CPU cooler, then power on:

- **It starts**: the problem is a device you removed. Add them back one at a
  time
- **It still does nothing**: test with a known-good power supply

## Beep codes

If you hear beeps, count them. These are the common patterns on desktop boards:

| Pattern | Meaning |
| --- | --- |
| One long, two or three short | Video card or display problem |
| Three short beeps | Memory problem |
| Four short beeps | Processor or video problem |
| Continuous beeps | Memory not detected, or no power |

Post codes vary between manufacturers, so check your motherboard manual if the
pattern does not match the table above.

## Test the power supply

A power supply rarely fails gracefully. Signs that point to it:

- Fans spin briefly then stop
- The machine restarts under load
- There is a burning smell or unusual buzzing
- It works with a different power supply but not its own

> [!DANGER]
> Never open a power supply. The capacitors inside hold a lethal charge even
> when it is unplugged from the wall. A technician can test it safely.

> [!WARNING]
> Only use modular cables that came with the same power supply model. Mixing
> cables from different units can permanently destroy your components.

## Still not working?

- Replace the CMOS battery, a CR2032 that costs almost nothing. On older
  motherboards this causes very strange symptoms.
- Load BIOS defaults by removing the CMOS battery or using the clear-CMOS jumper
- Update BIOS firmware, if you can still reach it
- Check whether the CPU cooler is mounted firmly. Many motherboards shut down
  instantly if the cooler is not detected
- On a laptop, disconnect the battery and try powering on, since a shorted
  battery can prevent any start

## When to see a technician

See a professional if:

- A known-good power supply and known-good memory do not start it
- The motherboard shows no lights at all with everything connected
- It is a laptop with a screen that stays black on an external monitor
- You hear clicking from the drive or any sign of burning

These point to motherboard, CPU or PSU failure, which is beyond a software fix.
