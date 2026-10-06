---
title: Intel driver install and troubleshooting
category: drivers
tags: [intel, driver, chipset, graphics, 12th gen, dsa]
difficulty: easy
os_version: Windows 10/11
---

Intel drivers matter more than most people expect, because chipset drivers
underpin storage, networking, power management and graphics stability.

## Update in the right order

1. **BIOS** from your motherboard or laptop vendor
2. **Chipset** driver from Intel
3. **Graphics** driver from Intel
4. Everything else from the PC vendor

Updating chipset first is not superstition. Storage and network drivers depend on
chipset components being current, and installing graphics first is a common
cause of unstable systems.

## Intel Driver & Support Assistant

Intel's own tool matches drivers to your exact hardware, which avoids the
mistakes of guessing.

1. Download Intel Driver & Support Assistant from
   [intel.com/content/www/us/en/support/detect.html](https://www.intel.com/content/www/us/en/support/detect.html)
2. Run it and accept the EULA
3. Choose Scan for driver updates
4. Install what it offers, chipset first

> [!WARNING]
> Uninstall the Intel Driver & Support Assistant after you are finished. It
> installs a background service that some people find intrusive, and it can
> reinstall drivers you have deliberately removed.

> [!WARNING]
> Do not enable its automatic driver installation. Install drivers manually so you
> know what changes.

## Where to get drivers

| Driver | Source |
| --- | --- |
| Chipset | Intel DSA or the PC vendor |
| Graphics | Intel, or the PC vendor |
| Wi-Fi and Bluetooth | The laptop vendor, preferred |
| Storage and RAID | The motherboard vendor |
| Anything else | The PC vendor |

> [!IMPORTANT]
> Laptop vendors tune drivers for their specific hardware, including power
> management and the lid switch. Their versions are usually better than Intel's
> generic ones for that machine.

## Intel graphics issues

**Black screen or flickering**

- Update the Intel graphics driver
- Disable hardware-accelerated GPU scheduling in Settings > System > Display >
  Graphics
- Turn off the panel self-refresh setting in Intel Graphics Command Center, which
  causes flickering on some laptops
- Update the BIOS, since some flicker issues are firmware-related

**High CPU usage from Intel graphics**

Newer Intel graphics drivers occasionally run a background process heavily. Update
the driver and turn off the tray application if you do not need it.

**Games not using the integrated GPU**

Applications choose the wrong adapter. Set it per application in Settings > System
> Display > Graphics > Options > High performance.

## Intel Wi-Fi issues

Intel Wi-Fi cards are common in laptops and have their own quirks.

- Update the driver from the laptop vendor rather than the Intel generic one
- Turn off the Intel Connectivity Performance Suite tray application, which is a
  common source of stuttering
- Disable Bluetooth power saving in the adapter properties

[Wi-Fi driver problems](/articles/fix-wifi-driver-windows-11) covers this in more
detail.

## Intel NUC and mini PCs

Intel NUCs are sensitive to memory configuration.

- Check the vendor's supported memory list
- Use matched kits
- Some models only support 16 GB per slot

## When a device shows no driver

Intel's driver and support assistant will tell you exactly which device and
where to get the driver. For devices with no Intel driver at all, you need the
PC vendor's driver or the Microsoft Update Catalog.

## How to tell what hardware you have

1. Press Windows key plus X, then Device Manager
2. Look under Processors for the CPU
3. Look under Display adapters for the graphics
4. Look under Network adapters for Wi-Fi

## Related stop codes

- [VIDEO_DXGKRNL_FATAL_ERROR](/bsod) can follow an Intel graphics driver fault
- [DPC_WATCHDOG_VIOLATION](/bsod) frequently names Intel network drivers
- [MICROCODE_REVISION_MISMATCH](/bsod) means the BIOS microcode does not match
  what Windows expects, so update the BIOS

## Related

- [Windows Device Manager error codes](/articles/windows-device-manager-error-codes)
- [Chipset drivers and Windows Update](/articles/chipset-drivers-windows-update)
- [Wi-Fi driver problems](/articles/fix-wifi-driver-windows-11)
