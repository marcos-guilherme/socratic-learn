[CmdletBinding()]
param(
    [string]$ManifestUrl = "https://github.com/marcos-guilherme/socratic-learn/releases/latest/download/release-manifest.json",
    [string]$InstallDirectory = (Join-Path $env:LOCALAPPDATA "SocraticLearn\bin"),
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

function Skip-JsonWhitespace {
    param([string]$Text, [ref]$Index)
    while ($Index.Value -lt $Text.Length -and [char]::IsWhiteSpace($Text[$Index.Value])) {
        $Index.Value++
    }
}

function Read-JsonString {
    param([string]$Text, [ref]$Index)
    if ($Index.Value -ge $Text.Length -or $Text[$Index.Value] -ne '"') {
        throw "release manifest contains invalid JSON"
    }
    $start = $Index.Value
    $Index.Value++
    $escaped = $false
    while ($Index.Value -lt $Text.Length) {
        $character = $Text[$Index.Value]
        $Index.Value++
        if ($escaped) {
            $escaped = $false
        } elseif ($character -eq '\') {
            $escaped = $true
        } elseif ($character -eq '"') {
            $raw = $Text.Substring($start, $Index.Value - $start)
            return ConvertFrom-Json -InputObject $raw
        }
    }
    throw "release manifest contains an unterminated JSON string"
}

function Assert-JsonValueHasUniqueKeys {
    param([string]$Text, [ref]$Index)
    Skip-JsonWhitespace $Text $Index
    if ($Index.Value -ge $Text.Length) {
        throw "release manifest contains incomplete JSON"
    }
    $character = $Text[$Index.Value]
    if ($character -eq '{') {
        $Index.Value++
        $keys = @{}
        Skip-JsonWhitespace $Text $Index
        if ($Index.Value -lt $Text.Length -and $Text[$Index.Value] -eq '}') {
            $Index.Value++
            return
        }
        while ($true) {
            Skip-JsonWhitespace $Text $Index
            $key = Read-JsonString $Text $Index
            if ($keys.ContainsKey($key)) {
                throw "release manifest contains duplicate key '$key'"
            }
            $keys[$key] = $true
            Skip-JsonWhitespace $Text $Index
            if ($Index.Value -ge $Text.Length -or $Text[$Index.Value] -ne ':') {
                throw "release manifest contains invalid JSON object syntax"
            }
            $Index.Value++
            Assert-JsonValueHasUniqueKeys $Text $Index
            Skip-JsonWhitespace $Text $Index
            if ($Index.Value -ge $Text.Length) {
                throw "release manifest contains incomplete JSON object"
            }
            if ($Text[$Index.Value] -eq '}') {
                $Index.Value++
                return
            }
            if ($Text[$Index.Value] -ne ',') {
                throw "release manifest contains invalid JSON object syntax"
            }
            $Index.Value++
        }
    }
    if ($character -eq '[') {
        $Index.Value++
        Skip-JsonWhitespace $Text $Index
        if ($Index.Value -lt $Text.Length -and $Text[$Index.Value] -eq ']') {
            $Index.Value++
            return
        }
        while ($true) {
            Assert-JsonValueHasUniqueKeys $Text $Index
            Skip-JsonWhitespace $Text $Index
            if ($Index.Value -ge $Text.Length) {
                throw "release manifest contains incomplete JSON array"
            }
            if ($Text[$Index.Value] -eq ']') {
                $Index.Value++
                return
            }
            if ($Text[$Index.Value] -ne ',') {
                throw "release manifest contains invalid JSON array syntax"
            }
            $Index.Value++
        }
    }
    if ($character -eq '"') {
        [void](Read-JsonString $Text $Index)
        return
    }
    $start = $Index.Value
    while (
        $Index.Value -lt $Text.Length -and
        $Text[$Index.Value] -notin @(',', '}', ']') -and
        -not [char]::IsWhiteSpace($Text[$Index.Value])
    ) {
        $Index.Value++
    }
    if ($Index.Value -eq $start) {
        throw "release manifest contains invalid JSON value"
    }
}

function ConvertFrom-StrictJson {
    param([string]$Text)
    $index = 0
    Assert-JsonValueHasUniqueKeys $Text ([ref]$index)
    Skip-JsonWhitespace $Text ([ref]$index)
    if ($index -ne $Text.Length) {
        throw "release manifest contains trailing JSON content"
    }
    return ConvertFrom-Json -InputObject $Text
}

function Assert-ExactKeys {
    param($Object, [string[]]$Expected, [string]$Label)
    if ($null -eq $Object -or $Object -isnot [psobject]) {
        throw "$Label must be a JSON object"
    }
    $actual = @($Object.PSObject.Properties.Name)
    foreach ($key in $Expected) {
        if (-not ($actual -ccontains $key)) {
            throw "$Label is missing required key '$key'"
        }
    }
    foreach ($key in $actual) {
        if (-not ($Expected -ccontains $key)) {
            throw "$Label contains unknown key '$key'"
        }
    }
}

function Test-Integer {
    param($Value)
    return (
        $Value -is [byte] -or $Value -is [int16] -or $Value -is [int32] -or
        $Value -is [int64] -or $Value -is [uint16] -or
        $Value -is [uint32] -or $Value -is [uint64]
    )
}

$canonicalManifestUrl = "https://github.com/marcos-guilherme/socratic-learn/releases/latest/download/release-manifest.json"

function Assert-TrustedRequestUri {
    param([Uri]$Uri, [string]$TrustMode)
    if (
        $null -eq $Uri -or
        -not $Uri.IsAbsoluteUri -or
        -not [string]::IsNullOrEmpty($Uri.UserInfo) -or
        -not [string]::IsNullOrEmpty($Uri.Fragment)
    ) {
        throw "URL is outside the trusted release boundary"
    }
    if ($TrustMode -eq "production") {
        if (
            $Uri.Scheme -cne [Uri]::UriSchemeHttps -or
            [string]::IsNullOrEmpty($Uri.Host)
        ) {
            throw "URL is outside the trusted HTTPS release boundary"
        }
        return
    }
    if (
        $TrustMode -ne "loopback" -or
        $Uri.Scheme -cne [Uri]::UriSchemeHttp -or
        $Uri.OriginalString -cnotmatch '^http://(?:localhost|127[.]0[.]0[.]1|\[::1\])(?::[0-9]+)?(?:/[^?#]*)?$' -or
        -not [string]::IsNullOrEmpty($Uri.Query)
    ) {
        throw "URL is outside the trusted loopback test boundary"
    }
}

function Get-ManifestTrust {
    param([string]$Value)
    $parsed = $null
    if (
        -not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$parsed) -or
        -not $parsed.IsWellFormedOriginalString()
    ) {
        throw "Manifest URL is not a trusted absolute URI"
    }
    if ($Value -ceq $canonicalManifestUrl) {
        Assert-TrustedRequestUri $parsed "production"
        return [pscustomobject]@{ Uri = $parsed; Mode = "production" }
    }
    Assert-TrustedRequestUri $parsed "loopback"
    return [pscustomobject]@{ Uri = $parsed; Mode = "loopback" }
}

function Invoke-TrustedGet {
    param(
        [Net.Http.HttpClient]$Client,
        [Uri]$Uri,
        [string]$TrustMode
    )
    $current = $Uri
    for ($redirects = 0; $redirects -le 10; $redirects++) {
        Assert-TrustedRequestUri $current $TrustMode
        $response = $Client.GetAsync(
            $current,
            [Net.Http.HttpCompletionOption]::ResponseHeadersRead
        ).GetAwaiter().GetResult()
        $status = [int]$response.StatusCode
        if ($status -ge 300 -and $status -lt 400) {
            $location = $response.Headers.Location
            $response.Dispose()
            if ($null -eq $location) {
                throw "Release redirect is missing a trusted Location"
            }
            $current = if ($location.IsAbsoluteUri) {
                $location
            } else {
                New-Object Uri($current, $location)
            }
            Assert-TrustedRequestUri $current $TrustMode
            continue
        }
        if (-not $response.IsSuccessStatusCode) {
            try {
                $response.EnsureSuccessStatusCode() | Out-Null
            } finally {
                $response.Dispose()
            }
        }
        return $response
    }
    throw "Release download exceeded the trusted redirect limit"
}

$architecture = if ($env:PROCESSOR_ARCHITEW6432) {
    $env:PROCESSOR_ARCHITEW6432
} else {
    $env:PROCESSOR_ARCHITECTURE
}
if ($architecture -notmatch '^(?i:AMD64|x86_64|x64)$') {
    throw "Only x86-64 Windows is supported. Fallback: pipx install socratic-learn"
}

Write-Warning "This release is unsigned and Windows SmartScreen may warn before it runs."
if (-not $Yes) {
    $confirmation = Read-Host "Continue with the download? [y/N]"
    if ($confirmation -notmatch '^(?i:y|yes)$') {
        throw "Installation cancelled. Fallback: pipx install socratic-learn"
    }
}

$manifestTrust = Get-ManifestTrust $ManifestUrl
$manifestUri = $manifestTrust.Uri
$trustMode = $manifestTrust.Mode
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.Net.Http

$installWasOverridden = $PSBoundParameters.ContainsKey("InstallDirectory")
$installPath = [IO.Path]::GetFullPath($InstallDirectory)
$target = Join-Path $installPath "socratic.exe"
$staged = Join-Path $installPath "socratic.new.exe"
$channelHome = Join-Path $HOME ".socratic-learn"
$channelTarget = Join-Path $channelHome "channel.json"
$channelStaged = Join-Path $channelHome "channel.json.new"
$channelPrevious = Join-Path $channelHome "channel.json.previous"
$channelFailed = Join-Path $channelHome "channel.json.failed"
$targetPrevious = Join-Path $installPath "socratic.previous.exe"
$targetFailed = Join-Path $installPath "socratic.failed.exe"

New-Item -ItemType Directory -Force -Path $installPath | Out-Null
New-Item -ItemType Directory -Force -Path $channelHome | Out-Null
Remove-Item -Force -ErrorAction SilentlyContinue `
    $staged, $channelStaged, $channelPrevious, $channelFailed, `
    $targetPrevious, $targetFailed

$handler = New-Object Net.Http.HttpClientHandler
$handler.AllowAutoRedirect = $false
$client = New-Object Net.Http.HttpClient($handler)
try {
    $manifestResponse = Invoke-TrustedGet $client $manifestUri $trustMode
    try {
        $manifestBytes = $manifestResponse.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
    } finally {
        $manifestResponse.Dispose()
    }
    $strictUtf8 = New-Object Text.UTF8Encoding($false, $true)
    $manifestText = $strictUtf8.GetString($manifestBytes)
    $manifest = ConvertFrom-StrictJson $manifestText
    Assert-ExactKeys $manifest @("schema_version", "version", "artifacts") "release manifest"
    if (-not (Test-Integer $manifest.schema_version) -or $manifest.schema_version -ne 1) {
        throw "release manifest schema_version must be integer 1"
    }
    if ($manifest.version -isnot [string] -or $manifest.version -notmatch '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$') {
        throw "release manifest version must be a semantic version"
    }
    if ($manifest.artifacts -isnot [Array]) {
        throw "release manifest artifacts must be a JSON array"
    }
    $artifacts = @($manifest.artifacts)
    if ($artifacts.Count -eq 0) {
        throw "release manifest artifacts must be a non-empty array"
    }
    $selectedArtifacts = @()
    $seenPairs = @{}
    for ($i = 0; $i -lt $artifacts.Count; $i++) {
        $artifact = $artifacts[$i]
        Assert-ExactKeys $artifact @(
            "platform", "architecture", "filename", "size", "sha256"
        ) "release manifest artifact"
        if (
            $artifact.platform -isnot [string] -or
            $artifact.architecture -isnot [string] -or
            $artifact.filename -isnot [string] -or
            -not (Test-Integer $artifact.size) -or $artifact.size -le 0 -or
            $artifact.sha256 -isnot [string] -or
            $artifact.sha256 -cnotmatch '^[0-9a-f]{64}$'
        ) {
            throw "release manifest artifact has invalid field types"
        }
        if (
            [string]::IsNullOrEmpty($artifact.filename) -or
            [IO.Path]::GetFileName($artifact.filename) -cne $artifact.filename -or
            $artifact.filename.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0
        ) {
            throw "release manifest artifact filename must be a safe leaf name"
        }
        $pair = "$($artifact.platform)`0$($artifact.architecture)"
        if ($seenPairs.ContainsKey($pair)) {
            throw "release manifest has a duplicate platform/architecture pair"
        }
        $seenPairs[$pair] = $true
        if (
            $artifact.platform -ceq "windows" -and
            $artifact.architecture -ceq "x86_64"
        ) {
            $selectedArtifacts += $artifact
        }
    }
    if ($selectedArtifacts.Count -ne 1) {
        throw "release manifest must contain exactly one windows/x86_64 artifact"
    }
    $selected = $selectedArtifacts[0]
    $artifactUri = New-Object Uri($manifestUri, $selected.filename)
    Assert-TrustedRequestUri $artifactUri $trustMode
    $artifactResponse = Invoke-TrustedGet $client $artifactUri $trustMode
    try {
        $artifactStream = $artifactResponse.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        try {
            $output = New-Object IO.FileStream(
                $staged,
                [IO.FileMode]::CreateNew,
                [IO.FileAccess]::Write,
                [IO.FileShare]::None
            )
            try {
                $artifactStream.CopyTo($output)
                $output.Flush($true)
            } finally {
                $output.Dispose()
            }
        } finally {
            $artifactStream.Dispose()
        }
    } finally {
        $artifactResponse.Dispose()
    }

    $actualSize = (Get-Item -LiteralPath $staged).Length
    if ($actualSize -ne $selected.size) {
        throw "release artifact size mismatch"
    }
    $actualHash = (Get-FileHash -LiteralPath $staged -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -cne $selected.sha256) {
        throw "release artifact SHA-256 mismatch"
    }

    $resolvedTarget = [IO.Path]::GetFullPath($target)
    $channel = [ordered]@{
        schema_version = 1
        channel = "native"
        executable = $resolvedTarget
        manifest_url = $canonicalManifestUrl
    }
    $channelJson = $channel | ConvertTo-Json
    $utf8WithoutBom = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($channelStaged, $channelJson, $utf8WithoutBom)

    $channelExisted = [IO.File]::Exists($channelTarget)
    if ($channelExisted) {
        [IO.File]::Replace($channelStaged, $channelTarget, $channelPrevious)
    } else {
        [IO.File]::Move($channelStaged, $channelTarget)
    }
    try {
        if (
            $trustMode -eq "loopback" -and
            $env:SOCRATIC_TEST_FAIL_EXECUTABLE_PUBLICATION -eq "1"
        ) {
            throw "Injected executable publication failure"
        }
        if ([IO.File]::Exists($target)) {
            [IO.File]::Replace($staged, $target, $targetPrevious)
        } else {
            [IO.File]::Move($staged, $target)
        }
        Remove-Item -Force -ErrorAction SilentlyContinue `
            $channelPrevious, $targetPrevious
    } catch {
        $publicationError = $_
        try {
            if ([IO.File]::Exists($targetPrevious)) {
                if ([IO.File]::Exists($target)) {
                    [IO.File]::Replace(
                        $targetPrevious,
                        $target,
                        $targetFailed
                    )
                } else {
                    [IO.File]::Move($targetPrevious, $target)
                }
                Remove-Item -Force -ErrorAction SilentlyContinue $targetFailed
            }
            if ($channelExisted) {
                if ([IO.File]::Exists($channelTarget)) {
                    [IO.File]::Replace(
                        $channelPrevious,
                        $channelTarget,
                        $channelFailed
                    )
                } else {
                    [IO.File]::Move($channelPrevious, $channelTarget)
                }
                Remove-Item -Force -ErrorAction SilentlyContinue $channelFailed
            } else {
                Remove-Item -LiteralPath $channelTarget -Force `
                    -ErrorAction SilentlyContinue
            }
        } catch {
            throw "Executable publication failed and channel metadata rollback failed"
        }
        throw $publicationError
    }

    if (-not $installWasOverridden) {
        $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
        $entries = @($userPath -split ';' | Where-Object { $_ })
        if (-not ($entries | Where-Object { $_.TrimEnd('\') -ieq $installPath.TrimEnd('\') })) {
            $updatedPath = if ([string]::IsNullOrEmpty($userPath)) {
                $installPath
            } else {
                "$userPath;$installPath"
            }
            [Environment]::SetEnvironmentVariable("Path", $updatedPath, "User")
        }
    }
} finally {
    $client.Dispose()
    $handler.Dispose()
    Remove-Item -Force -ErrorAction SilentlyContinue $staged, $channelStaged
}

Write-Output "Run: socratic"
