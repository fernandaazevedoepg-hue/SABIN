from pathlib import Path
import os
import subprocess
import sys
import threading

BASE_DIR = Path(__file__).resolve().parent.parent
CERTIFICADO = BASE_DIR / "certificados" / "prod-ca-2021.crt"
NOME_CERTIFICADO = "Supabase Root 2021 CA"


def _certificado_instalado():
    """Indica se o certificado do Supabase já está no arquivo de raiz do utilizador."""
    resultado = subprocess.run(
        ["certutil", "-user", "-verifystore", "Root", NOME_CERTIFICADO],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return resultado.returncode == 0


def _instalar_certificado():
    """Instala o certificado; o Windows pede confirmação ao utilizador."""
    try:
        if _certificado_instalado():
            return
        print("[SABIN] A instalar o certificado do Supabase para o Power BI...", flush=True)
        resultado = subprocess.run(
            ["certutil", "-user", "-addstore", "Root", str(CERTIFICADO)],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if resultado.returncode == 0:
            print("[SABIN] Certificado do Supabase instalado.", flush=True)
        else:
            print(
                "[SABIN] O certificado não foi instalado. "
                "Usa certificados/instalar_certificado.bat.",
                flush=True,
            )
    except OSError as erro:
        print("[SABIN] Não foi possível verificar o certificado:", erro, flush=True)


def garantir_certificado_supabase():
    """No Windows, instala o certificado do Supabase em segundo plano, se faltar."""
    if not sys.platform.startswith("win"):
        return
    if os.getenv("SABIN_ONLINE"):
        return
    if not CERTIFICADO.exists():
        return
    threading.Thread(target=_instalar_certificado, daemon=True).start()
