# SKILL: Security Review (Baseline)

## Use When
- auth/authz, storage, networking, web endpoints
- handling user data
- executing shell commands
- parsing untrusted input

## Checklist
- Threat model: what can go wrong and who attacks?
- Input validation & encoding
- AuthN/AuthZ boundaries
- Secrets management (no hardcoding)
- Least privilege
- Secure defaults
- Logging without leaking sensitive data

## Escalation Triggers
- financial logic
- destructive operations
- prod credential handling
- user PII retention

## Output Format
- Threats
- Mitigations
- Unsafe requests flagged + safer alternative
