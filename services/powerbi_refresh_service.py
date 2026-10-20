from datetime import datetime
from pathlib import Path
import subprocess
import sys
import threading

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT_POWERSHELL = Path(__file__).with_name("powerbi_refresh.ps1")
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "powerbi_refresh.log"

_lock = threading.Lock()
_worker_active = False
_pending_timeout = None
_pending_reason = None
_pending_report = None


def _registar(mensagem):
    linha = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SABIN-PowerBI] {mensagem}"
    print(linha, flush=True)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as ficheiro:
            ficheiro.write(linha + "\n")
    except OSError:
        pass


def _executar_refresh(caminho_relatorio, timeout_segundos, motivo):
    if not sys.platform.startswith("win"):
        _registar("A atualização automática do modelo local só está disponível no Windows.")
        return False

    if not SCRIPT_POWERSHELL.exists():
        _registar(f"Script de atualização não encontrado: {SCRIPT_POWERSHELL}")
        return False

    powershell = "powershell.exe"
    comando = [
        powershell,
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT_POWERSHELL),
        "-Relatorio",
        str(caminho_relatorio or ""),
        "-TimeoutSegundos",
        str(max(0, int(timeout_segundos))),
    ]

    _registar(f"A iniciar atualização pelo motor local do Power BI. Motivo: {motivo}.")
    try:
        processo = subprocess.run(
            comando,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(90, int(timeout_segundos) + 90),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        _registar("Tempo limite excedido ao atualizar o modelo Power BI.")
        return False
    except OSError as erro:
        _registar(f"Não foi possível iniciar o PowerShell: {erro}")
        return False

    saida = "\n".join(parte.strip() for parte in (processo.stdout, processo.stderr) if parte and parte.strip())
    if saida:
        for linha in saida.splitlines():
            _registar(linha)

    if processo.returncode == 0:
        _registar("O motor local confirmou a conclusão do comando de atualização.")
        return True

    _registar(f"A atualização não foi confirmada. Código de saída do PowerShell: {processo.returncode}.")
    return False


def _worker():
    global _worker_active, _pending_timeout, _pending_reason, _pending_report
    timeout_atual = 0
    motivo_atual = "Atualização analítica concluída"
    relatorio_atual = None

    with _lock:
        timeout_atual = _pending_timeout if _pending_timeout is not None else 0
        motivo_atual = _pending_reason or motivo_atual
        relatorio_atual = _pending_report
        _pending_timeout = None
        _pending_reason = None
        _pending_report = None

    while True:
        _executar_refresh(relatorio_atual, timeout_atual, motivo_atual)
        with _lock:
            if _pending_timeout is not None:
                timeout_atual = _pending_timeout
                motivo_atual = _pending_reason or "Pedido de atualização pendente"
                relatorio_atual = _pending_report
                _pending_timeout = None
                _pending_reason = None
                _pending_report = None
            else:
                _worker_active = False
                return


def iniciar_atualizacao_automatica(caminho_relatorio=None, aguardar_modelo=False, motivo=None):
    """Agenda o refresh sem bloquear o callback do Dash.

    Depois do ETL, faz uma tentativa imediata apenas se o modelo já estiver aberto.
    Ao abrir o PBIX, aguarda até 180 segundos para o motor local ficar disponível.
    Pedidos recebidos durante uma atualização ficam em fila, sem criar processos concorrentes.
    """
    global _worker_active, _pending_timeout, _pending_reason, _pending_report

    if not sys.platform.startswith("win"):
        _registar("Pedido ignorado: a atualização automática do Power BI Desktop exige Windows.")
        return False

    timeout = 180 if aguardar_modelo else 0
    descricao = motivo or ("Abertura do relatório" if aguardar_modelo else "ETL concluído")

    with _lock:
        if _worker_active:
            # Mantém o pedido de atualização mais completo quando já existe um em execução.
            if _pending_timeout is None or timeout > _pending_timeout:
                _pending_timeout = timeout
                _pending_reason = descricao
                _pending_report = caminho_relatorio
            return True

        _worker_active = True
        _pending_timeout = timeout
        _pending_reason = descricao
        _pending_report = caminho_relatorio
        thread = threading.Thread(target=_worker, name="SABIN-PowerBI-Refresh", daemon=True)
        thread.start()

    return True
