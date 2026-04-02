# Referencia para Atualizacao da Tabela gerencial.KeyResults

## Objetivo

Este documento serve como guia para uma IA interpretar imagens do painel de Key Results (PBI ou screenshots) e gerar o script SQL de UPDATE/INSERT correspondente na tabela `gerencial.KeyResults` do banco `INFO_CENTRAL`.

---

## Estrutura da Tabela

```
gerencial.KeyResults (
    ano             INT           -- Ano (ex: 2026)
    mes             INT NULL      -- 1-12 para mensal, NULL para acumulado anual
    indicador       VARCHAR(50)   -- Identifica a metrica (ver lista abaixo)
    segmento        VARCHAR(50)   -- Identifica o corte (ver lista abaixo)
    realizado       DECIMAL(18,2) -- Valor realizado
    meta            DECIMAL(18,2) -- Meta do periodo
    meta_total_ano  DECIMAL(18,2) -- Meta anual total (usado no PEL)
    projetado       DECIMAL(18,2) -- Valor projetado em R$ ou %
    projetado_pct   DECIMAL(10,2) -- % projetado de atingimento
    atingimento_pct DECIMAL(10,2) -- % de atingimento da meta
    gap_meta        DECIMAL(18,2) -- Diferenca entre projetado e meta (negativo = abaixo)
    necessidade     DECIMAL(10,2) -- % necessidade para atingir meta no periodo
    yoy_pct         DECIMAL(10,2) -- Variacao Year-over-Year em %
    avaliacoes      INT           -- Qtd avaliacoes (apenas NPS)
    ultimos_6m      DECIMAL(10,2) -- Media ultimos 6 meses (apenas NPS)
    dt_referencia   DATE          -- Data de referencia dos dados (ex: '2026-03-30')
)
```

**Chave unica:** `(ano, mes, indicador, segmento)` — nao pode haver duplicatas.

---

## Indicadores Validos

| indicador           | Descricao                          | Unidade do `realizado`     |
|---------------------|------------------------------------|----------------------------|
| `KR_PARCIAL`        | KR Resultado Parcial               | % (0-100)                  |
| `KR_PROJETADO`      | KR Resultado Projetado             | % (0-100)                  |
| `NPS`               | Net Promoter Score                 | Score (0-100)              |
| `PEL`               | Premio Emitido Liquido             | R$ (valor absoluto)        |
| `RETENCAO`          | Retencao                           | % (0-100)                  |
| `FCR`               | First Contact Resolution           | % (0-100)                  |
| `EFICIENCIA_DIGITAL`| Eficiencia Atendimento Digital     | % (0-100)                  |

---

## Segmentos Validos

| segmento           | Usado em       | Descricao                              |
|--------------------|----------------|----------------------------------------|
| `GERAL`            | Todos exceto PEL | Valor geral/consolidado              |
| `BRASILSEG`        | PEL            | Apenas Brasilseg (sem auto)            |
| `AUTOMOVEL`        | PEL            | Apenas Automovel                       |
| `BRASILSEG_AUTO`   | PEL            | Consolidado Brasilseg + Automovel      |
| `RESIDENCIAL`      | PEL            | Produto Residencial                    |
| `PATRIMONIAL`      | PEL            | Produto Patrimonial                    |
| `CREDITO_PROTEGIDO`| PEL            | Produto Credito Protegido              |
| `VIDA`             | PEL            | Produto Vida                           |
| `OUTROS`           | PEL            | Demais produtos agrupados              |

---

## Mapeamento Visual -> SQL

### Imagem 1: Visao Mensal (fundo escuro, layout com graficos)

Esta imagem contem dados mensais e acumulados. Referencia tipica: "Referencia: DD/MM/AAAA" no canto superior direito de cada secao.

#### Secao NPS
- **Gauge central (numero grande):** `realizado` do registro anual (mes=NULL, indicador='NPS', segmento='GERAL')
- **"Avaliacoes" abaixo do gauge:** `avaliacoes` do registro anual
- **"Meta" no topo do gauge (ex: 75,5):** `meta` do registro anual
- **Grafico mensal (pontos por mes):**
  - Cada ponto = 1 registro mensal (mes=1,2,3..., indicador='NPS', segmento='GERAL')
  - O valor do ponto = `realizado` daquele mes
  - Meta mensal pode ser constante, usar o campo `meta`
  - "Avaliacoes" pode variar por mes, campo `avaliacoes`
- **"Media Acumulada" (linha tracejada):** Calculada automaticamente pelo frontend (media dos meses)

#### Secao PEL (Premio Emitido Liquido)
- **"Resultado Geral" (ex: R$60,526 Mi / R$283,25 Mi):**
  - R$60,526 Mi = `realizado` do anual PEL/BRASILSEG
  - R$283,25 Mi = `meta_total_ano` do anual PEL/BRASILSEG
- **"% Atingimento" (ex: 21,4%):** `atingimento_pct` do anual PEL/BRASILSEG
- **"% Projetado" (ex: 89,6%):** `projetado_pct` do anual PEL/BRASILSEG
- **"Comparativo YoY" (ex: 23,5%):** `yoy_pct` do anual PEL/BRASILSEG
- **"Projetado Geral" (ex: 253,832 Mi / R$283,25 Mi):**
  - 253,832 Mi = `projetado` do anual PEL/BRASILSEG
- **Grafico mensal (barras por mes):**
  - Cada barra = `realizado` de (mes=N, indicador='PEL', segmento='BRASILSEG')
  - Linha "PEL Acumulado" = soma progressiva (calculada pelo frontend)
- **Linha de produtos (Residencial, Patrimonial, Credito Protegido, Vida, Outros):**
  - Valor grande (ex: R$21.881.729) = `realizado` do anual PEL/RESIDENCIAL
  - "Meta: R$22.142.101 (-1,18%)" = `meta_total_ano` e `yoy_pct`
  - "Projetado: R$ 46.709.858 (87%)" = `projetado` e `projetado_pct` (ou calcular %)

#### Secao Retencao
- **"% Retencao Total" (gauge, ex: 33,2%):** `realizado` do anual RETENCAO/GERAL
- **"Meta 40%":** `meta` do anual RETENCAO/GERAL
- **Pontos mensais (ex: jan 32,9%, fev 32,8%, mar 33,9%):**
  - Cada ponto = `realizado` de (mes=N, indicador='RETENCAO', segmento='GERAL')

---

### Imagem 2: Visao Anual/Resumo (fundo claro, layout tabular)

Esta imagem contem o resumo consolidado. Referencia tipica: "Atualizado em: DD/MM/AAAA" no topo.

#### KR Resultado Parcial / Projetado
- **"KR Resultado Parcial 82,5%":**
  - `realizado` = 82.5, `meta` = 100 (mes=NULL, indicador='KR_PARCIAL', segmento='GERAL')
- **"KR Resultado Projetado 97,0%":**
  - `realizado` = 97.0, `meta` = 100 (mes=NULL, indicador='KR_PROJETADO', segmento='GERAL')

#### Tabela PEL
| Campo na imagem   | Coluna SQL       | Notas                                      |
|--------------------|------------------|---------------------------------------------|
| Realizado          | `realizado`      | Valor em R$ sem formatacao                  |
| Meta Total         | `meta_total_ano` | Meta anual total em R$                      |
| Atg. Meta          | `atingimento_pct`| Percentual (ex: 22,67 = 22.67)             |
| Projetado (%)      | `projetado_pct`  | Percentual projetado de atingimento         |
| Valor Projetado    | `projetado`      | Valor projetado em R$                       |
| GAP Meta           | `gap_meta`       | Diferenca em R$ (negativo se abaixo)        |

Linhas da tabela:
- "BRASILSEG+AUTO" -> segmento = `BRASILSEG_AUTO`
- "BRASILSEG" -> segmento = `BRASILSEG`
- "AUTOMOVEL" -> segmento = `AUTOMOVEL`

#### Cards Retencao, NPS, FCR, Eficiencia
Cada card segue o mesmo padrao:

| Campo na imagem | Coluna SQL        |
|-----------------|-------------------|
| Realizado       | `realizado`       |
| Meta            | `meta`            |
| Atg. Meta       | `atingimento_pct` |
| Necessidade     | `necessidade`     |
| Ultimos 6 meses | `ultimos_6m` (so NPS) |

Indicadores:
- "Retencao" -> indicador = `RETENCAO`, segmento = `GERAL`
- "NPS" -> indicador = `NPS`, segmento = `GERAL`
  - "NPS 2026" = campo `realizado` do NPS anual
  - "Ultimos 6 meses" = campo `ultimos_6m`
- "FCR" -> indicador = `FCR`, segmento = `GERAL`
- "Eficiencia Atendimento Digital" -> indicador = `EFICIENCIA_DIGITAL`, segmento = `GERAL`

---

## Setas de tendencia na imagem

- Seta vermelha para baixo (triangulo vermelho) = realizado ABAIXO da meta
- Seta verde para cima (triangulo verde) = realizado ACIMA ou IGUAL a meta
- Essas setas NAO sao armazenadas no banco — o frontend calcula automaticamente

---

## Template SQL para Atualizacao

Ao gerar o script SQL a partir de uma imagem, use o padrao MERGE (ou DELETE+INSERT) abaixo.
A `dt_referencia` deve ser extraida do campo "Referencia:" ou "Atualizado em:" visivel na imagem.

```sql
-- ============================================================
-- Atualizacao Key Results - Referencia: YYYY-MM-DD
-- Gerado a partir de imagem do painel
-- ============================================================

-- Limpar dados do ano para reinserir
DELETE FROM gerencial.KeyResults WHERE ano = <ANO>;

-- KR PARCIAL E PROJETADO
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, dt_referencia)
VALUES
    (<ANO>, NULL, 'KR_PARCIAL',   'GERAL', <VALOR_PARCIAL>,   100, <VALOR_PARCIAL>,   '<YYYY-MM-DD>'),
    (<ANO>, NULL, 'KR_PROJETADO', 'GERAL', <VALOR_PROJETADO>, 100, <VALOR_PROJETADO>, '<YYYY-MM-DD>');

-- NPS MENSAL (um INSERT por mes disponivel)
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, avaliacoes, dt_referencia)
VALUES
    (<ANO>, 1, 'NPS', 'GERAL', <NPS_JAN>, <META_NPS>, <AVAL_JAN>, '<YYYY-MM-DD>'),
    (<ANO>, 2, 'NPS', 'GERAL', <NPS_FEV>, <META_NPS>, <AVAL_FEV>, '<YYYY-MM-DD>'),
    ...;
-- NPS ANUAL
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, avaliacoes, ultimos_6m, dt_referencia)
VALUES
    (<ANO>, NULL, 'NPS', 'GERAL', <NPS_ACUM>, <META_NPS_ANO>, <ATG_PCT>, <AVAL_TOTAL>, <ULT_6M>, '<YYYY-MM-DD>');

-- PEL MENSAL (Brasilseg)
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, dt_referencia)
VALUES
    (<ANO>, 1, 'PEL', 'BRASILSEG', <PEL_JAN>, NULL, '<YYYY-MM-DD>'),
    (<ANO>, 2, 'PEL', 'BRASILSEG', <PEL_FEV>, NULL, '<YYYY-MM-DD>'),
    ...;

-- PEL ANUAL por segmento
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta_total_ano, atingimento_pct, projetado_pct, projetado, gap_meta, dt_referencia)
VALUES
    (<ANO>, NULL, 'PEL', 'BRASILSEG_AUTO', <REAL>, <META_TOTAL>, <ATG>, <PROJ_PCT>, <PROJ_VAL>, <GAP>, '<YYYY-MM-DD>'),
    (<ANO>, NULL, 'PEL', 'BRASILSEG',      <REAL>, <META_TOTAL>, <ATG>, <PROJ_PCT>, <PROJ_VAL>, <GAP>, '<YYYY-MM-DD>'),
    (<ANO>, NULL, 'PEL', 'AUTOMOVEL',       <REAL>, <META_TOTAL>, <ATG>, <PROJ_PCT>, <PROJ_VAL>, <GAP>, '<YYYY-MM-DD>');

-- PEL ANUAL por produto Brasilseg (+ yoy_pct e projetado)
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta_total_ano, projetado, yoy_pct, dt_referencia)
VALUES
    (<ANO>, NULL, 'PEL', 'RESIDENCIAL',          <REAL>, <META>, <PROJ>, <YOY>, '<YYYY-MM-DD>'),
    (<ANO>, NULL, 'PEL', 'PATRIMONIAL',           <REAL>, <META>, <PROJ>, <YOY>, '<YYYY-MM-DD>'),
    (<ANO>, NULL, 'PEL', 'CREDITO_PROTEGIDO',     <REAL>, <META>, <PROJ>, <YOY>, '<YYYY-MM-DD>'),
    (<ANO>, NULL, 'PEL', 'VIDA',                  <REAL>, <META>, <PROJ>, <YOY>, '<YYYY-MM-DD>'),
    (<ANO>, NULL, 'PEL', 'OUTROS',                <REAL>, <META>, <PROJ>, <YOY>, '<YYYY-MM-DD>');

-- Atualizar YoY e % gerais do PEL BRASILSEG
UPDATE gerencial.KeyResults
SET yoy_pct = <YOY_GERAL>, atingimento_pct = <ATG>, projetado_pct = <PROJ_PCT>, projetado = <PROJ_VAL>
WHERE ano = <ANO> AND mes IS NULL AND indicador = 'PEL' AND segmento = 'BRASILSEG';

-- RETENCAO MENSAL
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, dt_referencia)
VALUES
    (<ANO>, 1, 'RETENCAO', 'GERAL', <RET_JAN>, <META_RET>, '<YYYY-MM-DD>'),
    (<ANO>, 2, 'RETENCAO', 'GERAL', <RET_FEV>, <META_RET>, '<YYYY-MM-DD>'),
    ...;
-- RETENCAO ANUAL
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, necessidade, dt_referencia)
VALUES
    (<ANO>, NULL, 'RETENCAO', 'GERAL', <RET_ACUM>, <META_RET>, <ATG>, <NEC>, '<YYYY-MM-DD>');

-- FCR MENSAL
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, dt_referencia)
VALUES
    (<ANO>, 1, 'FCR', 'GERAL', <FCR_JAN>, <META_FCR>, '<YYYY-MM-DD>'),
    (<ANO>, 2, 'FCR', 'GERAL', <FCR_FEV>, <META_FCR>, '<YYYY-MM-DD>'),
    ...;
-- FCR ANUAL
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, necessidade, dt_referencia)
VALUES
    (<ANO>, NULL, 'FCR', 'GERAL', <FCR_ACUM>, <META_FCR>, <ATG>, <NEC>, '<YYYY-MM-DD>');

-- EFICIENCIA DIGITAL MENSAL
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, dt_referencia)
VALUES
    (<ANO>, 1, 'EFICIENCIA_DIGITAL', 'GERAL', <EFD_JAN>, <META_EFD>, '<YYYY-MM-DD>'),
    (<ANO>, 2, 'EFICIENCIA_DIGITAL', 'GERAL', <EFD_FEV>, <META_EFD>, '<YYYY-MM-DD>'),
    ...;
-- EFICIENCIA DIGITAL ANUAL
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, necessidade, dt_referencia)
VALUES
    (<ANO>, NULL, 'EFICIENCIA_DIGITAL', 'GERAL', <EFD_ACUM>, <META_EFD>, <ATG>, <NEC>, '<YYYY-MM-DD>');
```

---

## Regras Importantes

1. **Valores monetarios (PEL):** Sempre em R$ sem abreviacao. Ex: "R$ 60,526 Mi" na imagem = `60525970.00` no SQL. "R$ 1.445.459.531" = `1445459531.00`.
2. **Percentuais:** Sempre como numero decimal. Ex: "22,67%" = `22.67`, "83,02%" = `83.02`.
3. **NPS score:** Nao e percentual, e um score. Ex: 71,1 = `71.1`.
4. **dt_referencia:** Extrair da imagem ("Referencia: 30/03/2026" = `'2026-03-30'`). Formato SQL: `YYYY-MM-DD`.
5. **mes = NULL:** Indica acumulado anual. NUNCA usar mes=0.
6. **Sinal do GAP:** Se a imagem mostra "-R$ 71.471.173" o valor e `-71471173.00`.
7. **Sinal do YoY:** Se mostra "+14,46%" = `14.46`. Se mostra "-1,18%" = `-1.18`.
8. **Dados mensais:** Se a imagem mostra grafico com pontos para jan/fev/mar, gerar 3 registros (mes=1,2,3). Se mostrar ate junho, gerar 6 (mes=1..6).
9. **DELETE antes de INSERT:** O script sempre apaga todos os dados do ano antes de reinserir, para evitar conflitos com a constraint UNIQUE.
10. **Dados nao visiveis:** Se um campo nao aparece na imagem, usar NULL. Nao inventar valores.
