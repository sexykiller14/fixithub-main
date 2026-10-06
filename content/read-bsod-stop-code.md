---
title: How to read a BSOD stop code
category: bsod
tags: [bsod, stop code, blue screen, minidump, troubleshooting]
difficulty: easy
os_version: Windows 10/11
featured: true
---

If your PC restarted unexpectedly with a blue screen, do not panic. Windows
tells you exactly what went wrong, and in most cases the fix is a driver update
or a memory test rather than a reinstall.

## What the blue screen is telling you

A blue screen, also called a BSOD or stop error, happens when Windows hits a
problem so serious it cannot keep running safely. It stops everything and
restarts rather than continue in a broken state.

The screen shows three useful things:

- **The stop code name**, such as `CRITICAL_PROCESS_DIED`
- **A short explanation** in plain language
- **Four parameters**, which are hexadecimal numbers describing the failure

The parameters look technical because they are written for engineers. For most
stop codes, you can ignore them and follow the guide for that code instead. Our
[BSOD stop code lookup](/bsod) has guides for over 90 codes.

## Where to find the stop code

If you missed the screen, Windows saves the crash details. Open File Explorer,
paste this into the address bar and press Enter:

```text
C:\Windows\Minidump
```

Each file is named like `071124-15325-01.dmp` and is a small crash report.
Upload one to our [minidump analyzer](/bsod/analyze) and we will extract the
bugcheck code and its parameters for you. The file is parsed in memory and is
never stored.

## The order that fixes most crashes

Whatever the code says, this order works most of the time:

1. **Test your memory.** Run MemTest86 for two full passes. Bad RAM causes more
   stop codes than anything else.
2. **Update drivers, chipset first.** Then graphics, then network. A clean GPU
   install with DDU is worth doing if graphics appear in the message.
3. **Repair system files.** Run DISM RestoreHealth then `sfc /scannow`.
4. **Check your drive.** A failing drive produces crashes that no software fix
   will solve.
5. **Remove overclocks.** Any CPU, GPU or memory overclock is worth
   temporarily reverting while you diagnose.

## When a stop code is really a hardware fault

Some codes are hardware warnings rather than software problems:

| Code | What it usually means |
| --- | --- |
| `MEMORY_MANAGEMENT` | RAM is faulty or badly seated |
| `WHEA_UNCORRECTABLE_ERROR` | CPU, memory or PCIe hardware fault |
| `FAULTY_HARDWARE_CORRUPTED_PAGE` | Hardware returned corrupt memory |
| `CLOCK_WATCHDOG_TIMEOUT` | Unstable overclock or failing CPU |
| `KERNEL_DATA_INPAGE_ERROR` | The drive could not supply data |

> [!WARNING]
> If `KERNEL_DATA_INPAGE_ERROR` or `STORAGE_DEVICE_ABNORMALITY_DETECTED` appears,
> back up your files immediately. These predict drive failure, and continuing to
> use the drive risks losing everything on it.

## What not to do

Do not reinstall Windows until you have tested memory, drivers and the disk. A
reinstall takes hours and will not fix failing hardware, and the same crash will
come back.

Do not use "driver updater" software from advertisements. Many install unsigned
drivers that Windows either refuses to load or that cause new crashes.

> [!DANGER]
> Never download drivers from sites that rank "best drivers". Use your PC or
> motherboard manufacturer's site, or the Microsoft Update Catalog. Wrong drivers
> can make a machine unbootable.

## Turning on automatic memory dumps

To make sure you always have crash details available, set Windows to write a
small dump on every crash:

1. Press Windows key plus R, type `sysdm.cpl` and press Enter
2. Go to the Advanced tab, then Settings under Startup and Recovery
3. Tick Write debugging information to: Small memory dump
4. Under Kernel memory dump, untick the option to automatically restart

Restarting automatically is fine in most cases, but leaving the screen up is
useful when the stop code changes between crashes.
