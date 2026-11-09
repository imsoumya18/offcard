# offcard installer for Windows. Paste this into PowerShell:
#
#   irm https://raw.githubusercontent.com/imsoumya18/offcard/main/install.ps1 | iex
#
# Downloads the latest release into your user folder (no admin rights needed) and adds
# "offcard" to the Start menu. Files downloaded this way don't get Windows' "from the
# internet" mark, so there's no SmartScreen warning. Run the same line again to update.
# offcard's panel draws in Edge WebView2: Windows 11 has it, and the installer adds it if a
# Windows 10 PC doesn't.
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
    function Get-File($url, $out, $accept) {
        # Show something at once: GitHub can take a while to answer on slow connections.
        Write-Progress -Activity 'Downloading offcard' -Status 'Connecting to GitHub...' -PercentComplete 0
        # A dead server address can hold a connection for a long time, and the next try may get a good one.
        $resp = $null
        foreach ($try in 1..3) {
            try {
                $req = [System.Net.WebRequest]::Create($url)
                $req.Timeout = 20000
                if ($req -is [System.Net.HttpWebRequest]) {
                    $req.UserAgent = 'offcard-installer'
                    if ($accept) { $req.Accept = $accept }
                }
                $resp = $req.GetResponse()
                break
            } catch {
                if ($try -eq 3) { throw }
            }
        }
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
    # offcard was called ShotLoft until v0.9.1, and Sony Import until v0.4.0.
    $oldNames = 'ShotLoft', 'Sony Import'
    $oldDirs = $oldNames | ForEach-Object { Join-Path $env:LOCALAPPDATA "Programs\$_" }

    # A release file. GitHub's API can serve it even when its usual download link fails (as it did,
    # with error 504, for some files on 9 Nov 2026), so that's the second try.
    function Get-Release($name, $out) {
        try { Get-File "$releases/$name" $out; return } catch { $first = $_ }
        $repo = 'https://github.com/imsoumya18/offcard/releases'
        $api = $null
        if ($releases -eq "$repo/latest/download") { $api = 'https://api.github.com/repos/imsoumya18/offcard/releases/latest' }
        elseif ($releases -like "$repo/download/*") { $api = 'https://api.github.com/repos/imsoumya18/offcard/releases/tags/' + ($releases -split '/')[-1] }
        if (-not $api) { throw $first }
        try {
            $asset = (Invoke-RestMethod -Uri $api -UseBasicParsing -Headers @{ 'User-Agent' = 'offcard-installer'; Accept = 'application/vnd.github+json' }).assets |
                Where-Object { $_.name -eq $name } | Select-Object -First 1
        } catch { throw $first }
        if (-not $asset) { throw $first }
        Get-File $asset.url $out 'application/octet-stream'
    }

    # Windows 10 PCs without the Edge web view get it from Microsoft, for this user.
    function Install-WebView2 {
        $id = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
        $keys = "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$id", "HKCU:\Software\Microsoft\EdgeUpdate\Clients\$id"
        foreach ($key in $keys) {
            $pv = (Get-ItemProperty -Path $key -Name pv -ErrorAction SilentlyContinue).pv
            if ($pv -and $pv -ne '0.0.0.0') { return }
        }
        Step 'Adding the Edge web view that offcard draws in...'
        $setup = Join-Path $env:TEMP 'MicrosoftEdgeWebview2Setup.exe'
        Get-File 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' $setup
        Start-Process -FilePath $setup -ArgumentList '/silent', '/install' -Wait
        Remove-Item -Force $setup -ErrorAction SilentlyContinue
    }

    function Wait-Closed {
        $isOpen = { @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
            $p = $_.Path
            $p -and ($p.StartsWith($installDir, 'OrdinalIgnoreCase') -or
                     @($oldDirs | Where-Object { $p.StartsWith($_, 'OrdinalIgnoreCase') }).Count -gt 0) }).Count -gt 0 }
        while (& $isOpen) {
            Write-Host '  ! offcard is open. Quit it (it has to be closed to update), then press Enter' -ForegroundColor Yellow -NoNewline
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
        $engine = Join-Path $installDir 'engine'
        $tmp = Join-Path $installDir 'download.zip'
        $new = Join-Path $installDir 'download'
        Get-Release 'offcard-windows.zip' $tmp
        Remove-Item -Recurse -Force $new -ErrorAction SilentlyContinue
        Expand-Archive -Path $tmp -DestinationPath $new
        Remove-Item -Force $tmp
        # make sure nothing carries the "from the internet" mark
        Get-ChildItem -Path $new -Recurse -File | Unblock-File

        Install-WebView2

        Wait-Closed   # in case it was opened meanwhile
        Step "Installing to $installDir ..."
        try {
            if (Test-Path $engine) { Remove-Item -Recurse -Force $engine }
            Move-Item -Force -Path (Join-Path $new 'offcard.exe') -Destination $exe
            Move-Item -Force -Path (Join-Path $new 'engine') -Destination $engine
            Remove-Item -Recurse -Force $new
        } catch {
            Remove-Item -Recurse -Force $new -ErrorAction SilentlyContinue
            Fail 'offcard is still open. Quit it and run this line again.'
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
    Write-Host '  It lives in the tray, by the clock. Drag its icon out from behind the ^ to keep it in view.' -ForegroundColor DarkGray
    Write-Host '  To update later, run the same line again.' -ForegroundColor DarkGray
    Write-Host ''
}
