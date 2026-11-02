"""Testes unitários para o módulo de busca e ingestão de ROMs (fetcher).

Valida a consulta de catálogo com cache local, filtragem de títulos,
download e extração de compactados e acionamento do pipeline de importação.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from rich.console import Console

from retrogame_lab.fetcher import (
    ArchiveRomEntry,
    download_and_extract_rom,
    fetch_and_ingest_rom,
    get_archive_catalog,
    run_interactive_snes_fetcher,
    search_catalog,
)


def test_get_archive_catalog_cached(mock_repo_root: Path) -> None:
    """Verifica que o catálogo é lido diretamente do cache local quando disponível.

    Args:
        mock_repo_root: Fixture de raiz mockada do repositório.

    Returns:
        None.

    Raises:
        None.
    """
    scratch_dir = mock_repo_root / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    cache_file = scratch_dir / "cache_nointro-snes_files.json"

    dummy_data = [
        {"name": "Super Mario World (USA).zip", "size": "1048576"},
        {"name": "Chrono Trigger (USA).sfc", "size": "4194304"},
        {"name": "ignore_metadata.xml", "size": "123"},
    ]
    cache_file.write_text(json.dumps(dummy_data), encoding="utf-8")

    catalog = get_archive_catalog(repo_root=mock_repo_root)

    assert len(catalog) == 2
    titles = [item.title for item in catalog]
    assert "Super Mario World (USA)" in titles
    assert "Chrono Trigger (USA)" in titles


def test_get_archive_catalog_network_success(
    mock_repo_root: Path,
    mocker: MockerFixture,
) -> None:
    """Verifica consulta de catálogo via rede e persistência no arquivo de cache.

    Args:
        mock_repo_root: Fixture de raiz mockada do repositório.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    mock_response_data = {
        "result": [
            {"name": "Donkey Kong Country (USA).zip", "size": "2097152"},
            {"name": "ignore_me.sqlite", "size": "5000"},
        ]
    }
    mock_bytes = json.dumps(mock_response_data).encode("utf-8")

    mock_resp = mocker.MagicMock()
    mock_resp.read.return_value = mock_bytes
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    mocker.patch("urllib.request.urlopen", return_value=mock_resp)

    catalog = get_archive_catalog(repo_root=mock_repo_root)

    assert len(catalog) == 1
    assert catalog[0].title == "Donkey Kong Country (USA)"
    assert catalog[0].filename == "Donkey Kong Country (USA).zip"
    assert catalog[0].size_bytes == 2097152

    cache_file = mock_repo_root / "scratch" / "cache_nointro-snes_files.json"
    assert cache_file.exists()


def test_get_archive_catalog_network_error(
    mock_repo_root: Path,
    mocker: MockerFixture,
) -> None:
    """Verifica lançamento de RuntimeError se houver falha de rede sem cache local.

    Args:
        mock_repo_root: Fixture de raiz mockada do repositório.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    mocker.patch(
        "urllib.request.urlopen",
        side_effect=OSError("Falha de conexão com archive.org"),
    )

    with pytest.raises(RuntimeError, match="Falha ao consultar catálogo remoto"):
        get_archive_catalog(repo_root=mock_repo_root, force_refresh=True)


def test_search_catalog() -> None:
    """Verifica filtragem por múltiplos termos e limitação de resultados.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    items = [
        ArchiveRomEntry("Super Mario World (USA).zip", "Super Mario World (USA)", 100, "url1"),
        ArchiveRomEntry("Super Mario Kart (USA).zip", "Super Mario Kart (USA)", 200, "url2"),
        ArchiveRomEntry("Chrono Trigger (USA).zip", "Chrono Trigger (USA)", 300, "url3"),
    ]

    all_res = search_catalog(items, query="", limit=10)
    assert len(all_res) == 3

    mario_res = search_catalog(items, query="mario", limit=10)
    assert len(mario_res) == 2

    kart_res = search_catalog(items, query="mario kart", limit=10)
    assert len(kart_res) == 1
    assert kart_res[0].title == "Super Mario Kart (USA)"

    empty_res = search_catalog(items, query="zelda", limit=10)
    assert len(empty_res) == 0


def test_download_and_extract_rom_uncompressed(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Verifica download de arquivo de ROM já descompactado (.sfc).

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    entry = ArchiveRomEntry(
        filename="Sample_Game.sfc",
        title="Sample Game",
        size_bytes=10,
        download_url="https://archive.org/download/test/Sample_Game.sfc",
    )

    fake_bytes = b"SFC_HEADER_CONTENT"
    mock_resp = mocker.MagicMock()
    mock_resp.read.side_effect = [fake_bytes, b""]
    mock_resp.headers = {"Content-Length": str(len(fake_bytes))}
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    mocker.patch("urllib.request.urlopen", return_value=mock_resp)

    result_path = download_and_extract_rom(entry, tmp_path)

    assert result_path.exists()
    assert result_path.name == "Sample_Game.sfc"
    assert result_path.read_bytes() == fake_bytes


def test_download_and_extract_rom_zip(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Verifica download e extração de ROM contida em arquivo compactado .zip.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    entry = ArchiveRomEntry(
        filename="Super Mario World (USA).zip",
        title="Super Mario World (USA)",
        size_bytes=100,
        download_url="https://archive.org/download/test/smw.zip",
    )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("Super Mario World (USA).sfc", b"SFC_GAME_DATA")
    zip_bytes = zip_buffer.getvalue()

    mock_resp = mocker.MagicMock()
    mock_resp.read.side_effect = [zip_bytes, b""]
    mock_resp.headers = {"Content-Length": str(len(zip_bytes))}
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    mocker.patch("urllib.request.urlopen", return_value=mock_resp)

    result_path = download_and_extract_rom(entry, tmp_path)

    assert result_path.exists()
    assert result_path.name == "Super Mario World (USA).sfc"
    assert result_path.read_bytes() == b"SFC_GAME_DATA"
    # O arquivo .zip original deve ter sido removido
    assert not (tmp_path / entry.filename).exists()


def test_download_and_extract_rom_zip_no_rom(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Verifica que RuntimeError é lançado quando o zip não contém arquivo .sfc ou .smc.

    Args:
        tmp_path: Diretório temporário fornecido pelo pytest.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    entry = ArchiveRomEntry(
        filename="Invalid.zip",
        title="Invalid Game",
        size_bytes=100,
        download_url="https://archive.org/download/test/invalid.zip",
    )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("readme.txt", b"NO ROM HERE")
    zip_bytes = zip_buffer.getvalue()

    mock_resp = mocker.MagicMock()
    mock_resp.read.side_effect = [zip_bytes, b""]
    mock_resp.headers = {"Content-Length": str(len(zip_bytes))}
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    mocker.patch("urllib.request.urlopen", return_value=mock_resp)

    with pytest.raises(RuntimeError, match="não contém arquivos"):
        download_and_extract_rom(entry, tmp_path, platform_code="snes")


def test_fetch_and_ingest_rom(
    mock_repo_root: Path,
    mocker: MockerFixture,
) -> None:
    """Verifica o pipeline completo: download, extração e importação canônica com sanitização.

    Args:
        mock_repo_root: Fixture de raiz mockada do repositório.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    entry = ArchiveRomEntry(
        filename="Chrono Trigger (USA).zip",
        title="Chrono Trigger (USA)",
        size_bytes=50,
        download_url="https://archive.org/download/test/ct.zip",
    )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("Chrono Trigger (USA).sfc", b"CHRONO_TRIGGER_DATA")
    zip_bytes = zip_buffer.getvalue()

    mock_resp = mocker.MagicMock()
    mock_resp.read.side_effect = [zip_bytes, b""]
    mock_resp.headers = {"Content-Length": str(len(zip_bytes))}
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    mocker.patch("urllib.request.urlopen", return_value=mock_resp)

    final_path = fetch_and_ingest_rom(entry, platform_code="snes", repo_root=mock_repo_root)

    assert final_path.exists()
    assert final_path.name == "chrono_trigger_(usa).sfc"
    assert final_path.parent == mock_repo_root / "data" / "roms" / "snes"
    assert final_path.read_bytes() == b"CHRONO_TRIGGER_DATA"


def test_run_interactive_snes_fetcher_flow(
    mock_repo_root: Path,
    mocker: MockerFixture,
) -> None:
    """Verifica a execução do loop interativo selecionando um jogo e saindo.

    Args:
        mock_repo_root: Fixture de raiz mockada do repositório.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    catalog = [
        ArchiveRomEntry("Super Mario World (USA).zip", "Super Mario World (USA)", 100, "url1"),
    ]
    mocker.patch("retrogame_lab.fetcher.get_archive_catalog", return_value=catalog)

    # Simula seleção "1", confirmação "s", enter "", e saída "q"
    mocker.patch("rich.prompt.Prompt.ask", side_effect=["1", "s", "", "q"])

    dummy_dest = mock_repo_root / "data" / "roms" / "snes" / "Super_Mario_World_(USA).sfc"
    dummy_dest.parent.mkdir(parents=True, exist_ok=True)
    dummy_dest.write_text("dummy", encoding="utf-8")

    mocker.patch("retrogame_lab.fetcher.fetch_and_ingest_rom", return_value=dummy_dest)

    console = Console(record=True)
    imported = run_interactive_snes_fetcher(repo_root=mock_repo_root, console=console)

    assert len(imported) == 1
    assert imported[0] == dummy_dest


def test_fetch_and_ingest_ps1_chd(
    mock_repo_root: Path,
    mocker: MockerFixture,
) -> None:
    """Verifica download e ingestão canônica direta de imagem .chd de PlayStation 1.

    Args:
        mock_repo_root: Fixture de raiz mockada.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    entry = ArchiveRomEntry(
        filename="Crash Bandicoot (USA).chd",
        title="Crash Bandicoot (USA)",
        size_bytes=100,
        download_url="https://archive.org/download/test/crash.chd",
    )

    fake_bytes = b"MOCK_CHD_FILE"
    mock_resp = mocker.MagicMock()
    mock_resp.read.side_effect = [fake_bytes, b""]
    mock_resp.headers = {"Content-Length": str(len(fake_bytes))}
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    mocker.patch("urllib.request.urlopen", return_value=mock_resp)

    final_path = fetch_and_ingest_rom(entry, platform_code="ps1", repo_root=mock_repo_root)

    assert final_path.exists()
    assert final_path.name == "crash_bandicoot_(usa).chd"
    assert final_path.parent == mock_repo_root / "data" / "roms" / "ps1"


def test_run_interactive_fetcher_invalid_platform(mock_repo_root: Path) -> None:
    """Verifica se ValueError é levantado quando a plataforma for desconhecida.

    Args:
        mock_repo_root: Fixture de raiz mockada.

    Returns:
        None.

    Raises:
        None.
    """
    from retrogame_lab.fetcher import run_interactive_fetcher

    with pytest.raises(ValueError, match="Plataforma 'xbox' inválida"):
        run_interactive_fetcher(platform_code="xbox", repo_root=mock_repo_root)


def test_parse_title_metadata() -> None:
    """Verifica a extração de título limpo, tag de região e informações adicionais.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    from retrogame_lab.fetcher import parse_title_metadata

    title1, reg1, extra1 = parse_title_metadata("Resident Evil 2 (USA) (Disc 1) (Rev 1)")
    assert title1 == "Resident Evil 2"
    assert reg1 == "USA"
    assert "Disc 1" in extra1

    title2, reg2, _ = parse_title_metadata("Sonic Adventure (Japan)")
    assert title2 == "Sonic Adventure"
    assert reg2 == "JPN"

    title3, reg3, _ = parse_title_metadata("Top Gear 2 (Brazil)")
    assert title3 == "Top Gear 2"
    assert reg3 == "BRA"


def test_format_helpers() -> None:
    """Verifica renderizadores auxiliares de badges e tamanhos de arquivos.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    from retrogame_lab.fetcher import format_file_size, format_region_badge

    assert "USA" in format_region_badge("USA")
    assert "EUR" in format_region_badge("EUR")
    assert "JPN" in format_region_badge("JPN")
    assert "BRA" in format_region_badge("BRA")
    assert "Global" in format_region_badge("Outro")

    assert "MB" in format_file_size(15 * 1024 * 1024)
    assert "GB" in format_file_size(2 * 1024 * 1024 * 1024)
    assert "KB" in format_file_size(500 * 1024)
    assert "-" in format_file_size(0)


def test_run_interactive_fetcher_pagination_and_search(
    mock_repo_root: Path,
    mocker: MockerFixture,
) -> None:
    """Verifica navegação por páginas (n/p) e busca textual direta.

    Args:
        mock_repo_root: Fixture de raiz mockada.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    from retrogame_lab.fetcher import run_interactive_fetcher

    catalog = [
        ArchiveRomEntry(f"Game_{i} (USA).zip", f"Game {i} (USA)", 100, f"url{i}")
        for i in range(35)
    ]
    mocker.patch("retrogame_lab.fetcher.get_archive_catalog", return_value=catalog)

    # Simula: vai para próxima página 'n', volta para anterior 'p', busca 'Game 10', sai 'q'
    mocker.patch("rich.prompt.Prompt.ask", side_effect=["n", "p", "Game 10", "q"])

    console = Console(record=True)
    res = run_interactive_fetcher(
        platform_code="snes", repo_root=mock_repo_root, console=console
    )
    assert res == []


def test_resolve_initial_identifier() -> None:
    """Verifica a resolução dinâmica de coleções e partições por plataforma e termo.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    from retrogame_lab.fetcher import resolve_initial_identifier

    # Identificador customizado tem precedência
    assert resolve_initial_identifier("snes", "mario", "custom-id") == "custom-id"

    # SNES padrão
    assert resolve_initial_identifier("snes", "mario") == "nointro-snes"

    # PS1 canônico
    assert resolve_initial_identifier("ps1", "resident") == "chd_psx"

    # PS2 roteamento de letras
    assert resolve_initial_identifier("ps2", "colossus") == "ps2-redump-usa-chd-part-C"
    assert resolve_initial_identifier("ps2", "shadow") == "ps2-redump-usa-chd-part-S"
    assert resolve_initial_identifier("ps2", "007 agent") == "ps2-redump-usa-chd-part-0"
    assert resolve_initial_identifier("ps2", "") == "ps2-redump-usa-chd-part-A"

    # PSP roteamento Part 1 (A-M) vs Part 2 (N-Z)
    assert resolve_initial_identifier("psp", "god of war") == "psp-chd-zstd-redump-part1"
    assert resolve_initial_identifier("psp", "persona 3") == "psp-chd-zstd-redump-part2"


def test_get_archive_catalog_subfolder_names(mock_repo_root: Path) -> None:
    """Verifica se arquivos dentro de subpastas do acervo têm o prefixo limpo no título.

    Args:
        mock_repo_root: Fixture de raiz mockada do repositório.

    Returns:
        None.

    Raises:
        None.
    """
    scratch_dir = mock_repo_root / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    cache_file = scratch_dir / "cache_chd_psx_files.json"

    dummy_data = [
        {"name": "CHD-PSX-USA/Resident Evil (USA).chd", "size": "318837841"},
        {"name": "CHD-PSX-USA/Silent Hill (USA).chd", "size": "350000000"},
    ]
    cache_file.write_text(json.dumps(dummy_data), encoding="utf-8")

    catalog = get_archive_catalog(
        identifier="chd_psx", platform_code="ps1", repo_root=mock_repo_root
    )

    assert len(catalog) == 2
    assert catalog[0].filename == "CHD-PSX-USA/Resident Evil (USA).chd"
    assert catalog[0].title == "Resident Evil (USA)"
    assert catalog[0].clean_title == "Resident Evil"
    assert catalog[0].region_tag == "USA"
    assert catalog[0].extension == ".chd"


def test_find_ps2_partition_with_matches_cache(mock_repo_root: Path) -> None:
    """Verifica localização rápida de títulos em partições de PS2 a partir do cache local.

    Args:
        mock_repo_root: Fixture de raiz mockada do repositório.

    Returns:
        None.

    Raises:
        None.
    """
    from retrogame_lab.fetcher import find_ps2_partition_with_matches

    scratch_dir = mock_repo_root / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    cache_s = scratch_dir / "cache_ps2-redump-usa-chd-part-S_files.json"

    dummy_s = [
        {"name": "Shadow of the Colossus (USA).chd", "size": "1110008023"},
        {"name": "Silent Hill 2 (USA).chd", "size": "2100000000"},
    ]
    cache_s.write_text(json.dumps(dummy_s), encoding="utf-8")

    found = find_ps2_partition_with_matches(
        query="colossus", repo_root=mock_repo_root
    )
    assert found == "ps2-redump-usa-chd-part-S"

    found_empty = find_ps2_partition_with_matches(
        query="", repo_root=mock_repo_root
    )
    assert found_empty is None


def test_run_interactive_fetcher_letra_and_parte_commands(
    mock_repo_root: Path,
    mocker: MockerFixture,
) -> None:
    """Verifica os comandos interativos /letra (PS2) e /parte (PSP).

    Args:
        mock_repo_root: Fixture de raiz mockada.
        mocker: Fixture do pytest-mock.

    Returns:
        None.

    Raises:
        None.
    """
    from retrogame_lab.fetcher import run_interactive_fetcher

    catalog_s = [ArchiveRomEntry("Shadow (USA).chd", "Shadow (USA)", 100, "url1")]
    catalog_part2 = [ArchiveRomEntry("Tekken (USA).chd", "Tekken (USA)", 200, "url2")]

    def fake_catalog(identifier: str, platform_code: str, **kwargs):
        if "part-S" in identifier:
            return catalog_s
        if "part2" in identifier:
            return catalog_part2
        return [ArchiveRomEntry("Default (USA).chd", "Default (USA)", 50, "url0")]

    mocker.patch("retrogame_lab.fetcher.get_archive_catalog", side_effect=fake_catalog)

    # Simula troca de letra no PS2: '/letra s', depois sai 'q'
    mocker.patch("rich.prompt.Prompt.ask", side_effect=["/letra s", "q"])
    console = Console(record=True)
    res_ps2 = run_interactive_fetcher(
        platform_code="ps2", repo_root=mock_repo_root, console=console
    )
    assert res_ps2 == []

    # Simula troca de parte no PSP: '/parte 2', depois sai 'q'
    mocker.patch("rich.prompt.Prompt.ask", side_effect=["/parte 2", "q"])
    res_psp = run_interactive_fetcher(
        platform_code="psp", repo_root=mock_repo_root, console=console
    )
    assert res_psp == []

