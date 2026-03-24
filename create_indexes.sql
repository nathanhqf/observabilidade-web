-- =============================================================================
-- ÍNDICES PARA OTIMIZAÇÃO DO DASHBOARD OBSERVABILIDADE CALL CENTER
-- Banco: INFO_CENTRAL
-- Data: 2026-03-20
--
-- IMPORTANTE: Executar em horário de baixo uso. Índices com ONLINE = ON para
-- minimizar impacto (requer Enterprise Edition; remova se Standard).
-- =============================================================================

USE INFO_CENTRAL;
GO

-- =============================================================================
-- 1. genesys.ConversationDetails
--    Tabela mais crítica - escaneada ~14x no /api/volume
-- =============================================================================

-- Índice principal: conversationStart + ddd (cobre TODOS os filtros de janela temporal)
-- INCLUDE cobre SELECT sem precisar ir na tabela base (covering index)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ConversationDetails_Start_DDD' AND object_id = OBJECT_ID('genesys.ConversationDetails'))
CREATE NONCLUSTERED INDEX IX_ConversationDetails_Start_DDD
ON genesys.ConversationDetails (conversationStart, ddd)
INCLUDE (conversationEnd, ivr_total_duration_seconds)
WITH (ONLINE = ON, FILLFACTOR = 90);
GO

-- Índice para JOIN com TLV (top_motivo, acw_by_ddd)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ConversationDetails_ConvId_DDD' AND object_id = OBJECT_ID('genesys.ConversationDetails'))
CREATE NONCLUSTERED INDEX IX_ConversationDetails_ConvId_DDD
ON genesys.ConversationDetails (conversationId)
INCLUDE (ddd, conversationStart)
WITH (ONLINE = ON, FILLFACTOR = 90);
GO

-- =============================================================================
-- 2. tlv.Atendimentos_Genesys
--    Usada em /api/motivos e JOINs com Genesys
-- =============================================================================

-- Índice principal: Dt_Atendimento + filtros de motivo
-- Cobre a query de motivos sem ir na tabela base
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_AtendimentosGenesys_DtAtend_Motivos' AND object_id = OBJECT_ID('tlv.Atendimentos_Genesys'))
CREATE NONCLUSTERED INDEX IX_AtendimentosGenesys_DtAtend_Motivos
ON tlv.Atendimentos_Genesys (Dt_Atendimento, Rank_Motivo_Principal)
INCLUDE (Classe_Processo, Grupo_Processo, Tipo_Processo, Duracao_Interacao, Duracao_Tabulacao, Conversation_ID)
WITH (ONLINE = ON, FILLFACTOR = 90);
GO

-- Índice para JOIN via Conversation_ID (usado em top_motivo, acw_by_ddd, motivos filtrado)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_AtendimentosGenesys_ConvId' AND object_id = OBJECT_ID('tlv.Atendimentos_Genesys'))
CREATE NONCLUSTERED INDEX IX_AtendimentosGenesys_ConvId
ON tlv.Atendimentos_Genesys (Conversation_ID)
INCLUDE (Classe_Processo, Rank_Motivo_Principal, Duracao_Tabulacao, Duracao_Interacao, Dt_Atendimento)
WITH (ONLINE = ON, FILLFACTOR = 90);
GO

-- =============================================================================
-- 3. controle.Municipios_DDD_IBGE
--    Usada em ddd_info (CTE) e /api/municipios
-- =============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_MunicipiosDDD_CN' AND object_id = OBJECT_ID('controle.Municipios_DDD_IBGE'))
CREATE NONCLUSTERED INDEX IX_MunicipiosDDD_CN
ON controle.Municipios_DDD_IBGE (CN)
INCLUDE (UF_CN, UF_REGIAO, [Nome-UF_CN], NO_MUNICIPIO_UF)
WITH (ONLINE = ON, FILLFACTOR = 95);
GO

-- =============================================================================
-- 4. dotacao.perfil
--    Usada em /api/agentes
-- =============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Perfil_Cargo_Deslig' AND object_id = OBJECT_ID('dotacao.perfil'))
CREATE NONCLUSTERED INDEX IX_Perfil_Cargo_Deslig
ON dotacao.perfil (cargo_atual, DT_DESLIGAMENTO)
INCLUDE (operacao, STATUS_PERFIL)
WITH (ONLINE = ON, FILLFACTOR = 95);
GO

-- =============================================================================
-- 5. sgdot.operations / sgdot.operations_groups
--    JOINs em /api/agentes
-- =============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Operations_Name' AND object_id = OBJECT_ID('sgdot.operations'))
CREATE NONCLUSTERED INDEX IX_Operations_Name
ON sgdot.operations (name)
INCLUDE (group_id)
WITH (ONLINE = ON, FILLFACTOR = 95);
GO

-- operations_groups provavelmente já tem PK em id, mas garantir:
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_OperationsGroups_Id' AND object_id = OBJECT_ID('sgdot.operations_groups'))
CREATE NONCLUSTERED INDEX IX_OperationsGroups_Id
ON sgdot.operations_groups (id)
INCLUDE (name)
WITH (ONLINE = ON, FILLFACTOR = 95);
GO

-- =============================================================================
-- VERIFICAÇÃO: Listar índices criados
-- =============================================================================
SELECT
    SCHEMA_NAME(t.schema_id) + '.' + t.name AS tabela,
    i.name AS indice,
    i.type_desc,
    STUFF((
        SELECT ', ' + c.name
        FROM sys.index_columns ic
        JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id AND ic.is_included_column = 0
        ORDER BY ic.key_ordinal
        FOR XML PATH('')
    ), 1, 2, '') AS colunas_chave,
    STUFF((
        SELECT ', ' + c.name
        FROM sys.index_columns ic
        JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id AND ic.is_included_column = 1
        ORDER BY ic.key_ordinal
        FOR XML PATH('')
    ), 1, 2, '') AS colunas_include
FROM sys.indexes i
JOIN sys.tables t ON t.object_id = i.object_id
WHERE i.name IN (
    'IX_ConversationDetails_Start_DDD',
    'IX_ConversationDetails_ConvId_DDD',
    'IX_AtendimentosGenesys_DtAtend_Motivos',
    'IX_AtendimentosGenesys_ConvId',
    'IX_MunicipiosDDD_CN',
    'IX_Perfil_Cargo_Deslig',
    'IX_Operations_Name',
    'IX_OperationsGroups_Id'
)
ORDER BY tabela, indice;
GO

PRINT '=== Índices criados com sucesso ===';
GO
