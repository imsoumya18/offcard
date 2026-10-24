# ShotLoft installer for Windows. Paste this into PowerShell:
#
#   irm https://raw.githubusercontent.com/imsoumya18/shotloft/main/install.ps1 | iex
#
# Downloads the latest release into your user folder (no admin rights needed) and adds
# "ShotLoft" to the Start menu. Files downloaded this way don't get Windows' "from the
# internet" mark, so there's no SmartScreen warning. Run the same line again to update.
#
# Overrides (used by the tests): SHOTLOFT_RELEASES, SHOTLOFT_INSTALL_DIR, SHOTLOFT_START_MENU

& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'   # the download progress bar makes PowerShell 5 very slow
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $releases = if ($env:SHOTLOFT_RELEASES) { $env:SHOTLOFT_RELEASES } else { 'https://github.com/imsoumya18/shotloft/releases/latest/download' }
    $installDir = if ($env:SHOTLOFT_INSTALL_DIR) { $env:SHOTLOFT_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA 'Programs\ShotLoft' }
    $startMenu = if ($env:SHOTLOFT_START_MENU) { $env:SHOTLOFT_START_MENU } else { [Environment]::GetFolderPath('Programs') }

    function Step($text) { Write-Host '  > ' -ForegroundColor DarkCyan -NoNewline; Write-Host $text }
    function Fail($text) { Write-Host ''; Write-Host "  x $text" -ForegroundColor Red; Write-Host '' }

    Write-Host ''
    Write-Host '  ShotLoft installer' -ForegroundColor DarkCyan
    Write-Host ''

    if (-not [Environment]::Is64BitOperatingSystem) { Fail 'ShotLoft needs 64-bit Windows.'; return }

    try {
        Step 'Downloading the latest version for Windows...'
        New-Item -ItemType Directory -Force -Path $installDir | Out-Null
        $exe = Join-Path $installDir 'ShotLoft.exe'
        $tmp = "$exe.download"
        # ShotLoft was called Sony Import until v2.0.0: until the first ShotLoft release exists,
        # fall back to the last Sony Import one.
        $got = $false
        foreach ($name in 'shotloft-windows.exe', 'sony-import-windows.exe') {
            try { Invoke-WebRequest -Uri "$releases/$name" -OutFile $tmp -UseBasicParsing; $got = $true; break } catch { }
        }
        if (-not $got) { throw 'Download failed. Check your internet connection.' }
        Unblock-File -Path $tmp   # make sure nothing carries the "from the internet" mark

        Step "Installing to $installDir ..."
        try {
            Move-Item -Force -Path $tmp -Destination $exe
        } catch {
            Remove-Item -Force $tmp -ErrorAction SilentlyContinue
            Fail 'ShotLoft is still open. Close it and run this line again.'
            return
        }
        # Remove the old Sony Import install (its own folder and Start menu entry), if present.
        # Only in a normal install; with an explicit folder (tests, CI) nothing outside it is touched.
        if (-not $env:SHOTLOFT_INSTALL_DIR) {
            $oldDir = Join-Path $env:LOCALAPPDATA 'Programs\Sony Import'
            if (Test-Path (Join-Path $oldDir '*.exe')) { Remove-Item -Recurse -Force $oldDir -ErrorAction SilentlyContinue }
        }
        Remove-Item -Force (Join-Path $startMenu 'Sony Import.lnk') -ErrorAction SilentlyContinue

        New-Item -ItemType Directory -Force -Path $startMenu | Out-Null
        $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $startMenu 'ShotLoft.lnk'))
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
    Write-Host '  ShotLoft is installed.' -ForegroundColor Green
    Write-Host ''
    Write-Host '  Open it from the Start menu: search for ' -NoNewline; Write-Host 'ShotLoft' -ForegroundColor DarkCyan
    Write-Host '  To update later, run the same line again.' -ForegroundColor DarkGray
    Write-Host ''
}
