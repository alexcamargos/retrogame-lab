"""Testes unitários para o módulo auditor do RetroGame Lab.

Valida cálculo de somas SHA-256, detecção de violações de formato de ROMs,
firmwares de BIOS e regras anti-conflito de salvamentos.
"""

import hashlib
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from retrogame_lab.auditor import (
    KNOWN_BIOS_HASHES,
    Severity,
    audit_bios,
    audit_roms,
    audit_saves,
    compute_sha256,
    run_full_audit,
)


def test_compute_sha256_real_file(tmp_path: Path) -> None:
    """Verifica o cálculo exato do hash SHA-256 para um arquivo real.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.

    Returns:
        None.

    Raises:
        None.
    """
    sample = tmp_path / "sample.bin"
    content = b"RetroGame Lab Test Content 12345"
    sample.write_bytes(content)

    expected = hashlib.sha256(content).hexdigest()
    actual = compute_sha256(sample)
    assert actual == expected


def test_compute_sha256_missing_file(tmp_path: Path) -> None:
    """Verifica se compute_sha256 levanta FileNotFoundError para arquivo inexistente.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.

    Returns:
        None.

    Raises:
        None.
    """
    non_existent = tmp_path / "missing.bin"
    with pytest.raises(FileNotFoundError, match="Arquivo não localizado"):
        compute_sha256(non_existent)


def test_compute_sha256_is_directory(tmp_path: Path) -> None:
    """Verifica se compute_sha256 levanta IsADirectoryError quando apontado para pasta.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.

    Returns:
        None.

    Raises:
        None.
    """
    folder = tmp_path / "subfolder"
    folder.mkdir()
    with pytest.raises(IsADirectoryError, match="Caminho é um diretório"):
        compute_sha256(folder)


def test_compute_sha256_with_mock(tmp_path: Path, mocker: MockerFixture) -> None:
    """Valida o cálculo de hash utilizando mock do stream de leitura via pytest-mock.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.
        mocker: Fixture de espionagem e mock do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    target_file = tmp_path / "mocked.bin"
    target_file.write_bytes(b"placeholder")

    mock_hasher = mocker.MagicMock()
    mock_hasher.hexdigest.return_value = "mockedhash1234567890"
    mocker.patch("hashlib.sha256", return_value=mock_hasher)

    result = compute_sha256(target_file)
    assert result == "mockedhash1234567890"
    assert mock_hasher.update.called


def test_audit_bios_missing_directory(tmp_path: Path) -> None:
    """Verifica alerta emitido quando a pasta de BIOS não existe.

    Args:
        tmp_path: Diretório temporário.

    Returns:
        None.

    Raises:
        None.
    """
    missing_dir = tmp_path / "non_existent_bios"
    summary = audit_bios(missing_dir)

    assert summary.is_healthy
    assert len(summary.issues) == 1
    assert summary.issues[0].severity == Severity.WARNING


def test_audit_bios_empty_directory(tmp_path: Path) -> None:
    """Verifica aviso informativo quando a pasta de BIOS está vazia.

    Args:
        tmp_path: Diretório temporário.

    Returns:
        None.

    Raises:
        None.
    """
    empty_dir = tmp_path / "bios"
    empty_dir.mkdir()
    summary = audit_bios(empty_dir)

    assert summary.is_healthy
    assert len(summary.issues) == 1
    assert summary.issues[0].severity == Severity.INFO


def test_audit_bios_valid_and_invalid_hash(tmp_path: Path, mocker: MockerFixture) -> None:
    """Verifica a correta validação de hashes conhecidos vs corrompidos de BIOS.

    Args:
        tmp_path: Diretório temporário.
        mocker: Fixture do pytest-mock para isolamento de estado global.

    Returns:
        None.

    Raises:
        None.
    """
    bios_dir = tmp_path / "bios" / "ps1"
    bios_dir.mkdir(parents=True)

    # 1. Arquivo com hash válido de scph5501.bin
    valid_file = bios_dir / "scph5501.bin"
    valid_file.write_bytes(b"dummy")

    # 2. Arquivo com hash inválido de scph7001.bin
    invalid_file = bios_dir / "scph7001.bin"
    invalid_file.write_bytes(b"corrupted dump")

    # Mapeamos o hash do dummy para ser aceito sem mutar permanentemente o dicionário
    dummy_hash = hashlib.sha256(b"dummy").hexdigest()
    mocker.patch.dict(KNOWN_BIOS_HASHES, {"scph5501.bin": dummy_hash})

    summary = audit_bios(tmp_path / "bios")
    # scph7001.bin deve gerar um ERROR
    error_issues = [i for i in summary.issues if i.severity == Severity.ERROR]
    assert len(error_issues) == 1
    assert "scph7001.bin" in error_issues[0].message


def test_audit_roms_gamecube_rules(tmp_path: Path) -> None:
    """Verifica a proibição estrita de .chd e recomendação de .rvz para GameCube.

    Args:
        tmp_path: Diretório temporário.

    Returns:
        None.

    Raises:
        None.
    """
    gc_dir = tmp_path / "roms" / "gc"
    gc_dir.mkdir(parents=True)

    # CHD no GameCube é proibido e gera ERROR
    (gc_dir / "smash_melee.chd").write_text("dummy", encoding="utf-8")
    # ISO no GameCube gera WARNING (recomendando RVZ)
    (gc_dir / "mario_sunshine.iso").write_text("dummy", encoding="utf-8")
    # RVZ no GameCube é válido e limpo
    (gc_dir / "zelda_windwaker.rvz").write_text("dummy", encoding="utf-8")

    summary = audit_roms(tmp_path / "roms")
    assert summary.total_scanned == 3

    errors = [i for i in summary.issues if i.severity == Severity.ERROR]
    warnings = [i for i in summary.issues if i.severity == Severity.WARNING]

    assert len(errors) == 1
    assert "smash_melee.chd" in errors[0].message
    assert len(warnings) == 1
    assert "mario_sunshine.iso" in warnings[0].message


def test_audit_roms_ps1_and_ps2_rules(tmp_path: Path) -> None:
    """Verifica recomendações de conversão para PS1 (.cue/.bin -> .chd) e PS2 (.iso).

    Args:
        tmp_path: Diretório temporário.

    Returns:
        None.

    Raises:
        None.
    """
    roms_dir = tmp_path / "roms"
    ps1_dir = roms_dir / "ps1"
    ps2_dir = roms_dir / "ps2"
    ps1_dir.mkdir(parents=True)
    ps2_dir.mkdir(parents=True)

    (ps1_dir / "mgs_disc1.cue").write_text("dummy", encoding="utf-8")
    (ps1_dir / "mgs_disc1.bin").write_text("dummy", encoding="utf-8")
    (ps2_dir / "shadow_of_colossus.iso").write_text("dummy", encoding="utf-8")

    summary = audit_roms(roms_dir)
    assert summary.total_scanned == 3

    warnings = [i for i in summary.issues if i.severity == Severity.WARNING]
    infos = [i for i in summary.issues if i.severity == Severity.INFO]

    assert len(warnings) == 2  # .cue e .bin no PS1
    assert len(infos) == 1  # .iso no PS2


def test_audit_saves_violations(tmp_path: Path) -> None:
    """Verifica a detecção de savestates proibidos, locks e memory cards compartilhados.

    Args:
        tmp_path: Diretório temporário.

    Returns:
        None.

    Raises:
        None.
    """
    saves_dir = tmp_path / "saves"
    ps1_saves = saves_dir / "ps1"
    ps1_saves.mkdir(parents=True)

    # 1. Savestate proibido -> ERROR
    (ps1_saves / "crash_bandicoot.state").write_text("state", encoding="utf-8")
    (ps1_saves / "metal_gear.s01").write_text("state", encoding="utf-8")
    # 2. Arquivo de lock -> WARNING
    (ps1_saves / "duckstation.lock").write_text("lock", encoding="utf-8")
    # 3. Memory Card global compartilhado -> ERROR
    (ps1_saves / "shared_card_1.mcd").write_text("card", encoding="utf-8")
    (ps1_saves / "mcd002.ps2").write_text("card", encoding="utf-8")
    # 4. Saves válidos por título (incluindo nomes com .s0 no meio) -> Válido
    (ps1_saves / "Tekken_3_SCUS-94238.mcd").write_text("valid", encoding="utf-8")
    (ps1_saves / "megaman_s01.srm").write_text("valid", encoding="utf-8")

    summary = audit_saves(saves_dir)
    assert summary.total_scanned == 7

    errors = [i for i in summary.issues if i.severity == Severity.ERROR]
    warnings = [i for i in summary.issues if i.severity == Severity.WARNING]

    # crash_bandicoot.state, metal_gear.s01, shared_card_1.mcd, mcd002.ps2
    assert len(errors) == 4
    assert len(warnings) == 1  # lock


def test_audit_roms_loose_file_in_root(tmp_path: Path) -> None:
    """Verifica aviso para arquivo de ROM colocado solto na raiz de data/roms/.

    Args:
        tmp_path: Diretório temporário.

    Returns:
        None.

    Raises:
        None.
    """
    roms_dir = tmp_path / "roms"
    roms_dir.mkdir()

    (roms_dir / "loose_game.sfc").write_text("dummy", encoding="utf-8")

    summary = audit_roms(roms_dir)
    assert summary.total_scanned == 1
    assert len(summary.issues) == 1
    assert summary.issues[0].severity == Severity.WARNING
    assert "Arquivo solto na raiz" in summary.issues[0].message


def test_audit_roms_dreamcast_gdi_and_cdi(tmp_path: Path) -> None:
    """Verifica recomendações de conversão para mídias desmembradas de Dreamcast.

    Args:
        tmp_path: Diretório temporário.

    Returns:
        None.

    Raises:
        None.
    """
    dc_dir = tmp_path / "roms" / "dc"
    dc_dir.mkdir(parents=True)

    (dc_dir / "sonic_adventure.gdi").write_text("dummy", encoding="utf-8")
    (dc_dir / "crazy_taxi.cdi").write_text("dummy", encoding="utf-8")

    summary = audit_roms(tmp_path / "roms")
    assert summary.total_scanned == 2

    warnings = [i for i in summary.issues if i.severity == Severity.WARNING]
    assert len(warnings) == 2


def test_audit_roms_special_characters_and_unsupported_extensions(tmp_path: Path) -> None:
    """Verifica detecção de caracteres especiais e extensões não homologadas ou proibidas.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.

    Returns:
        None.

    Raises:
        None.
    """
    roms_dir = tmp_path / "roms"
    snes_dir = roms_dir / "snes"
    ps1_dir = roms_dir / "ps1"
    snes_dir.mkdir(parents=True)
    ps1_dir.mkdir(parents=True)

    # 1. SNES com ponto de exclamação no nome -> WARNING de nomenclatura
    (snes_dir / "mario_[!].sfc").write_text("dummy", encoding="utf-8")
    # 2. SNES com .state -> ERROR de extensão proibida
    (snes_dir / "mario.state").write_text("dummy", encoding="utf-8")
    # 3. PS1 com .zip -> WARNING de extensão não suportada
    (ps1_dir / "crash.zip").write_text("dummy", encoding="utf-8")

    summary = audit_roms(roms_dir)
    errors = [i for i in summary.issues if i.severity == Severity.ERROR]
    warnings = [i for i in summary.issues if i.severity == Severity.WARNING]

    assert any("Extensão proibida '.state'" in i.message for i in errors)
    assert any("Nomenclatura fora do padrão" in i.message for i in warnings)
    assert any("Extensão não suportada '.zip'" in i.message for i in warnings)


def test_audit_saves_special_characters(tmp_path: Path) -> None:
    """Verifica detecção de caracteres especiais em nomes de saves.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.

    Returns:
        None.

    Raises:
        None.
    """
    saves_dir = tmp_path / "saves"
    snes_saves = saves_dir / "snes"
    snes_saves.mkdir(parents=True)

    (snes_saves / "mario_save_#1.srm").write_text("dummy", encoding="utf-8")
    summary = audit_saves(saves_dir)

    warnings = [i for i in summary.issues if i.severity == Severity.WARNING]
    assert any("Nome de save fora do padrão" in i.message for i in warnings)


def test_run_full_audit(mock_repo_root: Path) -> None:
    """Verifica a execução integrada do relatório de auditoria completa.

    Args:
        mock_repo_root: Fixture com a estrutura completa mockada.

    Returns:
        None.

    Raises:
        None.
    """
    report = run_full_audit(mock_repo_root)
    assert report.bios.category == "BIOS"
    assert report.roms.category == "ROMs"
    assert report.saves.category == "Saves"
    assert not report.has_errors
