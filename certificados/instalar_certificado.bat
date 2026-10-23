@echo off
chcp 65001 >nul
rem Instala o certificado raiz do Supabase no Windows (utilizador atual).
rem O Power BI Desktop precisa dele para ligar à base de dados com encriptação.

set "CERT=%~dp0prod-ca-2021.crt"

if not exist "%CERT%" (
    echo Não foi encontrado o ficheiro prod-ca-2021.crt nesta pasta.
    pause
    exit /b 1
)

echo A instalar o certificado do Supabase...
echo Se o Windows pedir confirmação, carrega em Sim.
certutil -user -addstore Root "%CERT%"

if errorlevel 1 (
    echo.
    echo A instalação falhou. Tenta instalar à mão: duplo clique no ficheiro .crt.
) else (
    echo.
    echo Certificado instalado. Fecha e volta a abrir o Power BI Desktop.
)
pause
