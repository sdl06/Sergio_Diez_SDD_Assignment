# Attendance migration 0003 on Azure

The [deployment job](https://github.com/sdl06/Sergio_Diez_SDD_Assignment/actions/runs/45974393003/job/140423689952) for commit `7df97492170cd45e471805462086509120979552` succeeded. The database recorded the migration on 27 November 2026 at 09:36:53 UTC (10:36:53 in Madrid).

The following read-only queries were run on `sdiez-ieu2024-attendance-db` after deployment.

```sql
SELECT DB_NAME() AS database_name, app, name, applied
FROM dbo.django_migrations
WHERE app = 'bus_tracker_app'
  AND name = '0003_rename_attendance_recorded_at_column';

SELECT id, trip_id, student_id, status, last_recorded_at
FROM dbo.bus_tracker_app_studentattendance
WHERE id = 1;
```

```text
database_name|app|name|applied
sdiez-ieu2024-attendance-db|bus_tracker_app|0003_rename_attendance_recorded_at_column|2026-11-27 09:36:53.5244920 +00:00

id|trip_id|student_id|status|last_recorded_at
1|2|1|present|2026-11-27 07:58:51.5944840 +00:00
```

Row 1 retained its trip ID, student ID, status and full timestamp. The timestamp matches the [before export](results.csv) after normalizing the date-time separator. The [before screenshot](migration.png) shows `recorded_at`, the [after screenshot](migration_name_change.png) shows `last_recorded_at`, and the [old query screenshot](migration_original_error.png) shows that Azure SQL rejects the old column name.

The migration record comes from Django's migration history table. The original startup line was absent from the available Container Apps console logs.

## Rollback and reapply on 28 November 2026

In the live Attendance container console, Django rolled back to `0002` and reapplied `0003` in one database transaction. The checks read row 1 before the rollback, under `recorded_at` after the rollback, and under `last_recorded_at` after the reapply. All five values matched at each stage. The transaction committed at approximately 10:27 Madrid time, and Attendance subsequently returned HTTP 200 from `/health` with both service and database status set to `ok`.

The following excerpt is from the manual console rerun. The original deployment is documented above.

```text
Before on sdiez-ieu2024-attendance-db: (1, 2, 1, 'present', '2026-11-27 07:58:51.5944840 +00:00') (last_recorded_at)
Original applied timestamp: 2026-11-27T09:36:53.524492+00:00
  Unapplying bus_tracker_app.0003_rename_attendance_recorded_at_column... OK
After rollback: (1, 2, 1, 'present', '2026-11-27 07:58:51.5944840 +00:00') (recorded_at)
  Applying bus_tracker_app.0003_rename_attendance_recorded_at_column... OK
After reapply: (1, 2, 1, 'present', '2026-11-27 07:58:51.5944840 +00:00') (last_recorded_at)
New applied timestamp: 2026-11-28T09:27:16.388248+00:00
ATTENDANCE_RERUN_COMMITTED
```
