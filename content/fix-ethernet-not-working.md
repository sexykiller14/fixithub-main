---
title: Fix Ethernet not working or no network cable detected
category: network
tags: [ethernet, lan, network, cable, port, adapter]
difficulty: easy
os_version: Windows 10/11
---

Ethernet problems are usually physical, and the physical fixes are free.

## Check the lights first

Look at the port on the PC and the matching port on the router.

- **Both ends lit**: there is a physical link, so the problem is software
- **One end dark**: cable, port or adapter fault
- **Both dark**: no link at all

## Fix 1: Reseat and swap the cable

- Push the connector in until it clicks firmly at both ends
- Try a different cable, since damaged cables are extremely common
- Try a different port on the router and a different port on the PC
- Check for sharp bends or crushing near the connectors

> [!IMPORTANT]
> A cable that works intermittently when the machine is warm points to damage at
> a connector. Replace the cable rather than repairing it.

## Fix 2: Check which port you are using

On the back of a desktop you have several ports, and they are not all for
network traffic:

- **Green**: network traffic, use this one
- **Pink**: microphone input
- **Orange or brown**: old FireWire
- **Grey**: USB, not network at all

On a laptop, look for the network icon rather than a plain rectangular socket.

> [!WARNING]
> Plugging a microphone into a network port can damage the microphone. Check the
> colour and the icon before connecting.

## Fix 3: Update the network adapter driver

1. Press Windows key plus X and choose Device Manager
2. Expand Network adapters
3. Right-click the Ethernet adapter and choose Update driver
4. Choose Search automatically for drivers
5. If that does not help, download the driver from your PC vendor

Realtek adapters are particularly prone to needing a clean reinstall. See
[Realtek driver guides](/articles/realtek-audio-network-drivers).

## Fix 4: Clean reinstall the adapter

1. Device Manager > View > Show hidden devices
2. Expand Network adapters
3. Right-click the Ethernet adapter and choose Uninstall device
4. Tick Delete the driver software
5. Restart and let Windows reinstall it
6. Then install the official driver

## Fix 5: Enable the adapter

If the entry is greyed out, right-click it and choose Enable device. If that
option is missing, uninstall and restart so Windows reinstalls it.

## Fix 6: Check for conflicts

Two things cause "Network cable is unplugged" despite a good cable:

- Two network managers running at once, such as a VPN client and a virtual
  machine host
- Duplicate IP address warnings

Reset the stack:

```text
netsh int ip reset
```

```text
netsh winsock reset
```

Restart afterwards.

## Fix 7: Set the link speed manually

If the connection works but is slow, force the adapter to negotiate properly:

1. Device Manager > the Ethernet adapter > Properties > Advanced
2. Find Speed & Duplex and set it to Auto Negotiation
3. If Auto is faulty, set it to the speed your cable and switch support, such as
   1.0 Gbps Full Duplex

## Fix 8: Check for duplex mismatch

Duplex mismatch gives a link light but almost no usable throughput, which looks
like a fault rather than a configuration error. Setting Speed & Duplex to match
your actual network equipment fixes it.

## Check the router side

- Confirm the correct cable is running to the router's LAN port, not a WAN port
- If using a switch, confirm its power light is on
- Try a different router port
- Power cycle the switch or router

## Related stop codes

- [DRIVER_IRQL_NOT_LESS_OR_EQUAL](/bsod) frequently names `tcpip.sys`
- [DPC_WATCHDOG_VIOLATION](/bsod) often points at the network adapter driver
- [BAD_POOL_HEADER](/bsod) can follow a corrupted network driver

## When it is hardware

If the adapter is missing from Device Manager, appears in BIOS but not Windows,
or fails on every cable and port, the network adapter or its controller has
failed. On a desktop that means replacing the motherboard's onboard adapter or
adding a USB or PCIe Ethernet adapter, both of which are inexpensive fixes.

## Related

- [Fix no internet on Windows](/articles/fix-no-internet-windows)
- [DNS problems](/articles/fix-dns-problems-windows)
- [Wi-Fi driver problems](/articles/fix-wifi-driver-windows-11)
