from pathlib import Path
import subprocess
import sys


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

    resultados.append(
        executar_comando(
            [
                sys.executable,
                "-m",
                "analysis.stock_alerts",
            ],
            "Alertas de stock",
        )
    )

    return {
        "sucesso": True,
        "mensagem": (
            "Data Warehouse, previsões e alertas "
            "atualizados com sucesso."
        ),
        "resultados": resultados,
    }


def main():
    print()
    print("SABIN - ATUALIZAÇÃO ANALÍTICA")
    print()

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
