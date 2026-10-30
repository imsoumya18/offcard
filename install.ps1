# offcard installer for Windows. Paste this into PowerShell:
#
#   irm https://raw.githubusercontent.com/imsoumya18/offcard/main/install.ps1 | iex
#
# Downloads the latest release into your user folder (no admin rights needed) and adds
# "offcard" to the Start menu. Files downloaded this way don't get Windows' "from the
# internet" mark, so there's no SmartScreen warning. Run the same line again to update.
#
# Overrides (used by the tests): OFFCARD_RELEASES, OFFCARD_INSTALL_DIR, OFFCARD_START_MENU

& {
    $ErrorActionPreference = 'Stop'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $releases = if ($env:OFFCARD_RELEASES) { $env:OFFCARD_RELEASES } else { 'https://github.com/imsoumya18/offcard/releases/latest/download' }
    $installDir = if ($env:OFFCARD_INSTALL_DIR) { $env:OFFCARD_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA 'Programs\offcard' }
    $startMenu = if ($env:OFFCARD_START_MENU) { $env:OFFCARD_START_MENU } else { [Environment]::GetFolderPath('Programs') }

    function Step($text) { Write-Host '  > ' -ForegroundColor DarkCyan -NoNewline; Write-Host $text }
    function Fail($text) { Write-Host ''; Write-Host "  x $text" -ForegroundColor Red; Write-Host '' }

    # Downloads with a progress bar. (Invoke-WebRequest's own progress bar makes PowerShell 5 very
    # slow, so the file is read in 1 MB chunks and progress is shown once per percent.)
    function Get-File($url, $out) {
        # Show something at once: GitHub can take a while to answer on slow connections.
        Write-Progress -Activity 'Downloading offcard' -Status 'Connecting to GitHub...' -PercentComplete 0
        $resp = [System.Net.WebRequest]::Create($url).GetResponse()
        $total = $resp.ContentLength
        $in = $resp.GetResponseStream(); $fs = [System.IO.File]::Create($out)
        $buf = New-Object byte[] 1MB; $done = 0; $last = -1
        try {
            while (($n = $in.Read($buf, 0, $buf.Length)) -gt 0) {
                $fs.Write($buf, 0, $n); $done += $n
                if ($total -gt 0) {
                    $pct = [int][math]::Floor($done * 100 / $total)
                    if ($pct -ne $last) {
                        Write-Progress -Activity 'Downloading offcard' -PercentComplete $pct `
                            -Status ('{0:N1} of {1:N1} MB' -f ($done / 1MB), ($total / 1MB))
                        $last = $pct
                    }
                }
            }
        } finally { $fs.Close(); $in.Close(); $resp.Close() }
        Write-Progress -Activity 'Downloading offcard' -Completed
    }

    # The app has to be closed to be replaced: ask before downloading, not after.
    # offcard was called ShotLoft until v2.6.1, and Sony Import until v2.0.0.
    $oldNames = 'ShotLoft', 'Sony Import'
    $oldDirs = $oldNames | ForEach-Object { Join-Path $env:LOCALAPPDATA "Programs\$_" }

    function Wait-Closed {
        $isOpen = { @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
            $p = $_.Path
            $p -and ($p.StartsWith($installDir, 'OrdinalIgnoreCase') -or
                     @($oldDirs | Where-Object { $p.StartsWith($_, 'OrdinalIgnoreCase') }).Count -gt 0) }).Count -gt 0 }
        while (& $isOpen) {
            Write-Host '  ! offcard is open. Close it (it has to be closed to update), then press Enter' -ForegroundColor Yellow -NoNewline
            Read-Host | Out-Null
        }
    }

    Write-Host ''
    Write-Host '  offcard installer' -ForegroundColor DarkCyan
    Write-Host ''

    if (-not [Environment]::Is64BitOperatingSystem) { Fail 'offcard needs 64-bit Windows.'; return }

    try {
        Wait-Closed
        Step 'Downloading the latest version for Windows...'
        New-Item -ItemType Directory -Force -Path $installDir | Out-Null
        $exe = Join-Path $installDir 'offcard.exe'
        $tmp = "$exe.download"
        # Until the first offcard release exists, fall back to the last ShotLoft one.
        $got = $false
        foreach ($name in 'offcard-windows.exe', 'shotloft-windows.exe') {
            try { Get-File "$releases/$name" $tmp; $got = $true; break } catch { Remove-Item -Force $tmp -ErrorAction SilentlyContinue }
        }
        if (-not $got) { throw 'Download failed. Check your internet connection.' }
        Unblock-File -Path $tmp   # make sure nothing carries the "from the internet" mark

        Wait-Closed   # in case it was opened meanwhile
        Step "Installing to $installDir ..."
        try {
            Move-Item -Force -Path $tmp -Destination $exe
        } catch {
            Remove-Item -Force $tmp -ErrorAction SilentlyContinue
            Fail 'offcard is still open. Close it and run this line again.'
            return
        }
        # Remove the old ShotLoft and Sony Import installs (their folders and Start menu entries).
        # Only in a normal install; with an explicit folder (tests, CI) nothing outside it is touched.
        if (-not $env:OFFCARD_INSTALL_DIR) {
            foreach ($oldDir in $oldDirs) {
                if (Test-Path (Join-Path $oldDir '*.exe')) { Remove-Item -Recurse -Force $oldDir -ErrorAction SilentlyContinue }
            }
        }
        foreach ($oldName in $oldNames) {
            Remove-Item -Force (Join-Path $startMenu "$oldName.lnk") -ErrorAction SilentlyContinue
        }

        New-Item -ItemType Directory -Force -Path $startMenu | Out-Null
        $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $startMenu 'offcard.lnk'))
        $shortcut.TargetPath = $exe
        $shortcut.WorkingDirectory = $installDir
        $shortcut.IconLocation = "$exe,0"
        $shortcut.Description = 'Back up your Sony camera card, sorted by date'
        $shortcut.Save()
    } catch {
        Fail "Installation failed: $($_.Exception.Message)"
        return
    }

    Write-Host ''
    Write-Host '  offcard is installed.' -ForegroundColor Green
    Write-Host ''
    Write-Host '  Open it from the Start menu: search for ' -NoNewline; Write-Host 'offcard' -ForegroundColor DarkCyan
    Write-Host '  To update later, run the same line again.' -ForegroundColor DarkGray
    Write-Host ''
}
