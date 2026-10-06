---
title: Disable Fast Startup and hibernation
category: windows
tags: [fast startup, hibernation, sleep, power, hiberfil, powercfg]
difficulty: easy
os_version: Windows 10/11
---

Fast Startup saves your session to disk when you shut down, then restores it
when you power on. It is convenient and it causes a specific set of problems.

## Why it causes trouble

Fast Startup does not perform a real shutdown. It saves the kernel session and
restores it, which means:

- Drivers are not fully unloaded, so a bad driver persists between boots
- [CRITICAL_PROCESS_DIED](/bsod) and
  [CRITICAL_OBJECT_TERMINATION](/bsod) become persistent
- Update problems that need a clean shutdown never clear
- Sleep and wake bugs become harder to diagnose

Disabling it costs a few seconds of startup time and solves all of that.

## Disable hibernation and Fast Startup together

Open Command Prompt as Administrator and run:

```text
powercfg /h off
```

This does two things: it turns off hibernation, and it disables Fast Startup,
which cannot work without hibernation.

> [!WARNING]
> This deletes hiberfil.sys, which can be several gigabytes on a laptop. Your
> files are untouched. To get the space back afterwards, empty the Recycle Bin
> from Disk Cleanup.

## Verify it worked

1. Control Panel > Hardware and Sound > Power Options
2. Choose Change what the power buttons do
3. Choose Change settings that are currently hidden
4. Confirm "Turn on fast startup" is unticked

You can also check with:

```text
powercfg /a
```

If hibernation is listed as unavailable, it is off.

## Turn it back on

```text
powercfg /h on
```

> [!IMPORTANT]
> Hibernation is genuinely useful on a laptop, since it preserves the exact
> state including open applications with no power use. If you use sleep
> deliberately, leave hibernation on and just untick Fast Startup in the Power
> Options panel instead.

## Disable sleep without touching hibernation

If sleep is the problem, set the timeout to Never:

1. Settings > System > Power & battery > Screen and sleep
2. Set "When plugged in, put my device to sleep after" to Never

Or from Command Prompt:

```text
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
```

## Related stop codes

Disabling Fast Startup often resolves these, since they involve saving and
restoring the kernel session:

- [CRITICAL_OBJECT_TERMINATION](/bsod)
- [POWER_STATE_FAILURE](/bsod)
- [INTERNAL_POWER_ERROR](/bsod)
- [INVALID_HIBERNATED_STATE](/bsod)

## When Fast Startup is genuinely useful

Fast Startup is a reasonable convenience when:

- You rarely have driver problems
- Your machine has an SSD so boot time is already quick
- You do not need clean shutdowns for troubleshooting

It is worth turning off while diagnosing anything related to drivers, sleep or
updates.

## Related

- [Laptop sleep and wake problems](/articles/laptop-sleep-wake-issues)
- [Laptop battery health](/articles/fix-laptop-battery-health)
- [Fix random restarts](/articles/fix-random-restarts-windows)
