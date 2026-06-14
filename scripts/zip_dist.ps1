param(
    [Parameter(Mandatory = $true)]
    [string]$SourceDir,

    [Parameter(Mandatory = $true)]
    [string]$DestinationZip,

    [int]$Retries = 6,

    [int]$DelaySeconds = 5
)

$ErrorActionPreference = "Stop"

for ($attempt = 1; $attempt -le $Retries; $attempt++) {
    try {
        if (Test-Path $DestinationZip) {
            Remove-Item $DestinationZip -Force
        }
        Compress-Archive -Path (Join-Path $SourceDir "*") -DestinationPath $DestinationZip -Force
        Write-Host "Zip created: $DestinationZip"
        exit 0
    }
    catch {
        Write-Host "Zip attempt $attempt/$Retries failed: $($_.Exception.Message)"
        if ($attempt -ge $Retries) {
            throw
        }
        Start-Sleep -Seconds $DelaySeconds
    }
}
