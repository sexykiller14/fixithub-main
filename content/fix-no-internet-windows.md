---
title: Fix "No internet" on Windows
category: network
tags: [network, internet, dns, wifi, ethernet, winsock, tcp/ip]
difficulty: easy
os_version: Windows 10/11
featured: true
---

The key question is whether other devices work on the same network. That single
test tells you whether to look at this PC or at your router.

## Start with that test

Connect your phone to the same Wi-Fi and try to load a page.

- **Phone works, PC does not**: the fault is on this PC, continue below
- **Nothing works**: the fault is the router, modem or your provider. Reboot both
  and call them if needed

## Fix 1: Reset the network stack

Open Command Prompt as Administrator. Right-click Start, then Terminal
(Admin), or search for cmd and choose Run as administrator.

```text
ipconfig /flushdns
```

```text
ipconfig /release
```

```text
ipconfig /renew
```

Then rebuild the components Windows uses for networking:

```text
netsh winsock reset
```

```text
netsh int ip reset
```

Restart the PC afterwards, since the last two commands do not take effect until
you do.

> [!WARNING]
> These resets disrupt VPN clients and virtual machine networks. You will need to
> reinstall or reconfigure that software afterwards.
>
> Run these in Command Prompt, not PowerShell. They will not work in PowerShell.

You can download our [network reset script](/scripts/network-reset) instead of
typing the commands by hand.

## Fix 2: Change your DNS servers

If numeric addresses work but website names do not, DNS is the problem. Test by
opening `https://1.1.1.1` in your browser: if that loads, the issue is name
resolution rather than the connection.

1. Settings > Network & internet > Wi-Fi or Ethernet
2. Click Properties on your connection
3. Under DNS server assignment choose Edit
4. Switch to Manual and enter `1.1.1.1` and `1.0.0.1`
5. Save, then run `ipconfig /flushdns`

You can verify resolution works using our [DNS lookup tool](/tools/dns).

> [!IMPORTANT]
> Workplace and school networks often supply their own DNS and block others. Ask
> your administrator before changing it there.

## Fix 3: Check the adapter

1. Press Windows key plus X and choose Device Manager
2. Expand Network adapters
3. Look for a yellow exclamation mark

If you see one, note the code shown in the device Properties > General > Status
text and look it up in our
[Device Manager error codes](/articles/windows-device-manager-error-codes) guide.

Code 28 simply means no driver is installed. Install from your PC vendor's site.

## Fix 4: Captive portals

Public and guest networks show a sign-in page before any traffic is allowed.
This looks exactly like a broken connection.

- Open a browser and visit `http://neverssl.com`
- If nothing appears, try `http://1.1.1.1`
- Accept the terms or sign in

> [!DANGER]
> Never disable certificate warnings or antivirus to force a captive portal
> through. That is precisely how captive portal credential theft works.

## Fix 5: Reset the network adapter itself

1. Open Device Manager and expand Network adapters
2. Right-click the adapter and choose Uninstall device
3. Tick Delete the driver software
4. Restart and let Windows reinstall it
5. Then install the official driver from your PC vendor

> [!WARNING]
> You will lose network access until the driver is reinstalled. Have Ethernet or a
> USB Wi-Fi dongle available in case the automatic install fails.

## Fix 6: Forget the Wi-Fi network

1. Settings > Network & internet > Wi-Fi > Manage known networks
2. Select your network and choose Forget
3. Reconnect and enter the password again

This clears a corrupted saved profile, which is a common cause of a network
that refuses to connect.

## Fix 7: Check the physical connection

For Ethernet:

- Reseat both ends of the cable until they click
- Try a different port on the router and on the PC
- Check the link lights are lit on both ends

For Wi-Fi:

- Move the router to a higher, open position
- Move away from microwaves, cordless phone bases and Bluetooth speakers
- Check how many walls are between the PC and router

Our [Wi-Fi signal guide](/articles/fix-wifi-signal-strength) covers this.

## Still broken?

- Turn off and on the Wi-Fi adapter in Device Manager
- Check that no VPN or metered connection is limiting you
- Try another browser, since a proxy set in one browser affects only that browser
- Check whether another security suite is installed alongside antivirus, since
  two firewalls conflict

If the network icon says "No internet access" but everything else works, run
`nslookup microsoft.com` in Command Prompt. An error there confirms DNS, while
a successful result points to a captive portal or a filter.
