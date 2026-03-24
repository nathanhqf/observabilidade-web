# Observabilidade Call Center - Web Dashboard

Painel web de monitoramento em tempo real da volumetria do call center Brasilseg, com visualização por DDD, região, motivos de atendimento e indicadores de criticidade.

![Stack](https://img.shields.io/badge/Python-FastAPI-009688?style=flat-square) ![DB](https://img.shields.io/badge/SQL%20Server-INFO__CENTRAL-CC2927?style=flat-square)

---

## Visão Geral

O dashboard exibe:

- **Volume de chamadas por DDD** — total do dia, chamadas em andamento, variação vs dia anterior
- **Mapa interativo do Brasil** — regiões de DDD com indicadores de severidade por cor
- **Heatmap horário** — distribuição de chamadas por hora para cada DDD
- **Motivos de atendimento** — árvore hierárquica (Classe > Grupo > Tipo) com TMA por motivo
- **Indicadores KPI** — volume total, em andamento, TMA, ACW, DDDs críticos, pico horário
- **Alertas de anomalia** — detecção automática baseada em variações percentuais
- **Auto-refresh** — dados atualizados automaticamente a cada 5 minutos

---

## Arquitetura

```
┌─────────────────┐       ┌──────────────┐       ┌──────────────────┐
│   Browser        │──────▶│  FastAPI      │──────▶│  SQL Server      │
│   (index.html)   │◀──────│  (app.py)    │◀──────│  INFO_CENTRAL    │
│                  │ JSON  │  :8050       │ pymssql│  10.206.244.39   │
└─────────────────┘       └──────────────┘       └──────────────────┘
```

**Frontend** (`static/index.html`): HTML/CSS/JS puro (sem frameworks). Faz `fetch()` nas APIs e renderiza mapas SVG, tabelas, gráficos e heatmaps.

**Backend** (`app.py`): FastAPI servindo arquivos estáticos e 4 endpoints REST que consultam SQL Server via `pymssql`.

---

## Estrutura do Projeto

```
observabilidade_web/
├── app.py              # Backend FastAPI — endpoints de API e servidor
├── requirements.txt    # Dependências Python
├── .env                # Variáveis de ambiente (conexão SQL Server)
├── adapt_html.py       # Script auxiliar que gerou o index.html
├── README.md
└── static/
    └── index.html      # Frontend — dashboard completo
```

---

## Pré-requisitos

- **Python 3.9+**
- **Acesso de rede** ao SQL Server `10.206.244.39:1433`
- **Credenciais** de leitura no banco `INFO_CENTRAL`

---

## Instalação e Execução Local

### 1. Clonar/copiar o projeto

```bash
cd observabilidade_web
```

### 2. Criar ambiente virtual (recomendado)

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac
```

### 3. Instalar dependências

```bash
python -m pip install -r requirements.txt
```

### 4. Configurar credenciais

Edite o arquivo `.env` com suas credenciais reais:

```env
SQL_SERVER=10.206.244.39
SQL_PORT=1433
SQL_DATABASE=INFO_CENTRAL
SQL_USER=seu_usuario_real
SQL_PASSWORD=sua_senha_real
```

> **Importante:** Nunca commite o `.env` com credenciais reais. Adicione `.env` ao `.gitignore`.

### 5. Executar

```bash
python app.py
```

O servidor inicia em **http://localhost:8050**. Abra no navegador.

---

## Endpoints da API

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/` | Serve o dashboard (index.html) |
| `GET` | `/api/volume` | Volume de chamadas por DDD do dia mais recente |
| `GET` | `/api/motivos` | Distribuição de motivos de atendimento |
| `GET` | `/api/municipios` | Municípios agrupados por DDD |
| `GET` | `/api/agentes` | Resumo de agentes por grupo de operação |

### Exemplo de resposta — `/api/volume`

```json
[
  {
    "ddd": 11,
    "micro": "São Paulo",
    "uf": "SP",
    "regiao": "Sudeste",
    "totalToday": 4523,
    "hourly": [0, 0, 0, 0, 0, 12, 85, 234, 456, ...],
    "ongoing": 32,
    "var24h": -8,
    "severity": "low",
    "tma": 285,
    "avgTalk": 120,
    "acw": 45,
    "topMotivo": "Solicitação Pós Venda"
  }
]
```

### Exemplo de resposta — `/api/motivos`

```json
[
  {"classe": "Solicitação Pós Venda", "qtd": 75314, "tma": 285},
  {"classe": "Sinistro", "qtd": 42100, "tma": 340}
]
```

### Exemplo de resposta — `/api/municipios`

```json
{
  "11": {"u": "SP", "m": ["São Paulo", "Guarulhos", "Osasco", "..."]},
  "21": {"u": "RJ", "m": ["Rio de Janeiro", "Niterói", "..."]}
}
```

---

## Tabelas SQL Server Utilizadas

| Schema.Tabela | Descrição |
|---------------|-----------|
| `genesys.ConversationDetails` | Detalhes de cada interação Genesys (conversationId, conversationStart, conversationEnd, ddd, ani, ivr_total_duration_seconds) |
| `tlv.Atendimentos_Genesys` | Atendimentos com classificação de motivo (Classe_Processo, Grupo_Processo, Tipo_Processo, Duracao_Interacao, Duracao_Tabulacao) |
| `controle.Municipios_DDD_IBGE` | Tabela de referência DDD ↔ Município ↔ UF ↔ Região (CN, UF_CN, NO_MUNICIPIO_UF, UF_REGIAO) |
| `dotacao.perfil` | Perfil de agentes (cargo_atual, operacao, STATUS_PERFIL, DT_DESLIGAMENTO) |
| `sgdot.operations` / `sgdot.operations_groups` | Grupos de operação para agrupamento de agentes |

---

## Deploy em Produção (EC2 / IIS)

### Opção 1 — Execução direta com Uvicorn

No servidor EC2 (onde já existe Python instalado):

```bash
# Copiar o projeto para o servidor
scp -r observabilidade_web/ ec2-user@servidor:/opt/observabilidade/

# No servidor
cd /opt/observabilidade/observabilidade_web
pip install -r requirements.txt
# Configurar .env com credenciais de produção

# Rodar como serviço
nohup python app.py > /var/log/observabilidade.log 2>&1 &
```

### Opção 2 — Systemd service (Linux)

Criar `/etc/systemd/system/observabilidade.service`:

```ini
[Unit]
Description=Observabilidade Call Center
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/observabilidade/observabilidade_web
ExecStart=/opt/observabilidade/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8050
Restart=always
RestartSec=5
EnvironmentFile=/opt/observabilidade/observabilidade_web/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable observabilidade
sudo systemctl start observabilidade
```

### Opção 3 — Reverse Proxy no IIS (Windows)

1. Instalar os módulos **URL Rewrite** e **Application Request Routing (ARR)** no IIS
2. Rodar o Uvicorn como serviço Windows (via `nssm` ou Task Scheduler):
   ```cmd
   nssm install Observabilidade "C:\Python39\python.exe" "C:\opt\observabilidade\app.py"
   nssm set Observabilidade AppDirectory "C:\opt\observabilidade"
   nssm start Observabilidade
   ```
3. Criar site no IIS com regra de Reverse Proxy apontando para `http://localhost:8050`

### Opção 4 — IIS com HttpPlatformHandler

No `web.config` do site IIS:

```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>
    <handlers>
      <add name="httpPlatformHandler"
           path="*" verb="*"
           modules="httpPlatformHandler"
           resourceType="Unspecified" />
    </handlers>
    <httpPlatform processPath="C:\Python39\python.exe"
                  arguments="app.py"
                  stdoutLogEnabled="true"
                  stdoutLogFile=".\logs\stdout"
                  startupTimeLimit="60">
      <environmentVariables>
        <environmentVariable name="PORT" value="%HTTP_PLATFORM_PORT%" />
      </environmentVariables>
    </httpPlatform>
  </system.webServer>
</configuration>
```

> **Nota:** Nesta opção, altere `app.py` para ler a porta da variável `PORT`:
> ```python
> port = int(os.getenv("PORT", "8050"))
> uvicorn.run(app, host="0.0.0.0", port=port)
> ```

---

## Funcionalidades do Dashboard

### Mapa Interativo
- Mapa do Brasil com todas as regiões de DDD em SVG
- Coloração por severidade (normal → baixo → médio → alto → crítico)
- Clique em um DDD no mapa para filtrar a tabela
- 5 painéis regionais (Sul, Sudeste, Centro-Oeste, Nordeste, Norte)

### Tabela de DDDs
- Ordenação por qualquer coluna (clique no cabeçalho)
- Busca textual por DDD, UF ou microrregião
- Sparklines de tendência 24h
- Badges de severidade com animação para críticos
- Colunas de variação: 15min, 30min, 1h, 12h, 24h, 7d

### Filtros
- Por Região, UF, DDD
- Por Município (busca com autocomplete)
- Por Período de comparação (15min a 7 dias)

### Abas
- **Geral** — mapa + gráficos + heatmap + tabela
- **Motivos** — árvore de atendimentos + TMA por motivo + heatmap motivo×DDD
- **Alertas** — lista de anomalias detectadas
- **Glossário** — explicação de cada métrica e indicador

### Temas
- Dark mode (padrão) e Light mode (botão no header)

---

## Troubleshooting

| Problema | Solução |
|----------|---------|
| Spinner infinito ao abrir | Abra o console do navegador (F12) → verifique erros de `fetch`. Provavelmente as credenciais SQL estão incorretas no `.env` |
| `Connection refused` no startup | Verifique se o SQL Server está acessível na rede (ping, telnet na porta 1433) |
| Dados não aparecem | Verifique se existem dados na tabela `genesys.ConversationDetails` para a data mais recente |
| Erro `pymssql` na instalação | No Windows pode ser necessário instalar o [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/). Alternativa: `pip install pymssql --no-build-isolation` |
| Porta 8050 em uso | Altere a porta em `app.py` na última linha, ou use: `uvicorn app:app --port 8051` |
