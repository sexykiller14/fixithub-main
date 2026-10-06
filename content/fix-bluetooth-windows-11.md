---
title: Fix Bluetooth problems on Windows 11
category: drivers
tags: [bluetooth, driver, pairing, audio, device manager, intel]
difficulty: easy
os_version: Windows 10/11
---

## Step 1: Check the basics

- Confirm Bluetooth is on in Settings > Bluetooth & devices
- Confirm the device is switched on and not out of battery
- Move the device closer, since Bluetooth range is around 10 metres
- Try the device on another computer to confirm it works at all

## Step 2: Restart the Bluetooth service

1. Press Windows key plus R
2. Type `services.msc` and press Enter
3. Find Bluetooth Support Service
4. Right-click it and choose Restart

This clears a stuck driver without needing a reboot.

## Step 3: Remove the device and re-pair

1. Settings > Bluetooth & devices > Devices
2. Remove the problem device
3. Turn the device off and on
4. Pair again

Stale pairing records are a common cause of devices that will not reconnect.

## Step 4: Clean reinstall the Bluetooth driver

1. Press Windows key plus X, then Device Manager
2. Expand Bluetooth
3. Right-click the adapter and choose Uninstall device
4. Tick Delete the driver software
5. Restart and let Windows reinstall
6. Then install the vendor driver from your PC vendor's site

> [!WARNING]
> You will have no Bluetooth until the driver is reinstalled. Download the
> installer first.

> [!TIP]
> Get the driver from your laptop vendor rather than the chip vendor. Vendors tune
> power management for their specific hardware.

## Step 5: Remove duplicate Bluetooth adapters

If you have ever changed hardware, ghost entries accumulate.

1. Device Manager > View > Show hidden devices
2. Expand Bluetooth
3. Uninstall every greyed-out adapter for hardware you no longer have

Two active Bluetooth adapters conflict, and one of them wins badly.

## Step 6: Turn off energy saving

Bluetooth radios power down aggressively by default.

1. Device Manager > Bluetooth > the adapter > Properties
2. Power Management tab, untick Allow the computer to turn off this device
3. On an Intel adapter, open Intel Connectivity Performance Suite and turn off its
   power-saving features

> [!TIP]
> Intel Connectivity Performance Suite is a frequent cause of Bluetooth
> stuttering and connection drops. If you do not use it, uninstall it or disable
> it from the tray.

## Step 7: Fix audio problems specifically

Bluetooth audio has its own set of issues.

**Crackling or poor quality:**

1. Settings > Bluetooth & devices > Devices > your headset > Properties
2. Choose the higher-quality audio codec, aptX or AAC, rather than SBC
3. Switch between available codecs and test each

**Delay:**

- Choose the higher-quality codec, which usually has less delay
- Reduce the distance between the PC and device
- For near-zero latency, use a 2.4 GHz dongle instead of Bluetooth

> [!IMPORTANT]
> Some headsets perform better with the legacy SBC codec on Windows despite its
> lower theoretical quality. Test both.

## Step 8: Check the driver provider

Realtek, Intel, MediaTek, Qualcomm and Broadcom all make Bluetooth chips. The
driver source matters:

| Source | Quality |
| --- | --- |
| Laptop vendor | Best, tuned for that machine |
| Chip vendor | Good |
| Windows Update | Often old |
| Third-party sites | Unacceptable |

> [!DANGER]
> Never install Bluetooth drivers from third-party download sites. Bluetooth
> drivers with a poor track record are a standard malware target.

## Step 9: Reset Bluetooth completely

1. Settings > System > Recovery > Advanced startup > Restart now
2. Troubleshoot > Advanced > Startup Repair > Restart

This resets the Bluetooth stack without removing drivers.

## When to see a technician

See a professional if:

- The adapter disappears from BIOS after a firmware update
- It is missing from Device Manager and BIOS both
- Bluetooth fails on another computer as well

That is hardware failure, which no driver fixes.

## Related stop codes

- [BUGCODE_WIFIADAPTER_DRIVER](/bsod), which often involves combined Wi-Fi and
  Bluetooth chips
- [SDHC_INTERNAL_FATAL_ERROR](/bsod) for card readers
- [DPC_WATCHDOG_VIOLATION](/bsod)

## Related

- [Wi-Fi driver problems](/articles/fix-wifi-driver-windows-11)
- [Fix no sound on Windows](/articles/fix-no-sound-windows)
- [Device Manager error codes](/articles/windows-device-manager-error-codes)
