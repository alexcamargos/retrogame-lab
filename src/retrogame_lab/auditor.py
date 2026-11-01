"""Módulo de auditoria de integridade para BIOS, ROMs e Saves.

Executa validação estática de formatos, cálculo de somas de verificação
SHA-256 e detecção de violações das regras de salvamento multiplataforma.
"""

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from retrogame_lab.config import (
    INVALID_FILENAME_CHARS_PATTERN,
    SUPPORTED_PLATFORMS,
    get_bios_dir,
    get_roms_dir,
    get_saves_dir,
)


class Severity(str, Enum):
    """Níveis de severidade para problemas identificados na auditoria."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class AuditIssue:
    """Representação de um problema ou aviso identificado durante a auditoria.

    Attributes:
        category: Categoria da auditoria (ex.: 'BIOS', 'ROMs', 'Saves').
        severity: Gravidade do apontamento (INFO, WARNING, ERROR).
        message: Descrição explicativa do problema e recomendação de mitigação.
        file_path: Caminho opcional do arquivo envolvido.
    """

    category: str
    severity: Severity
    message: str
    file_path: Path | None = None


@dataclass
class AuditSummary:
    """Resumo estatístico e coleção de problemas de uma categoria auditada.

    Attributes:
        category: Nome da categoria examinada.
        total_scanned: Quantidade total de arquivos ou diretórios inspecionados.
        issues: Lista de problemas detectados.
    """

    category: str
    total_scanned: int = 0
    issues: list[AuditIssue] = field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        """Indica se a categoria auditada está livre de erros impeditivos."""
        return not any(issue.severity == Severity.ERROR for issue in self.issues)


@dataclass
class AuditReport:
    """Relatório consolidado de auditoria de todo o pipeline.

    Attributes:
        bios: Resumo da auditoria de BIOS/firmwares.
        roms: Resumo da auditoria da biblioteca de ROMs.
        saves: Resumo da auditoria de regras de salvamento.
    """

    bios: AuditSummary
    roms: AuditSummary
    saves: AuditSummary

    @property
    def total_issues(self) -> int:
        """Retorna o total consolidado de problemas detectados."""
        return len(self.bios.issues) + len(self.roms.issues) + len(self.saves.issues)

    @property
    def has_errors(self) -> bool:
        """Indica se existe ao menos um erro crítico em qualquer categoria."""
        all_issues = self.bios.issues + self.roms.issues + self.saves.issues
        return any(issue.severity == Severity.ERROR for issue in all_issues)


# Banco de dados referencial de somas SHA-256 de firmwares canônicos
KNOWN_BIOS_HASHES: dict[str, str] = {
    # Sony PlayStation 1 (NTSC-U / PAL v4.1 / v4.5)
    "scph1001.bin": "42e4124be7623e2e28b1db0d8d426539646faee49d74b71166d8ba5bd7c472ed",
    "scph5501.bin": "8dd7d5296a650fac7319bce665a6a53c8b45ff033a20d4f13fb1457a3e74be88",
    "scph7001.bin": "1e260a1f764f66a3079109279a615e0203216c69f2e322b7dcf57960309995be",
    "scph7502.bin": "5e84a94818cf5282f4217591fefd88be36b9b174b3cc7cb0bcd75199beb450f1",
    # Sony PlayStation 2 (NTSC-U SCPH-39001 v1.60)
    "scph39001.bin": "8b9ff6923b3793e79e6e89f81f185c7cc68e1abfef1972b95b8bc6b5539fa73f",
    # Sega Dreamcast
    "boot.bin": "4064d4b1f630de88426027a0505c26b86e08287c71dcc390ea12b6b55be7ddf0",
    "dc_boot.bin": "4064d4b1f630de88426027a0505c26b86e08287c71dcc390ea12b6b55be7ddf0",
}


def compute_sha256(file_path: Path, chunk_size: int = 65536) -> str:
    """Calcula a soma de verificação SHA-256 de um arquivo de forma eficiente.

    Args:
        file_path: Caminho absoluto ou relativo para o arquivo no sistema de arquivos.
        chunk_size: Tamanho do bloco de leitura em bytes (padrão: 64KB).

    Returns:
        String hexadecimal contendo o hash SHA-256 em minúsculas.

    Raises:
        FileNotFoundError: Se o arquivo especificado não existir.
        IsADirectoryError: Se o caminho apontar para um diretório.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Arquivo não localizado para cálculo de hash: {file_path}")
    if file_path.is_dir():
        raise IsADirectoryError(f"Caminho é um diretório, não um arquivo: {file_path}")

    hasher = hashlib.sha256()
    with file_path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def audit_bios(bios_dir: Path) -> AuditSummary:
    """Audita a integridade de firmwares e BIOS centralizados no diretório 'data/bios/'.

    Args:
        bios_dir: Caminho para o diretório de BIOS.

    Returns:
        AuditSummary com a quantidade de firmwares inspecionados e problemas encontrados.

    Raises:
        None. Erros operacionais são registrados como instâncias de AuditIssue.
    """
    summary = AuditSummary(category="BIOS")
    if not bios_dir.exists():
        summary.issues.append(
            AuditIssue(
                category="BIOS",
                severity=Severity.WARNING,
                message=(
                    f"Diretório de BIOS '{bios_dir}' não foi encontrado. "
                    "Execute scripts/bootstrap.ps1."
                ),
                file_path=bios_dir,
            )
        )
        return summary

    files = [f for f in bios_dir.rglob("*") if f.is_file()]
    summary.total_scanned = len(files)

    if not files:
        summary.issues.append(
            AuditIssue(
                category="BIOS",
                severity=Severity.INFO,
                message=(
                    "Nenhuma BIOS instalada em 'data/bios/'. "
                    "Plataformas como PS1 e PS2 exigem firmware para iniciar."
                ),
                file_path=bios_dir,
            )
        )
        return summary

    for bios_file in files:
        filename_lower = bios_file.name.lower()
        if filename_lower in KNOWN_BIOS_HASHES:
            expected_hash = KNOWN_BIOS_HASHES[filename_lower]
            actual_hash = compute_sha256(bios_file)
            if actual_hash != expected_hash:
                summary.issues.append(
                    AuditIssue(
                        category="BIOS",
                        severity=Severity.ERROR,
                        message=(
                            f"Hash incorreto para '{bios_file.name}'. "
                            f"Esperado: {expected_hash[:8]}..., Obtido: {actual_hash[:8]}... "
                            "Possível dump corrompido ou modificado."
                        ),
                        file_path=bios_file,
                    )
                )

    return summary


def audit_roms(roms_dir: Path) -> AuditSummary:
    """Audita os formatos e estruturas da biblioteca de jogos em 'data/roms/'.

    Verifica se mídias baseadas em CD foram compactadas para .chd, se imagens de
    GameCube/Wii estão em formato .rvz e sinaliza arquivos inadequados.

    Args:
        roms_dir: Caminho para o diretório de ROMs.

    Returns:
        AuditSummary com total de títulos escaneados e irregularidades reportadas.

    Raises:
        None. Erros operacionais são registrados como instâncias de AuditIssue.
    """
    summary = AuditSummary(category="ROMs")
    if not roms_dir.exists():
        summary.issues.append(
            AuditIssue(
                category="ROMs",
                severity=Severity.WARNING,
                message=f"Diretório de ROMs '{roms_dir}' não foi encontrado.",
                file_path=roms_dir,
            )
        )
        return summary

    files = [f for f in roms_dir.rglob("*") if f.is_file()]
    summary.total_scanned = len(files)

    for rom_file in files:
        ext = rom_file.suffix.lower()
        rel_parts = rom_file.relative_to(roms_dir).parts

        # Detecção de arquivos soltos diretamente na raiz de data/roms/
        if len(rel_parts) <= 1:
            summary.issues.append(
                AuditIssue(
                    category="ROMs",
                    severity=Severity.WARNING,
                    message=(
                        f"Arquivo solto na raiz de roms/: '{rom_file.name}'. "
                        "Mova para a subpasta da plataforma correspondente (ex: data/roms/snes/)."
                    ),
                    file_path=rom_file,
                )
            )
            continue

        platform_code = rel_parts[0].lower()
        platform = SUPPORTED_PLATFORMS.get(platform_code)
        if not platform:
            continue

        # Regra 1: GameCube / Wii PROÍBE CHD e exige RVZ
        if platform_code == "gc":
            if ext == ".chd":
                summary.issues.append(
                    AuditIssue(
                        category="ROMs",
                        severity=Severity.ERROR,
                        message=(
                            "Mídia de GameCube convertida incorretamente para .chd: "
                            f"'{rom_file.name}'. O formato obrigatório para Dolphin é .rvz."
                        ),
                        file_path=rom_file,
                    )
                )
            elif ext in (".iso", ".gcm"):
                summary.issues.append(
                    AuditIssue(
                        category="ROMs",
                        severity=Severity.WARNING,
                        message=(
                            f"Imagem de GameCube não otimizada: '{rom_file.name}'. "
                            "Converta para .rvz nativo do Dolphin para economizar espaço."
                        ),
                        file_path=rom_file,
                    )
                )

        # Regra 2: PS1 e Dreamcast exigem CHD em vez de CUE/BIN/GDI/CDI desmembrado
        if platform_code in ("ps1", "dc"):
            if ext in (".cue", ".bin", ".iso", ".gdi", ".cdi"):
                summary.issues.append(
                    AuditIssue(
                        category="ROMs",
                        severity=Severity.WARNING,
                        message=(
                            f"Mídia de disco não compactada em {platform.name}: '{rom_file.name}'. "
                            "Execute scripts/convert_chd.ps1 para gerar uma imagem unificada .chd."
                        ),
                        file_path=rom_file,
                    )
                )

        # Regra 3: PS2 pode ser compactado para CHD (createdvd)
        if platform_code == "ps2" and ext == ".iso":
            summary.issues.append(
                AuditIssue(
                    category="ROMs",
                    severity=Severity.INFO,
                    message=(
                        f"Imagem ISO de PS2 elegível para compressão: '{rom_file.name}'. "
                        "Recomenda-se conversão via scripts/convert_chd.ps1 para formato .chd."
                    ),
                    file_path=rom_file,
                )
            )

        # Regra 4: Nomenclatura sem espaços e sem caracteres especiais ('"` etc.)
        if re.search(INVALID_FILENAME_CHARS_PATTERN, rom_file.name):
            summary.issues.append(
                AuditIssue(
                    category="ROMs",
                    severity=Severity.WARNING,
                    message=(
                        f"Nomenclatura fora do padrão (espaços/especiais): '{rom_file.name}'. "
                        "Execute 'retrogame-lab sanitize --apply' para normalizar com '_'."
                    ),
                    file_path=rom_file,
                )
            )

        # Regra 5: Extensões não suportadas ou não homologadas para a plataforma
        already_reported = any(
            issue.file_path == rom_file and issue.severity in (Severity.ERROR, Severity.WARNING)
            for issue in summary.issues
        )
        if not already_reported and ext not in platform.accepted_extensions:
            if ext in platform.prohibited_extensions:
                summary.issues.append(
                    AuditIssue(
                        category="ROMs",
                        severity=Severity.ERROR,
                        message=(
                            f"Extensão proibida '{ext}' para '{platform.name}': '{rom_file.name}'. "
                            f"Formato canônico homologado: {platform.canonical_format}."
                        ),
                        file_path=rom_file,
                    )
                )
            else:
                accepted_str = ", ".join(platform.accepted_extensions)
                summary.issues.append(
                    AuditIssue(
                        category="ROMs",
                        severity=Severity.WARNING,
                        message=(
                            f"Extensão não suportada '{ext}' para "
                            f"'{platform.name}': '{rom_file.name}'. "
                            f"Extensões homologadas: {accepted_str}."
                        ),
                        file_path=rom_file,
                    )
                )

    return summary


def audit_saves(saves_dir: Path) -> AuditSummary:
    """Audita a higiene da pasta de salvamento 'data/saves/' e previne conflitos.

    Detecta savestates proibidos na sincronização, travas de arquivo temporárias
    e memory cards globais compartilhados proibidos.

    Args:
        saves_dir: Caminho para o diretório de saves.

    Returns:
        AuditSummary com a contagem de saves examinados e potenciais riscos reportados.

    Raises:
        None. Violações são registradas como instâncias de AuditIssue.
    """
    summary = AuditSummary(category="Saves")
    if not saves_dir.exists():
        summary.issues.append(
            AuditIssue(
                category="Saves",
                severity=Severity.WARNING,
                message=f"Diretório de saves '{saves_dir}' não foi encontrado.",
                file_path=saves_dir,
            )
        )
        return summary

    # Escanear todos os arquivos recursivamente
    all_files = [f for f in saves_dir.rglob("*") if f.is_file()]
    summary.total_scanned = len(all_files)

    lock_extensions = [".tmp", ".lock", ".lck", ".wal", ".shm"]
    prohibited_card_patterns = [
        re.compile(r"^mcd\d+\.ps2$"),
        re.compile(r"^shared_card_\d+\.mcd$"),
        re.compile(r"^memcard\d+\.mcd$"),
    ]

    for save_file in all_files:
        name_lower = save_file.name.lower()

        # 1. Detecção de Savestates proibidos na sincronização via regex precisa
        is_state = bool(
            re.search(r"\.state.*$", name_lower)
            or re.search(r"\.s\d{2}$", name_lower)
            or name_lower.endswith(".nvram.bak")
        )
        if is_state:
            summary.issues.append(
                AuditIssue(
                    category="Saves",
                    severity=Severity.ERROR,
                    message=(
                        f"Savestate detectado indevidamente na pasta de saves: '{save_file.name}'. "
                        "Savestates dependem de arquitetura (x86 vs ARM) e corrompem a sincronia."
                    ),
                    file_path=save_file,
                )
            )

        # 2. Detecção de arquivos de trava e temporários
        if any(name_lower.endswith(ext) for ext in lock_extensions):
            summary.issues.append(
                AuditIssue(
                    category="Saves",
                    severity=Severity.WARNING,
                    message=(
                        f"Arquivo temporário ou trava ativa detectada: '{save_file.name}'. "
                        "Feche os emuladores antes de realizar a sincronização via Syncthing."
                    ),
                    file_path=save_file,
                )
            )

        # 3. Detecção de Memory Cards compartilhados globais em PS1/PS2
        is_shared_card = name_lower in (
            "shared_card_1.mcd",
            "mcd001.ps2",
            "mcd002.ps2",
            "memcard1.mcd",
        ) or any(pat.match(name_lower) for pat in prohibited_card_patterns)
        if is_shared_card:
            summary.issues.append(
                AuditIssue(
                    category="Saves",
                    severity=Severity.ERROR,
                    message=(
                        f"Memory Card global compartilhado detectado: '{save_file.name}'. "
                        "Configure o modo 'Title-specific Card' (cartão individual por jogo)."
                    ),
                    file_path=save_file,
                )
            )

        # 4. Nomenclatura sem espaços e sem caracteres especiais ('"` etc.)
        if re.search(INVALID_FILENAME_CHARS_PATTERN, save_file.name):
            summary.issues.append(
                AuditIssue(
                    category="Saves",
                    severity=Severity.WARNING,
                    message=(
                        f"Nome de save fora do padrão (espaços/especiais): '{save_file.name}'. "
                        "Execute 'retrogame-lab sanitize --apply' para normalizar com '_'."
                    ),
                    file_path=save_file,
                )
            )

    return summary


def run_full_audit(repo_root: Path | None = None) -> AuditReport:
    """Executa a auditoria completa de BIOS, ROMs e Saves no repositório.

    Args:
        repo_root: Caminho raiz do projeto. Se None, é detectado automaticamente.

    Returns:
        AuditReport consolidado contendo os sumários de cada subsistema.

    Raises:
        FileNotFoundError: Se a raiz do repositório não for encontrada.
    """
    bios_path = get_bios_dir(repo_root)
    roms_path = get_roms_dir(repo_root)
    saves_path = get_saves_dir(repo_root)

    return AuditReport(
        bios=audit_bios(bios_path),
        roms=audit_roms(roms_path),
        saves=audit_saves(saves_path),
    )
