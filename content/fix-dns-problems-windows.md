---
title: Fix DNS problems and change DNS servers
category: network
tags: [dns, network, ipconfig, dns servers, internet]
difficulty: easy
os_version: Windows 10/11
---

DNS translates website names into IP addresses. When DNS breaks, you can reach
a site by its numeric address but not by name.

## How to confirm it is DNS

In your browser, open:

```text
https://1.1.1.1
```

- **It loads**: your connection works and DNS is the problem
- **It does not load**: the connection itself is broken, so fix that first with
  the [no internet guide](/articles/fix-no-internet-windows)

You can also run this in Command Prompt:

```text
nslookup microsoft.com
```

An error such as "Non-existent domain" confirms a DNS problem.

## Fix 1: Flush the cache

Open Command Prompt as Administrator and run:

```text
ipconfig /flushdns
```

This clears cached name lookups so your computer resolves them again. It is
harmless and fixes a surprising share of problems.

## Fix 2: Renew your connection

```text
ipconfig /release
```

```text
ipconfig /renew
```

This returns your IP address to the router and requests a fresh one, which
sometimes picks up updated DNS settings.

## Fix 3: Change your DNS servers

Good public resolvers, in order of preference:

| Provider | Primary | Secondary |
| --- | --- | --- |
| Cloudflare | `1.1.1.1` | `1.0.0.1` |
| Google | `8.8.8.8` | `8.8.4.4` |
| Quad9 | `9.9.9.9` | `149.112.112.112` |
| OpenDNS | `208.67.222.222` | `208.67.220.220` |

To change them:

1. Settings > Network & internet > Wi-Fi or Ethernet
2. Click Properties on your connection
3. Under DNS server assignment choose Edit
4. Switch it to Manual
5. Enter the addresses above, then Save
6. Run `ipconfig /flushdns` again

Turn the Wi-Fi adapter off and on afterwards if changes do not take effect.

> [!IMPORTANT]
> Workplace and school networks usually supply their own DNS and block external
> resolvers. Ask your administrator before changing it there.

> [!TIP]
> Quad9 and Cloudflare both filter known malicious domains, so they are worth
> preferring on a machine that visits unfamiliar sites.

## Fix 4: Remove conflicting DNS software

Programs that filter or redirect DNS cause conflicts:

- VPN clients
- Ad blockers and privacy tools
- Third-party firewalls
- "Network accelerator" utilities
- Older antivirus suites with DNS filtering

Temporarily uninstall one at a time and test.

## Fix 5: Reset the Winsock catalog

DNS sits on top of Winsock, so a corrupted catalog breaks it:

```text
netsh winsock reset
```

```text
netsh int ip reset
```

Restart afterwards. Your VPN software may need reinstalling.

## Fix 6: Change DNS through Command Prompt

You can also set DNS with netsh, which is useful for a specific adapter:

```text
netsh interface ipv4 set dnsservers name="Wi-Fi" source=static address=1.1.1.1 primary
```

```text
netsh interface ipv4 add dnsservers name="Wi-Fi" address=1.0.0.1 index=2
```

To return to automatic:

```text
netsh interface ipv4 set dnsservers name="Wi-Fi" source=dhcp
```

> [!WARNING]
> These commands change DNS permanently for that adapter. To undo them, use the
> `source=dhcp` command above.

## Use our tools to check

- [DNS lookup](/tools/dns) resolves a hostname and shows the returned records
- [HTTP status check](/tools/http) confirms a site actually responds
- [Latency test](/tools/latency) shows whether DNS resolution is unusually slow

## Related

- [Fix no internet on Windows](/articles/fix-no-internet-windows)
- [Fix router lights and offline mode](/articles/fix-router-lights-offline)
- [Wi-Fi driver problems](/articles/fix-wifi-driver-windows-11)
