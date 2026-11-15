"""Verifica a preservação da configuração do Dolphin no provisionamento Android."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="Requer PowerShell Core")
@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("initial", [False, True])
def test_android_setup_preserves_dolphin_private_config(
    tmp_path: Path, force: bool, initial: bool
) -> None:
    """Preserva instalação existente e aplica perfil somente após criação pelo app."""
    script_dir = tmp_path / "scripts"
    template_dir = tmp_path / "templates" / "android"
    script_dir.mkdir()
    template_dir.mkdir(parents=True)
    script = script_dir / "setup_android_emulators.ps1"
    shutil.copy2(ROOT / "scripts" / script.name, script)
    shutil.copy2(ROOT / "templates" / "android" / "Dolphin.ini", template_dir)
    env = os.environ.copy()
    env.update(
        RETRO_TEST_SCRIPT=str(script),
        RETRO_TEST_LOG=str(tmp_path / "adb.jsonl"),
        RETRO_TEST_INITIAL=str(initial).lower(),
    )
    command = r"""
$global:configPresent = $env:RETRO_TEST_INITIAL -ne 'true'
$global:profileApplied = $false
$global:profile = ''
function adb {
    $arguments = @($args)
    $json = ConvertTo-Json -Compress -InputObject $arguments
    Add-Content -LiteralPath $env:RETRO_TEST_LOG -Value $json
    $global:LASTEXITCODE = 0
    if ($arguments[0] -eq 'devices') { return "List of devices attached`nserial`tdevice" }
    if ($arguments -contains 'getprop ro.product.cpu.abi') { return 'arm64-v8a' }
    if ($arguments -contains 'getprop ro.product.model') { return 'test-device' }
    if ($arguments -contains 'pm list packages') { return 'package:org.dolphinemu.dolphinemu' }
    $call = $arguments -join ' '
    if ($arguments -contains 'push' -and $arguments[-1] -match 'retrogame-dolphin-.*\.ini$') {
        $global:profile = Get-Content -Raw -LiteralPath $arguments[-2]
    }
    if ($call -match 'am start .*dolphinemu') { $global:configPresent = $true; return }
    if ($call -match 'if \[ -f .*dolphinemu.*Dolphin.ini') {
        if ($global:configPresent) { return 'present' }
        return 'missing'
    }
    if ($call -match "cat .* > .*Dolphin.ini") { $global:profileApplied = $true; return }
    if ($call -match "cat .*Dolphin.ini") {
        if ($global:profileApplied) { return $global:profile }
        return "[Analytics]`nEnabled = True`n[Core]`nExisting = keep"
    }
}
& $env:RETRO_TEST_SCRIPT -SkipDownload __FORCE__
if ($env:RETRO_TEST_INITIAL -eq 'true') {
    if ($global:profile -notmatch 'Existing = keep' -or
        $global:profile -notmatch 'Enabled = True' -or
        ([regex]::Matches($global:profile, '(?m)^\[Core\]$')).Count -ne 1) { exit 5 }
}
""".replace("__FORCE__", "-ForceTemplates" if force else "")
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
    lines = (tmp_path / "adb.jsonl").read_text(encoding="utf-8-sig").splitlines()
    calls = [json.loads(line) for line in lines]
    calls_text = [" ".join(call) for call in calls]
    assert any("/RetroGames/config/Dolphin.ini" in call for call in calls_text)
    assert not any(" mkdir " in call and "org.dolphinemu.dolphinemu" in call for call in calls_text)
    assert not any(" push " in call and "org.dolphinemu.dolphinemu" in call for call in calls_text)
    writes = [call for call in calls_text if " > " in call and "Dolphin.ini" in call]
    assert bool(writes) is initial
    if initial:
        start = next(i for i, call in enumerate(calls_text) if "am start" in call)
        stop = next(i for i, call in enumerate(calls_text) if "am force-stop" in call)
        write = next(i for i, call in enumerate(calls_text) if call in writes)
        assert start < stop < write
    assert not any("/dolphin-emu/Config" in call for call in calls_text)
