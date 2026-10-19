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

- **Gestão do catálogo:** consulta e gestão de livros, autores, géneros e preços.
- **Gestão de clientes:** registo e consulta de clientes.
- **Gestão de vendas:** registo de vendas, seleção dos métodos de pagamento e tratamento dos dados associados.
- **Gestão de reservas:** criação e acompanhamento de reservas.
- **Gestão de stock:** consulta de movimentos e registo de reposições.
- **Processos ETL:** extração, transformação e carregamento de dados para análise.
- **Data Warehouse:** organização da informação num modelo dimensional.
- **Indicadores e gráficos:** análise dos dados do negócio através de métricas e visualizações.
- **Previsão da receita:** utilização de um modelo de aprendizagem automática para apoiar a análise dos resultados.
- **Alertas:** identificação de situações relevantes relacionadas com o stock e as previsões.
- **Exportação de dados:** geração de ficheiros Excel e PDF.
- **Power BI:** exploração da informação através de dashboards e relatórios analíticos.

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

## 5. Organização do repositório

O código está organizado em diretórios, de acordo com as responsabilidades dos diferentes componentes.

- `app.py` — ficheiro principal da aplicação Web.
- `services/` — serviços associados às operações do catálogo, vendas, clientes, reservas, exportações e integração.
- `etl/` — componentes relacionados com os processos de extração, transformação e carregamento de dados.
- `analysis/` — componentes de análise, previsão e geração de alertas.
- `database/relational/` — scripts SQL relacionados com a estrutura da base de dados operacional, restrições, triggers e dados de teste.
- `database/dimensional/` — scripts de criação do modelo dimensional do Data Warehouse.
- `database/migrations/` — scripts de alterações à estrutura da base de dados.
- `database/validation/` — consultas SQL utilizadas na validação dos dados e das estruturas.
- `assets/` — ficheiros CSS e JavaScript utilizados pela interface.
- `outputs/` — ficheiros CSV produzidos por determinados processos analíticos.
- `powerbi/` — ficheiro do relatório Power BI.
- `requirements.txt` — lista de dependências Python necessárias ao projeto.
- `.env` — configuração das variáveis utilizadas na ligação à base de dados.

## 6. Instalação e configuração local

### 6.1. Pré-requisitos

Para executar o projeto localmente, são necessários:

- Python instalado.
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

O ficheiro `requirements.txt` contém as bibliotecas utilizadas pela aplicação, incluindo dependências específicas do Windows.

### 6.5. Configurar a ligação à base de dados

A aplicação utiliza o ficheiro `.env` para disponibilizar as variáveis de ambiente necessárias à ligação à base de dados PostgreSQL.

A configuração existente inclui as seguintes variáveis:

| Variável | Finalidade |
|---|---|
| `PGHOST` | Endereço do servidor PostgreSQL. |
| `PGPORT` | Porta de ligação ao servidor. |
| `PGDATABASE` | Nome da base de dados. |
| `PGUSER` | Utilizador da base de dados. |
| `PGPASSWORD` | Palavra-passe do utilizador. |
| `DATABASE_URL` | URL completa utilizada pela aplicação para estabelecer a ligação à base de dados. |

O ficheiro `.env` deve estar na pasta principal do projeto, ao mesmo nível de `app.py`.

A aplicação carrega as variáveis de ambiente através da biblioteca `python-dotenv` e utiliza a variável `DATABASE_URL` para criar a ligação à base de dados através do SQLAlchemy.

Se esta variável não estiver definida, a aplicação não consegue iniciar.

### 6.6. Preparar a base de dados

A aplicação necessita de uma base de dados PostgreSQL acessível e com a estrutura esperada pelo código.

Os scripts SQL encontram-se organizados no diretório `database/`. A estrutura relacional, o modelo dimensional, as migrações e as consultas de validação devem ser consultados de acordo com a finalidade de cada script.

Antes de executar scripts de criação ou de inserção de dados, deve confirmar-se a sua finalidade e o ambiente de destino.

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

## 7. Publicação da aplicação

A versão online do SABIN utiliza o Render para alojar a aplicação Web e o Supabase para alojar a base de dados PostgreSQL.

A configuração do ambiente online utiliza as seguintes variáveis:

- `DATABASE_URL` — URL de ligação à base de dados.
- `SABIN_ONLINE` — variável que identifica o modo de funcionamento online.

A aplicação é executada em produção através do Gunicorn. O comando de arranque configurado no serviço de alojamento deve corresponder ao objeto de aplicação definido no código.

O endereço público da aplicação é:

https://sabin-olmt.onrender.com/

## 8. Disponibilização pública das credenciais para avaliação

As credenciais de ligação à base de dados encontram-se disponibilizadas no ficheiro `.env` deste repositório de forma intencional e excecional, no âmbito da Prova de Aptidão Profissional.

Esta decisão foi tomada para **facilitar o acesso do júri à base de dados e permitir a avaliação prática do SABIN**, reduzindo a necessidade de procedimentos adicionais de configuração. A disponibilização das credenciais procura simplificar a utilização do sistema durante a avaliação académica.

Reconhece-se que a publicação de credenciais num repositório público constitui um risco de segurança e não corresponde a uma prática recomendada no desenvolvimento e na publicação de aplicações reais. Neste projeto, a decisão foi tomada conscientemente, tendo em consideração o contexto académico e as necessidades específicas de avaliação.

A exposição pública pode permitir que terceiros utilizem as credenciais para aceder aos recursos associados à base de dados. Por isso, esta opção deve ser entendida como uma exceção destinada à avaliação do projeto, não devendo ser reproduzida em aplicações destinadas a utilização real.

## 9. Relatório Power BI

O projeto inclui o relatório Power BI no diretório `powerbi/`.

O ficheiro pode ser aberto através do Microsoft Power BI Desktop, desde que esteja disponível localmente e exista uma configuração de acesso válida à fonte de dados.

O relatório permite explorar os dados através de dashboards e visualizações analíticas. O comportamento da ligação e a atualização dos dados dependem da configuração da fonte de dados e do ambiente de execução utilizado.