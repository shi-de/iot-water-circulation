$ErrorActionPreference = "Stop"

$sourcePath = Join-Path $PSScriptRoot "..\src\PressureSensor.cpp"
$source = Get-Content -Raw -LiteralPath $sourcePath
$mainPath = Join-Path $PSScriptRoot "..\src\main.cpp"
$main = Get-Content -Raw -LiteralPath $mainPath

function Assert-Contains {
    param(
        [string]$Text,
        [string]$Pattern,
        [string]$Message
    )

    if ($Text -notmatch $Pattern) {
        throw $Message
    }
}

function Assert-NotContains {
    param(
        [string]$Text,
        [string]$Pattern,
        [string]$Message
    )

    if ($Text -match $Pattern) {
        throw $Message
    }
}

Assert-Contains $source 'PS_I2C_ADDR\s+0x00' `
    "The documented 7-bit address 0x00 must remain supported."
Assert-Contains $source '0x7F' `
    "The vendor 8-bit address 0xFE/0xFF must be supported as 7-bit address 0x7F."
Assert-Contains $source 'endTransmission\([^)]*\)' `
    "I2C writes must check endTransmission() before continuing."
Assert-Contains $source 'requestFrom\([^;]+\)' `
    "I2C reads must check the number of bytes returned."
Assert-Contains $source 'while\s*\(\s*\(drdy\s*&\s*0x01\)\s*&&' `
    "DRDY polling must wait while bit0 is busy (1) and continue when it is 0."
Assert-NotContains $source 'if\s*\(\s*drdy\s*&\s*0x01\s*\)\s*break' `
    "DRDY=1 must not be treated as conversion complete."
Assert-NotContains $source '\*\s*65535' `
    "The 24-bit pressure value must not use the incorrect 65535 multiplier."

Assert-NotContains $main 'if\s*\(\s*IotMqtt_IsConnected\(\)\s*&&' `
    "Pressure sampling must not depend on MQTT being connected."
Assert-Contains $main 'float pressure\s*=\s*PressureSensor\(\)' `
    "The main loop must sample pressure independently of MQTT publishing."

Write-Output "Pressure sensor contract checks passed."
