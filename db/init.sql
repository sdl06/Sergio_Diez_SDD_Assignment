USE master;
GO

IF DB_ID(N'schoolrun_attendance') IS NULL
    CREATE DATABASE [schoolrun_attendance];
GO
IF DB_ID(N'schoolrun_trip_ops') IS NULL
    CREATE DATABASE [schoolrun_trip_ops];
GO

IF SUSER_ID(N'attendance_app') IS NULL
    CREATE LOGIN [attendance_app] WITH PASSWORD = N'$(ATTENDANCE_SQL_PASSWORD)';
GO
IF SUSER_ID(N'trip_ops_app') IS NULL
    CREATE LOGIN [trip_ops_app] WITH PASSWORD = N'$(TRIP_OPS_SQL_PASSWORD)';
GO

USE [schoolrun_attendance];
GO
IF DATABASE_PRINCIPAL_ID(N'attendance_app') IS NULL
    CREATE USER [attendance_app] FOR LOGIN [attendance_app];

IF IS_ROLEMEMBER(N'db_datareader', N'attendance_app') = 0
    ALTER ROLE [db_datareader] ADD MEMBER [attendance_app];
IF IS_ROLEMEMBER(N'db_datawriter', N'attendance_app') = 0
    ALTER ROLE [db_datawriter] ADD MEMBER [attendance_app];
IF IS_ROLEMEMBER(N'db_ddladmin', N'attendance_app') = 0
    ALTER ROLE [db_ddladmin] ADD MEMBER [attendance_app];
GO

USE [schoolrun_trip_ops];
GO
IF DATABASE_PRINCIPAL_ID(N'trip_ops_app') IS NULL
    CREATE USER [trip_ops_app] FOR LOGIN [trip_ops_app];

IF IS_ROLEMEMBER(N'db_datareader', N'trip_ops_app') = 0
    ALTER ROLE [db_datareader] ADD MEMBER [trip_ops_app];
IF IS_ROLEMEMBER(N'db_datawriter', N'trip_ops_app') = 0
    ALTER ROLE [db_datawriter] ADD MEMBER [trip_ops_app];
IF IS_ROLEMEMBER(N'db_ddladmin', N'trip_ops_app') = 0
    ALTER ROLE [db_ddladmin] ADD MEMBER [trip_ops_app];
GO
