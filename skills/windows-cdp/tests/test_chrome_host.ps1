# Offline tests: load production functions without executing the launcher entry point.
$ErrorActionPreference = 'Stop'
$hostScript = Join-Path $PSScriptRoot '../scripts/chrome-host.ps1'
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile(
    $hostScript, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
foreach ($statement in $ast.EndBlock.Statements) {
    if ($statement -is [Management.Automation.Language.FunctionDefinitionAst]) {
        . ([scriptblock]::Create($statement.Extent.Text))
    }
}

function Assert-True($Value, [string]$Message) {
    if (-not $Value) { throw $Message }
}
function Assert-Throws([scriptblock]$Body, [string]$Message) {
    $threw = $false
    try { & $Body | Out-Null } catch { $threw = $true }
    Assert-True $threw $Message
}

$isolatedProfile = Join-Path ([IO.Path]::GetTempPath()) 'John Doe/Chrome-CDP-Agent/Profile'
$Port = 9222
$script:commandLines = @{}
$script:nativeWindows = $env:OS -eq 'Windows_NT'
if (-not $script:nativeWindows) {
    # Only the Win32 API boundary is mocked on Linux; matching uses production code.
    function Split-WindowsCommandLine([string]$CommandLine) {
        $script:commandLines[$CommandLine]
    }
}
function Set-CommandLine([string[]]$Arguments) {
    $line = 'chrome.exe ' + (($Arguments | ForEach-Object { '"' + $_ + '"' }) -join ' ')
    $script:commandLines[$line] = @('chrome.exe') + $Arguments
    $script:process = [pscustomobject]@{ Name = 'chrome.exe'; CommandLine = $line }
}
$script:listener = [pscustomobject]@{ LocalAddress = '127.0.0.1'; OwningProcess = 42 }
function Get-NetTCPConnection { if ($script:listener) { $script:listener } }
function Get-CimInstance { $script:process }
$script:probeCalls = 0
$script:probeFailures = 0
function Invoke-RestMethod {
    $script:probeCalls++
    if ($script:probeCalls -le $script:probeFailures) { throw 'endpoint not ready' }
    [pscustomobject]@{ Browser = 'Chrome'; webSocketDebuggerUrl = 'ws://127.0.0.1:9222/devtools/browser/test' }
}

Set-CommandLine @("--user-data-dir=$isolatedProfile", '--remote-debugging-port=9222')
Assert-True (Test-ExpectedEndpoint) 'Valid isolated browser rejected'
Set-CommandLine @("--user-data-dir=$isolatedProfile/../Profile/", '--remote-debugging-port=9222')
Assert-True (Test-ExpectedEndpoint) 'Normalized profile spelling rejected'

foreach ($arguments in @(
    @("--user-data-dir=${isolatedProfile}-other", '--remote-debugging-port=9222'),
    @('--user-data-dir=other', '--remote-debugging-port=9222', "https://example.test/?p=$isolatedProfile"),
    @("--user-data-dir=$isolatedProfile", '--user-data-dir=other', '--remote-debugging-port=9222'),
    @("--user-data-dir=$isolatedProfile", '--remote-debugging-port=92220'),
    @("--user-data-dir=$isolatedProfile", '--remote-debugging-port=9222', '--remote-debugging-port=9223'),
    @("--user-data-dir=$isolatedProfile", '--remote-debugging-port=9222', '--type=utility'),
    @('--', "--user-data-dir=$isolatedProfile", '--remote-debugging-port=9222')
)) {
    Set-CommandLine $arguments
    Assert-Throws { Test-ExpectedEndpoint } 'Unrelated/ambiguous Chrome accepted'
}
Set-CommandLine @('--user-data-dir', $isolatedProfile, '--remote-debugging-port', '9222')
Assert-Throws { Test-ExpectedEndpoint } 'Noncanonical switch values accepted'
Set-CommandLine @("--user-data-dir=$isolatedProfile", '--remote-debugging-port=9222')
$script:listener.LocalAddress = '0.0.0.0'
Assert-Throws { Test-ExpectedEndpoint } 'Non-loopback listener accepted'
$script:listener.LocalAddress = '::1'
Assert-True (Test-ExpectedEndpoint) 'IPv6 loopback listener rejected'
$script:listener.LocalAddress = '127.0.0.1'
$script:process.Name = 'not-chrome.exe'
Assert-Throws { Test-ExpectedEndpoint } 'Non-Chrome owner accepted'
$script:process.Name = 'chrome.exe'
$script:process.CommandLine = $null
Assert-Throws { Test-ExpectedEndpoint } 'Unknown command line accepted'
Set-CommandLine @("--user-data-dir=$isolatedProfile", '--remote-debugging-port=9222')
$script:probeCalls = 0
$script:probeFailures = 1
Assert-True (-not (Test-ExpectedEndpoint -WaitForReady)) 'Readiness failure not retried'
Assert-True (Test-ExpectedEndpoint -WaitForReady) 'Ready endpoint rejected'
$script:probeCalls = 0
Assert-Throws { Test-ExpectedEndpoint } 'Status hid a failed endpoint probe'
$script:probeFailures = 0
$script:listener = $null
Assert-True (-not (Test-ExpectedEndpoint)) 'Missing listener accepted'

# Verify launch argument quoting at the Start-Process boundary, without starting Chrome.
$script:launchLine = $null
function Start-Process {
    param($FilePath, $ArgumentList)
    $script:launchLine = $ArgumentList
}
$script:listener = $null
function Get-ProfileProcesses { @() }
function Test-Path { $true }
function Start-Sleep { throw 'stop after capture' }
$env:LOCALAPPDATA = Join-Path ([IO.Path]::GetTempPath()) ('Chrome Host Tests ' + [guid]::NewGuid())
$env:ProgramFiles = [IO.Path]::GetTempPath()
try { Invoke-ChromeHost -Action start -Port 9222 -StartUrl 'https://example.test/?a=1&b=2' } catch {
    if ($_.Exception.Message -ne 'stop after capture') { throw }
}
Assert-True ($script:launchLine -is [string]) 'Arguments must be explicitly joined'
$expected = Join-Path $env:LOCALAPPDATA 'Chrome-CDP-Agent\Profile'
Assert-True ($script:launchLine.Contains("--user-data-dir=`"$expected`"")) 'Profile not quoted'
if ($script:nativeWindows) {
    $actual = @(Split-WindowsCommandLine ('chrome.exe ' + $script:launchLine))
    Assert-True ($actual.Count -eq 9) 'Windows argument round trip changed count'
    Assert-True ($actual[3] -eq "--user-data-dir=$expected") 'Windows split the profile path'
    Assert-True ($actual[8] -eq 'https://example.test/?a=1&b=2') 'Windows changed URL data'
}
# A held lock refuses a concurrent start and the finally block releases it after failure.
$lockPath = Join-Path $env:LOCALAPPDATA 'Chrome-CDP-Agent/launcher.lock'
$heldLock = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate,
    [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
try {
    $script:launchLine = $null
    Assert-Throws { Invoke-ChromeHost -Action start -Port 9222 -StartUrl 'about:blank' } 'Concurrent start accepted'
    Assert-True ($null -eq $script:launchLine) 'Concurrent start launched Chrome'
} finally { $heldLock.Dispose() }
foreach ($url in @('file:///sensitive', 'javascript:alert(1)', 'https://example.test/"quoted"', 'http://bad url')) {
    Assert-Throws { Invoke-ChromeHost -Action start -Port 9222 -StartUrl $url } 'Invalid URL accepted'
}
Remove-Item -LiteralPath $env:LOCALAPPDATA -Recurse -Force
Write-Output 'PowerShell host regression tests passed (Windows services mocked).'
