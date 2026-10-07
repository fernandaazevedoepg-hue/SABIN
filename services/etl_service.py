from pathlib import Path
import subprocess
import sys
import threading


BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)


def encontrar_load_script():
    caminho = (
        BASE_DIR
        / "etl"
        / "load.py"
    )

    if not caminho.exists():
        raise FileNotFoundError(
            "Não foi encontrado etl/load.py."
        )

    return caminho


def executar_comando(
    comando,
    nome_etapa,
):
    processo = subprocess.run(
        comando,
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
    )

    if processo.returncode != 0:
        detalhe = (
            processo.stderr.strip()
            or processo.stdout.strip()
        )

        raise RuntimeError(
            f"Falha na etapa '{nome_etapa}':\n"
            f"{detalhe}"
        )

    return {
        "etapa": nome_etapa,
        "log": processo.stdout.strip(),
    }


def atualizar_alertas_stock_rapido():
    from analysis.stock_alerts import (
        gerar_alertas_stock,
        guardar_alertas_stock,
    )

    dados, _, _ = gerar_alertas_stock()

    guardar_alertas_stock(
        dados
    )

    return {
        "sucesso": True,
        "livros": len(dados),
    }


def executar_atualizacao_analitica():
    resultados = []

    load_script = encontrar_load_script()

    resultados.append(
        executar_comando(
            [
                sys.executable,
                str(load_script),
            ],
            "Data Warehouse",
        )
    )

    resultados.append(
        executar_comando(
            [
                sys.executable,
                "-m",
                "analysis.previsao",
            ],
            "Modelo preditivo",
        )
    )

    resultados.append(
        executar_comando(
            [
                sys.executable,
                "-m",
                "analysis.alertas",
            ],
            "Alertas preditivos",
        )
    )

    return {
        "sucesso": True,
        "mensagem": (
            "Data Warehouse, previsões e alertas "
            "preditivos atualizados com sucesso."
        ),
        "resultados": resultados,
    }


_estado_lock = threading.Lock()
_atualizacao_em_execucao = False
_atualizacao_pendente = False
_versao_atualizacao = 0


def _executar_em_background():
    global _atualizacao_em_execucao
    global _atualizacao_pendente
    global _versao_atualizacao

    while True:
        try:
            executar_atualizacao_analitica()
        except Exception as erro:
            print(
                "Erro na atualização analítica em segundo plano:",
                erro,
            )

        with _estado_lock:
            _versao_atualizacao += 1

            if _atualizacao_pendente:
                _atualizacao_pendente = False
                continue

            _atualizacao_em_execucao = False
            break


def solicitar_atualizacao_analitica():
    global _atualizacao_em_execucao
    global _atualizacao_pendente

    try:
        atualizar_alertas_stock_rapido()
    except Exception as erro:
        print(
            "Erro na atualização rápida dos alertas de stock:",
            erro,
        )

    with _estado_lock:
        if _atualizacao_em_execucao:
            _atualizacao_pendente = True

            return {
                "agendada": True,
                "em_execucao": True,
            }

        _atualizacao_em_execucao = True

    thread = threading.Thread(
        target=_executar_em_background,
        daemon=True,
    )
    thread.start()

    return {
        "agendada": True,
        "em_execucao": False,
    }


def obter_estado_atualizacao():
    with _estado_lock:
        return {
            "em_execucao": _atualizacao_em_execucao,
            "pendente": _atualizacao_pendente,
            "versao": _versao_atualizacao,
        }


def main():
    print()
    print("SABIN - ATUALIZAÇÃO ANALÍTICA")
    print()

    try:
        resultado_stock = (
            atualizar_alertas_stock_rapido()
        )

        print(
            "[OK] Alertas de stock "
            f"({resultado_stock['livros']} livros)"
        )
    except Exception as erro:
        print(
            "[ERRO] Alertas de stock:",
            erro,
        )

    resultado = executar_atualizacao_analitica()

    for etapa in resultado["resultados"]:
        print(
            f"[OK] {etapa['etapa']}"
        )

    print()
    print(
        resultado["mensagem"]
    )


if __name__ == "__main__":
    main()
