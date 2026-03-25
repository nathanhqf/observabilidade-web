-- ============================================================
-- ConexReport - Migration 001: Schema + Users + Sessions
-- Banco: INFO_CENTRAL
-- Executar: sqlcmd -S 10.206.244.39 -U DOTACAO -P M@pfre123 -d INFO_CENTRAL -i 001_conexreport_schema.sql
-- ============================================================

USE INFO_CENTRAL;
GO

-- 1. Criar schema
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'conexreport')
    EXEC('CREATE SCHEMA conexreport');
GO

-- 2. Tabela de usuários
IF NOT EXISTS (SELECT 1 FROM sys.tables t JOIN sys.schemas s ON t.schema_id = s.schema_id WHERE s.name = 'conexreport' AND t.name = 'users')
BEGIN
    CREATE TABLE conexreport.users (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        email           VARCHAR(255) NOT NULL,
        display_name    VARCHAR(150) NOT NULL,
        password_hash   VARCHAR(512) NOT NULL,
        role            VARCHAR(20)  NOT NULL DEFAULT 'pending',
                        -- 'pending' = aguardando aprovação
                        -- 'viewer'  = acesso ao dashboard
                        -- 'admin'   = acesso total + gestão de usuários
        is_active       BIT NOT NULL DEFAULT 1,
        created_at      DATETIME NOT NULL DEFAULT GETDATE(),
        updated_at      DATETIME NOT NULL DEFAULT GETDATE(),
        last_login      DATETIME NULL,
        approved_by     INT NULL,
        CONSTRAINT UQ_users_email UNIQUE (email),
        CONSTRAINT FK_users_approved_by FOREIGN KEY (approved_by) REFERENCES conexreport.users(id)
    );
    PRINT 'Tabela conexreport.users criada.';
END
ELSE
    PRINT 'Tabela conexreport.users já existe.';
GO

-- 3. Tabela de sessões
IF NOT EXISTS (SELECT 1 FROM sys.tables t JOIN sys.schemas s ON t.schema_id = s.schema_id WHERE s.name = 'conexreport' AND t.name = 'sessions')
BEGIN
    CREATE TABLE conexreport.sessions (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        token           VARCHAR(128) NOT NULL,
        user_id         INT NOT NULL,
        created_at      DATETIME NOT NULL DEFAULT GETDATE(),
        expires_at      DATETIME NOT NULL,
        ip_address      VARCHAR(45)  NULL,
        user_agent      VARCHAR(512) NULL,
        CONSTRAINT UQ_sessions_token UNIQUE (token),
        CONSTRAINT FK_sessions_user FOREIGN KEY (user_id) REFERENCES conexreport.users(id) ON DELETE CASCADE
    );
    PRINT 'Tabela conexreport.sessions criada.';
END
ELSE
    PRINT 'Tabela conexreport.sessions já existe.';
GO

-- 4. Índices
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_sessions_token' AND object_id = OBJECT_ID('conexreport.sessions'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_sessions_token
    ON conexreport.sessions (token)
    INCLUDE (user_id, expires_at);
    PRINT 'Índice IX_sessions_token criado.';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_sessions_expires' AND object_id = OBJECT_ID('conexreport.sessions'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_sessions_expires
    ON conexreport.sessions (expires_at);
    PRINT 'Índice IX_sessions_expires criado.';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_users_email' AND object_id = OBJECT_ID('conexreport.users'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_users_email
    ON conexreport.users (email);
    PRINT 'Índice IX_users_email criado.';
END
GO

PRINT '=== Migration 001 concluída com sucesso ===';
GO
