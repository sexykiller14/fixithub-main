---
title: Fix high CPU usage
category: windows
tags: [cpu, performance, task manager, malware, windows defender, search index]
difficulty: easy
os_version: Windows 10/11
---

High CPU is usually one process doing too much, and Task Manager identifies it.

## Find the culprit

1. Press Ctrl plus Shift plus Esc for Task Manager
2. Open the Processes tab
3. Right-click the column header and tick CPU
4. Sort by CPU usage, descending

Leave it running for a minute while you work normally. The top consumer appears.

## Common causes and fixes

### Windows Defender or Antimalware Service Executable

Defender scanning in the background. It is often temporary.

- Let the scan finish
- Check whether it is a scheduled scan: Windows Security > Virus & threat
  protection > Protection history
- Exclude large, rarely changed folders such as game libraries and development
  directories

> [!IMPORTANT]
> Excluding folders reduces scanning coverage. Exclude only folders you are
> confident about, and never your Downloads folder.

### Windows Search indexing

Windows Search indexing every file on a large drive uses CPU and disk constantly.

1. Settings > Privacy & security > Windows Search > Indexing options
2. Click Modify
3. Select only your user folder and Program Files
4. Leave Windows, System32 and drive roots unindexed

### Windows Update

Updates install in the background and use CPU while they do.

- Let it finish rather than shutting down
- Check Settings > Windows Update for progress
- Avoid using the machine during a major update

### A browser with too many tabs

Each tab is a separate process using memory and CPU.

- Close tabs you are not using
- Use a tab-suspend extension
- Consider an extension that unloads inactive tabs

> [!TIP]
> Run an ad-blocker. Ads, trackers and auto-playing video are the biggest CPU
> consumers in a browser.

### A game or application in the background

Games launched from a launcher, video editors, and streaming software often keep
running.

- Check the system tray for background applications
- Close them properly rather than just minimising
- Disable background recording in your capture software

### A stuck process

1. Right-click the process and choose Restart
2. If that fails, choose End task
3. Reboot if a critical system process will not end

> [!WARNING]
> Do not end Antimalware Service Executable, Service Host, System, or the Desktop
> Window Manager. These are Windows components, and ending them causes
> instability and a forced restart.

### Malware

An unrecognised process using sustained CPU is worth checking.

1. Windows Security > Scan options > Full scan
2. Then run a Microsoft Defender Offline scan, which reboots into a separate
   environment

> [!WARNING]
> Never install antivirus from a pop-up or an advertisement. Free PC "optimiser"
> bundles are a standard malware delivery method.

### Overheating

A hot CPU throttles, which looks like slowness rather than high usage.

- Check temperatures with HWiNFO or Task Manager
- See [high CPU temperature](/articles/fix-high-cpu-temperature)

## Use the Process Explorer alternative

If Task Manager does not give enough detail, Microsoft's Process Explorer is
free and shows what each process is actually doing, including which threads use
CPU. It is the tool technicians use.

## Check startup impact

1. Task Manager > Startup apps tab
2. Look at the Startup impact column
3. Disable anything with high impact that you do not use daily

## After fixing it

Restart, then check whether it returns. If it does, note what you were doing
when it started, since the pattern identifies the cause.

## Collect more detail

Our [system report script](/scripts/system-report) captures running processes,
installed drivers and recent critical events, which helps identify a process you
cannot place.

## Related

- [Speed up a slow PC](/articles/speed-up-slow-windows-pc)
- [Why my PC is slow after an upgrade](/articles/fix-slow-pc-after-upgrade)
- [Repair Windows system files](/articles/repair-windows-system-files)
