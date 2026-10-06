---
title: Chipset drivers and Windows Update
category: drivers
tags: [chipset, drivers, windows update, inf, rollback, driver verifier]
difficulty: moderate
os_version: Windows 10/11
---

Chipset drivers are the foundation everything else stands on. Windows Update
installs them automatically, which is convenient and occasionally harmful.

## What a chipset driver actually does

Chipset drivers are usually INF files that tell Windows how to talk to the
motherboard's controller chips:

- **PCI Express** controllers, which includes the graphics card slot
- **SATA and NVMe** storage controllers
- **USB** controllers and power management
- **Memory controller** settings, including XMP and EXPO
- **Audio, networking and power management** on integrated hardware

They are not performance drivers. They make the hardware work correctly and
stably.

## Install chipset drivers first

Order matters:

1. BIOS update from the board vendor
2. Chipset driver from the board vendor
3. Graphics driver from the GPU vendor
4. Network, audio and everything else

> [!IMPORTANT]
> Windows will boot and mostly work without the chipset driver, but storage
> stability, power management and PCIe compatibility are all degraded. It is
> worth installing properly.

## Let Windows Update do it, then roll back if needed

Windows Update often installs a generic chipset driver that is older than the
vendor's.

1. Windows Update > Check for updates
2. Install any chipset or device driver offered
3. Reboot
4. Test stability

If the machine was unstable, go back to Device Manager and roll the driver back:

1. Device Manager > the device > Properties > Driver
2. Choose Roll Back Driver

> [!TIP]
> Rolling back is how you undo a driver that Windows Update installed without
> your asking. The previous version is still available for exactly this reason.

## Disable driver replacement

Once you have the right drivers, stop Windows Update replacing them.

1. Settings > Windows Update > Advanced options
2. Choose Optional updates
3. Under Driver updates, choose Pause updates

Leave it paused. Install drivers yourself from the PC vendor, so you know what you
are getting.

> [!WARNING]
> Do not disable Windows Update entirely. Keep security updates, and only pause
> driver replacement.

## Device Manager and drivers in general

- **Update driver > Search automatically**: good for peripheral hardware
- **Update driver > Browse my computer**: use when you have downloaded a driver
  yourself
- **Roll Back Driver**: your fastest fix after a bad automatic install

> [!WARNING]
> Never untick Delete the driver software when rolling back a storage or chipset
> driver. That removes files other devices depend on.

## Driver Verifier, and why to turn it off

If a machine suddenly will not boot and you suspect Driver Verifier was enabled,
for example by a support technician or a troubleshooting guide:

1. Boot into Safe Mode, which Verifier normally ignores
2. Open an elevated Command Prompt
3. Run:

```text
verifier /reset
```

4. Reboot

If Safe Mode is unreachable, boot from Windows installation media, choose Repair >
Command Prompt, and run `verifier /reset` there.

[DRIVER_VERIFIER_DETECTED_VIOLATION](/bsod) is the stop code it produces.

> [!WARNING]
> `verifier /reset` must be run from Safe Mode or the Recovery Environment.
> Running it in normal Windows does nothing useful.

## Storage drivers and RAID mode

RAID drivers are chipset drivers in effect, and they are the most dangerous ones
to change.

- Intel RST and VMD drivers must match the BIOS mode
- AMD RAID drivers must match the RAID controller
- Changing the BIOS storage mode after installing these drivers causes
  [INACCESSIBLE_BOOT_DEVICE](/bsod)

> [!DANGER]
> Do not change the SATA mode between AHCI and RAID after installing Windows.
> Windows will not boot. Decide the mode before installing.

## Where to get drivers

| Driver | Best source |
| --- | --- |
| Chipset | Board vendor, or Intel and AMD DSA |
| Graphics | NVIDIA, AMD, Intel |
| BIOS | Board vendor only |
| Network and audio | PC vendor |
| Old or unusual hardware | Microsoft Update Catalog |

The [Microsoft Update Catalog](https://www.catalog.update.microsoft.com/) is
official and hosts signed drivers that vendors have withdrawn.

> [!DANGER]
> Never download drivers from "best driver" sites or from pop-ups. They install
> unsigned drivers, which Windows either refuses or which cause crashes and
> instability.

## Verify what is loaded

1. Device Manager > any device > Properties > Driver
2. Check the driver date and version
3. Compare with the version your vendor publishes

If they do not match, something replaced it.

## Related stop codes

- [INACCESSIBLE_BOOT_DEVICE](/bsod)
- [CHIPSET_DETECTED_ERROR](/bsod)
- [DRIVER_CORRUPTED_EXPOOL](/bsod)
- [DRIVER_VERIFIER_DETECTED_VIOLATION](/bsod)
- [PCI_BUS_DRIVER_INTERNAL](/bsod)

## Related

- [Windows Device Manager error codes](/articles/windows-device-manager-error-codes)
- [Intel driver guide](/articles/intel-driver-guide)
- [Windows Update failing](/articles/fix-windows-update-failing)
