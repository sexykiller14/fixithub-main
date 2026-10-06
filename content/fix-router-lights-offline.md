---
title: Router lights and offline mode
category: network
tags: [router, modem, isp, offline, lights, reconnect]
difficulty: easy
os_version: Windows 10/11
---

When nothing in the house has internet, the problem is the router, the modem or
your provider. Windows settings will not fix it.

## Read the lights before touching anything

Typical meanings, though labels vary by brand:

| Light | Meaning | If off or flashing |
| --- | --- | --- |
| Power | Has electricity | Check the socket and the power brick |
| Broadband / DSL / WAN | Line sync from your provider | Line or modem fault |
| Internet | Provider connection established | Call your provider |
| LAN (per port) | A device is connected and talking | Cable, port or device fault |
| Wi-Fi | Radio is broadcasting | No wireless devices can connect |

A steady Internet light means the problem is on your side. A dark or
permanently flashing Internet light means the provider's line or the modem is at
fault.

## Fix 1: Power cycle properly

This is not the same as switching it off and on quickly.

1. Unplug the modem from the power socket
2. Unplug the router from the modem and the socket
3. Wait a full 60 seconds. This lets the line retrain
4. Plug in the modem first and wait until its Internet light is steady, about
   two to five minutes
5. Plug in the router and wait for its Internet light
6. Connect a device and test

> [!IMPORTANT]
> Wait for each light to become steady before moving on. Resetting a modem while
> it is still syncing restarts the process and it never completes.

## Fix 2: Check every cable

- Reconnect the coax or DSL cable at both ends
- Reseat the Ethernet cable from the modem to the router
- Try a different Ethernet cable
- Check that the coax is not sharply bent or pinched

## Fix 3: Test without the router

Connect a laptop directly to the modem with an Ethernet cable. If you get
internet, the router is the problem. If you do not, it is the modem or the line.

> [!WARNING]
> Connecting directly to the modem bypasses your router's parental controls and
> any local network sharing. Reconnect to the router afterwards.

## Fix 4: Call your provider

Have these ready:

- Your account number
- The modem's indicator lights and their states
- Whether a device connected directly to the modem works
- Whether there is a known outage in your area

Most providers can see a line fault from their side, which saves a lot of
fumbling.

> [!WARNING]
> Do not factory reset the modem before calling. The reset erases the credentials
> your provider needs to activate your line, and it often means a technician
> visit.

## Fix 5: Check the Wi-Fi radio

If the Internet light is steady but no wireless device connects:

- Look for a physical Wi-Fi switch or WPS/Wi-Fi button and turn it on
- Some routers disable Wi-Fi automatically after a period of inactivity
- Check for a hidden or changed network name after a firmware update
- Reset only the router's wireless settings, not its full factory reset

## Fix 6: Firmware

Outdated router firmware causes stability problems. Check your router's admin
page for updates, which is usually at `192.168.1.1` or `192.168.0.1`.

> [!WARNING]
> Do not interrupt a firmware update. A power cut mid-update can brick the router.
> Use a UPS or a laptop battery if mains power is unstable.

## Fix 7: Check whether the provider is blocking you

Some providers require you to use their DNS. If you changed DNS manually and
everything stopped working, return to automatic:

```text
netsh interface ipv4 set dnsservers name="Ethernet" source=dhcp
```

Our [DNS problems guide](/articles/fix-dns-problems-windows) covers this.

## When to replace the router

Replace it if:

- It fails to sync with the provider after several power cycles
- It is over six years old and the provider has dropped support for its chipset
- Its ports are physically damaged
- It overheats, which shows as random disconnects over months

A basic modern router costs far less than a technician visit.

## Related

- [Fix no internet on Windows](/articles/fix-no-internet-windows)
- [DNS problems](/articles/fix-dns-problems-windows)
- [Ethernet not working](/articles/fix-ethernet-not-working)
