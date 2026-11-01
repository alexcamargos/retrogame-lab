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

    with pytest.raises(RuntimeError, match="não contém ROMs .sfc ou .smc"):
        download_and_extract_rom(entry, tmp_path)


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
    assert final_path.name == "Chrono_Trigger_(USA).sfc"
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

    # Simula o usuário digitando "1" (seleciona jogo 1) e depois "n" (não continuar pesquisando)
    mocker.patch("rich.prompt.Prompt.ask", side_effect=["1", "n"])

    dummy_dest = mock_repo_root / "data" / "roms" / "snes" / "Super_Mario_World_(USA).sfc"
    dummy_dest.parent.mkdir(parents=True, exist_ok=True)
    dummy_dest.write_text("dummy", encoding="utf-8")

    mocker.patch("retrogame_lab.fetcher.fetch_and_ingest_rom", return_value=dummy_dest)

    console = Console(record=True)
    imported = run_interactive_snes_fetcher(repo_root=mock_repo_root, console=console)

    assert len(imported) == 1
    assert imported[0] == dummy_dest
