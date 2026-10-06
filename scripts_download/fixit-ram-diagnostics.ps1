# ===========================================================================
# FixIT Hub - RAM diagnostics (read-only)
#
# WHAT THIS DOES
#   Reports your memory layout, tells you whether an XMP or EXPO profile is
#   actually active, checks how the modules are paired across channels, and
#   reads any past memory test results and hardware error events.
#
#   It does NOT test your memory. It tells you what you have and what state it
#   is in, so you can read the right guide afterwards.
#
# WHY THAT MATTERS
#   The most common RAM problem is not a faulty stick. It is memory running at
#   its default speed instead of the rated speed, or modules paired into the
#   wrong slots so dual channel is disabled. This script shows which case you
#   are in.
#
# WHAT IT CHANGES
#   Nothing. Every command here only reads. No setting is modified, no test is
#   scheduled, and the machine is not restarted. You are shown the commands to
#   run yourself, with an explanation of each.
#
# TO RUN
#   Open PowerShell as Administrator and run:
#     .\fixit-ram-diagnostics.ps1
#
#   If PowerShell blocks the script, run this once in the same window first:
#     Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#
#   Administrator rights are needed for the Event Log. Everything else works
#   without them.
# ===========================================================================

#Requires -Version 5.1
$ErrorActionPreference = 'SilentlyContinue'

$reportPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'fixit-ram-diagnostics.txt'

function Write-Section {
    <#
        Runs a read-only block and captures both its console output and the
        rendered tables, so the report file matches what you see on screen.
    #>
    param(
        [string]$Title,
        [scriptblock]$Body
    )
    Write-Host ''
    Write-Host "  $Title" -ForegroundColor Cyan

    Add-Content -Path $reportPath -Value ''
    Add-Content -Path $reportPath -Value ('=' * 70)
    Add-Content -Path $reportPath -Value "  $Title"
    Add-Content -Path $reportPath -Value ('=' * 70)

    # Only the success stream is captured, which is why every table inside a
    # body ends with Out-String. Formatting records on other streams would be
    # written as type names instead of as a table.
    $captured = & $Body | ForEach-Object { $_.ToString() }

    if ($captured) {
        $captured | Add-Content -Path $reportPath
        foreach ($line in $captured) { Write-Host $line }
    }
    else {
        Add-Content -Path $reportPath -Value '(nothing reported on this system)'
        Write-Host '    (nothing reported on this system)' -ForegroundColor DarkGray
    }
}

function Write-Report {
    <#
        Renders a table to the report file and the console together, so the
        saved file always matches what you see. The built-in Format-Table
        cmdlet writes straight to the host, which would leave the report
        empty, so tables are rendered with Out-String first.
    #>
    param(
        [Parameter(Mandatory, ValueFromPipeline)]
        $InputObject
    )
    begin {
        $collected = @()
    }
    process {
        $collected += @($InputObject)
    }
    end {
        if ($collected.Count -gt 0) {
            $text = $collected | Out-String -Width 200
        }
        else {
            $text = '(none)'
        }
        Add-Content -Path $reportPath -Value $text
        Write-Host $text
    }
}

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)

Write-Host ''
Write-Host 'FixIT Hub - RAM diagnostics' -ForegroundColor Green
Write-Host 'Read-only. Nothing is changed and nothing is restarted.' -ForegroundColor DarkGray
if (-not $isAdmin) {
    Write-Host 'Run as Administrator for the Event Log section.' -ForegroundColor Yellow
}
Write-Host "Report will be saved to: $reportPath"
Write-Host ''

$header = @"
FixIT Hub RAM diagnostics report
Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Computer:  $env:COMPUTERNAME
Administrator: $isAdmin

This report is READ-ONLY. No setting was modified and no test was run.
"@

Set-Content -Path $reportPath -Value $header -Encoding UTF8

# ---------------------------------------------------------------------------
# Memory modules
# ---------------------------------------------------------------------------
Write-Section 'MEMORY MODULES' {
    $modules = @(Get-CimInstance Win32_PhysicalMemory | Sort-Object DeviceLocator)

    if (-not $modules) {
        Write-Output 'No memory modules were reported. That usually means this machine'
        Write-Output 'reports its memory through a different interface.'
        return
    }

    $modules |
        Select-Object DeviceLocator,
                      @{Name = 'CapacityGB'; Expression = { [math]::Round($_.Capacity / 1GB, 1) } },
                      Speed,
                      ConfiguredClockSpeed,
                      Manufacturer,
                      PartNumber,
                      SerialNumber |
        Write-Report

    $totalGB = [math]::Round((($modules | Measure-Object Capacity -Sum).Sum) / 1GB, 1)
    Write-Output "Total installed: $totalGB GB across $($modules.Count) module(s)"
}

# ---------------------------------------------------------------------------
# XMP / EXPO state
# ---------------------------------------------------------------------------
Write-Section 'XMP OR EXPO PROFILE STATUS' {
    $modules = @(Get-CimInstance Win32_PhysicalMemory)

    # Speed is what the module is rated at. ConfiguredClockSpeed is what the
    # firmware is actually running it at right now.
    #
    # When an XMP or EXPO profile is NOT enabled, the memory runs at its JEDEC
    # default and Windows reports ConfiguredClockSpeed as empty, even though
    # Speed still shows the much higher rated figure. That difference is the
    # single most useful thing this script can tell you.
    $rows = @($modules | ForEach-Object {
        $rated = $_.Speed
        $running = $_.ConfiguredClockSpeed

        if (-not $running -or $running -eq 0) {
            $state = 'NOT ACTIVE'
        }
        elseif ($rated -and $running -eq $rated) {
            $state = 'active at rated speed'
        }
        else {
            $state = 'active below rated speed'
        }

        [PSCustomObject]@{
            Slot    = $_.DeviceLocator
            Rated   = $rated
            Running = if ($running) { $running } else { '(none reported)' }
            Profile = $state
        }
    })

    $rows | Write-Report

    $notRunning = @($modules | Where-Object { -not $_.ConfiguredClockSpeed -or $_.ConfiguredClockSpeed -eq 0 })
    $throttled = @($modules | Where-Object {
        $_.ConfiguredClockSpeed -and $_.Speed -and $_.ConfiguredClockSpeed -ne $_.Speed
    })

    Write-Output ''
    if ($notRunning.Count -gt 0) {
        Write-Output 'VERDICT: A rated speed is reported but no configured speed is, which means'
        Write-Output 'an XMP or EXPO profile is not enabled. Your memory is running at its slower'
        Write-Output 'default speed. That is not a fault on its own, but if you have enabled the'
        Write-Output 'profile and the machine is unstable, this is the first thing to check. See'
        Write-Output 'the RAM stability guide.'
    }
    elseif ($throttled.Count -gt 0) {
        Write-Output 'VERDICT: Memory is running below its rated speed. This is expected when modules'
        Write-Output 'of different speeds are mixed: the whole group runs at the slowest common speed.'
    }
    else {
        Write-Output 'VERDICT: Every module reports a configured speed matching its rating.'
        Write-Output 'If the machine still crashes, XMP or EXPO timings are the next thing to suspect,'
        Write-Output 'because a profile can be active and still be unstable.'
    }
}

# ---------------------------------------------------------------------------
# Channel pairing
# ---------------------------------------------------------------------------
Write-Section 'CHANNEL PAIRING AND DUAL CHANNEL' {
    $modules = @(Get-CimInstance Win32_PhysicalMemory)
    $array = Get-CimInstance Win32_PhysicalMemoryArray | Select-Object -First 1

    if ($array) {
        # MaxCapacityEx is reported in kilobytes.
        $maxGB = [math]::Round($array.MaxCapacityEx / 1MB, 0)
        Write-Output "Board reports $($array.MemoryDevices) memory slot(s), maximum $maxGB GB"
        Write-Output ''
    }

    if ($modules.Count -lt 2) {
        Write-Output 'VERDICT: Only one module is installed. Dual channel needs a matched pair in'
        Write-Output 'the correct two slots, so memory bandwidth is currently halved.'
        return
    }

    # Pull the channel out of the slot name, for example ChannelA-DIMM1.
    $rows = @($modules | ForEach-Object {
        $channel = 'unknown'
        if ($_.DeviceLocator -match 'Channel([A-Z])') { $channel = "Channel $($Matches[1])" }
        else { $channel = $_.DeviceLocator }

        [PSCustomObject]@{
            Slot    = $_.DeviceLocator
            Channel = $channel
            GB      = [math]::Round($_.Capacity / 1GB, 1)
            Speed   = $_.Speed
            Part    = $_.PartNumber
        }
    })

    $rows | Write-Report

    $channels = @($modules | ForEach-Object {
        if ($_.DeviceLocator -match 'Channel([A-Z])') { $Matches[1] } else { $_.DeviceLocator }
    } | Sort-Object -Unique)

    $parts = @($modules | Select-Object -ExpandProperty PartNumber -Unique)

    Write-Output ''
    if ($channels.Count -lt 2) {
        Write-Output 'VERDICT: Both modules report the same channel, so dual channel is NOT active.'
        Write-Output 'Move one module to the slot in the other channel. On most boards that is the'
        Write-Output 'third or fourth slot, not the two nearest the CPU. Your board manual lists the'
        Write-Output 'correct pair.'
    }
    elseif ($parts.Count -gt 1) {
        Write-Output 'VERDICT: The modules sit on separate channels but are not the same part number.'
        Write-Output 'They will run at the slowest common speed, and mixing kits can prevent dual'
        Write-Output 'channel entirely on some boards. A matched pair performs better.'
    }
    else {
        Write-Output 'VERDICT: The modules are a matched pair across two channels, which is the'
        Write-Output 'arrangement you want for dual channel.'
    }
}

# ---------------------------------------------------------------------------
# Slot usage
# ---------------------------------------------------------------------------
Write-Section 'SLOT USAGE' {
    $modules = @(Get-CimInstance Win32_PhysicalMemory)
    $array = Get-CimInstance Win32_PhysicalMemoryArray | Select-Object -First 1

    if (-not $array) {
        Write-Output 'Slot count not reported by firmware.'
        return
    }

    $total = $array.MemoryDevices
    $used = $modules.Count
    $free = $total - $used

    Write-Output "Slots reported: $total"
    Write-Output "Slots in use:  $used"
    Write-Output "Slots free:    $free"
    Write-Output ''

    if ($free -gt 0) {
        Write-Output 'There is room to add memory. A matched kit of two identical modules per'
        Write-Output 'channel gives the best result. Adding one stick on its own leaves that'
        Write-Output 'channel single and gains less bandwidth.'
    }
    else {
        Write-Output 'Every slot is occupied. A further upgrade means replacing the modules.'
    }

    if ($modules.Count -eq 1 -and $free -ge 1) {
        Write-Output ''
        Write-Output 'VERDICT: You have one module in one slot and a free slot. Adding a second'
        Write-Output 'module in the matching channel slot would enable dual channel, which'
        Write-Output 'noticeably improves performance in games and video work.'
    }
}

# ---------------------------------------------------------------------------
# System view
# ---------------------------------------------------------------------------
Write-Section 'WINDOWS VIEW OF MEMORY' {
    $os = Get-CimInstance Win32_OperatingSystem
    $cs = Get-CimInstance Win32_ComputerSystem

    $totalGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
    $freeGB = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
    $usedGB = [math]::Round($totalGB - $freeGB, 1)
    $percent = if ($totalGB -gt 0) { [math]::Round($usedGB / $totalGB * 100) } else { 0 }

    Write-Output "Total physical memory: $totalGB GB"
    Write-Output "Currently free:          $freeGB GB"
    Write-Output "Currently in use:         $usedGB GB ($percent%)"
    Write-Output "Page file allocated:     $($os.SizeStoredInPagingFiles) KB"
    Write-Output ''

    Write-Output 'Sustained memory use above 85 percent means Windows is constantly paging to disk,'
    Write-Output 'which makes everything feel slow. That is a capacity problem, not a fault: add'
    Write-Output 'memory, or close applications.'
}

# ---------------------------------------------------------------------------
# Past test results
# ---------------------------------------------------------------------------
Write-Section 'PREVIOUS MEMORY TEST RESULTS' {
    $results = @(Get-WinEvent -FilterHashtable @{
        LogName       = 'System'
        ProviderName  = 'Microsoft-Windows-MemoryDiagnostics-Results'
    } -MaxEvents 5)

    if ($results) {
        foreach ($event in $results) {
            Write-Output "--- $($event.TimeCreated) ---"
            Write-Output $event.Message
            Write-Output ''
        }
    }
    else {
        Write-Output 'No Windows Memory Diagnostic results were found.'
        Write-Output ''
        Write-Output 'Either it has never been run, or this machine logs its results'
        Write-Output 'somewhere else. The commands to run it are in the next section.'
    }
}

# ---------------------------------------------------------------------------
# Hardware error events
# ---------------------------------------------------------------------------
Write-Section 'MEMORY AND HARDWARE ERROR EVENTS (last 30 days)' {
    if (-not $isAdmin) {
        Write-Output 'Skipped: reading the System Event Log requires Administrator rights.'
        return
    }

    $start = (Get-Date).AddDays(-30)

    # Source 17 is WHEA-Logger, which reports CPU, memory and PCIe hardware
    # faults. These events are worth reading before blaming a RAM module,
    # because they can point at the CPU or the board instead.
    $whea = @(Get-WinEvent -FilterHashtable @{
        LogName       = 'System'
        ProviderName  = 'Microsoft-Windows-WHEA-Logger'
        StartTime     = $start
    } -MaxEvents 15)

    if ($whea) {
        Write-Output "Found $($whea.Count) WHEA hardware event(s)."
        Write-Output ''
        foreach ($event in $whea) {
            Write-Output "--- $($event.TimeCreated) : event $($event.Id) ---"
            Write-Output (($event.Message -split "`n" | Select-Object -First 6) -join [Environment]::NewLine)
            Write-Output ''
        }
    }
    else {
        Write-Output 'No WHEA hardware errors in the last 30 days, which is good news. This rules'
        Write-Output 'out the most serious CPU, memory and PCIe faults.'
    }

    Write-Output ''
    Write-Output '--- Out-of-memory and resource exhaustion events ---'
    $exhaustion = @(Get-WinEvent -FilterHashtable @{
        LogName       = 'System'
        ProviderName  = 'Microsoft-Windows-Resource-Exhaustion-Detector'
        StartTime     = $start
    } -MaxEvents 10)

    if ($exhaustion) {
        foreach ($event in $exhaustion) {
            Write-Output "--- $($event.TimeCreated) : event $($event.Id) ---"
            Write-Output $event.Message
            Write-Output ''
        }
    }
    else {
        Write-Output 'No out-of-memory events found.'
    }
}

# ---------------------------------------------------------------------------
# What to run next
# ---------------------------------------------------------------------------
Write-Section 'HOW TO ACTUALLY TEST YOUR MEMORY' {
    Add-Content -Path $reportPath -Value @'
This script only reports. To test the memory itself, run one of these.

1. WINDOWS MEMORY DIAGNOSTIC (built in, quick, incomplete)

   Press Windows key + R, type mdsched.exe, press Enter.
   Choose "Restart now" or "Schedule for later".

   It restarts the machine and tests memory before Windows loads.
   This is a weak test: it often passes faulty memory. A clean result here is
   not proof your RAM is good.

2. MEMTEST86 (recommended, thorough, takes hours)

   Download from memtest86.com and boot from a USB drive.
   Run at least two full passes.

   ONE ERROR IS A FAILURE. Not a few errors, not one error occasionally.
   Memory either passes or it does not. A full pass on 8 GB takes 1-2 hours,
   so run it overnight.

WHAT TO DO WITH THE RESULT

   Any error at all
      -> replace the module. Test one stick at a time, in each slot, to
         identify which one. The RAM testing guide has that procedure.

   No errors, but the machine still crashes
      -> the memory is probably not defective. Check the XMP or EXPO section
         above first, then confirm dual channel is active. Unstable timings
         cause crashes that a memory test does not detect, because every
         access is technically valid.

BACKUP REMINDER

   If you have a failing drive, back up before running any memory test that
   involves restarting. A drive that is failing can become unreadable at any
   moment, and a test restart is one more opportunity for it to fail.

This report contains your computer name and memory serial numbers. Read it
before sharing it with anyone.
'@
    Write-Output 'See the end of this report for the commands to run a real memory test,'
    Write-Output 'and what each result means.'
}

Write-Host ''
Write-Host 'RAM report saved to your Desktop:' -ForegroundColor Green
Write-Host "  $reportPath"
Write-Host ''
Write-Host 'This report describes your memory setup. It did not test it.'
Write-Host 'The commands to run a real test are at the end of the report,'
Write-Host 'with an explanation of each.'
Write-Host ''
Start-Process notepad.exe -ArgumentList "`"$reportPath`""
