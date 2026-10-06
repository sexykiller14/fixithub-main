---
title: Black screen or no display on Windows
category: hardware
tags: [display, black screen, gpu, monitor, driver, no signal]
difficulty: easy
os_version: Windows 10/11
featured: true
---

This covers a PC that powers on but shows nothing. Work through in order,
because the cheapest fixes are at the top.

## Step 1: Rule out the monitor and cable

This is free and resolves more cases than anything else.

- Swap the video cable for a known-good one
- Try a different port on the monitor and select it in the monitor's input menu
- Check the monitor's power LED, which should be steady, not orange
- Test the monitor with a laptop to confirm the panel works

> [!IMPORTANT]
> Many monitors do not detect inputs automatically. If the screen says "No
> signal" but the PC is clearly running, press the buttons on the monitor and
> select the correct input manually.

## Step 2: Choose the right output

Check where the cable is plugged in:

- **Desktop with a graphics card**: plug it into the card, not the motherboard
- **Monitor connected over HDMI with a TV**: select the TV as the output in
  Settings > System > Sound, or change it in Settings > System > Display

If the PC has a graphics card and the CPU has integrated graphics, move the
cable to the motherboard's video output. If the display appears, the graphics
card, its power cables or its slot are at fault.

## Step 3: Try Safe Mode

If the screen goes black after the Windows logo appears, the display driver is
the likely cause.

1. Interrupt the boot three times, choosing Start your PC in Safe mode
2. Once loaded, open Device Manager and expand Display adapters
3. Right-click the adapter and choose Uninstall device, ticking Delete the
   driver software
4. Restart, then install the official driver from your PC vendor

For a stubborn fault, do a clean install in Safe Mode using our
[DDU guide](/articles/clean-gpu-driver-uninstall-ddu).

> [!WARNING]
> After removing the GPU driver you will run on a basic display driver until you
> install the real one. Download the installer first so you are not left without
> a working display driver.

## Step 4: Laptop-specific checks

- Press the brightness keys, since some laptops black out the internal panel
- Use Win plus P to choose the right display, since video sometimes goes to an
  external output
- Check Settings > System > Display for Dynamic brightness, which can black out
  a very bright panel
- Connect an external monitor. If it works, the panel, its cable or its backlight
  has failed

> [!TIP]
> Shine a torch close to a black laptop screen. If you can faintly see an image,
> the panel works and the backlight has failed. Backlight repairs are usually far
> cheaper than a new motherboard.

## Step 5: Check the graphics card is powered

Most modern graphics cards need two or three 8-pin power connectors. A card
running on slot power alone may produce no display or shut down under load.

- Reseat the card in its slot, with the PCIe latch open
- Push every power connector fully in until it clicks
- Confirm the PSU has adequate wattage

Never force the card into a slot. If it does not seat easily, something is
misaligned.

## Step 6: Reset the graphics hardware state

- Press Windows key plus Ctrl plus Shift plus B, which resets the graphics driver
- Restart
- In Safe Mode, reset the GPU to stock clocks, since some tools apply an
  overclock at startup that prevents boot

## Step 7: Disable problematic software

Turn off these one at a time and test:

- Hardware-accelerated GPU scheduling, in Settings > System > Display > Graphics
- Overlays from Discord, GeForce Experience, Xbox Game Bar and Steam
- Screen recorders and background wallpaper apps
- Hardware-accelerated video in your browser

## Stop codes related to this

If you get a blue screen rather than a plain black screen, look it up:

- [VIDEO_TDR_FAILURE](/bsod) and its relatives are all graphics-driver related
- [VIDEO_DXGKRNL_FATAL_ERROR](/bsod) points at the same area
- [VIDEO_DRIVER_INIT_FAILURE](/bsod) happens when the driver fails at startup

## When to see a technician

See a professional if:

- The display is black with a fresh driver at stock clocks
- The card fails in another PC or another slot
- A laptop's internal screen stays black with a working external monitor
- You see POST codes or hear beeps after a clean install

These point to failing graphics hardware, which no driver fixes.
