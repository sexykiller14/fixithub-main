---
title: Windows 11 install stuck or failing
category: windows
tags: [windows 11, install, upgrade, in-place, boot, media]
difficulty: moderate
os_version: Windows 11
---

Fresh Windows 11 installs get stuck for a small number of predictable reasons.

## Where Windows 11 gets stuck

| Screen | Usual cause |
| --- | --- |
| "Just a moment" | Server congestion or a network block |
| "Just a moment" forever | Your network blocks Windows Update servers |
| "Your PC doesn't meet the minimum requirements" | Unsupported CPU, TPM or Secure Boot |
| Getting files, 0 to 99 percent stalled | Slow connection or bad storage driver |
| Blue screen during install | Storage mode mismatch or bad driver |
| Setup can't find a driver | No driver for the storage controller |
| Rolling back after setup | Driver or hardware incompatibility |

## Fix: Bypass the network block

Windows needs its update servers during setup. Corporate networks, some ISPs and
VPNs block them.

Options that work:

- Use a phone hotspot
- Temporarily disconnect from the network, and connect after setup reaches the
  OOBE screen
- In the command prompt during setup, press Shift plus F10 and run:

```text
OOBE\BYPASSNRO
```

That skips the online account requirement on current builds. If that does not
work, the older registry method applies:

```text
reg add HKLM\SYSTEM\Setup\Status\CloudContent /v BypassNRO /t REG_DWORD /d 1 /f
```

Then reconnect and restart setup.

> [!IMPORTANT]
> After setup, delete the BypassNRO key if it was added, so your account is
> properly linked:
>
> ```text
> reg delete HKLM\SYSTEM\Setup\Status\CloudContent /v BypassNRO /f
> ```

## Fix: Meet the requirements

Windows 11 needs a supported CPU, TPM 2.0 and Secure Boot.

Check yours with PC Health Check, Microsoft's official tool at
[aka.ms/GetPCHealthCheckApp](https://aka.ms/GetPCHealthCheckApp).

If the CPU is not on the supported list but the hardware otherwise works, an
in-place upgrade often still works, though Microsoft does not support it.

## Fix: Create the USB properly

Common causes of a bad installer:

- Using a third-party Rufus or Rufus-based tool with a poor ISO
- A USB drive below 8 GB
- A USB drive that is fake or failing

Use Microsoft's own [Media Creation Tool](https://www.microsoft.com/software-download/windows11).
Choose "Create installation media", then "USB flash drive".

> [!WARNING]
> Do not use a USB drive with important data. Creating the installer erases it
> completely.

## Fix: Load the right driver during install

If setup says it cannot find a driver for your disk:

1. Load the USB drive with the storage driver on another computer
2. Download your chipset and storage drivers from your PC vendor's site
3. Copy them to a second USB drive, or to the same one in a separate folder
4. At the "Where do you want to install Windows?" screen, click Load driver
5. Browse to your copied drivers and load the storage one

> [!IMPORTANT]
> You only need the storage driver at that point. Loading everything is slow and
> unnecessary. Use the vendor's driver, since Windows does not include Intel or
> AMD RAID drivers.

## Fix: Storage mode mismatch

If setup shows [INACCESSIBLE_BOOT_DEVICE](/bsod) or "cannot find a driver", the
BIOS storage mode does not match. Set it to AHCI rather than RAID, or vice versa
depending on what the vendor intended.

> [!WARNING]
> Changing storage mode after installing Windows causes
> [INACCESSIBLE_BOOT_DEVICE](/bsod). Decide before installing, not after.

## Fix: In-place repair instead of a clean install

If Windows is already installed and broken, an in-place repair often works where
a fresh install does not.

1. Download the Windows 11 ISO from
   [microsoft.com/windows/download](https://www.microsoft.com/windows/download)
2. Mount it by double-clicking the ISO
3. Run setup.exe from the mounted drive
4. Choose Keep files and apps when asked

> [!DANGER]
> Back up anything irreplaceable before an in-place repair. It reinstalls Windows
> and can leave third-party drivers and software in an inconsistent state.

## Fix: Reset this PC

Settings > System > Recovery > Reset this PC > Keep my files rebuilds Windows
while keeping your data and applications.

> [!DANGER]
> Reset removes installed applications. Back up your Desktop, Documents and any
> software you cannot reinstall.

## Related stop codes

- [INACCESSIBLE_BOOT_DEVICE](/bsod) after an upgrade
- [CRITICAL_PROCESS_DIED](/bsod) after setup completes
- [DRIVER_INITIALIZATION_FAILED](/bsod) during setup
- [NO_SUCH_PARTITION](/bsod) if the wrong disk was chosen

## Related

- [Fix boot loop](/articles/fix-boot-recovery-loop)
- [CRITICAL_PROCESS_DIED](/articles/critical-process-died)
- [Windows Update failing](/articles/fix-windows-update-failing)
