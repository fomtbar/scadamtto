/* ---------------------------------------------------------------------------
   scadaMtto - tabla de valor actual
   Una fila por variable. No crece: el adquisidor la actualiza en el lugar.
   Es la que lee el SCADA.
   --------------------------------------------------------------------------- */
USE [Mantenimiento];
GO

IF OBJECT_ID('[test].[ValorActual]', 'U') IS NOT NULL
    PRINT 'La tabla [test].[ValorActual] ya existe, no se hace nada.';
ELSE
BEGIN
    CREATE TABLE [test].[ValorActual] (
        [NombreTag]    varchar(50) NOT NULL,
        [Valor]        real        NULL,        -- NULL si la ultima lectura fallo
        [Estado]       bit         NOT NULL,    -- 1 = lectura buena, 0 = error/timeout
        [FechaHora]    datetime    NOT NULL,    -- cuando CAMBIO el valor por ultima vez
        [FechaLectura] datetime    NOT NULL,    -- cuando se LEYO por ultima vez (aunque no cambie)
        CONSTRAINT [PK_ValorActual] PRIMARY KEY CLUSTERED ([NombreTag])
    );
    PRINT 'Tabla [test].[ValorActual] creada.';
END
GO

/* ---------------------------------------------------------------------------
   Consulta para el SCADA: valor actual + si el dato esta fresco.
   Si FechaLectura tiene mas de 30 s, el adquisidor no esta leyendo ese tag.
   --------------------------------------------------------------------------- */
SELECT
    [NombreTag],
    [Valor],
    [Estado],
    [FechaHora],
    [FechaLectura],
    DATEDIFF(SECOND, [FechaLectura], GETDATE()) AS [SegundosDesdeLectura],
    CASE WHEN [Estado] = 0 THEN 'ERROR'
         WHEN DATEDIFF(SECOND, [FechaLectura], GETDATE()) > 30 THEN 'DESACTUALIZADO'
         ELSE 'OK' END AS [Salud]
FROM [test].[ValorActual]
ORDER BY [NombreTag];
GO
