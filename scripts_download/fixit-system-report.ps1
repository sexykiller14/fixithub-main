# ===========================================================================
# FixIT Hub - Collect system info report
#
# WHAT THIS DOES
#   Writes a plain text report to your Desktop covering your hardware, Windows
#   version, installed drivers, drive health and recent critical errors from
#   the Event Log.
#
# WHEN TO USE IT
#   - Before asking someone for help, so they have the details they need
#   - Recording driver versions before and after making a change
#   - Capturing what happened just before a crash
#
# WHAT IT CHANGES
#   Nothing. This script only reads information. It makes no changes to any
#   setting, and installs nothing.
#
# TO RUN
#   Open PowerShell as Administrator (more detail is collected) and run:
#     .\fixit-system-report.ps1
#
#   If PowerShell blocks the script, run this once in the same window first:
#     Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#
# PRIVACY
#   The report contains your computer name, Windows user name, hardware serial
#   numbers and a list of installed software. Read it before sharing it.
#   Delete it when you are finished.
# ===========================================================================

#Requires -Version 5.1
$ErrorActionPreference = 'SilentlyContinue'

$reportPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'fixit-system-report.txt'

function Write-Section {
    param(
        [string]$Title,
        [scriptblock]$Body
    )
    Add-Content -Path $reportPath -Value ''
    Add-Content -Path $reportPath -Value ('=' * 70)
    Add-Content -Path $reportPath -Value "  $Title"
    Add-Content -Path $reportPath -Value ('=' * 70)
    # The body writes directly to the report file, so failures inside it do not
    # stop the rest of the report from being generated.
    & $Body
}

Write-Host 'FixIT Hub - Collecting system report' -ForegroundColor Green
Write-Host 'This reads information only and changes nothing.'
Write-Host "Report will be saved to: $reportPath"
Write-Host ''

$header = @"
FixIT Hub system report
Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Computer:  $env:COMPUTERNAME
User:      $env:USERNAME
"@

Set-Content -Path $reportPath -Value $header -Encoding UTF8

Write-Section 'WINDOWS VERSION AND INSTALLED UPDATES' {
    Get-ComputerInfo |
        Select-Object WindowsProductName, WindowsVersion, OsBuildNumber, OsArchitecture,
                    OsLastBootUpTime, CsTotalPhysicalMemory, CsNumberOfLogicalProcessors |
        Format-List
    Get-HotFix |
        Sort-Object InstalledOn -Descending |
        Select-Object -First 10 HotFixID, InstalledOn |
        Format-Table -AutoSize
}

Write-Section 'PROCESSOR' {
    # Reads CPU details straight from the hardware.
    Get-CimInstance Win32_Processor |
        Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed,
                      CurrentClockSpeed |
        Format-List
}

Write-Section 'MEMORY MODULES' {
    # Lists each installed RAM stick, including its speed and capacity.
    Get-CimInstance Win32_PhysicalMemory |
        Select-Object BankLabel, DeviceLocator,
                      @{Name='CapacityGB'; Expression={[math]::Round($_.Capacity / 1GB, 1)}},
                      Speed, ConfiguredClockSpeed, Manufacturer, PartNumber |
        Format-Table -AutoSize
}

Write-Section 'DRIVES AND VOLUMES' {
    # MediaType tells you whether a drive is an SSD or a mechanical drive.
    Get-CimInstance Win32_DiskDrive |
        Select-Object Model, InterfaceType,
                      @{Name='SizeGB'; Expression={[math]::Round($_.Size / 1GB, 1)}},
                      Status |
        Format-Table -AutoSize

    Get-Volume |
        Select-Object DriveLetter, FileSystemLabel, FileSystem, HealthStatus,
                      @{Name='SizeGB'; Expression={[math]::Round($_.Size / 1GB, 1)}},
                      @{Name='FreeGB'; Expression={[math]::Round($_.SizeRemaining / 1GB, 1)}} |
        Sort-Object DriveLetter |
        Format-Table -AutoSize
}

Write-Section 'DRIVE HEALTH (SMART COUNTERS)' {
    # Reallocated, pending and uncorrectable sectors should all be zero.
    # On an SSD, check PercentageUsed: 0% is new, 100% is end of rated life.
    Write-Output 'Available only on some drives, and usually needs Administrator.'
    Write-Output ''
    Get-PhysicalDisk |
        Select-Object DeviceId, FriendlyName, MediaType, BusType, HealthStatus, Size |
        Format-Table -AutoSize

    Get-PhysicalDisk |
        ForEach-Object {
            $disk = $_
            $counter = $disk | Get-StorageReliabilityCounter
            if ($counter) {
                Write-Output "--- $($disk.FriendlyName) ---"
                $counter |
                    Select-Object Temperature, Wear, PowerOnHours,
                                  ReadErrorsTotal, WriteErrorsTotal,
                                  ReadErrorsUncorrected, WriteErrorsUncorrected |
                    Format-List
            }
        }
}

Write-Section 'GRAPHICS AND NETWORK ADAPTERS' {
    Get-CimInstance Win32_VideoController |
        Select-Object Name, DriverVersion, DriverDate, AdapterRAM, Status |
        Format-List

    Get-CimInstance Win32_NetworkAdapter |
        Where-Object { $_.PhysicalAdapter -eq $true } |
        Select-Object Name, NetEnabled, MACAddress |
        Format-Table -AutoSize
}

Write-Section 'INSTALLED DRIVERS WITH PROBLEMS' {
    # Any device with a problem code is listed here. Record this output before
    # and after a driver change to confirm the problem was actually fixed.
    Get-CimInstance Win32_PnPEntity |
        Where-Object { $_.ConfigManagerErrorCode -ne 0 } |
        Select-Object Name, PNPClass, ConfigManagerErrorCode |
        Format-Table -AutoSize
}

Write-Section 'DISPLAY AND BOOT CRASH DETAILS' {
    # Bugcheck records show the stop code, its parameters and the driver that
    # was loaded at the time of the crash.
    Write-Output '--- Recent bugcheck (BSOD) events ---'
    Get-WinEvent -FilterHashtable @{ LogName = 'System'; Id = 1001 } -MaxEvents 10 |
        Select-Object TimeCreated, Message |
        Format-List

    Write-Output '--- Minidump files found ---'
    Get-ChildItem 'C:\Windows\Minidump\*.dmp' -ErrorAction SilentlyContinue |
        Select-Object Name, Length, LastWriteTime |
        Format-Table -AutoSize
}

Write-Section 'RECENT CRITICAL AND ERROR EVENTS (last 3 days)' {
    # Level 1 is critical and Level 2 is error. These are the entries worth
    # reading when something has gone wrong recently.
    Get-WinEvent -FilterHashtable @{ LogName = 'System'; Level = 1, 2; StartTime = (Get-Date).AddDays(-3) } -MaxEvents 40 |
        Select-Object TimeCreated, Id, ProviderName, LevelDisplayName, Message |
        Format-List
}

Write-Section 'MINIDUMP FILES ON DISK' {
    # Upload these on the FixIT Hub minidump analyzer to get the bugcheck code
    # and parameters explained.
    $dumps = Get-ChildItem 'C:\Windows\Minidump\*.dmp' -ErrorAction SilentlyContinue
    if ($dumps) {
        $dumps | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize
    }
    else {
        Write-Output 'No minidump files found.'
    }
}

Write-Section 'FULL DRIVER LIST' {
    # A long list, but it is how driver version mismatches get spotted.
    Get-CimInstance Win32_PnPSignedDriver |
        Select-Object DeviceName, DriverVersion, DriverDate, InfName |
        Sort-Object DeviceName |
        Format-Table -AutoSize
}

$footer = @"

==============================================================
END OF REPORT
Generated by FixIT Hub on $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')

This report contains your computer name, user name and hardware
serial numbers. Read it before sharing it with anyone.

Dump files can contain fragments of your filenames and file
contents. Treat them as private.
"@

Add-Content -Path $reportPath -Value $footer -Encoding UTF8

Write-Host ''
Write-Host 'Report saved to your Desktop:' -ForegroundColor Green
Write-Host "  $reportPath"
Write-Host ''
Write-Host 'Read the report before sharing it. It contains your computer'
Write-Host 'name, user name and hardware serial numbers.'
Write-Host ''
Start-Process notepad.exe -ArgumentList "`"$reportPath`""
