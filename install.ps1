# Sony Import installer for Windows. Paste this into PowerShell:
#
#   irm https://raw.githubusercontent.com/imsoumya18/sony-import/main/install.ps1 | iex
#
# Downloads the latest release into your user folder (no admin rights needed) and adds
# "Sony Import" to the Start menu. Files downloaded this way don't get Windows' "from the
# internet" mark, so there's no SmartScreen warning. Run the same line again to update.
#
# Overrides (used by the tests): SONY_IMPORT_RELEASES, SONY_IMPORT_INSTALL_DIR, SONY_IMPORT_START_MENU

& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'   # the download progress bar makes PowerShell 5 very slow
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $releases = if ($env:SONY_IMPORT_RELEASES) { $env:SONY_IMPORT_RELEASES } else { 'https://github.com/imsoumya18/sony-import/releases/latest/download' }
    $installDir = if ($env:SONY_IMPORT_INSTALL_DIR) { $env:SONY_IMPORT_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA 'Programs\Sony Import' }
    $startMenu = if ($env:SONY_IMPORT_START_MENU) { $env:SONY_IMPORT_START_MENU } else { [Environment]::GetFolderPath('Programs') }

    function Step($text) { Write-Host '  > ' -ForegroundColor DarkCyan -NoNewline; Write-Host $text }
    function Fail($text) { Write-Host ''; Write-Host "  x $text" -ForegroundColor Red; Write-Host '' }

    Write-Host ''
    Write-Host '  Sony Import installer' -ForegroundColor DarkCyan
    Write-Host ''

    if (-not [Environment]::Is64BitOperatingSystem) { Fail 'Sony Import needs 64-bit Windows.'; return }

    try {
        Step 'Downloading the latest version for Windows...'
        New-Item -ItemType Directory -Force -Path $installDir | Out-Null
        $exe = Join-Path $installDir 'Sony Import.exe'
        $tmp = "$exe.download"
        Invoke-WebRequest -Uri "$releases/sony-import-windows.exe" -OutFile $tmp -UseBasicParsing
        Unblock-File -Path $tmp   # make sure nothing carries the "from the internet" mark

        Step "Installing to $installDir ..."
        try {
            Move-Item -Force -Path $tmp -Destination $exe
        } catch {
            Remove-Item -Force $tmp -ErrorAction SilentlyContinue
            Fail 'Sony Import is still open. Close it and run this line again.'
            return
        }
        Remove-Item -Force (Join-Path $installDir 'sony-import.exe') -ErrorAction SilentlyContinue  # older terminal version

        New-Item -ItemType Directory -Force -Path $startMenu | Out-Null
        $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $startMenu 'Sony Import.lnk'))
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
    Write-Host '  Sony Import is installed.' -ForegroundColor Green
    Write-Host ''
    Write-Host '  Open it from the Start menu: search for ' -NoNewline; Write-Host 'Sony Import' -ForegroundColor DarkCyan
    Write-Host '  To update later, run the same line again.' -ForegroundColor DarkGray
    Write-Host ''
}
