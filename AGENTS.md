# TTT Enterprise AI Agent System

Before making ANY code change:

READ FILES IN THIS ORDER:

1. guardrails/PROJECT_GUARDRAILS.md
2. memory/project-context.md
3. memory/architecture.md
4. skills/backend-skill.md
5. skills/frontend-skill.md
6. skills/security-skill.md
7. skills/ttt-bug-fix.md

---

# Core Rules

- Backend is SSOT
- Never calculate business logic in frontend
- Never break existing workflows
- Follow Django layered architecture
- Preserve module-specific tray flow logic
- Always validate security impact
- Prevent regressions

---

# Mandatory Process

1. Understand module flow
2. Trace backend source
3. Verify queryset scope
4. Verify movement flags
5. Verify frontend rendering only
6. Validate security
7. Validate performance
8. Explain root cause before fix

---

# Project Stack

- Python
- Django
- HTML
- CSS
- JavaScript

Modules:
- IQF
- Brass QC
- Brass Audit
- Jig Loading
- Jig Unloading
- Jig Unloading (Zone 2)
- Input Screening
- Day Planning
- Inprocess Inspection
- Nickel Inspection
- Nickel Inspection (Zone 2)
- Nickel Audit
- Nickel Audit (Zone 2)
- Spider Spindle (Z1)
- Spider Spindle (Z2)
- Reports Module