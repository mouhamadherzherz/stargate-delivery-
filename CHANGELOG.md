# Changelog - Stargate Delivery Management System

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [4.1.0] - 2026-09-24

### Finance, audit and operations hardening
- Added migration `009_finance_controls` with idempotency keys, approval status, approver metadata and reversal references for treasury transactions.
- Treasury movements now validate positive amounts and known transaction types and safely return an existing result for duplicate idempotency keys.
- Audit records now include actor, IP address, user agent, and optional before/after JSON snapshots.
- Added verified compressed backup and restore service with SHA-256 manifests, SQLite integrity checks, atomic restore, and retention.
- Restricted credential resets to administrator roles; maintenance can no longer reset arbitrary employee passwords or PINs.
- Made the migration compatible with both legacy `created_at` and newer `timestamp` audit schemas.
- Added finance and backup regression tests.

---

## [4.0.0] - 2026-09-24

### Fixed and hardened
- Fixed the undefined `login_type` variable that could break all POST login attempts.
- Hashed employee and administrator PINs during recovery and maintenance-account provisioning.
- Protected recovery, security-wizard, and database-repair mutations with CSRF; database repair is now administrator-only POST.
- Replaced weak prefix-based Origin validation with exact scheme/host/port comparison.
- Removed schema migration from module import and added `migrate.py` for a single pre-deploy migration step.
- Removed production databases, backups, logs, keys, and update archives from the distributable source package.
- Added secure first-run credential provisioning using a mode-0600 local file deleted after successful login.

---

## [3.9.21] - 2026-09-24

### Security & Production Hardening (P0, P1, P2 Completed)
- **Eliminated Hardcoded Credentials & Master Keys**: Removed all hardcoded bypass passwords and PINs (`20122020`, `19701313`, `000000`, `admin`, `123456`, `stargate@19701313`) across `core/extensions.py`, `core/security.py`, `routes/auth.py`, batch scripts, and templates.
- **Removed Plaintext Maintenance File**: Permanently deleted `بيانات_حساب_الصيانة_MAINTENANCE.txt` and prevented automatic writing of credentials to plaintext files.
- **Secure One-Time Password Recovery**: Redesigned `/forgot_password` and `/recovery` to use cryptographically random one-time tokens (`STRG-XXXX-XXXX-XXXX-XXXX`), rotating the token hash immediately after single use, enforcing custom password definitions (min 8 chars) and invalidating active sessions.
- **Strict CSRF Enforcement**: Enforced CSRF tokens on all mutating HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`) with zero exception for `/api/` endpoints. Added Origin/Referer verification, custom headers (`X-CSRF-Token` / `X-CSRFToken`), and global JavaScript fetch/XHR interceptors.
- **Modern Authenticated Encryption**: Replaced custom XOR stream cipher in `secure_env.py` with Fernet (`AES-128-CBC` with `HMAC-SHA256`) via Python `cryptography` v49.0.0, with transparent backward-compatible migration.
- **Password Hashing & Auto-Rehash**: Prohibited raw plaintext and unseeded MD5 password checks. Implemented automatic rehashing of legacy password hashes to `scrypt` upon successful authentication.
- **Brute-Force & Rate Limiting Protection**: Implemented IP-based and username-based rate limiting (5 attempts per 15 minutes with progressive delay lockout) for login and account recovery. Flagged and rejected common weak PINs.
- **Session & Cookie Security**: Unified permanent session lifetime from 14 days down to 12 hours. Enforced `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE='Lax'`, and production `SESSION_COOKIE_SECURE=True`.
- **Database Concurrency Isolation**: Decoupled `auto_migrate_db()` from module import to prevent Gunicorn multi-worker race conditions. Moved pre-flight migrations to standalone startup block with safety backups.
- **Financial & Data Wipe Protections**: Added mandatory automated database snapshots before any data reset/wipe, and logged all wipe actions to `audit_log`.
- **Project Structure Hygiene**: Archived scratch test scripts and obsolete duplicate entrypoints (`app_legacy_monolith.py`, `app_new.py`) into `scratch_archive/`. Updated `.gitignore`.
- **Dependency Version Pinning**: Pinned all runtime dependencies in `requirements.txt` and generated `requirements.lock`.
- **Automated Security Suite**: Added comprehensive unittest security suite (`tests/run_security_suite.py`) verifying backdoor rejection, CSRF gate enforcement, origin validation, and encryption safety.

---

## [1.0.0] - 2026-09-08

### Added
- Complete unified single-file Flask web service (`app.py`).
- 70+ routes handling orders, couriers, merchants, treasuries, settlements, and customers.
- Dual-currency calculations (LBP / USD) with dynamic exchange rates.
- AI Assistant chat and dispatch integration hooks.
- Automated Google Drive backup synchronizer with Wal-checkpoint integration.
- Responsive Tailwind and FontAwesome management dashboards.
