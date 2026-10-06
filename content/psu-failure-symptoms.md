---
title: Power supply failure symptoms
category: hardware
tags: [psu, power supply, power, smoke, shutdown, underpowered]
difficulty: moderate
os_version: Windows 10/11
featured: true
---

Power supplies rarely fail cleanly. They usually give you months of warnings
before they stop, and they can destroy other components on the way out.

## Symptoms that point at the PSU

- Machine restarts or shuts off under load, especially in games
- Fans spin briefly then stop when you press power
- Random shutdowns with no blue screen and no error message
- A faint burning smell, or a buzzing noise
- The machine works when the graphics load is reduced
- Multiple components restarting at once
- Visible damage, bulging or scorch marks on the PSU

> [!DANGER]
> If you smell burning, see smoke, or see scorch marks: shut down, unplug, and
> stop using the machine immediately. Do not power it on again to test it.

## Warning signs that come first

Months before a PSU fails you may notice:

- The machine restarts when starting a demanding game
- Coil whine that gets louder or higher pitched
- The fan sounds rough or rattles
- Slight voltage instability under load
- Occasional freezes that a driver reinstall does not fix

If you notice these, test the PSU before you lose your system.

## Test it

**The only reliable test is a swap.** Borrow or buy a known-good PSU of adequate
rating and try it. Everything else is guesswork.

Power supplies rarely give an accurate fault indication through Windows software,
because the voltage sags before it fails rather than reporting itself.

With our [disk health script](/scripts/disk-health) you can also check whether
restarts are actually caused by the drive rather than the PSU, which produces
similar symptoms.

## Sizing the replacement

Add up your components' power draw and add headroom:

| Component | Typical draw |
| --- | --- |
| CPU | 65 to 170 W |
| Graphics card | 150 to 450 W |
| Motherboard and chipset | 50 to 100 W |
| Each RAM stick | 3 to 8 W |
| Each drive | 5 to 10 W |
| Fans and cooling | 10 to 30 W |

Then:

- Stay at or below 80 percent of the rating under load
- Never use a power supply at its maximum rating, since ratings assume ideal
  cooling
- For a high-end gaming PC, 750 to 1000 W is typical
- For a mid-range PC, 550 to 650 W is usually enough

## Modular cables are not interchangeable

This is the single most dangerous PSU mistake.

> [!DANGER]
> Only use modular cables that came with the same power supply model. The pinouts
> differ between models and brands. A wrong cable can destroy your motherboard and
> graphics card instantly.

If a cable does not fit easily, do not force it. It is the wrong cable.

## Quality matters

Buying a very cheap unbranded power supply to save money regularly costs more
in the end. Failing supplies destroy motherboards, graphics cards and drives.

Look for:

- 80 PLUS certification at Bronze or better
- A reputable brand with a real warranty
- A modular or semi-modular design for tidier cables
- Real reviews that test ripple and hold regulation under load

## Testing voltages

If you want to check without swapping, use a PSU tester or a multimeter:

- 12V rail on a modern PC should be within about 5 percent of 12V
- Ripple should be low, and multimeters cannot measure it accurately
- A load tester is more useful than a multimeter

## Do not open a power supply

> [!DANGER]
> Never open a power supply under any circumstances. The capacitors inside hold a
> lethal charge for minutes after unplugging, and there is no safe way to discharge
> them at home. This is a technician job.

## Other things that cause similar symptoms

Before blaming the PSU, rule out:

- **Overheating**, which causes load-related shutdowns. See
  [high temperatures](/articles/fix-high-cpu-temperature)
- **A failing drive**, which causes random restarts. See
  [disk health](/articles/check-disk-health-ssd-hdd)
- **Insufficient RAM**, which causes restarts under memory-heavy load
- **A failing motherboard**, which can also cause power-related restarts
- **Unstable overclock**, which throttles or resets under load

## Related stop codes

- [UNEXPECTED_STORE_EXCEPTION](/bsod)
- [KERNEL_DATA_INPAGE_ERROR](/bsod)
- [CRITICAL_PROCESS_DIED](/bsod)
- [CLOCK_WATCHDOG_TIMEOUT](/bsod)

## Related

- [PC will not turn on](/articles/fix-pc-wont-boot-power-on)
- [Fix random restarts](/articles/fix-random-restarts-windows)
- [Check disk health](/articles/check-disk-health-ssd-hdd)
