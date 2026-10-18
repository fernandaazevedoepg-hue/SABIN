# SABIN — Sistema de Análise de Business Intelligence para Negócios

O SABIN é um projeto de Prova de Aptidão Profissional que demonstra a utilização de dados operacionais e analíticos para apoiar a gestão de uma livraria fictícia, a Bookmarked.

## Aplicação online

A aplicação Web está publicada em:
https://sabin-olmt.onrender.com/

A disponibilidade do serviço pode variar. A instância gratuita do Render pode demorar a responder depois de um período de inatividade.

## Tecnologias principais

- **Python** — lógica da aplicação e processos de tratamento de dados.
- **Dash** — interface Web.
- **PostgreSQL e Supabase** — base de dados operacional e alojamento da base de dados.
- **Pandas** — preparação e transformação de dados.
- **Data Warehouse dimensional** — organização dos dados para análise.
- **Microsoft Power BI** — dashboards e exploração analítica.
- **Scikit-learn** — modelo de previsão da receita.
- **Render e Gunicorn** — alojamento e execução da aplicação Web.

## Organização do repositório

- `app.py` — aplicação principal e interface Web.
- `services/` — serviços associados ao catálogo, clientes, vendas, reservas, exportações e integração.
- `etl/` — componentes de extração, transformação e carga de dados.
- `analysis/` — indicadores, previsões e geração de alertas.
- `database/relational/` — scripts SQL para estrutura relacional, restrições, triggers e dados de teste.
- `database/dimensional/` — script de criação do modelo dimensional do Data Warehouse.
- `database/migrations/` — scripts de alterações à estrutura da base de dados.
- `database/validation/` — consultas SQL de validação.
- `assets/` — ficheiros CSS e JavaScript utilizados pela interface.
- `outputs/` — ficheiros CSV produzidos por alguns processos analíticos.
- `powerbi/` — ficheiro do relatório Power BI.

## Configuração local

1. Instalar uma versão de Python compatível com as dependências do projeto.
2. Clonar o repositório e abrir a pasta do projeto.
3. Criar e ativar um ambiente virtual.
4. Instalar as dependências:

   ```bash
   pip install -r requirements.txt
   ```

5. Criar um ficheiro `.env` local com as variáveis necessárias à ligação à base de dados, seguindo a configuração utilizada no ambiente de desenvolvimento. Não reutilizar credenciais que tenham sido expostas publicamente.
6. Confirmar que a base de dados PostgreSQL está acessível e que as variáveis de ambiente estão corretamente definidas.
7. Iniciar a aplicação com:

   ```bash
   python app.py
   ```

A configuração da ligação à base de dados e os requisitos de execução podem variar conforme o ambiente. Os scripts SQL existentes devem ser analisados antes de serem executados: alguns criam estruturas ou inserem dados de teste e não devem ser executados indiscriminadamente sobre uma base de dados com informação real.

## Publicação

A aplicação online utiliza o Render e o Gunicorn. O comando de arranque configurado no Render é:

```bash
gunicorn app:server --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
```

A variável `DATABASE_URL` é utilizada para a ligação à base de dados. A variável `SABIN_ONLINE` identifica o modo de funcionamento online. Os valores destas variáveis devem ser configurados no ambiente de alojamento e nunca documentados neste ficheiro.

## Estado atual e tarefas pendentes

- Rever no Power BI as tabelas e os campos que contêm informação desnecessária.
- Resolver, com o professor orientador, a configuração de atualização dos dados no Power BI e confirmar o comportamento pretendido no ambiente disponível.
- Voltar a validar os dashboards depois das alterações ao modelo de dados e às medidas.
- Rever e documentar os scripts SQL, distinguindo os scripts de criação, os dados de teste, as migrações e as consultas de validação.
- Executar testes finais à aplicação e atualizar o relatório da PAP de acordo com os resultados efetivamente confirmados.

## Segurança

- Não guardar ficheiros `.env`, palavras-passe, tokens ou URLs com credenciais no repositório.
- Manter as credenciais em variáveis de ambiente locais ou na configuração segura do serviço de alojamento.
- Se uma credencial tiver sido publicada, alterá-la e avaliar a necessidade de remover os valores do histórico do Git.
- Não executar scripts de criação ou de dados de teste numa base de dados de produção sem verificar previamente o seu conteúdo e impacto.

## Nota sobre validação

A existência de um ficheiro ou script no repositório não significa que tenha sido executado no ambiente atual. Antes de utilizar scripts SQL, processos ETL ou funcionalidades analíticas, deve confirmar-se a configuração da base de dados e testar o comportamento no ambiente pretendido.
