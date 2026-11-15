"""Testes isolados dos caminhos críticos dos scripts PowerShell no Windows."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or shutil.which("pwsh") is None,
    reason="Requer Windows e PowerShell Core",
)


def test_convert_chd_requires_explicit_iso_type_and_verifies_output(tmp_path: Path) -> None:
    """ISOs ambíguas não são convertidas; resultados são verificados antes da publicação."""
    script_dir = tmp_path / "project" / "scripts"
    script_dir.mkdir(parents=True)
    script = script_dir / "convert_chd.ps1"
    shutil.copy2(ROOT / "scripts" / "convert_chd.ps1", script)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "chdman.ps1").write_text(
        "param($Command, $i, $o)\n"
        "Add-Content -LiteralPath $env:RETRO_TEST_LOG -Value $Command\n"
        "if ($o) { Set-Content -LiteralPath $o -Value 'chd' }\n"
        "$global:LASTEXITCODE = 0\n",
        encoding="utf-8",
    )
    media = tmp_path / "media"
    media.mkdir()
    (media / "Game.iso").write_bytes(b"test")
    log = tmp_path / "calls.txt"
    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env["PATH"]
    env["RETRO_TEST_LOG"] = str(log)

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        """Executa a cópia isolada do conversor."""
        return subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(script), "-SourceDirectory", str(media), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=False,
        )

    assert run().returncode != 0
    assert not log.exists()
    result = run("-MediaType", "dvd")
    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8-sig").splitlines() == ["createdvd", "verify"]
    assert (media / "game.chd").is_file()
    assert run("-MediaType", "dvd").returncode != 0


def test_staged_install_rolls_back_if_a_later_file_cannot_be_installed(tmp_path: Path) -> None:
    """Restaura arquivos anteriores quando uma junção bloqueia a aplicação."""
    stage = tmp_path / "stage"
    destination = tmp_path / "destination"
    backup = tmp_path / "backup"
    (stage / "zlink").mkdir(parents=True)
    destination.mkdir()
    (stage / "a.txt").write_text("new", encoding="utf-8")
    (stage / "zlink" / "file.txt").write_text("new", encoding="utf-8")
    (destination / "a.txt").write_text("old", encoding="utf-8")
    external = tmp_path / "external"
    external.mkdir()
    env = os.environ.copy()
    env.update(
        RETRO_TEST_SCRIPT=str(ROOT / "scripts" / "download_emulators.ps1"),
        RETRO_TEST_STAGE=str(stage),
        RETRO_TEST_DEST=str(destination),
        RETRO_TEST_BACKUP=str(backup),
        RETRO_TEST_EXTERNAL=str(external),
    )
    command = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:RETRO_TEST_SCRIPT, [ref]$tokens, [ref]$errors)
$fn = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Install-StagedFiles'
}, $true)
Invoke-Expression $fn.Extent.Text
New-Item -ItemType Junction -Path (Join-Path $env:RETRO_TEST_DEST 'zlink') `
    -Target $env:RETRO_TEST_EXTERNAL | Out-Null
try {
    Install-StagedFiles $env:RETRO_TEST_STAGE $env:RETRO_TEST_DEST $env:RETRO_TEST_BACKUP
    exit 2
} catch {
    if ((Get-Content -Raw (Join-Path $env:RETRO_TEST_DEST 'a.txt')) -ne 'old') { exit 3 }
    if (Test-Path (Join-Path $env:RETRO_TEST_EXTERNAL 'file.txt')) { exit 4 }
}
"""
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_junction_repair_preserves_existing_old_saves(tmp_path: Path) -> None:
    """Recusa desviar uma junção se o destino anterior ainda existir."""
    old = tmp_path / "old"
    new = tmp_path / "new"
    missing = tmp_path / "missing"
    old.mkdir()
    new.mkdir()
    missing.mkdir()
    (old / "save.dat").write_text("progress", encoding="utf-8")
    link = tmp_path / "link"
    env = os.environ.copy()
    env.update(
        RETRO_TEST_SCRIPT=str(ROOT / "scripts" / "bootstrap.ps1"),
        RETRO_TEST_OLD=str(old),
        RETRO_TEST_NEW=str(new),
        RETRO_TEST_LINK=str(link),
        RETRO_TEST_MISSING=str(missing),
    )
    command = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:RETRO_TEST_SCRIPT, [ref]$tokens, [ref]$errors)
$fn = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Ensure-SaveJunction'
}, $true)
Invoke-Expression $fn.Extent.Text
New-Item -ItemType Junction -Path $env:RETRO_TEST_LINK -Target $env:RETRO_TEST_OLD | Out-Null
try { Ensure-SaveJunction $env:RETRO_TEST_LINK $env:RETRO_TEST_NEW; exit 2 } catch { }
if ((Get-Content -Raw (Join-Path $env:RETRO_TEST_LINK 'save.dat')) -ne 'progress') { exit 3 }
$broken = $env:RETRO_TEST_LINK + '2'
New-Item -ItemType Junction -Path $broken -Target $env:RETRO_TEST_MISSING | Out-Null
Remove-Item -LiteralPath $env:RETRO_TEST_MISSING
Ensure-SaveJunction $broken $env:RETRO_TEST_NEW
if (-not (Test-Path -LiteralPath $broken)) { exit 4 }
if ((Get-Item -LiteralPath $broken).Target -ne $env:RETRO_TEST_NEW) { exit 5 }
"""
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (old / "save.dat").read_text(encoding="utf-8") == "progress"
