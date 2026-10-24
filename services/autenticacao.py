"""Login simples do SABIN: uma única conta, sem registo de novos utilizadores.

O utilizador e a palavra-passe vêm de variáveis de ambiente (no Render):

    SABIN_UTILIZADOR      ex.: juri
    SABIN_PALAVRA_PASSE   palavra-passe entregue ao júri

Não devem ser postas no .env, porque o .env está público no repositório.
Se as variáveis não existirem (por exemplo, a correr localmente), a aplicação
abre sem pedir login, como antes.
"""

import hashlib
import hmac
import os
import time
from datetime import timedelta

from flask import redirect, render_template_string, request, session


PAGINA_LOGIN = """<!doctype html>
<html lang="pt-PT">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Entrar | SABIN</title>
<style>
* { box-sizing: border-box; }
body {
    margin: 0; min-height: 100vh; display: grid; place-items: center;
    background: #f1f5f9; color: #0f172a;
    font-family: Inter, "Segoe UI", Arial, sans-serif;
}
.card {
    width: min(400px, calc(100% - 32px)); background: white;
    padding: 36px 34px; border-radius: 16px; border: 1px solid #e2e8f0;
    box-shadow: 0 12px 40px rgba(15, 23, 42, 0.08);
}
.marca { display: flex; align-items: baseline; gap: 10px; }
h1 { margin: 0; font-size: 30px; color: #1e293b; }
.marca span { color: #64748b; font-size: 14px; }
p { margin: 10px 0 0; color: #64748b; font-size: 14px; line-height: 1.5; }
label { display: block; margin: 20px 0 6px; font-weight: 600; font-size: 13px; color: #475569; }
input {
    width: 100%; padding: 12px 14px; border: 1px solid #cbd5e1;
    border-radius: 8px; font-size: 15px;
}
input:focus { outline: none; border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15); }
button {
    width: 100%; margin-top: 24px; padding: 13px; border: 0; border-radius: 8px;
    background: #2563eb; color: white; font-weight: 700; font-size: 15px; cursor: pointer;
}
button:hover { background: #1d4ed8; }
.erro {
    margin-top: 18px; padding: 10px 12px; border-radius: 8px;
    background: #fef2f2; color: #b91c1c; font-size: 14px;
}
.rodape { margin-top: 20px; text-align: center; font-size: 12px; color: #94a3b8; }
</style>
</head>
<body>
<main class="card">
    <div class="marca"><h1>SABIN</h1><span>Business Intelligence</span></div>
    <p>Sistema de apoio à decisão da livraria Bookmarked. Inicia sessão para continuar.</p>
    {% if erro %}<div class="erro">{{ erro }}</div>{% endif %}
    <form method="post" action="/login">
        <label for="utilizador">Utilizador</label>
        <input id="utilizador" name="utilizador" autocomplete="username" value="{{ utilizador }}" required autofocus>
        <label for="palavra_passe">Palavra-passe</label>
        <input id="palavra_passe" name="palavra_passe" type="password" autocomplete="current-password" required>
        <button type="submit">Entrar</button>
    </form>
    <div class="rodape">Acesso reservado. Não é possível criar contas novas.</div>
</main>
</body>
</html>"""

# Endereços que não precisam de sessão (página de login e ficheiros de estilo).
CAMINHOS_PUBLICOS = ("/login", "/logout", "/favicon.ico", "/assets/")


def credenciais_configuradas():
    """Devolve (utilizador, palavra-passe) ou None se o login estiver desligado."""
    utilizador = (os.getenv("SABIN_UTILIZADOR") or "").strip()
    palavra_passe = os.getenv("SABIN_PALAVRA_PASSE") or ""

    if not utilizador or not palavra_passe:
        return None

    return utilizador, palavra_passe


def login_ativo():
    return credenciais_configuradas() is not None


def ativar_autenticacao(server):
    """Protege todas as páginas da aplicação com o login simples."""
    credenciais = credenciais_configuradas()

    if credenciais is None:
        print("[Login] SABIN_UTILIZADOR/SABIN_PALAVRA_PASSE não definidas: login desligado.")
        return

    utilizador_certo, palavra_passe_certa = credenciais

    # A chave das sessões tem de ser igual em todos os processos do Gunicorn;
    # se não for indicada, é derivada da palavra-passe (mudar a palavra-passe
    # termina as sessões abertas).
    server.secret_key = os.getenv("SABIN_SESSION_SECRET") or hashlib.sha256(
        f"sabin-sessao:{utilizador_certo}:{palavra_passe_certa}".encode()
    ).hexdigest()

    server.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=bool(os.getenv("SABIN_ONLINE")),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    )

    @server.route("/login", methods=["GET", "POST"])
    def pagina_login():
        if session.get("sabin_utilizador"):
            return redirect("/")

        erro = None
        utilizador = ""

        if request.method == "POST":
            utilizador = (request.form.get("utilizador") or "").strip()
            palavra_passe = request.form.get("palavra_passe") or ""

            # compare_digest evita revelar a palavra-passe pelo tempo de resposta.
            certo = hmac.compare_digest(
                utilizador.casefold().encode(),
                utilizador_certo.casefold().encode(),
            ) & hmac.compare_digest(
                palavra_passe.encode(),
                palavra_passe_certa.encode(),
            )

            if certo:
                session.clear()
                session.permanent = True
                session["sabin_utilizador"] = utilizador_certo
                return redirect("/")

            # Pequena pausa para dificultar tentativas repetidas.
            time.sleep(1)
            erro = "Utilizador ou palavra-passe incorretos."

        return render_template_string(
            PAGINA_LOGIN,
            erro=erro,
            utilizador=utilizador,
        )

    @server.route("/logout")
    def terminar_sessao():
        session.clear()
        return redirect("/login")

    @server.before_request
    def exigir_login():
        if request.path.startswith(CAMINHOS_PUBLICOS):
            return None

        if session.get("sabin_utilizador"):
            return None

        # Pedidos internos do Dash (callbacks) recebem 401 em vez de um
        # redirecionamento, que o Dash não saberia mostrar.
        if request.path.startswith("/_dash") and request.method != "GET":
            return "Sessão terminada. Volta a iniciar sessão.", 401

        return redirect("/login")

    print(f"[Login] Login ativo para o utilizador «{utilizador_certo}».")
