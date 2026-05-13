-- ============================================================
-- Atualizacao Key Results - Referencia: 2026-04-30 (fechamento de abril)
-- Gerado a partir da imagem do painel "KEY RESULTS | Central de Atendimento"
-- Painel atualizado em: 12/05/2026 | Ultimo mes exibido: abril/2026
-- ============================================================

-- Limpar dados do ano para reinserir
DELETE FROM gerencial.KeyResults WHERE ano = 2026;

-- ─────────────────────────────────────────────
-- KR RESULTADO PARCIAL E PROJETADO (anual)
-- ─────────────────────────────────────────────
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, dt_referencia)
VALUES
    (2026, NULL, 'KR_PARCIAL',   'GERAL', 101.6, 100, 101.6, '2026-04-30'),
    (2026, NULL, 'KR_PROJETADO', 'GERAL',  97.3, 100,  97.3, '2026-04-30');

-- ─────────────────────────────────────────────
-- PEL (Premio Emitido Liquido) - TABELA ANUAL
-- ─────────────────────────────────────────────
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta_total_ano, atingimento_pct, projetado_pct, projetado, gap_meta, dt_referencia)
VALUES
    -- BRASILSEG+AUTO (consolidado)
    (2026, NULL, 'PEL', 'BRASILSEG_AUTO', 451213696.00, 470830630.00,  95.83,  74.14, 451213696.00, -157423302.00, '2026-04-30'),
    -- BRASILSEG (acima da meta)
    (2026, NULL, 'PEL', 'BRASILSEG',       89512281.00,  75116968.00, 119.16, 119.16,  89512281.00,   14395313.00, '2026-04-30'),
    -- AUTOMOVEL
    (2026, NULL, 'PEL', 'AUTOMOVEL',      390779253.00, 395713662.00,  98.75,  73.25, 390779253.00, -142740777.00, '2026-04-30');

-- ─────────────────────────────────────────────
-- PEL MENSAL (BRASILSEG_AUTO consolidado) - valores em R$ a partir do grafico
-- jan: R$121,01 Mi | fev: R$100,61 Mi | mar: R$120,70 Mi | abr: R$108,90 Mi
-- ─────────────────────────────────────────────
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, atingimento_pct, dt_referencia)
VALUES
    (2026, 1, 'PEL', 'BRASILSEG_AUTO', 121010000.00,  98, '2026-04-30'),
    (2026, 2, 'PEL', 'BRASILSEG_AUTO', 100610000.00,  86, '2026-04-30'),
    (2026, 3, 'PEL', 'BRASILSEG_AUTO', 120700000.00, 102, '2026-04-30'),
    (2026, 4, 'PEL', 'BRASILSEG_AUTO', 108900000.00,  98, '2026-04-30');

-- ─────────────────────────────────────────────
-- RETENCAO
-- ─────────────────────────────────────────────
-- Mensal
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, dt_referencia)
VALUES
    (2026, 1, 'RETENCAO', 'GERAL', 32.7, 40.0, 81, '2026-04-30'),
    (2026, 2, 'RETENCAO', 'GERAL', 32.8, 40.0, 81, '2026-04-30'),
    (2026, 3, 'RETENCAO', 'GERAL', 33.8, 40.0, 83, '2026-04-30'),
    (2026, 4, 'RETENCAO', 'GERAL', 35.2, 40.0, 88, '2026-04-30');
-- Acumulado anual (Necessidade = "Infinito" no painel -> NULL no SQL)
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, necessidade, dt_referencia)
VALUES
    (2026, NULL, 'RETENCAO', 'GERAL', 33.6, 40.0, 83.97, NULL, '2026-04-30');

-- ─────────────────────────────────────────────
-- NPS
-- ─────────────────────────────────────────────
-- Mensal
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, dt_referencia)
VALUES
    (2026, 1, 'NPS', 'GERAL', 70.4, 75.5, 93, '2026-04-30'),
    (2026, 2, 'NPS', 'GERAL', 69.3, 75.5, 92, '2026-04-30'),
    (2026, 3, 'NPS', 'GERAL', 72.1, 75.5, 95, '2026-04-30'),
    (2026, 4, 'NPS', 'GERAL', 73.7, 75.5, 98, '2026-04-30');
-- Acumulado anual
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, ultimos_6m, dt_referencia)
VALUES
    (2026, NULL, 'NPS', 'GERAL', 71.3, 75.5, 94.5, 71.3, '2026-04-30');

-- ─────────────────────────────────────────────
-- FCR (First Contact Resolution)
-- ─────────────────────────────────────────────
-- Mensal
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, dt_referencia)
VALUES
    (2026, 1, 'FCR', 'GERAL', 77.9, 56.0, 139, '2026-04-30'),
    (2026, 2, 'FCR', 'GERAL', 78.1, 56.0, 139, '2026-04-30'),
    (2026, 3, 'FCR', 'GERAL', 76.6, 56.0, 137, '2026-04-30'),
    (2026, 4, 'FCR', 'GERAL', 76.4, 56.0, 136, '2026-04-30');
-- Acumulado anual (Necessidade = "-Infinito" no painel -> NULL no SQL, ja batido)
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, necessidade, dt_referencia)
VALUES
    (2026, NULL, 'FCR', 'GERAL', 77.2, 56.0, 137.9, NULL, '2026-04-30');

-- ─────────────────────────────────────────────
-- EFICIENCIA ATENDIMENTO DIGITAL (EAD)
-- ─────────────────────────────────────────────
-- Mensal
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, dt_referencia)
VALUES
    (2026, 1, 'EFICIENCIA_DIGITAL', 'GERAL', 20.6, 20.0, 105, '2026-04-30'),
    (2026, 2, 'EFICIENCIA_DIGITAL', 'GERAL', 17.1, 20.0,  85, '2026-04-30'),
    (2026, 3, 'EFICIENCIA_DIGITAL', 'GERAL', 18.1, 20.0,  91, '2026-04-30'),
    (2026, 4, 'EFICIENCIA_DIGITAL', 'GERAL', 20.8, 20.0, 105, '2026-04-30');
-- Acumulado anual (Necessidade = "Infinito" no painel -> NULL no SQL)
INSERT INTO gerencial.KeyResults (ano, mes, indicador, segmento, realizado, meta, atingimento_pct, necessidade, dt_referencia)
VALUES
    (2026, NULL, 'EFICIENCIA_DIGITAL', 'GERAL', 19.2, 20.0, 95.8, NULL, '2026-04-30');

-- ============================================================
-- Verificacao
-- ============================================================
SELECT indicador, segmento, mes, realizado, meta, atingimento_pct, projetado_pct, dt_referencia
FROM gerencial.KeyResults
WHERE ano = 2026
ORDER BY indicador, segmento, ISNULL(mes, 99);
GO
