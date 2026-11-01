<#
.SYNOPSIS
    Orquestrador e CLI Unificada do RetroGame Lab no Windows.
.DESCRIPTION
    Fornece um ponto de entrada unificado para execução transparente de
    automações em PowerShell Core (pwsh) e tarefas analíticas/ingestão em Python (uv).
.EXAMPLE
    .\retrogame bootstrap -SkipWinget
    .\retrogame audit
    .\retrogame sanitize --apply
    .\retrogame launch snes data/roms/snes/Super_Mario_World.sfc
#>
$Command = if ($args.Count -gt 0) { $args[0] } else { "help" }
[string[]]$RemainingArgs = if ($args.Count -gt 1) { @($args[1..($args.Count - 1)]) } else { @() }

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$ScriptsDir = Join-Path $ScriptDir "scripts"

function Show-Help {
    Write-Host "`n=== RetroGame Lab - Interface de Linha de Comando Unificada ===" -ForegroundColor Green
    Write-Host "Uso: .\retrogame <subcomando> [opções...]`n" -ForegroundColor Cyan

    Write-Host "Comandos de Automação do Sistema (PowerShell):" -ForegroundColor Yellow
    Write-Host "  bootstrap          Cria diretórios, templates e instala ferramentas via winget"
    Write-Host "                     Ex.: .\retrogame bootstrap [-SkipWinget]"
    Write-Host "  download-emulators Baixa e extrai versões portáteis oficiais dos emuladores em bin/"
    Write-Host "                     Ex.: .\retrogame download-emulators [-Force] [-Emulators pcsx2,duckstation]"
    Write-Host "  check-updates      Compara versões instaladas contra os repositórios oficiais"
    Write-Host "                     Ex.: .\retrogame check-updates"
    Write-Host "  update-emulators   Atualiza apenas os emuladores que possuem novas versões disponíveis"
    Write-Host "                     Ex.: .\retrogame update-emulators"
    Write-Host "  launch             Inicializa jogos com seleção dinâmica de GPU e afinidade de CPU"
    Write-Host "                     Ex.: .\retrogame launch -Platform ps1 -RomPath data\roms\ps1\jogo.chd"
    Write-Host "  convert-chd     Compacta imagens de disco em lote para formato CHD determinístico"
    Write-Host "                  Ex.: .\retrogame convert-chd -SourceDirectory c:\temp\jogos"
    Write-Host "  android         Provisiona diretórios, permissões e APKs no Android via ADB"
    Write-Host "                  Ex.: .\retrogame android [-SkipDownload]`n"

    Write-Host "Comandos Analíticos e de Biblioteca (Python / uv):" -ForegroundColor Yellow
    Write-Host "  audit           Audita integridade de BIOS, formatos de ROMs e regras de saves"
    Write-Host "                  Ex.: .\retrogame audit [--json]"
    Write-Host "  sanitize        Higieniza nomes de ROMs e saves (remove espaços e caracteres especiais)"
    Write-Host "                  Ex.: .\retrogame sanitize [--apply]"
    Write-Host "  import-rom      Ingere e higieniza uma nova ROM para a biblioteca canônica"
    Write-Host "                  Ex.: .\retrogame import-rom c:\temp\jogo.bin -p ps1"
    Write-Host "  fetch-roms      Busca e ingere interativamente ROMs de preservação (todas as plataformas)"
    Write-Host "                  Ex.: .\retrogame fetch-roms -p ps1 [-q crash] [-i colecao]"
    Write-Host "  fetch-snes      Atalho para busca interativa em SNES (No-Intro)"
    Write-Host "                  Ex.: .\retrogame fetch-snes [-q mario]"
    Write-Host "  info            Exibe o catálogo de plataformas suportadas e formatos aceitos"
    Write-Host "  version         Exibe a versão instalada do RetroGame Lab`n"

    Write-Host "Dica: Você também pode executar diretamente via uv:" -ForegroundColor DarkGray
    Write-Host "  uv run retrogame <subcomando> [opções...]`n" -ForegroundColor DarkGray
}

switch -Regex ($Command.ToLower()) {
    "^(help|-h|--help)$" {
        Show-Help
    }
    "^bootstrap$" {
        & pwsh -NoProfile -File "$ScriptsDir\bootstrap.ps1" @RemainingArgs
    }
    "^(download-emulators|download_emulators|install-emulators|install_emulators|emulators)$" {
        & pwsh -NoProfile -File "$ScriptsDir\download_emulators.ps1" @RemainingArgs
    }
    "^(check-updates|check_updates|check)$" {
        & pwsh -NoProfile -File "$ScriptsDir\download_emulators.ps1" -CheckOnly @RemainingArgs
    }
    "^(update-emulators|update_emulators|update)$" {
        & pwsh -NoProfile -File "$ScriptsDir\download_emulators.ps1" -Update @RemainingArgs
    }
    "^(audit|audit_library|audit-library)$" {
        & uv run retrogame-lab audit @RemainingArgs
    }
    "^sanitize$" {
        & uv run retrogame-lab sanitize @RemainingArgs
    }
    "^(import-rom|import_rom|import)$" {
        & uv run retrogame-lab import-rom @RemainingArgs
    }
    "^(fetch-roms|fetch_roms)$" {
        & uv run retrogame-lab fetch-roms @RemainingArgs
    }
    "^fetch$" {
        if ($RemainingArgs.Count -gt 0 -and $RemainingArgs[0] -match "^(snes|ps1|ps2|psp|gc|dc)$") {
            $Plat = $RemainingArgs[0]
            $QueryArgs = if ($RemainingArgs.Count -gt 1) { @("-q", ($RemainingArgs[1..($RemainingArgs.Count - 1)] -join " ")) } else { @() }
            & uv run retrogame-lab fetch-roms -p $Plat @QueryArgs
        } else {
            & uv run retrogame-lab fetch-roms @RemainingArgs
        }
    }
    "^fetch-(snes|ps1|ps2|psp|gc|dc)$" {
        $Plat = $Matches[1]
        & uv run retrogame-lab fetch-roms -p $Plat @RemainingArgs
    }
    "^fetch_snes$" {
        & uv run retrogame-lab fetch-snes @RemainingArgs
    }
    "^launch$" {
        & pwsh -NoProfile -File "$ScriptsDir\launch.ps1" @RemainingArgs
    }
    "^(convert-chd|convert_chd|convert)$" {
        & pwsh -NoProfile -File "$ScriptsDir\convert_chd.ps1" @RemainingArgs
    }
    "^(setup-android|setup_android|android)$" {
        & pwsh -NoProfile -File "$ScriptsDir\setup_android_emulators.ps1" @RemainingArgs
    }
    "^info$" {
        & uv run retrogame-lab info @RemainingArgs
    }
    "^(version|-v|--version)$" {
        & uv run retrogame-lab version @RemainingArgs
    }
    default {
        Write-Host ">>> Repassando '$Command' para a CLI Python do RetroGame Lab..." -ForegroundColor DarkGray
        & uv run retrogame-lab $Command @RemainingArgs
    }
}

if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
