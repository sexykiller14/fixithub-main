---
title: Fix no sound on Windows
category: windows
tags: [audio, sound, volume, realtek, mute, bluetooth, speakers]
difficulty: easy
os_version: Windows 10/11
featured: true
---

Completely silent Windows has a short list of causes, and most are settings
rather than faults.

## Step 1: Confirm what is silent

1. Press Windows key plus I, then System > Sound
2. Use the Test button under Output

If the test sound plays, Windows and your audio device are fine and the problem
is per-application volume or a specific app. If it is silent too, the fault is
the device, its driver, or the physical connection.

## Step 2: Check volume and mute

These are separate controls and they multiply together:

- The main volume slider in Settings > System > Sound
- The speaker icon in the taskbar, which mutes
- The volume mixer, which has a slider per application
- The physical volume knob or buttons on your speakers or headset

The volume mixer is the most commonly missed. Browsers also have their own audio
settings, including per-tab mute.

## Step 3: Check the selected output device

Windows switches output automatically when you connect a monitor over HDMI, and
sometimes forgets to switch back.

1. Settings > System > Sound > Output
2. Choose your speakers or headphones
3. Test with the Test button

Bluetooth devices also need setting as the output after pairing.

## Step 4: Turn off enhancements

Audio enhancements, spatial sound and mono audio are features that can silence a
working device.

1. Settings > System > Sound, click your output device, then Device properties
2. Open the Enhancements tab and tick Disable all enhancements
3. Turn spatial sound off, or try Windows Sonic instead of the hardware option
4. In Device properties > Advanced, untick Allow applications to take exclusive
   control of this device

> [!IMPORTANT]
> Some professional audio software requires exclusive mode. If you use it,
> re-enable that afterwards.

## Step 5: Check Device Manager

1. Press Windows key plus X, then Device Manager
2. Expand Sound, video and game controllers

- **Yellow exclamation mark**: note the code in Properties > General and look it
  up in our [Device Manager error codes](/articles/windows-device-manager-error-codes)
- **Greyed out**: right-click and choose Enable device
- **Not listed at all**: check BIOS for onboard audio being disabled, and update
  BIOS firmware

## Step 6: Reinstall the audio driver

Realtek audio drivers are the most common failure.

1. Right-click the audio device in Device Manager
2. Choose Uninstall device and tick Delete the driver software
3. Restart and let Windows install a basic driver
4. Then install the official driver from your PC vendor, or from our
   [Realtek driver guide](/articles/realtek-audio-network-drivers)
5. Update chipset drivers as well, since the audio driver depends on them

> [!WARNING]
> You will have no sound until the driver is reinstalled. Download the installer
> before removing the driver.

> [!WARNING]
> Do not use driver updater software. It installs unsigned drivers that Windows
> may refuse, or that cause worse problems.

## Step 7: Check the connection

**Headphones or speakers with a cable:**

- Push the plug fully in until it clicks
- Wiggle it gently at the jack, since cutting out when moved means a worn
  connector
- Try another pair of headphones to rule out the cable
- Clean lint from the jack with a soft brush or compressed air
- Try another port

**Desktop speakers:** use the green line-out port, not the pink microphone port.
If your graphics card has its own audio ports, use those instead.

**Wireless:** confirm the headset is the selected output, and check its own
battery and volume.

## Step 8: Fix crackling and distortion

1. Device properties > Advanced
2. Untick exclusive mode control
3. Set the default format to 16 bit, 44100 Hz as a compatible baseline
4. Turn off all enhancements

Sample rate mismatches cause crackling. If you work with video, try 24 bit,
48000 Hz instead.

## Step 9: Fix Bluetooth delay

1. Settings > Bluetooth & devices > Devices, then your headset's properties
2. Choose the higher-quality audio codec, such as aptX or AAC, rather than SBC
3. Switch between available codecs and test

Bluetooth always has some delay. For near-zero latency, use a 2.4 GHz dongle.

## Step 10: Laptop internal speakers

- Check the volume mixer, since the speakers can be muted separately
- Run the test sound with the lid open, since some laptops mute when closed
- Test with headphones. If they work, the speakers or their internal connector
  are at fault
- Move the laptop gently and listen for cutting, which indicates a loose
  connector

> [!WARNING]
> Opening a laptop to reseat an internal speaker connector risks damaging ribbon
> cables. It is a common and usually inexpensive repair, but use a repair centre
> if you are not confident.

## Related stop codes

- [BAD_SYSTEM_SERVICE_INFO](/bsod) often names an audio driver
- [ATTEMPTED_WRITE_TO_READONLY_MEMORY](/bsod) follows a badly written filter driver
- [DPC_WATCHDOG_VIOLATION](/bsod) sometimes names an audio driver

## Related

- [Realtek audio and network drivers](/articles/realtek-audio-network-drivers)
- [Device Manager error codes](/articles/windows-device-manager-error-codes)
- [Bluetooth problems](/articles/fix-bluetooth-windows-11)
