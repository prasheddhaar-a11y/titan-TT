# Project Context

Project Name:
TTT Watchcase Manufacturing System

Purpose:
Track and Trace system for watchcase manufacturing workflow management.

Tech Stack:
- Python
- Django
- HTML
- CSS
- JavaScript

Architecture:
- Backend-driven business logic
- Frontend is render layer only
- Django is Single Source of Truth (SSOT)

Core Goals:
- Prevent quantity mismatches
- Maintain tray traceability
- Preserve manufacturing flow integrity
- Avoid duplicate processing
- Ensure module movement accuracy

Core Modules:
- Input Screening
- Brass QC
- Brass Audit
- IQF
- Jig Loading
- Jig Unloading
- Day Planning
- Spider Spindle

Core Concepts:
- Tray lifecycle tracking
- Delink vs rejection handling
- Module movement flags
- RW quantity processing
- Draft persistence
- Verification workflows

Critical Rules:
- Existing workflows must never break
- Frontend must not calculate business quantities
- All validations belong to backend
- Lot movement controlled through flags
- All tray transitions must be traceable

Project Priorities:
1. Data integrity
2. Tray traceability
3. Quantity accuracy
4. Performance
5. Security
6. Maintainability