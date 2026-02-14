#!/usr/bin/env python3
"""Bootstrap de desenvolvimento do backend NetGuru.

Fluxo padrão:
1. Garante que a execução está no diretório `backend/`.
2. Garante virtual environment (`venv`) e executável Python.
3. Carrega e valida variáveis essenciais do `.env`.
4. Instala/valida requirements.
5. Valida e aplica migrations.
6. Sobe o servidor FastAPI em modo dev.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Iterable

REQUIRED_ENV_VARS: tuple[str, ...] = (
    "SECRET_KEY",
    "FERNET_KEY",
    "DATABASE_URL",
    "REDIS_URL",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Configura e sobe o backend NetGuru em modo desenvolvimento."
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host do servidor Uvicorn")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Porta do servidor Uvicorn (default: UVICORN_PORT ou 8000)",
    )
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Desativa autoreload do Uvicorn",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Pula atualização do pip e instalação de requirements",
    )
    parser.add_argument(
        "--skip-migrations",
        action="store_true",
        help="Não valida/aplica migrations",
    )
    return parser.parse_args()


def quote_command(command: Iterable[str]) -> str:
    """Return a shell-safe command preview for logs."""
    return " ".join(shlex.quote(part) for part in command)


def run_step(
    command: list[str],
    description: str,
    env: dict[str, str],
    cwd: Path | None = None,
) -> None:
    """Execute a command and stop the bootstrap flow on failure.

    Args:
        command: Command and args to execute.
        description: Human-readable description of the step.
        env: Environment variables for subprocess.
        cwd: Working directory for the subprocess.

    Raises:
        SystemExit: If command execution fails.
    """
    print(f"\n==> {description}")
    print(f"$ {quote_command(command)}")

    try:
        subprocess.run(command, check=True, env=env, cwd=cwd)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"\nErro ao executar '{description}' (exit code: {exc.returncode})."
        ) from exc


def ensure_backend_cwd() -> Path:
    """Change cwd to backend root (directory that contains this script)."""
    backend_dir = Path(__file__).resolve().parent
    os.chdir(backend_dir)
    return backend_dir


def venv_python_path(backend_dir: Path) -> Path:
    """Return the Python executable path inside backend venv."""
    if sys.platform == "win32":
        return backend_dir / "venv" / "Scripts" / "python.exe"
    return backend_dir / "venv" / "bin" / "python"


def ensure_venv_python(backend_dir: Path) -> Path:
    """Ensure virtual environment exists and return its Python executable."""
    python_in_venv = venv_python_path(backend_dir)

    if python_in_venv.exists():
        return python_in_venv

    print("\n==> Criando virtual environment em ./venv")
    subprocess.run([sys.executable, "-m", "venv", str(backend_dir / "venv")], check=True)

    if not python_in_venv.exists():
        raise SystemExit("Falha ao criar venv: executável Python não encontrado.")

    return python_in_venv


def load_and_validate_env(env_file: Path) -> None:
    """Load .env and validate required settings for app bootstrap.

    Args:
        env_file: Path to `.env` file.

    Raises:
        SystemExit: If file does not exist or required keys are missing.
    """
    if not env_file.exists():
        raise SystemExit(
            "Arquivo .env não encontrado em backend/. Crie a partir de .env.example antes de rodar."
        )

    try:
        from dotenv import load_dotenv
    except ImportError:
        raise SystemExit(
            "Pacote 'python-dotenv' não encontrado. "
            "Instale com: pip install python-dotenv"
        )

    load_dotenv(dotenv_path=env_file, override=False)

    missing = [key for key in REQUIRED_ENV_VARS if not os.getenv(key)]
    if missing:
        missing_str = ", ".join(missing)
        raise SystemExit(f"Variáveis obrigatórias ausentes no .env: {missing_str}")


def validate_requirements(
    python_executable: Path,
    env: dict[str, str],
    requirements_file: Path,
    cwd: Path | None = None,
) -> None:
    """Install and validate Python requirements."""
    if not requirements_file.exists():
        raise SystemExit("requirements.txt não encontrado em backend/.")

    run_step(
        [str(python_executable), "-m", "pip", "install", "--upgrade", "pip"],
        "Atualizando pip",
        env,
        cwd=cwd,
    )
    run_step(
        [str(python_executable), "-m", "pip", "install", "--no-deps", "-r", str(requirements_file)],
        "Instalando requirements",
        env,
        cwd=cwd,
    )
    run_step(
        [str(python_executable), "-m", "pip", "check"],
        "Validando compatibilidade das dependências (pip check)",
        env,
        cwd=cwd,
    )


def validate_and_apply_migrations(
    python_executable: Path,
    env: dict[str, str],
    cwd: Path | None = None,
) -> None:
    """Validate migration chain and apply pending migrations."""
    # Verificar se há múltiplos heads (branch divergente)
    heads_cmd = [str(python_executable), "-m", "alembic", "heads"]
    print(f"\n==> Validando chain de migrations (heads)")
    print(f"$ {quote_command(heads_cmd)}")
    result = subprocess.run(
        heads_cmd, capture_output=True, text=True, env=env, cwd=cwd,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"\nErro ao verificar alembic heads (exit code: {result.returncode}).\n"
            f"{result.stderr.strip()}"
        )
    head_lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    if len(head_lines) > 1:
        raise SystemExit(
            f"\nMigrations divergentes detectadas ({len(head_lines)} heads).\n"
            f"Execute 'alembic merge heads' para resolver antes de continuar.\n"
            f"Heads encontrados:\n{result.stdout.strip()}"
        )

    run_step(
        [str(python_executable), "-m", "alembic", "current"],
        "Validando conexão e estado atual de migrations",
        env,
        cwd=cwd,
    )
    run_step(
        [str(python_executable), "-m", "alembic", "upgrade", "head"],
        "Aplicando migrations pendentes",
        env,
        cwd=cwd,
    )
    run_step(
        [str(python_executable), "-m", "alembic", "current"],
        "Confirmando versão após upgrade",
        env,
        cwd=cwd,
    )


def start_dev_server(
    python_executable: Path,
    env: dict[str, str],
    host: str,
    port: int,
    reload_enabled: bool,
    cwd: Path | None = None,
) -> None:
    """Start Uvicorn development server."""
    uvicorn_cmd = [
        str(python_executable),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload_enabled:
        uvicorn_cmd.append("--reload")

    print("\n==> Subindo backend em modo desenvolvimento")
    print(f"$ {quote_command(uvicorn_cmd)}")

    try:
        subprocess.run(uvicorn_cmd, check=True, env=env, cwd=cwd)
    except KeyboardInterrupt:
        print("\nServidor interrompido pelo usuário.")
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"Falha ao iniciar servidor de desenvolvimento (exit code: {exc.returncode})."
        ) from exc


def resolve_port(cli_port: int | None, env_default: str = "8000") -> int:
    """Resolve server port from CLI arg or UVICORN_PORT env var.

    Args:
        cli_port: Port passed via --port flag (takes precedence).
        env_default: Fallback if UVICORN_PORT is not set.

    Returns:
        Validated port number.

    Raises:
        SystemExit: If port is not a valid integer or out of range.
    """
    if cli_port is not None:
        port = cli_port
    else:
        raw = os.getenv("UVICORN_PORT", env_default)
        try:
            port = int(raw)
        except ValueError:
            raise SystemExit(
                f"UVICORN_PORT='{raw}' não é um número válido. "
                "Defina um inteiro entre 1 e 65535."
            )

    if not 1 <= port <= 65535:
        raise SystemExit(
            f"Porta {port} fora do intervalo válido (1-65535)."
        )
    return port


def main() -> None:
    """Entry point for development bootstrap."""
    args = parse_args()
    backend_dir = ensure_backend_cwd()
    python_executable = ensure_venv_python(backend_dir)

    env_file = backend_dir / ".env"
    load_and_validate_env(env_file)

    # load_dotenv() injeta variáveis do .env em os.environ.
    # O copy() isola o env para subprocessos sem afetar o processo pai.
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    requirements_file = backend_dir / "requirements.txt"
    if not args.skip_install:
        validate_requirements(python_executable, env, requirements_file, cwd=backend_dir)
    else:
        print("\n==> Pulando instalação de requirements (--skip-install)")

    if not args.skip_migrations:
        validate_and_apply_migrations(python_executable, env, cwd=backend_dir)
    else:
        print("\n==> Pulando validação/aplicação de migrations (--skip-migrations)")

    port = resolve_port(args.port)
    reload_enabled = not args.no_reload

    start_dev_server(
        python_executable=python_executable,
        env=env,
        host=args.host,
        port=port,
        reload_enabled=reload_enabled,
        cwd=backend_dir,
    )


if __name__ == "__main__":
    main()
