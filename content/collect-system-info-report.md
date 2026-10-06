---
title: Collect a system info report for support
category: windows
tags: [system report, diagnostics, event log, support, reliability monitor]
difficulty: easy
os_version: Windows 10/11
---

When you ask for help, the first thing anyone will ask for is details about your
system. This guide covers how to gather them quickly.

## The fastest route: our script

Download [fixit-system-report](/scripts/system-report) and run it. It writes a
text report to your Desktop covering hardware, Windows version, drivers, drive
health and recent critical events, then opens it in Notepad.

Read the report before sharing it. It contains your computer name, user name and
hardware serial numbers.

> [!IMPORTANT]
> The script only reads information. It changes nothing and installs nothing.

## Do it manually

### Windows version and updates

Press Windows key plus R, type `winver` and press Enter. That shows the exact
build number, which matters because fixes differ between 22H2 and 23H2.

### Reliability Monitor

1. Press Windows key plus R
2. Type `perfmon /rel` and press Enter
3. Look at the red X markers

This shows every crash, hardware error and app failure, with the date and time.
For most problems this single view identifies the cause.

### Event Log

1. Event Viewer, from the Start menu
2. Windows Logs > System
3. Filter by Critical and Error
4. Read the events around the time of the problem

Our system report script does this for you and captures the last three days.

### Hardware summary

- Task Manager > Performance shows CPU, RAM, disk, GPU and network at a glance
- Settings > System > About shows the Windows edition, version and processor
- `dxdiag` shows detailed graphics and sound information

### Driver list

- Device Manager > View > Show system devices
- `pnputil /enum-drivers` from Command Prompt lists installed driver packages with
  their versions

## Get the crash details

Minidump files are the most useful evidence for a blue screen.

1. Open `C:\Windows\Minidump` in File Explorer
2. Sort by date and find recent `.dmp` files
3. Upload one to our [minidump analyzer](/bsod/analyze), which reads the bugcheck
   code and parameters safely

> [!IMPORTANT]
> Dump files can contain fragments of your filenames and file contents. Treat
> them as private, and delete them after you are finished. Our analyzer parses
> them in memory and never stores them.

## What to include when asking for help

- Exact error message or stop code, copied exactly
- When it started and what you were doing
- What you have already tried, and the result
- Windows version and build from `winver`
- Whether it happens on another device or network
- Your hardware model, if it is a laptop

## What not to share

- BitLocker recovery keys
- Wi-Fi passwords
- Serial numbers for anything you might claim on
- Personal file names from a dump file
- Browser data or email addresses

> [!DANGER]
> Do not post your BitLocker recovery key anywhere. Anyone with it can decrypt
> your drive.

## Collect before you change anything

If you are about to reinstall a driver or reset Windows, run the report first.
It is the evidence you will want afterwards.

## Related

- [How to read a BSOD stop code](/articles/read-bsod-stop-code)
- [Repair Windows system files](/articles/repair-windows-system-files)
- [Test RAM](/articles/test-ram-memory-errors)
