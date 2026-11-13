<#
.SYNOPSIS
Save a locally entered Cloudflare token with Windows DPAPI, or inspect Access.
.DESCRIPTION
Run -SaveToken once in your own interactive PowerShell. No token arguments.
Default mode is read-only and prints counts only, never log contents or tokens.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-fA-F0-9]{32}$')]
    [string]$AccountId,
    [switch]$SaveToken
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$AccountId = $AccountId.ToLowerInvariant()
$credentialDirectory = Join-Path $env:LOCALAPPDATA 'Argus\credentials'
$credentialFile = Join-Path $credentialDirectory "cloudflare-$AccountId.dpapi"
$tokenPointer = [IntPtr]::Zero
$plainToken = $null
$headers = $null
$stage = 'local credential'

function Get-CloudflareResult([string]$RelativePath) {
    try {
        $response = Invoke-RestMethod -Method Get -Uri (
            'https://api.cloudflare.com/client/v4/' + $RelativePath
        ) -Headers $headers -TimeoutSec 30 -MaximumRedirection 0
    }
    catch {
        # Avoid exception/response dumps: request metadata may contain credentials.
        throw 'Cloudflare request failed. Check network, token expiry and account permissions.'
    }
    if (-not $response.success) {
        throw 'Cloudflare rejected the request. Check token validity and account permissions.'
    }
    return $response
}

try {
    if ($SaveToken) {
        $secureToken = Read-Host 'Paste Cloudflare API token locally (hidden)' -AsSecureString
    }
    else {
        if (-not (Test-Path -LiteralPath $credentialFile)) {
            throw 'No saved token for this account. Run this script locally with -SaveToken first.'
        }
        $secureToken = (Get-Content -LiteralPath $credentialFile -Raw).Trim() | ConvertTo-SecureString
    }
    $tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
    if ([string]::IsNullOrWhiteSpace($plainToken)) { throw 'Token must not be empty.' }
    $headers = @{ Authorization = 'Bearer ' + $plainToken }
    $stage = 'token verification'
    $verification = Get-CloudflareResult 'user/tokens/verify'
    if ($verification.result.status -ne 'active') { throw 'Token is not active.' }

    if ($SaveToken) {
        $stage = 'encrypted credential storage'
        # Default ConvertFrom-SecureString uses Windows current-user DPAPI.
        $encryptedToken = $secureToken | ConvertFrom-SecureString
        New-Item -ItemType Directory -Path $credentialDirectory -Force | Out-Null
        Set-Content -LiteralPath $credentialFile -Value $encryptedToken -Encoding ASCII
        Write-Output 'Token verified and saved using Windows current-user DPAPI.'
    }

    $stage = 'application read'
    $apps = Get-CloudflareResult "accounts/$AccountId/access/apps?per_page=1"
    $stage = 'identity-provider read'
    $providers = Get-CloudflareResult "accounts/$AccountId/access/identity_providers"
    $stage = 'authentication-log read'
    $logs = Get-CloudflareResult "accounts/$AccountId/access/logs/access_requests?limit=1&direction=desc"
    # Apps count is intentionally a bounded sample, not an account-wide total.
    [pscustomobject]@{
        ApplicationSampleCount = @($apps.result).Count
        IdentityProviderCount = @($providers.result).Count
        AuthenticationLogSampleCount = @($logs.result).Count
        Inspection = 'read-only; no application or policy changed'
    } | ConvertTo-Json -Compress
}
catch {
    # Only our own fixed messages are safe to display. Do not output $_ directly.
    Write-Output "Cloudflare inspection failed at $stage. Check local credential access, network, token validity and endpoint permissions. No cloud settings were changed."
    exit 1
}
finally {
    if ($tokenPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
    }
    if ($null -ne $headers) { $headers.Clear() }
    $plainToken = $null
    $tokenVariable = Get-Variable secureToken -ErrorAction SilentlyContinue
    if ($null -ne $tokenVariable -and $tokenVariable.Value -is [Security.SecureString]) {
        $tokenVariable.Value.Dispose()
    }
}
