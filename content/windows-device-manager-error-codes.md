---
title: Windows Device Manager error codes
category: drivers
tags: [device manager, code 10, code 28, code 43, driver, hardware]
difficulty: easy
os_version: Windows 10/11
featured: true
---

A yellow exclamation mark in Device Manager is not a mystery. The device's
Properties > General > Status text explains exactly what the driver is
complaining about, usually with a numbered code.

## How to read the code

1. Press Windows key plus X, then Device Manager
2. Find the device with the yellow exclamation mark
3. Double-click it to open Properties
4. Read the General tab, in the Device status section

> [!IMPORTANT]
> The status message itself often names the exact file or setting causing the
> problem. Read it in full before assuming the code tells you everything.

## The codes you will actually see

### Code 1: The driver failed to load

Windows found hardware but the driver did not initialise. Usually a partial or
corrupt install.

- Uninstall the device with Delete the driver software ticked
- Reboot and let Windows reinstall it
- Install the vendor's driver rather than a third-party one
- Run the hardware changes troubleshooter

### Code 10: Cannot start this device

The hardware works but its driver reported a problem starting. Very common on
graphics cards after an unclean shutdown or a Windows Update driver.

- Roll back the driver: Properties > Driver > Roll Back Driver
- If Roll Back is greyed out, remove the device, reboot and install the vendor's
  package
- Use [DDU](/articles/clean-gpu-driver-uninstall-ddu) in Safe Mode for a clean
  removal
- Check the Resource settings for a manual IRQ conflict on older machines

> [!TIP]
> Roll Back Driver is the fastest fix for Code 10, because the last known good
> driver is still installed. It is greyed out when you have never updated that
> driver.

### Code 22: This device is disabled

The device is simply switched off.

- Right-click the device and choose Enable device

### Code 28: Drivers are not installed

Windows has no driver for this hardware. Extremely common for network adapters
and chipsets after a fresh install.

- Install chipset and network drivers from your PC vendor's site
- Use Ethernet or a USB Wi-Fi dongle to download them if you have no network
- On a laptop, check the physical wireless switch and the BIOS setting

### Code 31: A problem occurred and Windows stopped this device

The driver failed to load, usually conflicting with another driver.

- Roll back or reinstall the driver
- Uninstall conflicting older driver packages from the driver's Details tab
- Check Reliability Monitor for the exact failure time

### Code 43: Windows has stopped this device

The driver told Windows it hit a fatal error. On NVIDIA and AMD cards this is
very often an overclock, a bad driver version, or overheating.

- Uninstall the GPU driver, reboot and install the latest stable version
- Remove any overclock or undervolt from MSI Afterburner or the vendor app
- Check GPU temperatures and clean dust from the cooler
- On a laptop, confirm it is not overheating

### Code 45: This device is disconnected or not responding

The device stopped responding.

- Reconnect the device and run the hardware troubleshooter
- Try a different port or cable
- Try a known-good USB port on the case itself
- Update the chipset driver, which manages USB power management

### Code 48: The software for this device has been blocked

The driver is not Windows-signed.

- Uninstall with Delete the driver software ticked, then install the official
  signed driver
- Avoid test signing and unsigned driver packages

### Code 52: The driver was blocked because it caused Windows to fail to start

A driver that crashed during boot was quarantined so Windows could start.

- Uninstall the offending device and reinstall a working driver
- If it keeps happening, remove it in Safe Mode

### Code 54: The device uses a legacy driver

The driver is old 16-bit and no longer works correctly.

- Install a modern driver from the vendor
- The device may be unusable on Windows 11 24H2, which drops legacy support

### Code 141: GPU engine error

The graphics driver crashed and Windows recovered the GPU.

- Update the GPU driver
- Turn off hardware-accelerated GPU scheduling
- Disable Windows Update driver replacement so your version is not swapped out

## No code, just an exclamation mark

Read the status message. It usually names the real problem, such as a missing
file, a resource conflict, or a service that is not running.

## Show hidden devices

Old drivers for hardware you no longer own cause conflicts.

1. Device Manager > View > Show hidden devices
2. Look for greyed-out entries
3. Uninstall anything for hardware that is not present

This removes a large number of mysterious problems, especially after upgrading
motherboards or moving storage between machines.

## Scan for hardware changes

After plugging in new hardware or uninstalling a device:

1. Device Manager > Action > Scan for hardware changes

## Find the exact hardware

If you need to identify a chip:

1. Open the device's Properties
2. Go to the Details tab
3. Select Hardware Ids
4. The VEN and DEV codes identify the manufacturer and device

`VEN_10EC` is Realtek, for example.

> [!DANGER]
> Do not download drivers from driver-download sites that host every driver from
> every manufacturer. They bundle unsigned and outdated drivers that Windows
> refuses or that cause crashes. Use your PC vendor, the chip vendor, or the
> Microsoft Update Catalog.

## Related stop codes

- [DRIVER_INITIALIZATION_FAILED](/bsod)
- [DRIVER_CORRUPTED_EXPOOL](/bsod)
- [BAD_SYSTEM_SERVICE_INFO](/bsod)
- [VIDEO_DRIVER_INIT_FAILURE](/bsod)
- [CHIPSET_DETECTED_ERROR](/bsod)

## Related

- [NVIDIA driver guide](/articles/nvidia-driver-guide)
- [AMD driver guide](/articles/amd-driver-guide)
- [Chipset drivers and Windows Update](/articles/chipset-drivers-windows-update)
