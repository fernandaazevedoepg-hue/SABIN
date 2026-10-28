# SABIN — Sistema de Análise de Business Intelligence para Negócios

## 1. Apresentação do projeto

O SABIN é um projeto desenvolvido no âmbito da Prova de Aptidão Profissional do curso de Programador de Informática. Consiste num sistema de Business Intelligence aplicado a uma livraria fictícia, denominada **Bookmarked**, com o objetivo de transformar dados operacionais em informação útil para a análise do negócio e o apoio à tomada de decisão.

A solução integra uma aplicação Web, uma base de dados PostgreSQL, um Data Warehouse dimensional, um processo ETL, um modelo de previsão da receita e dashboards desenvolvidos no Microsoft Power BI.

## 2. Aplicação online

A aplicação Web está disponível em:

**https://sabin-olmt.onrender.com/**

A aplicação está alojada no Render e utiliza uma base de dados PostgreSQL disponibilizada pelo Supabase. Por utilizar um plano gratuito de alojamento, poderá demorar algum tempo a responder após períodos de inatividade.

### Credenciais de acesso para o júri

| Campo | Valor |
|---|---|
| Utilizador | `admin` |
| Palavra-passe | `12345` |

Estas credenciais permitem aceder à versão de demonstração do SABIN para efeitos de avaliação académica.

## 3. Funcionalidades principais

- **Gestão do catálogo:** consulta, pesquisa, adição e edição de livros, atualização de preços e gestão do stock.
- **Gestão de clientes:** registo de clientes durante o processo de venda.
- **Gestão de vendas:** registo de vendas através de um carrinho e seleção do método de pagamento.
- **Gestão de reservas:** criação, cancelamento e conclusão de reservas, com registo da venda quando o livro é levantado.
- **Gestão de stock:** consulta do histórico de movimentos e alterações de preços.
- **Processo ETL:** extração, transformação e carregamento dos dados para o Data Warehouse, executado automaticamente após as operações relevantes.
- **Data Warehouse:** organização dos dados através de um modelo dimensional.
- **Análise de desempenho:** indicadores, gráficos e dashboards para analisar a atividade comercial.
- **Previsão da receita:** estimativa da receita dos três meses seguintes, com visualizações temporais.
- **Alertas preditivos:** identificação de variações previstas e tendências relevantes.
- **Stock e reposição:** identificação dos livros prioritários e das quantidades a repor.
- **Exportação de relatórios:** geração de ficheiros Excel e PDF para um período selecionado.
- **Power BI:** dashboards ligados ao Data Warehouse através de DirectQuery.

## 4. Tecnologias utilizadas

| Tecnologia | Finalidade |
|---|---|
| Python | Desenvolvimento da aplicação e processamento dos dados |
| Dash | Construção da interface Web |
| PostgreSQL | Sistema de gestão da base de dados |
| Supabase | Alojamento da base de dados PostgreSQL |
| SQLAlchemy | Ligação e interação com a base de dados |
| Pandas | Tratamento e transformação de dados |
| Plotly | Criação de gráficos e visualizações |
| Scikit-learn | Modelo de previsão da receita |
| Microsoft Power BI | Dashboards e análise visual |
| Render | Alojamento da aplicação Web |
| Gunicorn | Execução da aplicação em produção |
| Flask | Servidor utilizado pelo Dash e suporte às sessões de autenticação |
| openpyxl e ReportLab | Geração de ficheiros Excel e PDF |
| python-dotenv | Leitura das variáveis de ambiente a partir do ficheiro `.env` |
| Google Books, Open Library e pesquisa Web | Pesquisa de informação bibliográfica através do ISBN |

## 5. Organização do repositório

| Ficheiro ou diretório | Descrição |
|---|---|
| `app.py` | Ponto de entrada da aplicação Web |
| `services/` | Serviços de catálogo, vendas, clientes, reservas, exportações e integração |
| `etl/` | Componentes de extração, transformação e carregamento de dados |
| `analysis/` | Análise de dados, previsões e alertas |
| `database/relational/` | Scripts SQL da base de dados operacional |
| `database/dimensional/` | Criação do Data Warehouse |
| `database/migrations/` | Alterações à estrutura da base de dados |
| `database/validation/` | Consultas para validação dos dados |
| `assets/` | Ficheiros CSS da interface |
| `certificados/` | Certificado público do Supabase utilizado pelo Power BI Desktop |
| `tests/` | Testes unitários automáticos |
| `powerbi/` | Relatório Power BI |
| `requirements.txt` | Dependências Python do projeto |
| `.env` | Configuração da ligação à base de dados |

Os diretórios `outputs/` e `exports/` são utilizados para os ficheiros gerados durante a execução da aplicação e não fazem parte do repositório.

## 6. Instalação e configuração local

### 6.1. Pré-requisitos

Antes de iniciar a instalação, é necessário ter:

- Python 3.13, versão utilizada no desenvolvimento e no Render.
- Git instalado.
- Acesso a uma base de dados PostgreSQL compatível com a estrutura do SABIN.
- Um editor de código, como o Visual Studio Code.

### 6.2. Obter o código-fonte

Clonar o repositório:

```bash
git clone https://github.com/fernandaazevedoepg-hue/SABIN.git
```

Entrar na pasta do projeto:

```bash
cd SABIN
```

### 6.3. Criar e ativar o ambiente virtual

Criar um ambiente virtual para instalar as dependências sem interferir com as restantes instalações Python do computador:

```bash
python -m venv venv
```

No Windows, utilizando o PowerShell, ativar o ambiente virtual:

```powershell
.\venv\Scripts\Activate.ps1
```

Se surgir um erro de permissões a indicar que a execução de scripts está desativada, executar o seguinte comando na mesma janela do PowerShell:

```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
```

Depois, voltar a executar o comando de ativação:

```powershell
.\venv\Scripts\Activate.ps1
```

Esta alteração é temporária e aplica-se apenas ao processo atual do PowerShell.

Se estiver a ser utilizado o Command Prompt (CMD), executar:

```bat
venv\Scripts\activate.bat
```

### 6.4. Instalar as dependências

Com o ambiente virtual ativo, instalar as bibliotecas necessárias:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 6.5. Configurar a ligação à base de dados

A aplicação utiliza o ficheiro `.env`, localizado na pasta principal do projeto, ao mesmo nível de `app.py`.

A variável obrigatória para a ligação da aplicação à base de dados é:

| Variável | Finalidade |
|---|---|
| `DATABASE_URL` | URL de ligação à base de dados PostgreSQL |
| `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` | Parâmetros de ligação separados, utilizados por ferramentas externas, como o `psql` e o Power BI |
| `DW_SCHEMA` | Esquema do Data Warehouse; por omissão, `dw` |
| `SABIN_DATA_REFERENCIA` | Data de referência opcional para testes de stock e previsão |
| `POWER_BI_FILE` | Caminho opcional para outro ficheiro `.pbix` |

A aplicação utiliza a biblioteca `python-dotenv` para carregar as variáveis e o SQLAlchemy para estabelecer a ligação à base de dados. Sem a variável `DATABASE_URL`, a aplicação não consegue iniciar.

### 6.6. Preparar uma nova base de dados

A base de dados utilizada pela versão de demonstração já se encontra preparada. Os passos seguintes destinam-se a quem pretenda criar uma nova base de dados.

Executar os scripts pela ordem indicada:

1. `database/relational/01_schema.sql` — criação das tabelas operacionais.
2. `database/relational/02_constraints.sql` — criação das restrições.
3. `database/relational/03_triggers.sql` — criação das funções e triggers.
4. `database/relational/04_dados_teste.sql` — inserção de dados de exemplo, opcional.
5. `database/migrations/01_gestao_catalogo.sql` — criação das estruturas de histórico de stock e preços.
6. `database/dimensional/01_data_warehouse.sql` — criação das tabelas do Data Warehouse.

Após a criação das estruturas, executar o ETL:

```bash
python -m services.etl_service
```

Numa base de dados nova, poderá surgir inicialmente uma mensagem de erro relacionada com datas em falta na dimensão temporal, porque o calendário ainda não foi carregado. Após a criação do calendário, o processo volta a calcular os alertas de stock.

Para validar os dados, executar as consultas existentes em:

`database/validation/queries_validacao.sql`

Os totais de vendas, receita e unidades devem corresponder entre a base operacional e o Data Warehouse.

O Data Warehouse utiliza um modelo dimensional composto por seis dimensões de negócio, três dimensões de apoio e quatro tabelas de factos. A tabela `fact_vendas` utiliza a granularidade item de venda × autor × género, distribuindo o valor através do atributo `peso`.

O ETL limpa e volta a carregar as dimensões de negócio e a tabela `fact_vendas` numa única transação. No final, compara os resultados com a base operacional e anula a carga se forem detetadas inconsistências.

### 6.7. Executar a aplicação

Com as dependências instaladas e a ligação à base de dados configurada, executar:

```bash
python app.py
```

Abrir o navegador e aceder a:

http://127.0.0.1:8050/

A aplicação utiliza a porta definida pela variável de ambiente `PORT`, quando disponível, ou a porta `8050` por omissão.

### 6.8. Executar os testes automáticos

Os testes unitários verificam regras de gestão de stock, validação do ISBN e cálculo de indicadores.

Executar na pasta principal do projeto:

```bash
python -m unittest -v tests.test_unitarios
```

O resultado esperado na versão documentada é a execução de 15 testes com sucesso, terminando com a indicação `OK`.

## 7. Publicação e autenticação

A aplicação Web está alojada no Render e utiliza o Supabase para a base de dados PostgreSQL.

A configuração do ambiente de produção utiliza as seguintes variáveis:

| Variável | Finalidade |
|---|---|
| `DATABASE_URL` | Ligação à base de dados |
| `SABIN_ONLINE` | Identificação do ambiente online |
| `SABIN_UTILIZADOR` | Utilizador de acesso à aplicação |
| `SABIN_PALAVRA_PASSE` | Palavra-passe de acesso |
| `SABIN_SESSION_SECRET` | Chave opcional para assinatura das sessões |

A aplicação online utiliza uma conta única e não permite criar novas contas. As credenciais para avaliação encontram-se indicadas na secção 2.

A sessão de autenticação tem uma duração máxima de 12 horas. Em produção, a aplicação é executada através do Gunicorn, utilizando o comando:

```bash
gunicorn app:server
```

## 8. Configuração pública para avaliação académica

O ficheiro `.env` encontra-se disponibilizado no repositório de forma intencional, no contexto da avaliação académica do projeto.

Esta decisão destina-se a facilitar o acesso do júri à base de dados e a execução do sistema. Reconhece-se, contudo, que a publicação de credenciais num repositório público constitui um risco de segurança e não é uma prática recomendada para aplicações destinadas a utilização real.

A disponibilização pública das credenciais deve, por isso, ser entendida como uma exceção associada ao contexto de demonstração do SABIN.

## 9. Relatório Power BI

O projeto inclui o ficheiro `powerbi/sabin.pbix`, que pode ser aberto no Microsoft Power BI Desktop.

O relatório liga-se ao Data Warehouse alojado no Supabase através de um modelo composto: as tabelas do Data Warehouse utilizam DirectQuery, enquanto a tabela `_Medidas` utiliza o modo Import.

As páginas do relatório estão configuradas para atualização automática a cada minuto. Após uma operação na aplicação e a conclusão do ETL, os novos dados ficam disponíveis de acordo com a configuração de atualização.

A aplicação também disponibiliza o ficheiro Power BI através do botão existente na página Exportações.

### 9.1. Certificado do Supabase

Para estabelecer a ligação cifrada ao Supabase noutro computador Windows, o Power BI Desktop necessita do certificado raiz do Supabase.

O certificado público encontra-se na pasta `certificados/`, no ficheiro `prod-ca-2021.crt`.

Para o instalar:

1. Abrir a pasta `certificados/`.
2. Executar o ficheiro `instalar_certificado.bat`.
3. Confirmar a instalação quando o Windows solicitar autorização.
4. Fechar e voltar a abrir o Power BI Desktop.
5. Abrir o ficheiro `powerbi/sabin.pbix` e verificar a ligação.

Em alternativa, o certificado pode ser instalado manualmente através do ficheiro `prod-ca-2021.crt`, selecionando o arquivo «Autoridades de Certificação de Raiz Fidedignas».

## 10. Limitações conhecidas

O SABIN foi desenvolvido e validado com dados de uma livraria fictícia. Os resultados obtidos não garantem o mesmo desempenho num negócio real.

O modelo de previsão utiliza um histórico limitado e foi superado pelo modelo sazonal ingénuo na avaliação realizada. A aplicação utiliza uma única conta de acesso, sem perfis diferenciados, e algumas funcionalidades poderão ser melhoradas numa versão futura.

Estas limitações devem ser consideradas na interpretação dos indicadores e na eventual adaptação do sistema a um contexto empresarial real.
