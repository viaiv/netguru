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

from dotenv import load_dotenv

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
        help="Não reinstala requirements",
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


def run_step(command: list[str], description: str, env: dict[str, str]) -> None:
    """Execute a command and stop the bootstrap flow on failure.

    Args:
        command: Command and args to execute.
        description: Human-readable description of the step.
        env: Environment variables for subprocess.

    Raises:
        SystemExit: If command execution fails.
    """
    print(f"\n==> {description}")
    print(f"$ {quote_command(command)}")

    try:
        subprocess.run(command, check=True, env=env)
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

    load_dotenv(dotenv_path=env_file, override=False)

    missing = [key for key in REQUIRED_ENV_VARS if not os.getenv(key)]
    if missing:
        missing_str = ", ".join(missing)
        raise SystemExit(f"Variáveis obrigatórias ausentes no .env: {missing_str}")


def validate_requirements(python_executable: Path, env: dict[str, str], requirements_file: Path) -> None:
    """Install and validate Python requirements."""
    if not requirements_file.exists():
        raise SystemExit("requirements.txt não encontrado em backend/.")

    run_step(
        [str(python_executable), "-m", "pip", "install", "--upgrade", "pip"],
        "Atualizando pip",
        env,
    )
    run_step(
        [str(python_executable), "-m", "pip", "install", "-r", str(requirements_file)],
        "Instalando requirements",
        env,
    )
    run_step(
        [str(python_executable), "-m", "pip", "check"],
        "Validando compatibilidade das dependências (pip check)",
        env,
    )


def validate_and_apply_migrations(python_executable: Path, env: dict[str, str]) -> None:
    """Validate migration chain and apply pending migrations."""
    run_step(
        [str(python_executable), "-m", "alembic", "heads"],
        "Validando chain de migrations (heads)",
        env,
    )
    run_step(
        [str(python_executable), "-m", "alembic", "current"],
        "Validando conexão e estado atual de migrations",
        env,
    )
    run_step(
        [str(python_executable), "-m", "alembic", "upgrade", "head"],
        "Aplicando migrations pendentes",
        env,
    )
    run_step(
        [str(python_executable), "-m", "alembic", "current"],
        "Confirmando versão após upgrade",
        env,
    )


def start_dev_server(
    python_executable: Path,
    env: dict[str, str],
    host: str,
    port: int,
    reload_enabled: bool,
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
        subprocess.run(uvicorn_cmd, check=True, env=env)
    except KeyboardInterrupt:
        print("\nServidor interrompido pelo usuário.")
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"Falha ao iniciar servidor de desenvolvimento (exit code: {exc.returncode})."
        ) from exc


def main() -> None:
    """Entry point for development bootstrap."""
    args = parse_args()
    backend_dir = ensure_backend_cwd()
    python_executable = ensure_venv_python(backend_dir)

    env_file = backend_dir / ".env"
    load_and_validate_env(env_file)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    requirements_file = backend_dir / "requirements.txt"
    if not args.skip_install:
        validate_requirements(python_executable, env, requirements_file)
    else:
        print("\n==> Pulando instalação de requirements (--skip-install)")

    if not args.skip_migrations:
        validate_and_apply_migrations(python_executable, env)
    else:
        print("\n==> Pulando validação/aplicação de migrations (--skip-migrations)")

    port = args.port or int(os.getenv("UVICORN_PORT", "8000"))
    reload_enabled = not args.no_reload

    start_dev_server(
        python_executable=python_executable,
        env=env,
        host=args.host,
        port=port,
        reload_enabled=reload_enabled,
    )


if __name__ == "__main__":
    main()
