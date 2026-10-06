# ===========================================================================
# FixIT Hub - System file repair
#
# WHAT THIS DOES
#   Repairs the Windows component store and protected system files using the
#   Microsoft-supported tools DISM and SFC, run in the correct order.
#
# WHEN TO USE IT
#   - Many different Windows errors that do not have another explanation
#   - System files damaged by an interrupted update or a failed antivirus scan
#   - Before a larger repair such as an in-place upgrade
#
# WHAT IT CHANGES
#   Yes. DISM downloads replacement files from Windows Update and reinstalls
#   them, and SFC replaces protected files that do not match known good copies.
#   This is a repair, not a scan.
#
# TO RUN
#   Open PowerShell as Administrator, then run:
#     .\fixit-system-file-repair.ps1
#
#   If PowerShell blocks the script, run this once in the same window first:
#     Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#
# REVIEW FIRST
#   Read this file before running it. Nothing here is hidden.
# ===========================================================================

#Requires -Version 5.1
$ErrorActionPreference = 'Continue'

function Write-Step {
    param([string]$Message)
    Write-Host ''
    Write-Host '============================================' -ForegroundColor Cyan
    Write-Host "  $Message" -ForegroundColor Cyan
    Write-Host '============================================' -ForegroundColor Cyan
}

function Assert-Administrator {
    # Every command in this script needs administrator rights, so check first
    # and stop cleanly rather than failing halfway through.
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host 'ERROR: This script must be run as Administrator.' -ForegroundColor Red
        Write-Host 'Right-click PowerShell and choose "Run as administrator", then run it again.'
        exit 1
    }
}

Assert-Administrator

Write-Host ''
Write-Host 'FixIT Hub - System file repair' -ForegroundColor Green
Write-Host 'This can take 10 to 30 minutes. Do not close this window.'
Write-Host ''

Write-Step 'Step 1 of 4: Quick health check'
# CheckHealth reads a flag and finishes in under a minute. It tells us whether
# the component store is already known to be repairable.
DISM /Online /Cleanup-Image /CheckHealth

Write-Step 'Step 2 of 4: Scanning the component store'
# ScanHealth looks for corruption in detail. This is the slow diagnostic pass
# and it does not change anything.
DISM /Online /Cleanup-Image /ScanHealth

Write-Step 'Step 3 of 4: Restoring component store health'
# RestoreHealth is the step that actually repairs. It downloads good copies of
# damaged files from Windows Update and reinstalls them.
# It needs an internet connection and can take 20 minutes on a slow line.
DISM /Online /Cleanup-Image /RestoreHealth

Write-Step 'Step 4 of 4: Repairing protected system files'
# sfc must run AFTER DISM, because DISM repairs the source files that SFC needs
# to compare against. Running SFC first often reports failures DISM can fix.
sfc /scannow

Write-Host ''
Write-Host '============================================' -ForegroundColor Green
Write-Host '  Finished' -ForegroundColor Green
Write-Host '============================================' -ForegroundColor Green
Write-Host ''
Write-Host 'How to read the result:'
Write-Host '  sfc reported "did not find any integrity violations"'
Write-Host '    -> Your system files were already fine. Look elsewhere for the cause.'
Write-Host '  sfc reported "found corrupt files and successfully repaired them"'
Write-Host '    -> Reboot and see whether the problem is gone.'
Write-Host '  sfc reported "was unable to fix some of them"'
Write-Host '    -> Run this script a second time. Often the second pass succeeds,'
Write-Host '       because DISM needed to finish first.'
Write-Host ''
Write-Host 'If DISM said it could not repair the source files, see the full guide'
Write-Host 'for using installation media to repair Windows.'
Write-Host ''
Read-Host 'Press Enter to close'
