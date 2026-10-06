---
title: USB device not recognized
category: hardware
tags: [usb, not recognized, driver, device manager, cable, port]
difficulty: easy
os_version: Windows 10/11
featured: true
---

USB problems work from the cheapest check to the most expensive, because cables
and ports fail far more often than devices.

## Step 1: Swap the cable and port

This fixes a large share of cases and costs nothing.

- Try a different known-good USB cable
- Move to a rear motherboard port, which has more power than a front panel port
- Avoid hubs and extension cables for the first test
- Try a different port on the PC and on any hub

> [!IMPORTANT]
> Many cheap USB-C cables are power-only and carry no data lines at all. A
> device that charges but never appears as storage is the classic symptom.

## Step 2: Check Device Manager

1. Press Windows key plus X, then Device Manager
2. Look for Unknown USB Device, which means Windows found hardware with no driver

| What you see | Meaning | Fix |
| --- | --- | --- |
| Unknown USB Device | No driver | Update driver |
| Yellow exclamation mark | Driver problem | Read the code |
| Greyed out | Disabled | Enable device |
| Not listed at all | Not detected | Try another port and cable |

> [!IMPORTANT]
> Also look under Universal Serial Bus controllers, Portable Devices and Disk
> drives. Windows often files USB storage in an unexpected category.

## Step 3: Update the driver

1. Right-click the device and choose Update driver
2. Choose Search automatically for drivers

If that fails, download the driver from your PC vendor, or from the device
manufacturer's site.

> [!WARNING]
> Do not use driver updater software or driver packs. They install unsigned
> drivers that Windows refuses to load, or that cause instability.

## Step 4: Clean reinstall

1. Right-click the device > Uninstall device
2. Tick Delete the driver software
3. Restart and let Windows reinstall
4. Then install the official driver

## Step 5: Check power delivery

A device that appears but will not work is usually short of power.

- Connect the device's own power adapter
- Move it from a hub to a direct port
- Check whether the device draws more than one port supplies
- On a desktop, check whether other devices are loading the same controller

> [!WARNING]
> If a port becomes unusually warm, unplug the device. That indicates overload.

## Storage devices: check Disk Management

If the drive does not appear in File Explorer:

1. Right-click Start > Disk Management
2. Look for the drive by capacity
3. If it appears without a letter, assign one with Change Drive Letter and Paths
4. If it shows as RAW or unallocated, see below

> [!DANGER]
> Never format a drive that contains data you have not backed up. A drive
> appearing as RAW usually means it is failing, and formatting destroys what is
> still recoverable.

## Phones

Android phones default to charging-only over USB.

1. Connect and unlock the phone
2. Pull down the notification shade
3. Tap the USB notification and choose File transfer
4. If nothing appears, go to Settings > Connected devices > USB preferences

> [!IMPORTANT]
> Turn USB debugging off after use. Leaving it enabled lets any authorised
> computer control your phone.

## USB-C ports

Inspect and clean the port:

1. Power off and unplug
2. Look into the port with a torch for pocket lint
3. Clear gently with a wooden toothpick or a plastic tray tool
4. Never use metal tweezers, which bend the contacts

A port that only works at certain angles has worn contacts and needs repair.

## Docks and hubs

- Most docks need their own power adapter
- Plug the host cable into a rear motherboard port
- Reduce attached devices to find the failing one
- Two displays usually need a dock with DisplayPort or Thunderbolt output

> [!WARNING]
> Do not power a laptop from a dock while charging the laptop from the same
> dock. That can cause power problems in both.

## Show hidden devices

Device Manager > View > Show hidden devices. Greyed-out entries for hardware you
no longer own cause conflicts.

## Test methodically

1. Does the device work on another computer?
2. Does it work in a different port?
3. Does another device work in the same port?

Those three answers isolate the fault to the device, the port, or the PC.

## Related stop codes

- [BUGCODE_USB_DRIVER](/bsod)
- [BUGCODE_USB3_DRIVER](/bsod)
- [HARDWARE_INTERRUPT_STORM](/bsod), from a failing USB device
- [PASSIVE_INTERRUPT_ERROR](/bsod)

## Related

- [USB-C and dock problems](/articles/fix-usb-c-dock-problems)
- [Bluetooth problems](/articles/fix-bluetooth-windows-11)
- [Device Manager error codes](/articles/windows-device-manager-error-codes)
