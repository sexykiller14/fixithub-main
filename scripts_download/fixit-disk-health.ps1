# ===========================================================================
# FixIT Hub - Disk health check (read-only)
#
# WHAT THIS DOES
#   Decodes the raw SMART attributes for every drive, gives each critical
#   attribute a plain-English verdict, compares against the previous run to show
#   whether bad-sector counts are climbing, and scans each volume for
#   filesystem errors without changing anything.
#
# WHY THE RAW ATTRIBUTES
#   Get-StorageReliabilityCounter reports a summary, but it does not always
#   expose reallocated, pending or uncorrectable sector counts, which are the
#   numbers that actually predict a drive failing. Those live in the raw SMART
#   attribute table, so this script reads both and cross-checks them.
#
# WHAT IT CHANGES
#   Nothing. Repair-Volume -Scan inspects and reports but does not repair, and
#   the SMART reads are pure queries. Your files are never written to.
#
#   The only file this creates is the report on your Desktop, so that you can
#   compare one run against the next.
#
# TO RUN
#   Open PowerShell as Administrator and run:
#     .\fixit-disk-health.ps1
#
#   If PowerShell blocks the script, run this once in the same window first:
#     Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#
#   Administrator rights are needed for the SMART counters and the volume scan.
# ===========================================================================

#Requires -Version 5.1
$ErrorActionPreference = 'SilentlyContinue'

$desktop = [Environment]::GetFolderPath('Desktop')
$reportPath = Join-Path $desktop 'fixit-disk-health.txt'
$historyPath = Join-Path $desktop 'fixit-disk-health-history.csv'

# SMART attribute IDs worth reading, with what they mean and how to read them.
#
# Direction says which way is healthy:
#   'low'  a low number is healthy, so error counters use this
#   'high' a high number is healthy, so remaining life percentages use this
#
# Pass and Warn are the two thresholds that matter. Anything past Warn is a
# FAIL. Because drives disagree about the exact meaning of some attributes,
# the thresholds here are deliberately generous on Pass and strict on Warn.
#
# Field is which part of the 12-byte entry holds the number:
#   'raw'      the six vendor data bytes, the actual count
#   'norm'     the normalised value the drive computed, 1 to 100
#   'info'     recorded but never given a verdict, because the number alone
#              means nothing without knowing how the drive has been used
$WatchedAttributes = @(
    @{ Id = 5;   Name = 'Reallocated sectors';       Dir = 'low';  Field = 'raw';  Pass = 0; Warn = 1
       Note = 'Sectors the drive could not use and marked bad. On an SSD a small steady number is normal; on a mechanical drive any count above zero is worth replacing.' }
    @{ Id = 196; Name = 'Reallocated event count';  Dir = 'low';  Field = 'raw';  Pass = 0; Warn = 10
       Note = 'How many times the drive ran out of spare sectors and had to move data. On an SSD this rises steadily and is normal; on a mechanical drive any value means remapping has started.' }
    @{ Id = 197; Name = 'Pending sectors';          Dir = 'low';  Field = 'raw';  Pass = 0; Warn = 1
       Note = 'Sectors awaiting remapping. Any value above zero means the drive is finding unreadable sectors right now.' }
    @{ Id = 198; Name = 'Uncorrectable sectors';    Dir = 'low';  Field = 'raw';  Pass = 0; Warn = 1
       Note = 'Sectors that failed error correction and the data is lost. This should always be zero.' }
    @{ Id = 199; Name = 'CRC uncorrectable errors'; Dir = 'low';  Field = 'raw';  Pass = 0; Warn = 1
       Note = 'Usually a cabling problem rather than the drive itself. Reseat the SATA or power cable before blaming the drive.' }
    @{ Id = 187; Name = 'Reported uncorrectable';   Dir = 'low';  Field = 'raw';  Pass = 0; Warn = 1
       Note = 'Uncorrectable errors reported through the interface, typically a cable or connector fault.' }
    @{ Id = 188; Name = 'Command timeout';          Dir = 'low';  Field = 'raw';  Pass = 0; Warn = 1
       Note = 'The drive failed to respond to a command in time. Above zero on a mechanical drive means it is struggling to spin up or seek.' }
    @{ Id = 184; Name = 'End-to-end data errors';   Dir = 'low';  Field = 'raw';  Pass = 0; Warn = 1
       Note = 'Errors detected while reading data back. Any non-zero value means data at the platter or cell level is wrong.' }
    @{ Id = 10;  Name = 'Spin retries';             Dir = 'low';  Field = 'raw';  Pass = 0; Warn = 1
       Note = 'Mechanical drives only. The drive failed to reach speed and retried. Above zero is a strong early warning of a failing motor or heads.' }
    @{ Id = 183; Name = 'Runtime bad blocks';       Dir = 'low';  Field = 'raw';  Pass = 0; Warn = 10
       Note = 'Mechanical drives only. Bad blocks are being remapped around. A rising count means the surface is degrading.' }
    # This is a normalised percentage on most drives, not a raw count. It is
    # recorded rather than graded because drives disagree on what it means.
    @{ Id = 190; Name = 'Airflow or head sticking'; Dir = 'info'; Field = 'norm'; Pass = 0; Warn = 0
       Note = 'Reported as a percentage rather than a raw count on most drives, and vendors disagree on whether it means temperature or head clearance. Recorded for context only.' }
    @{ Id = 194; Name = 'Temperature (Celsius)';    Dir = 'low';  Field = 'raw';  Pass = 50; Warn = 60
       Note = 'Operating temperature. Sustained readings above 55C shorten lifespan, especially in a drive bay with little airflow.' }
    # Hours are recorded but never failed on. A drive is not unhealthy at
    # 5,000 hours and a new one at 20,000, so any threshold would be a guess.
    # Age is worth knowing because it sets context for the error counters.
    @{ Id = 9;   Name = 'Power-on hours';           Dir = 'info'; Field = 'raw';  Pass = 0; Warn = 0
       Note = 'Total hours the drive has been powered. Recorded for context, not graded. Consumer mechanical drives often fail before 40,000 hours, but an SSD can run far longer without trouble.' }
    @{ Id = 231; Name = 'SSD life left (percent)';  Dir = 'high'; Field = 'raw';  Pass = 90; Warn = 80
       Note = 'Percentage of rated write life remaining. Treat this as a countdown to replacement.' }
    @{ Id = 233; Name = 'Media wear indicator';     Dir = 'high'; Field = 'raw';  Pass = 90; Warn = 80
       Note = 'Another vendor naming for SSD remaining life, using 100 for new.' }
    @{ Id = 202; Name = 'Percent lifetime used';    Dir = 'low';  Field = 'raw';  Pass = 20; Warn = 30
       Note = 'Percentage of rated write endurance consumed. The inverse of SSD life remaining.' }
    @{ Id = 241; Name = 'Total LBAs written';       Dir = 'info'; Field = 'raw';  Pass = 0; Warn = 0
       Note = 'Cumulative sectors written, recorded so you can work out write endurance. On its own it is not a pass or fail, because how much a drive can take depends entirely on its model.' }
    @{ Id = 235; Name = 'Wear levelling count';     Dir = 'info'; Field = 'raw';  Pass = 0; Warn = 0
       Note = 'Vendor specific wear metric. The meaning of the number changes between manufacturers, so it is recorded without a verdict.' }
)

function Write-Section {
    <#
        Runs a read-only block and captures its console output, including
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
    # body ends with Write-Report. Formatting records on other streams would be
    # written out as type names rather than as a table.
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
        Renders a table to the report file and the console together. The
        built-in Format-Table cmdlet writes straight to the host, which would
        leave the report file empty, so tables are rendered with Out-String.
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
        if ($collected.Count -gt 0) { $text = $collected | Out-String -Width 200 }
        else { $text = '(none)' }
        Add-Content -Path $reportPath -Value $text
        Write-Host $text
    }
}

function Get-SmartAttributes {
    <#
        Decodes the SMART attribute table for one physical disk.

        The table is a fixed 512-byte array. Bytes 0 and 1 are a revision
        number, then 30 twelve-byte entries follow. Each entry is laid out as:

            0      attribute ID
            1, 2   status flags
            3      normalised value the drive calculated, 1 to 100
            4      worst normalised value ever recorded
            5-10   six vendor data bytes, the actual reading
            11     reserved

        The six vendor data bytes are a little-endian number, so byte 5 is the
        least significant. Reading a single byte, or indexing by attribute ID
        instead of entry position, produces numbers that look plausible and are
        completely wrong, which is why this walks the table in order.
    #>
    param(
        [byte[]]$VendorSpecific
    )

    $results = @()

    # Attribute ID 0 marks an unused entry, so an empty table is common on
    # drives that only publish a handful of attributes.
    for ($slot = 0; $slot -lt 30; $slot++) {
        $base = 2 + ($slot * 12)
        if (($base + 12) -gt $VendorSpecific.Length) { break }

        $id = [int]$VendorSpecific[$base]
        if ($id -eq 0) { continue }

        $watched = $WatchedAttributes | Where-Object { $_.Id -eq $id } | Select-Object -First 1
        if (-not $watched) { continue }

        # The vendor bytes are little-endian, so the byte at offset 5 is the
        # least significant. Reading them in the other order turns 13966 hours
        # into 156362579378176, which still looks like a number and is wrong.
        [uint64]$rawValue = 0
        for ($byte = 5; $byte -ge 0; $byte--) {
            $rawValue = ($rawValue -shl 8) -bor [uint64]$VendorSpecific[$base + 5 + $byte]
        }

        $results += [PSCustomObject]@{
            Id      = $id
            Name    = $watched.Name
            Dir     = $watched.Dir
            Field   = $watched.Field
            Pass    = $watched.Pass
            Warn    = $watched.Warn
            Raw     = $rawValue
            Norm    = [int]$VendorSpecific[$base + 3]
            Worst   = [int]$VendorSpecific[$base + 4]
            Note    = $watched.Note
        }
    }

    return $results
}

function Get-Verdict {
    <#
        Grades one attribute using the direction its own definition declares.
        Counting errors are healthy at zero, while remaining life is healthy
        when high, so the caller states the direction rather than this function
        guessing from the attribute name.
    #>
    param(
        $Attribute
    )

    # The value to judge depends on the field. Most attributes carry the real
    # count in the vendor bytes, but a few are only meaningful as the
    # normalised value the drive computed for itself.
    if ($Attribute.Field -eq 'norm') { $value = $Attribute.Norm }
    else { $value = $Attribute.Raw }

    # Recorded but never graded, because the number means nothing on its own.
    if ($Attribute.Dir -eq 'info') { return 'INFO' }

    if ($Attribute.Dir -eq 'high') {
        if ($value -ge $Attribute.Pass) { return 'PASS' }
        if ($value -ge $Attribute.Warn) { return 'WARN' }
        return 'FAIL'
    }

    # Low is healthy. Pass and Warn are both ceilings here, so a value between
    # them is worth watching and anything above Warn is a failure.
    if ($value -le $Attribute.Pass) { return 'PASS' }
    if ($value -le $Attribute.Warn) { return 'WARN' }
    return 'FAIL'
}

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)

Write-Host ''
Write-Host 'FixIT Hub - Disk health check' -ForegroundColor Green
Write-Host 'Read-only. Nothing is repaired and nothing is written to your drives.' -ForegroundColor DarkGray
if (-not $isAdmin) {
    Write-Host 'Run as Administrator for SMART counters and the volume scan.' -ForegroundColor Yellow
}
Write-Host "Report will be saved to: $reportPath"
Write-Host ''

$header = @"
FixIT Hub disk health report
Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Computer:  $env:COMPUTERNAME
Administrator: $isAdmin

This report is READ-ONLY. No volume was repaired and no drive was modified.
"@

Set-Content -Path $reportPath -Value $header -Encoding UTF8

# Read the previous run so a trend can be reported.
$previous = @{}
if (Test-Path $historyPath) {
    try {
        Import-Csv -Path $historyPath | ForEach-Object {
            $key = "$($_.Disk)|$($_.AttributeId)"
            $previous[$key] = [int]$_.Value
        }
    }
    catch {
        Write-Verbose "Could not read the previous history file: $_"
    }
}

$historyRows = @()

# ---------------------------------------------------------------------------
# Physical drives
# ---------------------------------------------------------------------------
Write-Section 'PHYSICAL DRIVES' {
    $disks = @(Get-PhysicalDisk)

    if (-not $disks) {
        Write-Output 'No physical drives were reported.'
        return
    }

    $disks |
        Select-Object DeviceId, FriendlyName, MediaType, BusType, HealthStatus, OperationalStatus,
                      @{Name = 'SizeGB'; Expression = { [math]::Round($_.Size / 1GB, 1) }} |
        Write-Report

    Write-Output 'MediaType of HDD means a mechanical drive with spinning platters, which is'
    Write-Output 'considerably slower and more shock-sensitive than SSD.'
}

# ---------------------------------------------------------------------------
# SMART reliability counters
# ---------------------------------------------------------------------------
Write-Section 'SMART RELIABILITY COUNTERS (summary)' {
    $disks = @(Get-PhysicalDisk)
    if (-not $disks) { Write-Output 'No drives to read.'; return }

    foreach ($disk in $disks) {
        $counter = $disk | Get-StorageReliabilityCounter
        if (-not $counter) {
            Write-Output "--- $($disk.FriendlyName) ---"
            Write-Output 'No reliability counters exposed. Some drives and USB bridges'
            Write-Output 'do not provide them. Check the raw SMART table below, and use'
            Write-Output 'your drive vendor tool for a definitive answer.'
            Write-Output ''
            continue
        }

        Write-Output "--- $($disk.FriendlyName) ---"
        $counter |
            Select-Object Temperature, Wear, PowerOnHours,
                          ReadErrorsTotal, WriteErrorsTotal,
                          ReadErrorsUncorrected, WriteErrorsUncorrected |
            Write-Report
        Write-Output ''
    }
}

# ---------------------------------------------------------------------------
# Raw SMART attributes with verdicts
# ---------------------------------------------------------------------------
Write-Section 'RAW SMART ATTRIBUTES WITH VERDICTS' {
    $smartDevices = @(Get-CimInstance -Namespace 'root\wmi' -ClassName MSStorageDriver_FailurePredictData)
    $smartStatus = @(Get-CimInstance -Namespace 'root\wmi' -ClassName MSStorageDriver_FailurePredictStatus)

    if (-not $smartDevices) {
        Write-Output 'The raw SMART table is not available through WMI.'
        Write-Output ''
        Write-Output 'This normally means one of three things:'
        Write-Output '  - the drive is connected through a USB bridge, which hides SMART'
        Write-Output '  - the drive is NVMe, which uses a different attribute format'
        Write-Output '  - the machine is a VM, where no physical SMART data exists'
        Write-Output ''
        Write-Output 'For an NVMe drive, read Percentage Used, Media and Data Units'
        Write-Output 'Written in the summary section above instead.'
        return
    }

    foreach ($device in $smartDevices) {
        $name = $device.InstanceName -replace '^\\.*?\\', ''
        $status = $smartStatus | Where-Object { $_.InstanceName -eq $device.InstanceName } | Select-Object -First 1

        Write-Output "--- $name ---"

        if ($status) {
            if ($status.PredictFailure) {
                Write-Output "SMART self-assessment: PREDICT FAILURE. Replace this drive now."
            }
            else {
                Write-Output "SMART self-assessment: no failure predicted (Reason $($status.Reason))"
            }
        }

        $attributes = Get-SmartAttributes -VendorSpecific $device.VendorSpecific

        if (-not $attributes) {
            Write-Output 'This drive published a SMART table but none of the attributes'
            Write-Output 'this script knows how to interpret. That is normal for NVMe drives,'
            Write-Output 'which describe wear differently. Use the summary counters above.'
            Write-Output ''
            continue
        }

        $rows = @()
        foreach ($attribute in $attributes) {
            $verdict = Get-Verdict -Attribute $attribute

            $rows += [PSCustomObject]@{
                Attribute = $attribute.Name
                Id        = $attribute.Id
                Value     = $attribute.Raw
                Normalised = $attribute.Norm
                Verdict   = $verdict
            }

            $script:historyRows += [PSCustomObject]@{
                Run         = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
                Disk        = $name
                AttributeId = $attribute.Id
                Attribute   = $attribute.Name
                Dir         = $attribute.Dir
                Field       = $attribute.Field
                Value       = $attribute.Raw
                Normalised  = $attribute.Norm
                Verdict     = $verdict
            }
        }

        $rows | Write-Report

        Write-Output ''
        foreach ($attribute in $attributes) {
            Write-Output "$($attribute.Name) (id $($attribute.Id)):"
            Write-Output "  $($attribute.Note)"
        }
        Write-Output ''
    }
}

# ---------------------------------------------------------------------------
# Trend comparison
# ---------------------------------------------------------------------------
Write-Section 'CHANGE SINCE THE LAST RUN' {
    # An empty hashtable is still truthy in PowerShell, so the count has to be
    # checked rather than relying on -not, which would skip the first-run
    # message and claim every counter was unchanged.
    if ($previous.Count -eq 0) {
        Write-Output 'No previous run was found, so there is nothing to compare against yet.'
        Write-Output ''
        Write-Output 'Keep this report. Run the script again in a week or a month and this'
        Write-Output 'section will show which counters moved. Reallocated sectors that climb'
        Write-Output 'between runs are the earliest reliable sign that a drive is failing.'
        Write-Output ''
        Write-Output "History is kept in: $historyPath"
        return
    }

    $changes = @()
    $climbing = @()

    foreach ($row in $script:historyRows) {
        $key = "$($row.Disk)|$($row.AttributeId)"
        if (-not $previous.ContainsKey($key)) { continue }

        # Compare whichever field the verdict used, so a change in the graded
        # number is what gets reported rather than a change in a field the
        # report does not show.
        if ($row.Field -eq 'norm') { $now = [int64]$row.Normalised }
        else { $now = [int64]$row.Value }

        $before = $previous[$key]
        $delta = $now - $before

        if ($delta -eq 0) { continue }

        # Direction comes from the attribute definition, not from its name.
        # A rising error count is bad; a falling life percentage is bad. Values
        # recorded for information only are shown but never judged.
        if ($row.Dir -eq 'info') { $direction = 'recorded' }
        elseif ($row.Dir -eq 'high') { $direction = if ($delta -lt 0) { 'worse' } else { 'better' } }
        else { $direction = if ($delta -gt 0) { 'worse' } else { 'better' } }

        $changes += [PSCustomObject]@{
            Disk      = $row.Disk
            Attribute = $row.Attribute
            Previous  = $before
            Now       = $now
            Change    = if ($delta -gt 0) { "+$delta" } else { "$delta" }
            Direction = $direction
        }

        if ($direction -eq 'worse') { $climbing += $row.Attribute }
    }

    if (-not $changes) {
        Write-Output 'Every watched counter is unchanged since the last run.'
    }
    else {
        $changes | Write-Report
    }

    Write-Output ''
    if ($climbing) {
        $unique = $climbing | Sort-Object -Unique
        Write-Output "VERDICT: These counters moved in the wrong direction since the last run:"
        foreach ($attribute in $unique) { Write-Output "  - $attribute" }
        Write-Output ''
        Write-Output 'Error counters that rise are the clearest early warning that a drive is'
        Write-Output 'going to fail. Back up your files now, and plan to replace the drive rather'
        Write-Output 'than trying to repair it.'
    }
    else {
        Write-Output 'VERDICT: Nothing has moved in the wrong direction. That is the result you'
        Write-Output 'want to see. Keep the report and check again periodically.'
    }
}

# ---------------------------------------------------------------------------
# Volumes
# ---------------------------------------------------------------------------
Write-Section 'VOLUMES AND FREE SPACE' {
    $volumes = @(Get-Volume | Where-Object { $_.DriveLetter })

    if (-not $volumes) {
        Write-Output 'No volumes were reported.'
        return
    }

    $volumes |
        Select-Object DriveLetter, FileSystemLabel, FileSystem, DriveType, HealthStatus,
                      @{Name = 'SizeGB'; Expression = { [math]::Round($_.Size / 1GB, 1) }},
                      @{Name = 'FreeGB'; Expression = { [math]::Round($_.SizeRemaining / 1GB, 1) }},
                      @{Name = 'FreePercent'; Expression = {
                          if ($_.Size -gt 0) { [math]::Round($_.SizeRemaining / $_.Size * 100, 1) }
                          else { 0 } } },
                      @{Name = 'Verdict'; Expression = {
                          if ($_.Size -gt 0 -and ($_.SizeRemaining / $_.Size) -lt 0.10) { 'low space' }
                          else { 'ok' } } } |
        Sort-Object DriveLetter |
        Write-Report

    Write-Output 'Keep 15 to 20 percent free on the Windows drive. A nearly full system drive is'
    Write-Output 'slow and can cause Windows Update to fail.'
}

# ---------------------------------------------------------------------------
# Read-only filesystem scan
# ---------------------------------------------------------------------------
Write-Section 'READ-ONLY FILESYSTEM SCAN' {
    if (-not $isAdmin) {
        Write-Output 'Skipped: scanning volumes requires Administrator rights.'
        return
    }

    # Only fixed local volumes can carry a filesystem worth scanning. Optical
    # and removable drives refuse direct access, and counting that refusal as
    # a filesystem error would report a healthy machine as failing.
    $volumes = @(Get-Volume | Where-Object {
        $_.DriveLetter -and $_.DriveType -eq 'Fixed' -and $_.FileSystem -and $_.Size -gt 0
    })

    if (-not $volumes) {
        Write-Output 'No scannable volumes were found.'
        return
    }

    Write-Output "Scanning $($volumes.Count) fixed volume(s). On a large drive this takes"
    Write-Output 'several minutes per volume. The script appears to be doing nothing'
    Write-Output 'during that time, which is normal.'
    Write-Output ''

    $errorsFound = @()

    foreach ($volume in $volumes) {
        $letter = $volume.DriveLetter
        Write-Output "--- Scanning drive $letter`: ---"

        try {
            # -Scan inspects and reports. It deliberately does not repair, so
            # it cannot make a failing drive worse.
            $result = Repair-Volume -DriveLetter $letter -Scan -ErrorAction Stop
            if ($result) {
                $result | Select-Object DriveLetter, HealthStatus, OperationalStatus, FileSystemType |
                    Write-Report
            }
            Write-Output 'Scan completed. No errors were reported.'
        }
        catch {
            $errorsFound += "$letter`: $($_.Exception.Message)"
            Write-Output "The scan reported a problem:"
            Write-Output "  $($_.Exception.Message)"
            Write-Output ''
            Write-Output 'Back up this drive before attempting any repair.'
        }
        Write-Output ''
    }

    if ($errorsFound) {
        Write-Output 'VERDICT: At least one volume has filesystem errors. Back up before going'
        Write-Output 'further, then use the drive health guide.'
    }
}

# ---------------------------------------------------------------------------
# Disk related event log
# ---------------------------------------------------------------------------
Write-Section 'DISK AND STORAGE EVENTS (last 30 days)' {
    if (-not $isAdmin) {
        Write-Output 'Skipped: reading the System Event Log requires Administrator rights.'
        return
    }

    $start = (Get-Date).AddDays(-30)

    # Source 51 is disk, 153 is storage, 157 is surprise removal. All three mean
    # the storage stack had a problem worth reading before trusting the drive.
    $providers = @(
        'disk',
        'Ntfs',
        'Microsoft-Windows-StorPort',
        'Microsoft-Windows-StorDiag'
    )

    $found = 0
    foreach ($provider in $providers) {
        $events = @(Get-WinEvent -FilterHashtable @{
            LogName       = 'System'
            ProviderName  = $provider
            StartTime     = $start
            Level         = 1, 2, 3
        } -MaxEvents 10)

        if ($events) {
            $found += $events.Count
            Write-Output "--- $provider ---"
            foreach ($event in $events) {
                Write-Output "$($event.TimeCreated)  level $($event.LevelDisplayName)  event $($event.Id)"
                Write-Output (($event.Message -split "`n" | Select-Object -First 4) -join [Environment]::NewLine)
                Write-Output ''
            }
        }
    }

    if ($found -eq 0) {
        Write-Output 'No disk or storage warnings in the last 30 days, which is good.'
    }
    else {
        Write-Output "VERDICT: $found storage event(s) were logged. Event 51 from disk usually"
        Write-Output 'means Windows could not read part of the volume. Event 157 means a drive'
        Write-Output 'was removed unexpectedly, which is either a loose cable or a failing drive.'
    }
}

# ---------------------------------------------------------------------------
# How to read it
# ---------------------------------------------------------------------------
Write-Section 'HOW TO READ THIS REPORT' {
    Add-Content -Path $reportPath -Value @'
THE VERDICT COLUMN IS THE SHORT ANSWER

  PASS   the counter is within what a healthy drive shows
  WARN   worth watching, or the drive is ageing
  FAIL   this counter alone is reason to replace the drive
  INFO   recorded for context, not graded

  INFO is not a lesser PASS. Some counters, like total sectors written, have
  no single number that means healthy, because it depends entirely on which
  drive you own. They are shown so you can read the trend, and they never
  count as a failure.

THE COUNTERS THAT ACTUALLY PREDICT FAILURE

  Reallocated sectors    rising between runs is the earliest reliable warning
  Pending sectors        non-zero means unreadable sectors found right now
  Uncorrectable sectors  should be zero, always
  Command timeout        mechanical drives failing to respond in time
  Spin retries           mechanical drive struggling to reach speed
  SSD life left          below about 10 percent means the rated write life is gone

WHY A RISING COUNTER MATTERS MORE THAN A HIGH ONE

  Error counters are cumulative. A drive with 12 reallocated sectors that has
  had none for a year is in a different position from one with 12 that gained
  them this month. The second one is degrading now.

  That is what the change-since-last-run section is for. Keep this report and
  run the script again in a month. A counter that moves is more informative
  than a counter that is merely non-zero.

WHAT IS NOT WORTH WORRYING ABOUT

  Power-on hours on its own. A modern SSD can run for tens of thousands of
  hours without trouble. Hours matter much more for a mechanical drive.

  CRC errors, which usually mean a bad cable rather than a bad drive. Reseat
  the SATA or power cable and re-check before replacing anything.

  Sectors written. It looks alarming and means nothing on its own, which is
  why it is marked INFO rather than graded.

ABOUT YOUR DRIVE NOT BEING LISTED

  A USB drive, an NVMe drive, or any drive behind a bridge usually hides the
  SMART table. If the raw section says so, that is the drive refusing to
  report, not a fault in the drive. Your vendor's own tool can usually read
  what Windows cannot.

  The same applies inside a virtual machine, where there is no physical SMART
  data to read at all.

WHAT TO DO IF A DRIVE IS FAILING

  1. Back up your files now, onto different media.
  2. Replace the drive. Do not try to repair it into service.
  3. Do NOT run chkdsk with /f on it. Repair writes to the drive and can
     destroy data that is still recoverable.
  4. Check your other drives too. They fail from the same age and environment.

THIS REPORT IS READ-ONLY BY DESIGN

  Repair-Volume -Scan inspects and reports but does not repair, and every SMART
  read is a query. That is deliberate: when a drive is failing, the most
  valuable thing you can do is copy files off it, not write to it.

  It contains your computer name and drive serial numbers. Read it before
  sharing it with anyone.
'@
    Write-Output 'See the end of this report for how to read each verdict, and what to do'
    Write-Output 'if a drive is actually failing.'
}

# Save the history so the next run can show a trend.
if ($historyRows) {
    $historyRows | Export-Csv -Path $historyPath -NoTypeInformation -Encoding UTF8
}

Write-Host ''
Write-Host 'Disk health report saved to your Desktop:' -ForegroundColor Green
Write-Host "  $reportPath"
if ($historyRows) {
    Write-Host ''
    Write-Host 'Counter history saved for trend comparison:'
    Write-Host "  $historyPath"
}
Write-Host ''
Write-Host 'This script did not repair anything. If any counter shows FAIL, back up your'
Write-Host 'files before you take any other action.'
Write-Host ''
Start-Process notepad.exe -ArgumentList "`"$reportPath`""
