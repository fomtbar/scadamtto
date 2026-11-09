-- =============================================================================
-- Consultas para la app web sobre los datos del bloque SCADA del PLC.
-- Solo leen test.ValorActual: no crean nada en la base.
-- Las tags llevan el prefijo de la celda (FCA0203.); para otra celda, cambiarlo.
-- =============================================================================
USE Mantenimiento;
GO

-- 1) Estado en vivo -----------------------------------------------------------
SELECT NombreTag, Valor, Estado, FechaHora AS UltimoCambio, FechaLectura,
       CASE WHEN DATEDIFF(SECOND, FechaLectura, GETDATE()) > 60
            THEN 1 ELSE 0 END AS Desactualizado,
       CASE WHEN NombreTag LIKE '%.Estado' THEN
            CASE CAST(Valor AS int)
                 WHEN 0 THEN 'Sin modo'       WHEN 1 THEN 'Manual'
                 WHEN 2 THEN 'Auto esperando' WHEN 3 THEN 'Produciendo'
                 WHEN 4 THEN 'Falla'          WHEN 5 THEN 'Emergencia'
                 WHEN 6 THEN 'Dry run'        ELSE 'Desconocido' END
       END AS EstadoTexto
FROM test.ValorActual
WHERE NombreTag LIKE 'FCA0203.%' AND NombreTag NOT LIKE 'FCA0203.Hora.%'
ORDER BY NombreTag;

-- 2) Ultimas 24 horas (la tabla que arma el PLC) -------------------------------
-- Cada hora trae su fecha MMDD. Se descarta un renglon si su fecha no es
-- la de hoy (horas ya pasadas de hoy) o la de ayer (horas posteriores a la
-- actual): asi no se muestran datos viejos si el PLC estuvo apagado.
-- Usa la fecha y hora del PROPIO PLC (FCA0203.PLC.FechaMMDD / FCA0203.PLC.HoraHHMM).
WITH crudo AS (
    SELECT CAST(SUBSTRING(NombreTag, 14, 2) AS int) AS Hora,
           SUBSTRING(NombreTag, 17, 20)             AS Campo,
           Valor
    FROM test.ValorActual
    WHERE NombreTag LIKE 'FCA0203.Hora.__.%'
),
tabla AS (
    SELECT Hora, Fecha, PiezasJ1, PiezasJ2, SegProd, SegFalla
    FROM crudo
    PIVOT (MAX(Valor) FOR Campo IN (Fecha, PiezasJ1, PiezasJ2, SegProd, SegFalla)) p
),
reloj AS (
    SELECT MAX(CASE WHEN NombreTag = 'FCA0203.PLC.FechaMMDD' THEN CAST(Valor AS int) END) AS HoyMMDD,
           MAX(CASE WHEN NombreTag = 'FCA0203.PLC.HoraHHMM'  THEN CAST(Valor AS int) END) / 100 AS HoraAhora
    FROM test.ValorActual
    WHERE NombreTag IN ('FCA0203.PLC.FechaMMDD', 'FCA0203.PLC.HoraHHMM')
),
ayer AS (
    -- MMDD de ayer segun el PLC (el anio no importa para comparar)
    SELECT r.*,
           MONTH(DATEADD(DAY, -1, DATEFROMPARTS(2001, r.HoyMMDD / 100, r.HoyMMDD % 100))) * 100
         + DAY  (DATEADD(DAY, -1, DATEFROMPARTS(2001, r.HoyMMDD / 100, r.HoyMMDD % 100))) AS AyerMMDD
    FROM reloj r
)
SELECT t.Hora,
       CASE WHEN t.Hora <= a.HoraAhora THEN 'hoy' ELSE 'ayer' END AS Dia,
       CAST(t.PiezasJ1 AS int)                   AS PiezasJ1,
       CAST(t.PiezasJ2 AS int)                   AS PiezasJ2,
       CAST(t.PiezasJ1 + t.PiezasJ2 AS int)      AS PiezasTotal,
       CAST(t.SegProd  / 60.0 AS decimal(5,1))   AS MinProduciendo,
       CAST(t.SegFalla / 60.0 AS decimal(5,1))   AS MinEnFalla,
       CASE WHEN t.Hora = a.HoraAhora THEN 1 ELSE 0 END AS EnCurso
FROM tabla t CROSS JOIN ayer a
WHERE (t.Hora <= a.HoraAhora AND t.Fecha = a.HoyMMDD)
   OR (t.Hora >  a.HoraAhora AND t.Fecha = a.AyerMMDD)
ORDER BY CASE WHEN t.Hora <= a.HoraAhora THEN 1 ELSE 0 END, t.Hora;
-- (ordena de la hora mas vieja a la actual)
