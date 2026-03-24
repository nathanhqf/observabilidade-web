# Observabilidade Call Center - Web Dashboard

## Visao Geral do Projeto

Dashboard web de monitoramento em tempo real da volumetria do call center Brasilseg.
Substituiu a abordagem anterior via Power BI HTML Content (abandonada por limitacoes de 32K chars por medida DAX e fragilidade no deploy de chunks).

**Motivacao:** Detectar picos de volume por DDD causados por desastres naturais (enchentes, tempestades) que impactam a operacao do seguro.

## Arquitetura

```
Browser (static/index.html)  -->  FastAPI (app.py :8050)  -->  SQL Server (INFO_CENTRAL 10.206.244.39:1433)
```

- **Frontend:** HTML/CSS/JS puro (sem frameworks). SVG maps do Brasil por DDD, tabelas, heatmaps, graficos.
- **Backend:** FastAPI + pymssql. 4 endpoints REST + servir arquivos estaticos.
- **Banco:** SQL Server `INFO_CENTRAL` com autenticacao SQL (credenciais no `.env`).

## Estrutura de Arquivos

```
observabilidade_web/
  app.py              # Backend FastAPI - todos os endpoints
  requirements.txt    # fastapi, uvicorn, pymssql, python-dotenv
  .env                # SQL_SERVER, SQL_PORT, SQL_DATABASE, SQL_USER, SQL_PASSWORD
  adapt_html.py       # Script one-shot que gerou index.html a partir do painel PBI original
  static/
    index.html        # Frontend completo (~260KB, inclui SVG_MAP_DATA inline)
```

## Endpoints da API

| Rota | Retorno | Fonte SQL |
|------|---------|-----------|
| `GET /` | Serve index.html | - |
| `GET /api/volume` | `{data: [...], meta: {tlvDate}}` - Volume por DDD do dia | `genesys.ConversationDetails` + `controle.Municipios_DDD_IBGE` + `tlv.Atendimentos_Genesys` |
| `GET /api/motivos?ddds=11,21` | `[{classe, qtd, tma, grupos: [{grupo, qtd, tma, tipos: [...]}]}]` - Filtro DDD opcional | `tlv.Atendimentos_Genesys` + `genesys.ConversationDetails` (quando filtrado) |
| `GET /api/municipios` | `{"11": {"u":"SP", "m":["Sao Paulo",...]}, ...}` | `controle.Municipios_DDD_IBGE` |
| `GET /api/agentes` | `[{grupo_operacao, total, ativos}]` | `dotacao.perfil` + `sgdot.operations*` |

## Tabelas SQL Server (banco INFO_CENTRAL)

### genesys.ConversationDetails
Detalhes de cada interacao Genesys Cloud.
- `conversationId` (PK varchar 100)
- `conversationStart`, `conversationEnd` (datetime)
- `ddd` (varchar 100) - codigo DDD extraido do ANI
- `ani` (varchar 100) - numero de origem
- `originatingDirection` (varchar 50)
- `ivr_total_duration_seconds` (int)
- `ivr_abandon` (bit)
- `customer_mediaTypes`, `call_flow_detail`, `ivr_participantNames`, `ivr_disconnectTypes`, `ivr_flow_exitReasons`
- `external_disconnectTypes`, `agent_disconnect_types`, `acd_participantNames`
- `loadDate` (datetime, default getdate())

### tlv.Atendimentos_Genesys
Classificacao de motivos por atendimento. Pode ter **1 dia de defasagem** em relacao ao Genesys.
- `Conversation_ID` (FK para ConversationDetails.conversationId)
- `Atendimento_id`, `ID_Sistema_Interacao`, `Evento_id` (ints)
- `Dt_Atendimento`, `Dt_Interacao`, `Dt_Evento` (datetime)
- `Classe_Processo`, `Grupo_Processo`, `Tipo_Processo` (varchar 100) - hierarquia de motivos
- `Duracao_Interacao` (int, segundos)
- `Duracao_Tabulacao` (int, segundos - ACW)
- `Rank_Motivo_Principal` (int) - usar = 1 para motivo principal
- `Rank_Duracao`, `Ordem_Evento`, `Evento_Dentro_Janela`

### controle.Municipios_DDD_IBGE
Mapeamento DDD -> Municipio -> UF -> Regiao. ~5571 municipios.
- `CN` (bigint) - codigo DDD
- `CO_MUNICIPIO_IBGE` (bigint)
- `UF_CN` (varchar) - sigla UF
- `[Nome-UF_CN]` (varchar) - nome da microrregiao/estado
- `NO_MUNICIPIO_UF` (varchar) - nome do municipio
- `UF_REGIAO` (varchar 50) - "Sul", "Sudeste", "Centro-Oeste", "Nordeste", "Norte"

### dotacao.perfil + sgdot.operations + sgdot.operations_groups
Perfil de agentes do call center.
- `cargo_atual` IN ('atendente', 'assistente')
- `STATUS_PERFIL` = 'Ativo'
- `operacao` -> `sgdot.operations.name` -> `sgdot.operations_groups.name` (grupo_operacao)

## Logica de Negocio Importante

### Severidade
Calculada em `_severity()` no app.py. Considera:
- Todas as janelas temporais (var15, var30, var1h, var12h, var24h, var7d)
- Janelas curtas (15m/30m/1h) tem thresholds mais altos que longas
- DDDs com volume < 10 chamadas sao automaticamente "normal" (evita falsos alertas por volatilidade)

### Variacoes Temporais
Cada `varXX` compara o volume da janela atual vs mesma janela do dia anterior.
Ex: `var1h` = ((volume ultima hora hoje) / (volume mesma hora ontem) - 1) * 100

### TMA (Tempo Medio de Atendimento)
Calculado somente para chamadas finalizadas (`conversationEnd IS NOT NULL`).
Chamadas ainda em andamento sao excluidas para nao distorcer a media.

### ACW (After Contact Work)
Calculado por DDD quando possivel (JOIN com TLV), com fallback para media global.

### Defasagem TLV
A tabela `tlv.Atendimentos_Genesys` pode estar 1+ dia atrasada em relacao ao Genesys.
O endpoint `/api/volume` retorna `meta.tlvDate` e o frontend exibe aviso no header.
A query de motivos usa a data mais recente da propria TLV (nao do Genesys).

## Frontend - Pontos de Atencao

- `static/index.html` e um arquivo unico grande (~260KB) com HTML+CSS+JS inline
- SVG_MAP_DATA contem os paths de todos os DDDs do Brasil (manter, e estatico)
- `init()` faz fetch nos 3 endpoints em cascata (volume -> motivos -> municipios)
- Auto-refresh a cada 5 minutos via `setInterval`
- `CLS` armazena a arvore de motivos com `_grupos` para dados reais (nao mais Math.random)
- DDDs sem regiao valida sao ignorados no agrupamento por regiao
- 4 abas: Geral (mapa+graficos+tabela), Motivos (arvore+TMA+heatmap), Alertas, Glossario
- Dark/Light theme toggle

## Deploy

- **Local:** `python app.py` -> http://localhost:8050
- **Producao:** EC2 com IIS/Python/Node ja configurado. Usar uvicorn como servico ou reverse proxy no IIS.
- Credenciais em `.env` (nunca commitar)

## Historico de Decisoes

1. **PBI HTML Content abandonado** (2026-03-19): Limite de 32K chars por medida DAX, chunks frageis, deploy complexo via TOM library. Pivotou para web server.
2. **pymssql em vez de pyodbc** (2026-03-20): Mais simples de instalar no Windows, sem dependencia de ODBC drivers.
3. **Coluna CN (nao ddd) na Municipios_DDD_IBGE** (2026-03-20): A tabela de municipios usa `CN` como coluna de DDD, nao `ddd`.
4. **TLV com data propria** (2026-03-20): Motivos usam MAX(Dt_Atendimento) da TLV, nao do Genesys, por causa da defasagem.
5. **Variacoes reais implementadas** (2026-03-20): var15/30/1h/12h/24h/7d calculados comparando janela atual vs dia anterior.
6. **Volume minimo para severidade** (2026-03-20): DDDs com <10 chamadas = "normal" sempre.
7. **Motivos filtrados via backend** (2026-03-20): Arvore de motivos usa dados reais do banco filtrados por DDD (nao inferencia/proporcional). Frontend re-fetcha `/api/motivos?ddds=` quando filtros mudam.
