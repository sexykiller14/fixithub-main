---
title: Fix high CPU and GPU temperatures
category: hardware
tags: [temperature, overheating, thermal throttling, fan, thermal paste, cooler]
difficulty: moderate
os_version: Windows 10/11
featured: true
---

Computers throttle their processors to prevent damage, which makes them feel
slow. Overheating also shortens hardware life, so it is worth fixing properly.

## Safe temperature ranges

| Component | Good | Throttling | Dangerous |
| --- | --- | --- | --- |
| CPU under gaming load | Under 85C | Above 90C | Above 100C |
| CPU idle | Under 45C | Above 60C | Above 85C |
| GPU under load | Under 80C | Above 85C | Above 95C |
| Laptop CPU | Under 90C | Above 95C | Above 105C |
| Hard drive | Under 45C | Above 50C | Above 60C |

Laptops run hotter by design and are harder to cool, so their numbers look
higher for the same workload.

## Measure it

Windows has a built-in view: Task Manager > Performance, then look at CPU
temperature and GPU temperature.

For more detail, use HWiNFO64 or HWMonitor. Both are free and read from the
hardware sensors directly.

> [!TIP]
> Watch temperatures under load rather than at idle. A machine that idles at
> 60C and throttles at 90C needs its cooler checked.

## Fix 1: Clear the dust

Dust is the single most common cause. It acts as insulation on fins and fans.

1. Power off and unplug, then hold the power button 10 seconds
2. Open the case
3. Use compressed air to clean every fan, heatsink and radiator
4. Hold fan blades still so compressed air does not spin them

> [!WARNING]
> Do not use a vacuum cleaner. Static from a vacuum can destroy components
> instantly.

## Fix 2: Check the CPU cooler

- Confirm the fan spins when the machine is on
- Confirm it is plugged into the CPU fan header on the motherboard
- Reseat it so it is mounted firmly
- Check that you have not over-tightened it, which can crack the motherboard

## Fix 3: Improve airflow

- Follow the case's airflow path: cool air in at the front and bottom, hot air out
  at the rear and top
- Do not block intake fans against a wall or inside a cupboard
- Keep at least a few centimetres of clearance around vents on a laptop
- Remove dust mats and thick cases that restrict intake

## Fix 4: Replace thermal paste

Thermal paste improves with age and poor application. Repasting after three or
four years helps noticeably.

1. Remove the cooler
2. Clean both surfaces with isopropyl alcohol and a lint-free cloth
3. Apply a small pea-sized dot of fresh paste
4. Spread it evenly with the paste applicator that came with the cooler

> [!WARNING]
> Too much paste is as bad as none. Air bubbles and overflow reduce contact and
> make temperatures worse.

> [!DANGER]
> Do not run the machine without a cooler mounted. Modern processors throttle to
> near-zero or shut down within seconds of being uncovered.

## Fix 5: Check laptop specific causes

- Blocked air vents, often by a bag or bedding
- A cooling pad or unused USB fan resting on the base blocking vents
- A swollen battery pressing on the bottom cover from inside, which is common on
  old laptops and needs repair
- A dusty heatsink reachable through the bottom vents
- A degraded thermal compound, common after two or three years

## Fix 6: Adjust power limits

In Windows 11, Settings > System > Power & battery lets you limit the maximum
processor state to 99 percent, which caps turbo clocks and cuts temperatures a
few degrees at a small performance cost.

For more control, use your CPU vendor's utility such as Ryzen Master, Intel
XTU, or ThrottleStop. Careful: those tools can also damage hardware if you push
voltage too far.

> [!WARNING]
> Do not increase voltage or disable thermal protection. Thermal shutdowns exist
> to prevent permanent damage.

## Fix 7: Undervolt, which is safer than overclocking

Lowering voltage reduces heat and improves efficiency at the same clocks.
Tools like ThrottleStop or Ryzen Master do this on most modern chips.

> [!DANGER]
> Do this carefully and test for stability. An unstable undervolt causes crashes
> and can corrupt data. Only change voltage in small steps and test thoroughly.

## Fix 8: Replace an ageing cooler

Stock coolers on older CPUs often cannot keep up with upgraded processors. A
tower cooler is inexpensive and quiet. See
[beep codes and POST](/articles/beep-codes-and-post-codes) for related startup
diagnostics.

## When overheating is not the cause

High temperatures with no throttling are usually fine. Modern CPUs are designed
to run hot. Check the behaviour rather than the number:

- Throttling under sustained load with temperatures at 95C or above: fix the
  cooling
- 90C briefly then dropping: this is normal turbo behaviour
- Idle temperatures above 60C: something is running constantly. Check Task
  Manager

## Related stop codes

- [WHEA_UNCORRECTABLE_ERROR](/bsod), which is a hardware-level warning
- [CLOCK_WATCHDOG_TIMEOUT](/bsod) from unstable clocks under heat
- [MACHINE_CHECK_EXCEPTION](/bsod) after overheating

## Related

- [PSU failure symptoms](/articles/psu-failure-symptoms)
- [Test RAM](/articles/test-ram-memory-errors)
- [Fix random restarts](/articles/fix-random-restarts-windows)
