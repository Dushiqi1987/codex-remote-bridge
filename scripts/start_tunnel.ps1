[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9.-]*$')][string]$ServerHost,
    [Parameter(Mandatory=$true)][ValidateRange(1,65535)][int]$SshPort,
    [ValidatePattern('^[A-Za-z0-9_][A-Za-z0-9_.-]*$')][string]$ServerUser = 'root',
    [ValidateRange(1,65535)][int]$RemotePort = 17891,
    [ValidateRange(1,65535)][int]$LocalPort = 11450,
    [string]$IdentityFile,
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$sshArgs = @('-N', '-T', '-p', "$SshPort", '-o', 'ExitOnForwardFailure=yes',
    '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3',
    '-R', "127.0.0.1:${RemotePort}:127.0.0.1:${LocalPort}")
if ($IdentityFile) {
    $keyPath = (Resolve-Path -LiteralPath $IdentityFile).Path
    $sshArgs += @('-i', $keyPath)
}
$sshArgs += "${ServerUser}@${ServerHost}"
Write-Host "Remote 127.0.0.1:$RemotePort -> local 127.0.0.1:$LocalPort"
if ($DryRun) {
    Write-Host ('ssh ' + (($sshArgs | ForEach-Object { "'" + $_.Replace("'", "''") + "'" }) -join ' '))
    return
}
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) { throw 'OpenSSH client (ssh) is not on PATH.' }
Write-Host 'Keep this window open. Ctrl+C stops the tunnel. Verify new SSH host fingerprints with your provider.'
& ssh @sshArgs
if ($LASTEXITCODE -ne 0) { throw "SSH tunnel exited with code $LASTEXITCODE" }
