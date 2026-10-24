# SABIN — Sistema de Análise de Business Intelligence para Negócios

## 1. Apresentação do projeto

O SABIN é um projeto desenvolvido no âmbito da Prova de Aptidão Profissional (PAP) do curso de Programador de Informática. O sistema demonstra a aplicação de técnicas de Business Intelligence na análise de dados de uma livraria fictícia, denominada **Bookmarked**.

O projeto integra uma aplicação Web, uma base de dados relacional, um Data Warehouse dimensional, processos ETL, ferramentas de análise de dados e dashboards. O seu objetivo é apoiar a gestão da livraria através da organização, exploração e análise da informação do negócio.

## 2. Aplicação online

A aplicação Web está disponível no seguinte endereço:

**https://sabin-olmt.onrender.com/**

A aplicação utiliza o Render para o alojamento e o Supabase para disponibilizar a base de dados PostgreSQL.

O serviço de alojamento utiliza um plano gratuito, pelo que poderá demorar algum tempo a responder após períodos de inatividade.

## 3. Funcionalidades principais

O SABIN reúne funcionalidades operacionais e analíticas, nomeadamente:

- **Gestão do catálogo:** catálogo completo com pesquisa por título, autor ou ISBN e filtro por género; janelas para editar um livro, repor stock, alterar o preço e adicionar livros novos. Ao adicionar, a pesquisa por ISBN preenche os dados do livro e sugere o PVP.
- **Gestão de clientes:** registo de clientes novos durante a venda.
- **Gestão de vendas:** registo de vendas com carrinho e escolha do método de pagamento.
- **Gestão de reservas:** criação, cancelamento e conclusão de reservas. Ao concluir (quando o cliente levanta o livro), a venda é registada com o método de pagamento escolhido. As reservas pendentes expiram automaticamente depois da data limite.
- **Gestão de stock:** histórico dos movimentos de stock e das alterações de preço.
- **Processos ETL:** extração, transformação e carregamento dos dados para o Data Warehouse. O ETL corre automaticamente em segundo plano depois de cada operação na aplicação (venda, reserva, reposição, alteração de preço ou livro novo); não há botão para o executar. Também pode ser executado manualmente (secção 6.6).
- **Data Warehouse:** organização da informação num modelo dimensional.
- **Indicadores e gráficos:** análise dos dados do negócio através de métricas e visualizações.
- **Previsão da receita:** modelo de aprendizagem automática, com gráfico por mês, trimestre ou ano e *drill* (clicar num ponto para descer até aos meses e aos dias).
- **Alertas e interpretação do stock:** níveis de stock (Crítico, Atenção, Normal), livros a repor, livros mais procurados e textos curtos com sugestões.
- **Exportação de dados:** ficheiros Excel e PDF de um período escolhido.
- **Acesso com login:** conta única na versão online (secção 7.1).
- **Power BI:** dashboards ligados ao Data Warehouse em DirectQuery (secção 9).

## 4. Tecnologias utilizadas

| Tecnologia | Finalidade |
|---|---|
| Python | Desenvolvimento da aplicação e processamento dos dados. |
| Dash | Construção da interface Web. |
| PostgreSQL | Sistema de gestão da base de dados. |
| Supabase | Alojamento da base de dados PostgreSQL. |
| SQLAlchemy | Ligação e interação com a base de dados. |
| Pandas | Tratamento e transformação de dados. |
| Plotly | Criação de gráficos e visualizações. |
| Scikit-learn | Desenvolvimento do modelo de previsão da receita. |
| Microsoft Power BI | Construção de dashboards e análise visual. |
| Render | Alojamento da aplicação Web. |
| Gunicorn | Execução da aplicação no ambiente de produção. |
| Flask | Servidor usado pelo Dash; sessões do login. |
| openpyxl e ReportLab | Criação dos relatórios em Excel e em PDF. |
| python-dotenv | Leitura das variáveis do ficheiro `.env`. |
| Google Books, Open Library e pesquisa web (requests, ddgs) | Pesquisa dos dados de um livro pelo ISBN. |

## 5. Organização do repositório

O código está organizado em diretórios, de acordo com as responsabilidades dos diferentes componentes.

- `app.py` — ficheiro principal da aplicação Web.
- `services/` — serviços associados às operações do catálogo, vendas, clientes, reservas, exportações e integração.
- `etl/` — componentes relacionados com os processos de extração, transformação e carregamento de dados.
- `analysis/` — componentes de análise, previsão e geração de alertas.
- `database/relational/` — scripts SQL relacionados com a estrutura da base de dados operacional, restrições, triggers e dados de teste.
- `database/dimensional/` — script de criação do modelo dimensional do Data Warehouse (esquema `dw`).
- `database/migrations/` — scripts de alterações à estrutura da base de dados.
- `database/validation/` — consultas SQL utilizadas na validação dos dados e das estruturas.
- `assets/` — ficheiros CSS utilizados pela interface.
- `certificados/` — certificado público do Supabase para o Power BI Desktop (secção 9.1).
- `outputs/` e `exports/` — ficheiros gerados pela aplicação (CSV das análises, Excel e PDF exportados). São criados automaticamente e não fazem parte do repositório.
- `tests/` — testes unitários automáticos (TU01–TU15).
- `powerbi/` — ficheiro do relatório Power BI.
- `requirements.txt` — lista de dependências Python necessárias ao projeto.
- `.env` — configuração das variáveis utilizadas na ligação à base de dados.

## 6. Instalação e configuração local

### 6.1. Pré-requisitos

Para executar o projeto localmente, são necessários:

- Python 3.13 (a versão usada no desenvolvimento e no Render, definida no ficheiro `.python-version`). As bibliotecas do `requirements.txt` também têm instalação para Python 3.11, 3.12 e 3.14. No Python 3.10 ou anterior e no 3.15 a instalação falha (o pandas 3 exige pelo menos o 3.11 e ainda não há versão do pandas e do psycopg2 para o 3.15).
- Git instalado para clonar o repositório.
- Acesso a uma base de dados PostgreSQL compatível com a estrutura do SABIN.
- Um editor de código, como o Visual Studio Code.

### 6.2. Obter o código

Clonar o repositório:

```bash
git clone https://github.com/fernandaazevedoepg-hue/SABIN.git
```

Entrar na pasta do projeto:

```bash
cd SABIN
```

### 6.3. Criar o ambiente virtual

Criar um ambiente virtual Python:

```bash
python -m venv venv
```

No Windows, ativar o ambiente virtual através do PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

Se estiver a ser utilizado o Command Prompt (CMD), executar:

```bat
venv\Scripts\activate.bat
```

O ambiente virtual permite instalar as dependências do projeto de forma isolada.

### 6.4. Instalar as dependências

Com o ambiente virtual ativo, executar:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

O ficheiro `requirements.txt` contém as bibliotecas utilizadas pela aplicação.

### 6.5. Configurar a ligação à base de dados

A aplicação utiliza o ficheiro `.env` para disponibilizar as variáveis de ambiente necessárias à ligação à base de dados PostgreSQL.

A configuração existente inclui as seguintes variáveis:

| Variável | Finalidade |
|---|---|
| `DATABASE_URL` | URL completa utilizada pela aplicação para estabelecer a ligação à base de dados. É a única variável obrigatória. |
| `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` | Os mesmos dados de ligação, separados. Não são usados pelo código Python; servem para ligar à base de dados noutras ferramentas (por exemplo, `psql` ou o Power BI). |
| `DW_SCHEMA` | Opcional. Esquema do Data Warehouse usado pelo ETL, pelas análises e pela aplicação (por omissão, `dw`). Permite testar num esquema separado, por exemplo `dw_teste`. |
| `SABIN_DATA_REFERENCIA` | Opcional, só para testes. Data (AAAA-MM-DD) usada como «hoje» na análise de stock e na previsão. |
| `POWER_BI_FILE` | Opcional. Caminho de outro ficheiro `.pbix` para o botão Power BI da página Exportações (por omissão, `powerbi/sabin.pbix`). |

O ficheiro `.env` deve estar na pasta principal do projeto, ao mesmo nível de `app.py`.

A aplicação carrega as variáveis de ambiente através da biblioteca `python-dotenv` e utiliza a variável `DATABASE_URL` para criar a ligação à base de dados através do SQLAlchemy.

Se esta variável não estiver definida, a aplicação não consegue iniciar.

### 6.6. Preparar a base de dados

A aplicação necessita de uma base de dados PostgreSQL acessível e com a estrutura esperada pelo código. A base de dados do Supabase indicada no `.env` já está preparada; os passos abaixo só são necessários para criar uma base de dados nova.

Executar os scripts de `database/` por esta ordem (por exemplo, no SQL Editor do Supabase ou com `psql`):

1. `database/relational/01_schema.sql` — tabelas da base operacional.
2. `database/relational/02_constraints.sql` — restrições.
3. `database/relational/03_triggers.sql` — funções e *triggers* (stock, reservas, totais dos clientes).
4. `database/relational/04_dados_teste.sql` — dados de exemplo (opcional).
5. `database/migrations/01_gestao_catalogo.sql` — histórico de stock e de preços.
6. `database/dimensional/01_data_warehouse.sql` — tabelas do Data Warehouse (esquema `dw`), vazias.

Depois, carregar o Data Warehouse executando o ETL na pasta do projeto:

```bash
python -m services.etl_service
```

Numa base de dados nova, a primeira linha mostra «[ERRO] Alertas de stock: Datas sem correspondência na dim_data». É normal: o calendário só é criado pela carga, e os alertas de stock voltam a ser calculados logo a seguir, com «[OK] Alertas de stock». A partir daí, a aplicação executa o ETL sozinha depois de cada operação.

Para confirmar que o Data Warehouse está coerente com a base operacional, podem executar-se as consultas de `database/validation/queries_validacao.sql`: as vendas, a receita e as unidades devem ser iguais nos dois lados, e as consultas de pesos e de duplicados não devem devolver linhas.

O Data Warehouse segue o modelo dimensional definido pelo professor (`database/dimensional/01_data_warehouse.sql`): seis dimensões de negócio (`dim_data`, `dim_cliente`, `dim_livro`, `dim_autor`, `dim_genero`, `dim_pagamento`), três dimensões de apoio (`dim_nivel_stock`, `dim_modelo_previsao`, `dim_alerta_previsao`) e quatro factos (`fact_vendas`, `fact_stock`, `fact_previsao`, `fact_alerta_previsao`). A `fact_vendas` tem o grão item de venda × autor × género, e o valor de cada item é repartido pelo `peso`.

O ETL (`etl/load.py`) limpa e volta a carregar as dimensões de negócio e a `fact_vendas` numa única transação. Mantém o calendário e as fotografias de stock dos dias anteriores, e no fim compara o resultado com a base operacional. Se algum valor não coincidir, a carga é anulada.

### 6.7. Executar a aplicação

Depois de instalar as dependências e configurar a ligação à base de dados, executar:

```bash
python app.py
```

A aplicação utiliza a porta definida pela variável de ambiente `PORT`, quando disponível, ou a porta `8050` como valor predefinido.

No ambiente local, abrir o seguinte endereço no navegador:

```text
http://127.0.0.1:8050/
```

### 6.8. Executar os testes automáticos

Os testes unitários TU01–TU15 verificam as regras de stock, a validação do ISBN e o cálculo dos KPIs. Não precisam de ligação à base de dados nem de instalar nada além das dependências do projeto. Na pasta do projeto, executar:

```bash
python -m unittest -v tests.test_unitarios
```

No fim deve aparecer `Ran 15 tests` e `OK`.

## 7. Publicação da aplicação

A versão online do SABIN utiliza o Render para alojar a aplicação Web e o Supabase para alojar a base de dados PostgreSQL.

A configuração do ambiente online utiliza as seguintes variáveis:

- `DATABASE_URL` — URL de ligação à base de dados.
- `SABIN_ONLINE` — identifica a versão online: o cookie da sessão só é enviado por HTTPS e não se tenta instalar o certificado do Supabase (secção 9.1).
- `SABIN_UTILIZADOR` e `SABIN_PALAVRA_PASSE` — conta única de acesso à aplicação (ver secção 7.1).
- `SABIN_SESSION_SECRET` — opcional. Chave usada para assinar as sessões; se não existir, é derivada da conta.

### 7.1. Acesso com login

A aplicação online pede utilizador e palavra-passe. Existe uma única conta, definida pelas variáveis `SABIN_UTILIZADOR` e `SABIN_PALAVRA_PASSE` no Render (*Environment*), e não é possível criar contas novas. As credenciais de acesso para avaliação são entregues ao júri juntamente com o relatório.

Estas duas variáveis não são colocadas no `.env`, porque esse ficheiro está público no repositório. Sem elas (por exemplo, ao executar localmente), a aplicação abre sem pedir login. Para testar o login localmente no Windows (PowerShell):

```powershell
$env:SABIN_UTILIZADOR="juri"
$env:SABIN_PALAVRA_PASSE="escolher-uma-palavra-passe"
python app.py
```

O botão «Terminar sessão» fica no fundo do menu lateral. A sessão dura no máximo 12 horas.

A aplicação é executada em produção através do Gunicorn, com o comando de arranque `gunicorn app:server` (o objeto `server` é definido em `app.py`).

O endereço público da aplicação é:

https://sabin-olmt.onrender.com/

## 8. Disponibilização pública das credenciais para avaliação

As credenciais de ligação à base de dados encontram-se disponibilizadas no ficheiro `.env` deste repositório de forma intencional e excecional, no âmbito da Prova de Aptidão Profissional.

Esta decisão foi tomada para **facilitar o acesso do júri à base de dados e permitir a avaliação prática do SABIN**, reduzindo a necessidade de procedimentos adicionais de configuração. A disponibilização das credenciais procura simplificar a utilização do sistema durante a avaliação académica.

Reconhece-se que a publicação de credenciais num repositório público constitui um risco de segurança e não corresponde a uma prática recomendada no desenvolvimento e na publicação de aplicações reais. Neste projeto, a decisão foi tomada conscientemente, tendo em consideração o contexto académico e as necessidades específicas de avaliação.

A exposição pública pode permitir que terceiros utilizem as credenciais para aceder aos recursos associados à base de dados. Por isso, esta opção deve ser entendida como uma exceção destinada à avaliação do projeto, não devendo ser reproduzida em aplicações destinadas a utilização real.

## 9. Relatório Power BI

O projeto inclui o relatório Power BI no diretório `powerbi/`.

O ficheiro `sabin.pbix` abre-se no Microsoft Power BI Desktop. Liga-se ao Data Warehouse no Supabase em modo **DirectQuery**: as tabelas não são copiadas para o ficheiro, e cada visual consulta a base de dados. Só a tabela das medidas (`_Medidas`) está em modo de importação.

As páginas atualizam-se automaticamente de 1 em 1 minuto. Assim, depois de uma operação na aplicação e de o ETL terminar, os dados novos aparecem no relatório sem ser preciso carregar em Atualizar.

Na página **Exportações** da aplicação, o botão Power BI descarrega o ficheiro `sabin.pbix`.

### 9.1. Certificado do Supabase (Power BI noutro computador)

O Power BI Desktop liga-se ao Supabase com encriptação e, no Windows, só aceita essa ligação se o certificado raiz do Supabase estiver instalado no computador. Sem ele, ao abrir o `sabin.pbix` noutro computador aparece um erro de certificado.

O certificado está na pasta `certificados/` (`prod-ca-2021.crt`, «Supabase Root 2021 CA», válido até 26/04/2031). É um certificado público e não contém credenciais.

Ao executar `python app.py` no Windows, a aplicação verifica se o certificado já está instalado e, se faltar, instala-o automaticamente. O Windows pede uma única confirmação, à qual se responde **Sim**. Isto não acontece na versão online (Render).

Para o instalar sem executar a aplicação (por exemplo, para abrir apenas o `sabin.pbix`):

1. Abrir a pasta `certificados/` no Explorador de Ficheiros.
2. Fazer duplo clique em `instalar_certificado.bat` e carregar em **Sim** quando o Windows pedir confirmação.
3. Fechar e voltar a abrir o Power BI Desktop.

Em alternativa, pode instalar-se à mão: duplo clique em `prod-ca-2021.crt` › **Instalar certificado** › **Utilizador atual** › **Colocar todos os certificados no arquivo seguinte** › **Autoridades de Certificação de Raiz Fidedignas**.

A aplicação Python não precisa deste passo.
