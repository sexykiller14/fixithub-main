---
title: Realtek audio and network driver fixes
category: drivers
tags: [realtek, audio, network, driver, rtl, lan, wifi]
difficulty: easy
os_version: Windows 10/11
---

Realtek makes extremely common audio and network chips, and their generic drivers
are famously prone to problems. Most are solved by installing the PC vendor's
version instead.

## Prefer your PC vendor's driver

Realtek drivers are almost identical across all the chips in a family. The PC
vendor's driver has been tested with your exact hardware, which the generic one
has not been.

Get it from your laptop or motherboard vendor's support page, matching your exact
model.

> [!WARNING]
> Do not install every Realtek driver you can find. Installing several drivers
> for the same chip conflicts with each other. Install one, the vendor's.

## Clean reinstall Realtek audio

Realtek audio is the most common cause of "no sound" that a normal reinstall
does not fix.

1. Press Windows key plus X, then Device Manager
2. Expand Sound, video and game controllers
3. Right-click the Realtek audio device
4. Choose Uninstall device and tick Delete the driver software
5. Restart and let Windows install a basic driver
6. Install the vendor's Realtek driver

> [!WARNING]
> You will have no sound until the driver is reinstalled. Download the installer
> first.

## Realtek audio options

The Realtek Console or Realtek Audio Console app adds configuration options:

- Speaker configuration, such as 2.0, 5.1 or 7.1
- Sound effects and equaliser
- Jack detection settings
- Mic boost, useful for quiet microphones

If the console app is missing after installing the driver, install the OEM
version from your PC vendor, since the console is often a separate package.

## No sound only through headphones

Realtek's jack detection sometimes misreads the headset.

1. Open the Realtek Audio Console
2. Look for a Disable Speaker Jack Detect option
3. Or set the headphone and microphone jacks to fixed functions
4. Try a different jack, since laptops often have a combined headphone and
   microphone port

## Realtek network and LAN

Realtek network adapters are frequent sources of:

- [DPC_WATCHDOG_VIOLATION](/bsod), which names the network driver
- Connection dropouts
- Slow throughput at gigabit speeds

**Fixes:**

1. Uninstall the network driver with Delete the driver software ticked
2. Restart
3. Install the vendor's driver
4. Disable Energy Efficient Ethernet and Green Ethernet in the adapter's
   Properties > Advanced tab, which cause disconnects on many systems
5. Set Speed & Duplex to Auto Negotiation
6. Turn off power management on the adapter

> [!TIP]
> Energy Efficient Ethernet and Green Ethernet are the two most commonly
> overlooked causes of random Ethernet disconnections on Realtek chips.

## Realtek Wi-Fi

Same approach: vendor driver, clean reinstall, disable the tray application.

Also try in the adapter's Advanced tab:

- Set 802.11n or 802.11ac to enable if they are disabled
- Turn on "Enable hardware 256-bit encryption" if available
- Disable power saving

## Realtek Bluetooth

Realtek Bluetooth adapters sometimes conflict with Intel or Mediatek Bluetooth
if two are installed.

1. Device Manager, then remove any Bluetooth adapter for hardware you do not
   have
2. Reinstall the correct one
3. Remove only unused Bluetooth entries, keeping the one matching your hardware

## When the chip is not in the list

If your audio or network chip is something else, the vendor name is not Realtek.
Check Device Manager for the actual hardware ID:

1. Open the device's Properties
2. Go to the Details tab
3. Select Hardware Ids
4. Look for `VEN_10EC` for Realtek, or another four-character code for other
   vendors

> [!DANGER]
> Never install drivers from sites that host every driver from every vendor.
> They bundle unsigned drivers and old versions that cause crashes. Use your PC
> vendor, the chip vendor, or the Microsoft Update Catalog.

## Related stop codes

- [DPC_WATCHDOG_VIOLATION](/bsod)
- [DRIVER_IRQL_NOT_LESS_OR_EQUAL](/bsod)
- [BAD_SYSTEM_SERVICE_INFO](/bsod)
- [ATTEMPTED_WRITE_TO_READONLY_MEMORY](/bsod)

## Related

- [Fix no sound on Windows](/articles/fix-no-sound-windows)
- [Wi-Fi driver problems](/articles/fix-wifi-driver-windows-11)
- [Ethernet not working](/articles/fix-ethernet-not-working)
