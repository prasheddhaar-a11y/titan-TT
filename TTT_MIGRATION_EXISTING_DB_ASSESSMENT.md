# TTT Existing Database Migration Assessment

Project assessed:

```text
C:\Users\Shals\TTT-May2026
```

Database configured by `watchcase_tracker/settings.py`:

```text
ENGINE: django.db.backends.postgresql
NAME: watchcase2026
HOST: localhost
USER: postgres
```

## 1. Summary

This project is using an existing PostgreSQL database whose schema and `django_migrations` history do not fully match the migration files currently present in the checkout.

The project is not in a clean migration state. Running `python manage.py migrate` blindly is risky because some pending migrations contain operations that already exist in the database.

The right repair path is migration reconciliation:

1. Back up the database.
2. Restore or recreate missing migration files where possible.
3. Fake-apply migrations only when their exact database operations already exist.
4. Create forward migrations only for schema that is genuinely missing.
5. Re-run checks until `migrate --plan` is empty and `makemigrations --check --dry-run` reports no model changes.

## 2. Confirmed Facts

`manage.py check` passed:

```text
System check identified no issues (0 silenced).
```

`manage.py migrate --plan` showed pending operations:

```text
IQF.0002_initial
InputScreening.0002_initial
```

`manage.py makemigrations --check --dry-run --verbosity 2` detected many model changes that are not represented by current migration files.

Important settings:

```text
DEBUG = True
DATABASE = watchcase2026 on localhost
AUTHENTICATION_BACKENDS = adminportal.auth_backends.AccountLockoutBackend
```

## 3. Migration History Drift

The database has applied migration rows that do not exist as migration files in the current checkout.

Applied in database but missing on disk:

```text
adminportal.0002_module_groups_shortcutconfiguration
modelmasterapp.0002_add_inputscreening_fk
SpiderSpindle_Z1.0001_initial
SpiderSpindle_Z2.0001_initial
nickel_audit_zone_two.0001_initial
```

Legacy or stale social-auth/default app labels also exist:

```text
default.0001_initial
default.0002_add_related_name
default.0003_alter_email_max_length
default.0004_auto_20160423_0400
social_auth.0001_initial
social_auth.0002_add_related_name
social_auth.0003_alter_email_max_length
social_auth.0004_auto_20160423_0400
social_auth.0005_auto_20160727_2333
```

These rows indicate the database was migrated under a different migration file set than the current project checkout.

## 4. Pending Migrations That Already Appear Applied

Django reports these as pending:

```text
IQF.0002_initial
InputScreening.0002_initial
```

However, live schema inspection showed that the main operations from those migrations already exist.

### IQF.0002_initial

Migration operations:

```text
Add IQFTrayId.batch_id
Add IQFTrayId.user
Alter unique_together for IQF_Draft_Store
Alter unique_together for IQF_OptimalDistribution_Draft
```

Live DB already has:

```text
IQF_iqftrayid.batch_id_id
IQF_iqftrayid.user_id
IQF_iqf_draft_store unique(lot_id, draft_type)
IQF_iqf_optimaldistribution_draft unique(lot_id, user_id)
```

### InputScreening.0002_initial

Migration operations:

```text
Add IPTrayId.batch_id
Add IPTrayId.user
Alter unique_together for IP_Rejection_Draft
Alter unique_together for IP_TrayVerificationStatus
```

Live DB already has:

```text
InputScreening_iptrayid.batch_id_id
InputScreening_iptrayid.user_id
InputScreening_ip_rejection_draft unique(lot_id, user_id)
InputScreening_ip_trayverificationstatus unique(lot_id, tray_id)
```

Because the DB already contains these columns and constraints, running these migrations normally may fail with duplicate column or duplicate constraint errors.

## 5. Real Schema Gaps Found

Model-vs-database comparison found real missing schema:

```text
modelmasterapp.TotalStockModel missing column: current_stage
Jig_Unloading.JigUnloadAfterTable missing column: current_stage
modelmasterapp.SSOAccount missing table: modelmasterapp_ssoaccount
```

These are not just migration-record problems. The current model code expects schema that is not present in the database.

## 6. Adminportal Status

In this `C:\Users\Shals\TTT-May2026` project/database, these tables already exist:

```text
adminportal_accountlockout
adminportal_useractivesession
adminportal_shortcutconfiguration
adminportal_module_groups
```

That means the earlier login-related missing-table issue is not present in this database.

However, the migration file that likely created these tables is missing from disk:

```text
adminportal.0002_module_groups_shortcutconfiguration
```

This should be restored from the codebase/version that originally migrated this database if possible.

## 7. Root Cause

The root cause is migration-file and database-history drift caused by using an existing database with a checkout whose migration files do not match the database's actual migration lineage.

Likely causes:

```text
Migrations were deleted or regenerated.
The database came from another branch/version.
Some tables/columns were manually created.
Some model changes were made without committing migrations.
Some apps have django_migrations rows but no local migrations directory/files.
```

## 8. What Not To Do

Do not run this blindly:

```powershell
python manage.py migrate
```

Do not delete `django_migrations` rows manually.

Do not fake all migrations globally.

Do not regenerate every migration and apply them without comparing against the live schema.

Do not drop/recreate tables in this existing database.

## 9. Safe Server-Run Plan

### Step 1: Back Up The Database

Before any repair:

```powershell
pg_dump -U postgres -h localhost -p 5432 -Fc watchcase2026 > watchcase2026_before_migration_repair.dump
```

If `pg_dump` is not in PATH, run it from the PostgreSQL `bin` folder.

### Step 2: Confirm Current State

Run:

```powershell
cd C:\Users\Shals\TTT-May2026
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py showmigrations
.\venv\Scripts\python.exe manage.py migrate --plan
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run --verbosity 2
```

Expected current problem:

```text
IQF.0002_initial and InputScreening.0002_initial appear pending.
makemigrations dry-run reports many model changes.
```

### Step 3: Fake-Apply Only Verified Already-Applied Migrations

Only after confirming the columns/constraints already exist, mark these two as applied:

```powershell
.\venv\Scripts\python.exe manage.py migrate IQF 0002 --fake
.\venv\Scripts\python.exe manage.py migrate InputScreening 0002 --fake
```

Reason:

```text
The DB already has the fields and unique constraints from these migrations.
This aligns django_migrations with the existing schema without changing data.
```

### Step 4: Restore Missing Historical Migration Files If Possible

Best option:

```text
Recover missing migration files from the branch/version that originally migrated this database.
```

Highest priority:

```text
adminportal/migrations/0002_module_groups_shortcutconfiguration.py
modelmasterapp/migrations/0002_add_inputscreening_fk.py
SpiderSpindle_Z1/migrations/0001_initial.py
SpiderSpindle_Z2/migrations/0001_initial.py
nickel_audit_zone_two/migrations/0001_initial.py
```

This keeps the project honest and makes future migration graph behavior predictable.

### Step 5: Create Forward Migrations For Missing Schema

Create proper migrations for the real missing schema:

```text
modelmasterapp_totalstockmodel.current_stage
Jig_Unloading_jigunloadaftertable.current_stage
modelmasterapp_ssoaccount
```

Recommended command:

```powershell
.\venv\Scripts\python.exe manage.py makemigrations modelmasterapp Jig_Unloading
```

Before applying, review the generated migration files carefully. The migration should create only the missing table/columns that are actually absent.

Then apply:

```powershell
.\venv\Scripts\python.exe manage.py migrate modelmasterapp
.\venv\Scripts\python.exe manage.py migrate Jig_Unloading
```

If generated migrations include operations for columns/tables that already exist, do not apply them as-is. Split or edit the migration to include only missing schema.

### Step 6: Recheck Until Clean

Run:

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py migrate --plan
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run --verbosity 2
```

Target clean state:

```text
manage.py check: no issues
migrate --plan: no planned operations
makemigrations --check --dry-run: no changes detected
```

### Step 7: Run The Server

Run:

```powershell
cd C:\Users\Shals\TTT-May2026
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Then test:

```text
GET  http://127.0.0.1:8000/accounts/login/
POST http://127.0.0.1:8000/accounts/login/
GET  http://127.0.0.1:8000/home/
```

## 10. Practical Minimal Path To Get Server Running

If you need the fastest safe route:

1. Back up `watchcase2026`.
2. Fake-apply the two pending migrations whose operations already exist:

```powershell
.\venv\Scripts\python.exe manage.py migrate IQF 0002 --fake
.\venv\Scripts\python.exe manage.py migrate InputScreening 0002 --fake
```

3. Add/apply forward migrations for:

```text
TotalStockModel.current_stage
JigUnloadAfterTable.current_stage
SSOAccount
```

4. Confirm:

```powershell
.\venv\Scripts\python.exe manage.py migrate --plan
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

5. Start server:

```powershell
.\venv\Scripts\python.exe manage.py runserver
```

## 11. Final Recommendation

Treat this database as production-like.

Use fake migrations only to align Django history with schema that is already present.

Use real forward migrations only for schema that is genuinely missing.

The long-term clean fix is to restore the missing migration files from the original branch/version and stop regenerating initial migrations against an existing database.

