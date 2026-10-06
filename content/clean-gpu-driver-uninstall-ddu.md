---
title: Clean GPU driver uninstall with DDU
category: drivers
tags: [gpu, nvidia, amd, ddu, driver, clean install, display]
difficulty: moderate
os_version: Windows 10/11
featured: true
---

Windows driver removal is unreliable. Files are left behind, and Windows may
reinstall a different version. DDU removes graphics drivers properly.

## When to use DDU

- Device Manager shows Code 43 or Code 10 on your graphics card
- You are switching between NVIDIA and AMD
- Crashes that survived a normal driver reinstall
- [VIDEO_TDR_FAILURE](/bsod) or
  [VIDEO_DXGKRNL_FATAL_ERROR](/bsod) keep returning
- A driver install ends with "the best version is already installed" when you
  know it is not

## Before you start

1. **Download your new driver now**, so you have it ready
2. **Note your GPU model** from Device Manager, so you know which to download
3. **Run our [system report script](/scripts/system-report)** first, so you can
   compare driver versions afterwards

> [!WARNING]
> After DDU you will run on the basic Windows display driver, which is slow and
> does not support most features. Have the new installer downloaded before you
> start.

## Step 1: Get DDU

Download Display Driver Uninstaller from
[guru3d.com/display-driver-uninstaller](https://www.guru3d.com/download/display-driver-uninstaller-download/).
It is the standard tool for this job and is free.

> [!WARNING]
> Only download it from Guru3D. Copies bundled with "driver packs" are a common
> malware delivery method.

## Step 2: Create a restore point

Search for "create a restore point" in the Start menu and make one. If
something goes wrong, you can roll back.

## Step 3: Boot into Safe Mode

Press Windows key plus X, then Restart. If it boots normally, interrupt the
boot three times and choose Start your PC in Safe mode.

Safe Mode uses the basic display driver, which is what makes a clean removal
possible.

## Step 4: Run DDU

1. Extract DDU to a folder on your desktop, not a network drive
2. Run Display Driver Uninstaller as administrator
3. Choose the device type: GPU
4. Choose the vendor: NVIDIA or AMD, whichever you have
5. Click Clean and restart
6. Wait for the computer to restart, which Windows does automatically

## Step 5: Install the new driver

1. Boot into Windows
2. Run the driver installer you downloaded
3. Choose Custom or Clean Install if offered
4. Reboot

> [!IMPORTANT]
> Never tick "Perform a clean installation" in the NVIDIA installer after using
> DDU. DDU already did the clean part, and the NVIDIA option can reinstall
> everything DDU removed.

## Disable Windows Update driver replacement

Otherwise Windows will silently replace your working driver with an older one.

1. Settings > Windows Update > Advanced options
2. Choose Optional updates
3. Under Driver updates, choose Pause updates

Leave it paused. Install drivers from your PC vendor or the GPU vendor instead.

## Stop the vendor's automatic driver installs

**NVIDIA:** open GeForce Experience, choose Settings > Account, and turn off
Driver Downloads. Turn off the overlay in Settings > In-game overlay.

**AMD:** open Adrenalin Edition, check for updates automatically, and turn off
the overlay. AMD also installs an automatic driver service, which you can
disable.

> [!WARNING]
> Do not uninstall the vendor's control panel entirely unless you have a reason.
> It is useful for recording and frame limiting. Just disable its automatic driver
> downloads.

## If DDU cannot run

- Safe Mode is required. If Windows will not boot into Safe Mode, you can run
  DDU in regular mode, but the result is less reliable
- A pending update may install a driver while you work, so finish or cancel it
  first
- Some RGB or fan control software reinstalls the graphics driver. Uninstall it
  before using DDU

## When to use a clean install instead

For most driver problems, a clean install from within the vendor's installer is
enough. Reach for DDU when:

- A clean install does not fix it
- You are switching GPU vendors
- You see Code 43 or Code 10
- Crashes persist across several driver versions

## Related stop codes

- [VIDEO_TDR_FAILURE](/bsod)
- [VIDEO_TDR_TIMEOUT_DETECTED](/bsod)
- [VIDEO_DXGKRNL_FATAL_ERROR](/bsod)
- [VIDEO_DRIVER_INIT_FAILURE](/bsod)
- [THREAD_STUCK_IN_DEVICE_DRIVER](/bsod)

## Related

- [NVIDIA driver guide](/articles/nvidia-driver-guide)
- [AMD driver guide](/articles/amd-driver-guide)
- [Intel driver guide](/articles/intel-driver-guide)
- [Black screen or no display](/articles/fix-black-screen-no-display)
