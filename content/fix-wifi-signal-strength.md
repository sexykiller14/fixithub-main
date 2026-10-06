---
title: Improve weak Wi-Fi signal
category: network
tags: [wifi, signal, router, 5ghz, 2.4ghz, interference]
difficulty: easy
os_version: Windows 10/11
---

Weak signal is different from no connection. Pages stall, video buffers, and
calls drop, even though the network technically works.

## Check what you actually have

Look at the network icon in your taskbar. The number of bars is a rough guide,
but run our [latency test](/tools/latency) against your router or a nearby server
for a real number.

Also check the link speed: Settings > Network & internet > Wi-Fi > Properties.
For 5 GHz Wi-Fi 6 on a modern laptop you would expect 866 Mbps or more.

## Fix 1: Move and orient the router

- Put it in an open, elevated position, not inside a cupboard
- Avoid behind a television, inside a cupboard, or on the floor
- Keep it away from metal, mirrors and windows
- If the router has external antennas, point them outward rather than into a
  wall

Router placement makes more difference than any router upgrade.

## Fix 2: Find the interference

2.4 GHz is crowded. These devices cause the most problems:

- Microwaves
- Cordless phone bases
- Baby monitors
- Bluetooth speakers and headphones
- Neighbouring Wi-Fi networks on the same channel

Move the router away from them, and if you have one, set the 2.4 GHz channel to 1,
6 or 11 rather than auto, since auto often picks a busy channel.

## Fix 3: Choose the right band

| Band | Range | Speed | Best for |
| --- | --- | --- | --- |
| 2.4 GHz | Further | Slower | Through walls, distant rooms |
| 5 GHz | Shorter | Faster | Same room, nearby rooms |
| 6 GHz | Shortest | Fastest | Modern devices, close range |

Use 5 GHz in the same room, and 2.4 GHz for distant rooms or through walls. If
your router supports both, it usually broadcasts both at once, called band
steering.

## Fix 4: Use Ethernet where it matters

For a desktop, a cable always beats Wi-Fi in both speed and reliability. If you
cannot run a cable across a room:

- Powerline adapters use your electrical wiring
- A mesh system adds nodes in the rooms that are weak
- A MoCA adapter works over coax if you have old TV cabling

Avoid long cable runs under carpets or through doorways, since those degrade the
signal badly.

## Fix 5: Set the adapter to maximum performance

Windows defaults Wi-Fi cards to a power-saving mode that costs a lot of
throughput.

1. Press Windows key plus X and choose Device Manager
2. Expand Network adapters and open your Wi-Fi adapter's Properties
3. Go to the Advanced tab
4. Set Power Saving Mode to Maximum Performance
5. Apply, then restart

Also turn off the adapter's power management tab's option to allow the computer
to turn off the device to save power.

## Fix 6: Update the driver

Outdated drivers handle weak signals badly. Install the driver from your laptop
vendor rather than relying on Windows Update. See the
[Wi-Fi driver guide](/articles/fix-wifi-driver-windows-11).

## Fix 7: Change the transmit power

If the router allows it, set the transmit power to High or Medium rather than
Low. Some routers ship set to Low, which is correct for apartments with very
close neighbours and wrong for most homes.

## What the signal bars mean

Windows bars are relative to the adapter's maximum, not absolute quality. A
workable setup:

- Three bars or more for video calls and streaming
- Two bars for browsing and downloads
- One bar for basic browsing only

Anything below one bar means you need range, not a driver fix.

## Do not do these

- Do not add a signal booster that just rebroadcasts the same crowded channel
- Do not increase router transmit power beyond High, which causes interference
- Do not run microwaves and video calls at the same time on 2.4 GHz
- Do not buy a faster internet package before fixing signal and placement, since
  a weak signal wastes the extra bandwidth

## Related

- [Fix no internet on Windows](/articles/fix-no-internet-windows)
- [Fix Ethernet not working](/articles/fix-ethernet-not-working)
- [Router lights and offline mode](/articles/fix-router-lights-offline)
