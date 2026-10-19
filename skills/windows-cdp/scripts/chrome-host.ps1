# Invoked by windows-chrome using powershell.exe -EncodedCommand from WSL2.
param(
    [ValidateSet('start', 'status')]
    [string]$Action = 'status',
    [ValidateRange(1, 65535)]
    [int]$Port = 9222,
    [string]$StartUrl = 'about:blank'
)
$ErrorActionPreference = 'Stop'

function Split-WindowsCommandLine([string]$CommandLine) {
    # Reuse Windows parsing rules, rather than matching substrings or inventing a tokenizer.
    if (-not ('ChromeCdp.Native' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
namespace ChromeCdp {
    public static class Native {
        [DllImport("shell32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr CommandLineToArgvW(string commandLine, out int argc);
        [DllImport("kernel32.dll")]
        private static extern IntPtr LocalFree(IntPtr memory);
        public static string[] Split(string commandLine) {
            int count;
            IntPtr memory = CommandLineToArgvW(commandLine, out count);
            if (memory == IntPtr.Zero) throw new Win32Exception();
            try {
                string[] result = new string[count];
                for (int i = 0; i < count; i++)
                    result[i] = Marshal.PtrToStringUni(Marshal.ReadIntPtr(memory, i * IntPtr.Size));
                return result;
            } finally { LocalFree(memory); }
        }
    }
}
'@
    }
    [ChromeCdp.Native]::Split($CommandLine)
}

function Get-ChromeOptions([string]$CommandLine) {
    $options = @{}
    $arguments = @(Split-WindowsCommandLine $CommandLine)
    for ($i = 1; $i -lt $arguments.Count; $i++) {
        if ($arguments[$i] -ceq '--') { break }
        $parts = $arguments[$i] -split '=', 2
        # Chromium switches are case-sensitive. Duplicate safety-critical switches fail closed.
        if ($parts[0] -cnotin @('--user-data-dir', '--remote-debugging-port', '--type')) { continue }
        if ($options.ContainsKey($parts[0])) { throw 'Ambiguous Chrome command line; duplicate switch.' }
        # Require the same --name=value spelling used at launch; do not guess
        # whether a following positional argument is a Chromium switch value.
        if ($parts.Count -ne 2 -or [string]::IsNullOrEmpty($parts[1])) {
            throw 'Chrome command line has a missing switch value.'
        }
        $options[$parts[0]] = $parts[1]
    }
    return $options
}

function Test-ProfileCommand([string]$CommandLine) {
    if (-not $CommandLine) { return $false }
    $options = Get-ChromeOptions $CommandLine
    # A child process is not proof that the browser owns this profile.
    if ($options.ContainsKey('--type') -or -not $options.ContainsKey('--user-data-dir')) { return $false }
    $directory = $options['--user-data-dir']
    if (-not [IO.Path]::IsPathRooted($directory)) { return $false }
    $actual = [IO.Path]::GetFullPath($directory).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $expected = [IO.Path]::GetFullPath($isolatedProfile).TrimEnd([IO.Path]::DirectorySeparatorChar)
    return [string]::Equals($actual, $expected, [StringComparison]::OrdinalIgnoreCase)
}

function Get-ProfileProcesses {
    @(
        Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" |
        Where-Object { Test-ProfileCommand $_.CommandLine }
    )
}

function Test-ExpectedEndpoint([switch]$WaitForReady) {
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -eq 0) { return $false }
    foreach ($listener in $listeners) {
        if ($listener.LocalAddress -notin @('127.0.0.1', '::1')) {
            throw "Port $Port has a non-loopback listener at $($listener.LocalAddress); refusing to attach."
        }
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
        if (-not $process -or $process.Name -ine 'chrome.exe' -or -not $process.CommandLine) {
            throw "Port $Port is owned by an unrecognized process; refusing to attach."
        }
        $options = Get-ChromeOptions $process.CommandLine
        if (-not (Test-ProfileCommand $process.CommandLine) -or
            $options['--remote-debugging-port'] -cne [string]$Port) {
            throw "Port $Port belongs to Chrome outside the expected isolated profile; refusing to attach."
        }
    }
    # Only readiness errors are retryable. Ownership errors above always fail immediately.
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/json/version" -TimeoutSec 1
    } catch {
        if ($WaitForReady) { return $false }
        throw
    }
    return $true
}

function Write-Ready {
    Write-Output "Chrome CDP ready: http://127.0.0.1:$Port (Windows loopback)"
    Write-Output "Isolated profile: $isolatedProfile"
}

function Invoke-ChromeHost {
    param([string]$Action, [int]$Port, [string]$StartUrl)
    $isolatedProfile = Join-Path $env:LOCALAPPDATA 'Chrome-CDP-Agent\Profile'
    if ($Action -eq 'status') {
        if (-not (Test-ExpectedEndpoint)) {
            throw "Isolated Chrome is not listening on port $Port. Run 'windows-chrome start' first."
        }
        Write-Ready
        return
    }
    if ([string]::IsNullOrWhiteSpace($StartUrl) -or $StartUrl -match '[\s"'']') {
        throw 'Invalid startup URL. Provide a URL without whitespace or quotes, or use about:blank.'
    }
    if ($StartUrl -ne 'about:blank' -and $StartUrl -notmatch '^https?://') {
        throw 'Startup URL must be about:blank, http://, or https://.'
    }

    # FileShare.None serializes the check-and-launch sequence across shells and ports.
    # Keep the lock file: deleting it could allow a second launcher to lock a new file.
    $stateDirectory = Split-Path -Parent $isolatedProfile
    New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
    try {
        $lock = [IO.File]::Open((Join-Path $stateDirectory 'launcher.lock'),
            [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    } catch { throw 'Another Chrome launcher is active, or its lock is inaccessible. Retry after it finishes.' }
    try {
        if (Test-ExpectedEndpoint -WaitForReady) {
            Write-Output 'The isolated Chrome instance is already running.'
            Write-Ready
            return
        }
        if ((Get-ProfileProcesses).Count -gt 0) {
            throw 'Chrome is using the isolated profile but its expected CDP endpoint is unavailable. Close only that Chrome instance manually, then retry.'
        }
        $candidates = @(
            (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
            (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
        )
        $programFilesX86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
        if ($programFilesX86) {
            $candidates += Join-Path $programFilesX86 'Google\Chrome\Application\chrome.exe'
        }
        $chrome = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
        if (-not $chrome) { throw 'Google Chrome executable not found in the standard Windows installation locations.' }
        New-Item -ItemType Directory -Path $isolatedProfile -Force | Out-Null
        # Escaped quotes survive ArgumentList joining in Windows PowerShell 5.1.
        # None of these arguments contain quotes or trailing backslashes inside quotes.
        $chromeArguments = @(
            '--remote-debugging-address=127.0.0.1',
            "--remote-debugging-port=$Port",
            "--user-data-dir=`"$isolatedProfile`"",
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-sync',
            '--disable-extensions',
            $StartUrl
        )
        Start-Process -FilePath $chrome -ArgumentList ($chromeArguments -join ' ') | Out-Null
        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep -Milliseconds 250
            if (Test-ExpectedEndpoint -WaitForReady) {
                Write-Ready
                return
            }
        }
        throw "Chrome did not open its CDP endpoint on port $Port. Check browser policy, launch errors, or an approval prompt; do not bypass it."
    } finally { $lock.Dispose() }
}

Invoke-ChromeHost -Action $Action -Port $Port -StartUrl $StartUrl
