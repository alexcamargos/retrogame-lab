<#
.SYNOPSIS
    Validação e provisionamento automatizado do Syncthing (Windows 11 e Android).
.DESCRIPTION
    Executa a auditoria de conformidade das regras de sincronização, integridade do .stignore,
    presença de marcadores .stfolder, permissões Scoped Storage e Doze Mode no Android,
    além de suportar auto-configuração do config.xml local e geração de template para o app móvel.
.PARAMETER Apply
    Aplica correções automaticamente e provisiona os arquivos de configuração necessários.
.PARAMETER NoAndroid
    Ignora as verificações no dispositivo Android conectado via ADB.
.PARAMETER NoWindows
    Ignora as verificações no host Windows.
.PARAMETER DeviceId
    Identificador específico de dispositivo Android no ADB (caso haja múltiplos conectados).
.PARAMETER Json
    Retorna o diagnóstico estruturado em formato JSON.
.EXAMPLE
    .\scripts\manage_syncthing.ps1
    .\scripts\manage_syncthing.ps1 -Apply
    .\scripts\manage_syncthing.ps1 -NoAndroid
#>
[CmdletBinding()]
param (
    [switch]$Apply = $false,
    [switch]$NoAndroid = $false,
    [switch]$NoWindows = $false,
    [string]$DeviceId = "",
    [switch]$Json = $false
)

$ErrorActionPreference = "Stop"

$ArgsList = @("run", "retrogame-lab", "syncthing")

if ($Apply) {
    $ArgsList += "--apply"
}

if ($NoAndroid) {
    $ArgsList += "--no-android"
}

if ($NoWindows) {
    $ArgsList += "--no-windows"
}

if ($DeviceId) {
    $ArgsList += @("--device-id", $DeviceId)
}

if ($Json) {
    $ArgsList += "--json"
}

& uv @ArgsList
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
