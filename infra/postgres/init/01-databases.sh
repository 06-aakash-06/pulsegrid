#!/bin/sh
# PostgreSQL's official image runs this on a new volume. It can be rerun manually.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<'SQL'
SELECT format('REVOKE CONNECT, TEMPORARY ON DATABASE %I FROM PUBLIC', datname) FROM pg_database \gexec
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<'SQL'
\getenv app_password PATIENT_DB_PASSWORD
\getenv migration_password PATIENT_MIGRATION_PASSWORD
SELECT format('CREATE ROLE patient_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'app_password') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='patient_app') \gexec
SELECT format('CREATE ROLE patient_migration LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'migration_password') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='patient_migration') \gexec
SELECT format('ALTER ROLE patient_app PASSWORD %L', :'app_password') \gexec
SELECT format('ALTER ROLE patient_migration PASSWORD %L', :'migration_password') \gexec
SELECT 'CREATE DATABASE patient_db OWNER patient_migration' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='patient_db') \gexec
REVOKE ALL ON DATABASE patient_db FROM PUBLIC;
GRANT CONNECT ON DATABASE patient_db TO patient_app, patient_migration;
\connect patient_db
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO patient_migration;
GRANT USAGE ON SCHEMA public TO patient_app;
ALTER DEFAULT PRIVILEGES FOR ROLE patient_migration IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO patient_app;
ALTER DEFAULT PRIVILEGES FOR ROLE patient_migration IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO patient_app;
ALTER DEFAULT PRIVILEGES FOR ROLE patient_migration IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<'SQL'
\getenv app_password DOCTOR_DB_PASSWORD
\getenv migration_password DOCTOR_MIGRATION_PASSWORD
SELECT format('CREATE ROLE doctor_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'app_password') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='doctor_app') \gexec
SELECT format('CREATE ROLE doctor_migration LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'migration_password') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='doctor_migration') \gexec
SELECT format('ALTER ROLE doctor_app PASSWORD %L', :'app_password') \gexec
SELECT format('ALTER ROLE doctor_migration PASSWORD %L', :'migration_password') \gexec
SELECT 'CREATE DATABASE doctor_db OWNER doctor_migration' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='doctor_db') \gexec
REVOKE ALL ON DATABASE doctor_db FROM PUBLIC;
GRANT CONNECT ON DATABASE doctor_db TO doctor_app, doctor_migration;
\connect doctor_db
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO doctor_migration;
GRANT USAGE ON SCHEMA public TO doctor_app;
ALTER DEFAULT PRIVILEGES FOR ROLE doctor_migration IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO doctor_app;
ALTER DEFAULT PRIVILEGES FOR ROLE doctor_migration IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO doctor_app;
ALTER DEFAULT PRIVILEGES FOR ROLE doctor_migration IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<'SQL'
\getenv app_password APPOINTMENT_DB_PASSWORD
\getenv migration_password APPOINTMENT_MIGRATION_PASSWORD
SELECT format('CREATE ROLE appointment_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'app_password') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='appointment_app') \gexec
SELECT format('CREATE ROLE appointment_migration LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'migration_password') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='appointment_migration') \gexec
SELECT format('ALTER ROLE appointment_app PASSWORD %L', :'app_password') \gexec
SELECT format('ALTER ROLE appointment_migration PASSWORD %L', :'migration_password') \gexec
SELECT 'CREATE DATABASE appointment_db OWNER appointment_migration' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='appointment_db') \gexec
REVOKE ALL ON DATABASE appointment_db FROM PUBLIC;
GRANT CONNECT ON DATABASE appointment_db TO appointment_app, appointment_migration;
\connect appointment_db
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO appointment_migration;
GRANT USAGE ON SCHEMA public TO appointment_app;
ALTER DEFAULT PRIVILEGES FOR ROLE appointment_migration IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO appointment_app;
ALTER DEFAULT PRIVILEGES FOR ROLE appointment_migration IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO appointment_app;
ALTER DEFAULT PRIVILEGES FOR ROLE appointment_migration IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<'SQL'
\getenv app_password RECORDS_DB_PASSWORD
\getenv migration_password RECORDS_MIGRATION_PASSWORD
SELECT format('CREATE ROLE records_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'app_password') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='records_app') \gexec
SELECT format('CREATE ROLE records_migration LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'migration_password') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='records_migration') \gexec
SELECT format('ALTER ROLE records_app PASSWORD %L', :'app_password') \gexec
SELECT format('ALTER ROLE records_migration PASSWORD %L', :'migration_password') \gexec
SELECT 'CREATE DATABASE records_db OWNER records_migration' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='records_db') \gexec
REVOKE ALL ON DATABASE records_db FROM PUBLIC;
GRANT CONNECT ON DATABASE records_db TO records_app, records_migration;
\connect records_db
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO records_migration;
GRANT USAGE ON SCHEMA public TO records_app;
ALTER DEFAULT PRIVILEGES FOR ROLE records_migration IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO records_app;
ALTER DEFAULT PRIVILEGES FOR ROLE records_migration IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO records_app;
ALTER DEFAULT PRIVILEGES FOR ROLE records_migration IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<'SQL'
\getenv app_password PHARMACY_DB_PASSWORD
\getenv migration_password PHARMACY_MIGRATION_PASSWORD
SELECT format('CREATE ROLE pharmacy_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'app_password') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='pharmacy_app') \gexec
SELECT format('CREATE ROLE pharmacy_migration LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'migration_password') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='pharmacy_migration') \gexec
SELECT format('ALTER ROLE pharmacy_app PASSWORD %L', :'app_password') \gexec
SELECT format('ALTER ROLE pharmacy_migration PASSWORD %L', :'migration_password') \gexec
SELECT 'CREATE DATABASE pharmacy_db OWNER pharmacy_migration' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='pharmacy_db') \gexec
REVOKE ALL ON DATABASE pharmacy_db FROM PUBLIC;
GRANT CONNECT ON DATABASE pharmacy_db TO pharmacy_app, pharmacy_migration;
\connect pharmacy_db
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO pharmacy_migration;
GRANT USAGE ON SCHEMA public TO pharmacy_app;
ALTER DEFAULT PRIVILEGES FOR ROLE pharmacy_migration IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO pharmacy_app;
ALTER DEFAULT PRIVILEGES FOR ROLE pharmacy_migration IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO pharmacy_app;
ALTER DEFAULT PRIVILEGES FOR ROLE pharmacy_migration IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<'SQL'
\getenv app_password BILLING_DB_PASSWORD
\getenv migration_password BILLING_MIGRATION_PASSWORD
SELECT format('CREATE ROLE billing_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'app_password') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='billing_app') \gexec
SELECT format('CREATE ROLE billing_migration LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'migration_password') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='billing_migration') \gexec
SELECT format('ALTER ROLE billing_app PASSWORD %L', :'app_password') \gexec
SELECT format('ALTER ROLE billing_migration PASSWORD %L', :'migration_password') \gexec
SELECT 'CREATE DATABASE billing_db OWNER billing_migration' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='billing_db') \gexec
REVOKE ALL ON DATABASE billing_db FROM PUBLIC;
GRANT CONNECT ON DATABASE billing_db TO billing_app, billing_migration;
\connect billing_db
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO billing_migration;
GRANT USAGE ON SCHEMA public TO billing_app;
ALTER DEFAULT PRIVILEGES FOR ROLE billing_migration IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO billing_app;
ALTER DEFAULT PRIVILEGES FOR ROLE billing_migration IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO billing_app;
ALTER DEFAULT PRIVILEGES FOR ROLE billing_migration IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<'SQL'
\getenv app_password EMERGENCY_DB_PASSWORD
\getenv migration_password EMERGENCY_MIGRATION_PASSWORD
SELECT format('CREATE ROLE emergency_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'app_password') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='emergency_app') \gexec
SELECT format('CREATE ROLE emergency_migration LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', :'migration_password') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='emergency_migration') \gexec
SELECT format('ALTER ROLE emergency_app PASSWORD %L', :'app_password') \gexec
SELECT format('ALTER ROLE emergency_migration PASSWORD %L', :'migration_password') \gexec
SELECT 'CREATE DATABASE emergency_db OWNER emergency_migration' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='emergency_db') \gexec
REVOKE ALL ON DATABASE emergency_db FROM PUBLIC;
GRANT CONNECT ON DATABASE emergency_db TO emergency_app, emergency_migration;
\connect emergency_db
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO emergency_migration;
GRANT USAGE ON SCHEMA public TO emergency_app;
ALTER DEFAULT PRIVILEGES FOR ROLE emergency_migration IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO emergency_app;
ALTER DEFAULT PRIVILEGES FOR ROLE emergency_migration IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO emergency_app;
ALTER DEFAULT PRIVILEGES FOR ROLE emergency_migration IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
SQL
