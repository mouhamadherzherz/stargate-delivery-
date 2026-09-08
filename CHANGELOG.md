# Changelog - Stargate Delivery Management System

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] - 2026-09-09

### Security Hardening & Architecture Overhaul (In Progress)
- Initiated Production Upgrade Plan (Phases 1 through 12).
- Created full project safety snapshot in `stargate-backup-before-upgrade`.
- Switched to dedicated `development` branch for progressive hardening.
- Target: Remove hardcoded secrets, enforce password hashing, implement robust permission checks and financial validation.

---

## [1.0.0] - 2026-09-08

### Added
- Complete unified single-file Flask web service (`app.py`).
- 70+ routes handling orders, couriers, merchants, treasuries, settlements, and customers.
- Dual-currency calculations (LBP / USD) with dynamic exchange rates.
- AI Assistant chat and dispatch integration hooks.
- Automated Google Drive backup synchronizer with Wal-checkpoint integration.
- Responsive Tailwind and FontAwesome management dashboards.
