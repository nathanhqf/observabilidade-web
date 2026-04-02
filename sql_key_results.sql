-- ============================================================================
-- KEY RESULTS - Tabela Fato para Painel de Resultados
-- Banco: INFO_CENTRAL | Schema: gerencial
-- Atualização: D-1 (manual)
-- ============================================================================

-- Tabela principal: armazena todos os KPIs de Key Results
-- Cada linha = 1 métrica + 1 período (mês ou ano)
IF NOT EXISTS (SELECT * FROM sys.tables t JOIN sys.schemas s ON t.schema_id = s.schema_id
               WHERE s.name = 'gerencial' AND t.name = 'KeyResults')
BEGIN
    CREATE TABLE gerencial.KeyResults (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        -- Período
        ano             INT            NOT NULL,       -- ex: 2026
        mes             INT            NULL,           -- 1-12 (NULL = acumulado anual)
        -- Identificação da métrica
        indicador       VARCHAR(50)    NOT NULL,       -- NPS, PEL, RETENCAO, FCR, EFICIENCIA_DIGITAL, KR_PARCIAL, KR_PROJETADO
        segmento        VARCHAR(50)    NOT NULL,       -- GERAL, BRASILSEG, AUTOMOVEL, BRASILSEG_AUTO, RESIDENCIAL, PATRIMONIAL, CREDITO_PROTEGIDO, VIDA, OUTROS
        -- Valores
        realizado       DECIMAL(18,2)  NULL,           -- Valor realizado (R$ para PEL, % para outros)
        meta            DECIMAL(18,2)  NULL,           -- Meta do período
        meta_total_ano  DECIMAL(18,2)  NULL,           -- Meta anual total (PEL)
        projetado       DECIMAL(18,2)  NULL,           -- Valor projetado
        projetado_pct   DECIMAL(10,2)  NULL,           -- % projetado de atingimento
        atingimento_pct DECIMAL(10,2)  NULL,           -- % de atingimento da meta
        gap_meta        DECIMAL(18,2)  NULL,           -- GAP em relação à meta
        necessidade     DECIMAL(10,2)  NULL,           -- % necessidade para atingir meta
        yoy_pct         DECIMAL(10,2)  NULL,           -- Comparativo Year-over-Year %
        -- NPS específico
        avaliacoes      INT            NULL,           -- Quantidade de avaliações (NPS)
        ultimos_6m      DECIMAL(10,2)  NULL,           -- Média últimos 6 meses (NPS)
        -- Controle
        dt_referencia   DATE           NOT NULL,       -- Data de referência do dado (último dia dos dados)
        dt_carga        DATETIME       NOT NULL DEFAULT GETDATE(),  -- Quando foi inserido/atualizado
        -- Índice único para evitar duplicatas
        CONSTRAINT UQ_KeyResults UNIQUE (ano, mes, indicador, segmento)
    );
END;
GO

-- Índice para consultas frequentes
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_KeyResults_Indicador' AND object_id = OBJECT_ID('gerencial.KeyResults'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_KeyResults_Indicador
        ON gerencial.KeyResults (indicador, ano, mes)
        INCLUDE (segmento, realizado, meta, projetado, atingimento_pct);
END;
GO

-- ============================================================================
-- INSERÇÃO DE DADOS FICTÍCIOS (para testes)
-- Referência: 30/03/2026
-- ============================================================================

-- Limpar dados de exemplo anteriores
DELETE FROM gerencial.KeyResults WHERE ano = 2026;

-- ─────────────────────────────────────────────
-- KR RESULTADO PARCIAL E PROJETADO (anual)
-- ─────────────────────────────────────────────
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, projetado_pct, dt_referencia)
VALUES
    (2026, NULL, 'KR_PARCIAL',   'GERAL', 82.5, 100, 82.5, NULL, '2026-03-30'),
    (2026, NULL, 'KR_PROJETADO', 'GERAL', 97.0, 100, 97.0, NULL, '2026-03-30');

-- ─────────────────────────────────────────────
-- NPS
-- ─────────────────────────────────────────────
-- Mensal
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, avaliacoes, dt_referencia)
VALUES
    (2026, 1, 'NPS', 'GERAL', 70.6, 75, 2105, '2026-03-30'),
    (2026, 2, 'NPS', 'GERAL', 70.4, 75, 2198, '2026-03-30'),
    (2026, 3, 'NPS', 'GERAL', 72.2, 75, 2235, '2026-03-30');
-- Acumulado anual
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, avaliacoes, ultimos_6m, dt_referencia)
VALUES
    (2026, NULL, 'NPS', 'GERAL', 71.1, 75.5, 93.4, 6538, 70.5, '2026-03-30');

-- ─────────────────────────────────────────────
-- PEL (Prêmio Emitido Líquido)
-- ─────────────────────────────────────────────
-- Mensal - GERAL (Brasilseg apenas, sem auto)
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, dt_referencia)
VALUES
    (2026, 1, 'PEL', 'BRASILSEG', 15230450.00, NULL, '2026-03-30'),
    (2026, 2, 'PEL', 'BRASILSEG', 22150880.00, NULL, '2026-03-30'),
    (2026, 3, 'PEL', 'BRASILSEG', 23144640.00, NULL, '2026-03-30');

-- Acumulado anual - por segmento
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta_total_ano, atingimento_pct, projetado_pct, projetado, gap_meta, dt_referencia)
VALUES
    -- BRASILSEG+AUTO (consolidado)
    (2026, NULL, 'PEL', 'BRASILSEG_AUTO', 327626271.00, 1445459531.00, 22.67, 95.06, 1373988358.00, -71471173.00, '2026-03-30'),
    -- BRASILSEG
    (2026, NULL, 'PEL', 'BRASILSEG',       60525970.00,  283249303.00, 21.37, 89.61,  253831836.00, -29417467.00, '2026-03-30'),
    -- AUTOMÓVEL
    (2026, NULL, 'PEL', 'AUTOMOVEL',       267100301.00, 1162210228.00, 22.98, 96.38, 1120156522.00, -42053706.00, '2026-03-30');

-- Acumulado anual - Brasilseg por produto
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta_total_ano, atingimento_pct, projetado_pct, projetado, yoy_pct, dt_referencia)
VALUES
    (2026, NULL, 'PEL', 'RESIDENCIAL',         21881729.00, 22142101.00, NULL, NULL, 46709858.00,  -1.18,  '2026-03-30'),
    (2026, NULL, 'PEL', 'PATRIMONIAL',          30036980.00, 26242297.00, NULL, NULL, 125968105.00, 14.46, '2026-03-30'),
    (2026, NULL, 'PEL', 'CREDITO_PROTEGIDO',     5326446.00,  8643391.00, NULL, NULL, 22337876.00, -38.38, '2026-03-30'),
    (2026, NULL, 'PEL', 'VIDA',                 10742097.00,  8860942.00, NULL, NULL, 45057023.00,  21.23, '2026-03-30'),
    (2026, NULL, 'PEL', 'OUTROS',                3280815.00,  2756116.00, NULL, NULL, 13758974.00,  19.04, '2026-03-30');

-- PEL - YoY e % gerais (Brasilseg)
UPDATE gerencial.KeyResults
SET yoy_pct = 23.5,
    atingimento_pct = 21.4,
    projetado_pct = 89.6,
    projetado = 253832000.00
WHERE ano = 2026 AND mes IS NULL AND indicador = 'PEL' AND segmento = 'BRASILSEG';

-- ─────────────────────────────────────────────
-- RETENÇÃO
-- ─────────────────────────────────────────────
-- Mensal
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, dt_referencia)
VALUES
    (2026, 1, 'RETENCAO', 'GERAL', 32.9, 40.0, '2026-03-30'),
    (2026, 2, 'RETENCAO', 'GERAL', 32.8, 40.0, '2026-03-30'),
    (2026, 3, 'RETENCAO', 'GERAL', 33.9, 40.0, '2026-03-30');
-- Acumulado anual
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, necessidade, dt_referencia)
VALUES
    (2026, NULL, 'RETENCAO', 'GERAL', 33.2, 40.0, 83.02, 42.1, '2026-03-30');

-- ─────────────────────────────────────────────
-- FCR (First Contact Resolution)
-- ─────────────────────────────────────────────
-- Mensal
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, dt_referencia)
VALUES
    (2026, 1, 'FCR', 'GERAL', 68.5, 56.0, '2026-03-30'),
    (2026, 2, 'FCR', 'GERAL', 70.2, 56.0, '2026-03-30'),
    (2026, 3, 'FCR', 'GERAL', 71.0, 56.0, '2026-03-30');
-- Acumulado anual
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, necessidade, dt_referencia)
VALUES
    (2026, NULL, 'FCR', 'GERAL', 71.0, 56.0, 126.8, 51.3, '2026-03-30');

-- ─────────────────────────────────────────────
-- EFICIÊNCIA ATENDIMENTO DIGITAL
-- ─────────────────────────────────────────────
-- Mensal
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, dt_referencia)
VALUES
    (2026, 1, 'EFICIENCIA_DIGITAL', 'GERAL', 15.8, 20.0, '2026-03-30'),
    (2026, 2, 'EFICIENCIA_DIGITAL', 'GERAL', 16.9, 20.0, '2026-03-30'),
    (2026, 3, 'EFICIENCIA_DIGITAL', 'GERAL', 17.5, 20.0, '2026-03-30');
-- Acumulado anual
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, necessidade, dt_referencia)
VALUES
    (2026, NULL, 'EFICIENCIA_DIGITAL', 'GERAL', 17.5, 20.0, 87.4, 20.8, '2026-03-30');

-- ============================================================================
-- Verificação
-- ============================================================================
SELECT indicador, segmento, mes, realizado, meta, atingimento_pct, projetado_pct
FROM gerencial.KeyResults
WHERE ano = 2026
ORDER BY indicador, segmento, ISNULL(mes, 99);
GO
