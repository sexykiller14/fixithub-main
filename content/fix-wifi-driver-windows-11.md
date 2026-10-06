---
title: Fix Wi-Fi driver problems on Windows 11
category: drivers
tags: [wifi, driver, network adapter, windows 11, device manager]
difficulty: easy
os_version: Windows 11
featured: true
---

Wi-Fi adapters are the most commonly misbehaving device in a laptop, because
Windows Update frequently installs a generic driver that works badly.

## Install the official driver first

Windows Update drivers for network adapters are frequently older and worse than
what your laptop vendor ships.

1. Note your exact model number, usually on a sticker on the bottom
2. Go to your laptop vendor's support site
3. Find your model and download the Wi-Fi driver for Windows 11 22H2 or newer
4. Install it before doing anything else

## Check the adapter state

1. Press Windows key plus X and choose Device Manager
2. Expand Network adapters
3. Look at the Wi-Fi entry

- **Yellow exclamation mark**: read the code in Properties > General > Status
- **Greyed out**: right-click and choose Enable device
- **Missing entirely**: the adapter is not being detected at all

If the adapter is greyed out or missing, check the physical switch before
anything else. Most laptops have:

- A physical Wi-Fi switch on the side
- A function key combination such as Fn plus F2 or F12
- A BIOS setting under Security or Advanced called Wireless or WLAN

A laptop missing the adapter from BIOS entirely has a hardware fault.

## Clean reinstall

1. Right-click the Wi-Fi adapter and choose Uninstall device
2. Tick Delete the driver software
3. Restart, and let Windows install a basic driver
4. Then install the vendor driver you downloaded earlier

> [!WARNING]
> You will have no Wi-Fi until the driver is reinstalled. Have Ethernet or a USB
> Wi-Fi dongle available in case the automatic install fails.

> [!IMPORTANT]
> Turn off Windows Update's driver replacement first, or it will silently
> overwrite your working driver again:
> Settings > Windows Update > Advanced options > Optional updates >
> Driver updates > Pause updates

## Hidden and phantom adapters

Windows keeps adapters you have removed, and a ghost adapter can confuse the
real one.

1. Device Manager > View > Show hidden devices
2. Expand Network adapters
3. Right-click any greyed-out adapter for hardware you no longer own
4. Choose Uninstall device

## Forget and reconnect

A corrupted saved profile causes connections that appear to succeed then drop.

1. Settings > Network & internet > Wi-Fi > Manage known networks
2. Select the network and choose Forget
3. Reconnect and enter the password again

## Reset the adapter at the hardware level

1. Device Manager > View > Show hidden devices
2. Expand Network adapters
3. Right-click the Wi-Fi adapter > Properties > Advanced
4. Change Power Saving Mode to Maximum Performance

Modern cards default to a low-power mode that reduces throughput significantly.

## If the adapter is missing from Device Manager entirely

1. Restart, then check again
2. Enter BIOS with Del or F2 and confirm the wireless option is enabled
3. Update BIOS firmware, since older firmware can fail to detect newer cards
4. On a laptop, confirm the card is seated and its antenna cables are attached
5. Load BIOS defaults, in case a power or sleep setting is interfering

## Which stop codes point at Wi-Fi?

- [DPC_WATCHDOG_VIOLATION](/bsod) frequently names a network driver
- [BUGCODE_WIFIADAPTER_DRIVER](/bsod) is a direct network adapter fault
- [TIMER_OR_DPC_INVALID](/bsod) and
  [DRIVER_POWER_STATE_FAILURE](/bsod) often trace back to network adapters

## When to see a technician

See a professional if the adapter disappears from BIOS, fails in another
computer as well, or if the card is not detected after a BIOS update. That is
hardware failure, not a driver problem.
