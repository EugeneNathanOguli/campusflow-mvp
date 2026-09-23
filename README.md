# CampusFlow MVP

A Streamlit prototype for automated student allowance pacing and a financial lockbox workflow.

## Run locally

```bash
source .venv/Scripts/activate
streamlit run app.py
```

Open http://localhost:8501.

## Local admin access

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`, then replace the example value with a long random passcode. The secrets file is ignored by Git and must never be committed.

## Authentication and privacy

Local development runs in demo mode with sample data. For a deployed app, configure the `[auth]` OIDC values in `secrets.toml` using Google, Microsoft Entra, Auth0, or another OpenID Connect provider. Once `client_id` is present, CampusFlow requires sign-in before rendering the workspace and provides a sign-out control.

Authentication alone is not enough for real financial data. A production release also needs:

- A database with one student profile per authenticated account.
- Server-side authorization on every profile, vault, and payout query.
- HTTPS, encrypted backups, audit logs, rate limiting, and monitoring.
- Secure payment-provider webhooks and an immutable payout ledger.
- A formal privacy policy, retention rules, and appropriate regulatory review.

This prototype uses simulated balances and payout approvals. It does not connect to Mobile Money, XENO, a bank, or a production database.

## Save to GitHub with Git Bash

Run these commands from the project folder in the VS Code Git Bash terminal:

```bash
git init
git add .
git status
git commit -m "Create CampusFlow MVP"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/campusflow-mvp.git
git push -u origin main
```

Keep the GitHub repository private. The local `.streamlit/secrets.toml` file is excluded from Git; only commit `.streamlit/secrets.toml.example`.
