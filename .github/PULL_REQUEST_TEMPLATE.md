## Summary

<!-- One sentence: what does this PR do? -->

## Why is this change needed?

<!-- Link an issue or briefly explain the motivation. -->
Closes #

## What changed?

<!-- List the key files/modules modified and why. -->

- 
- 

## How to test locally

```bash
docker compose -f docker-compose.dev.yml up --build
# Then describe the specific steps to verify your change
```

## ✅ PR Checklist

- [ ] `docker compose up -d --build` succeeds without errors
- [ ] No hardcoded credentials, API keys, or secrets
- [ ] New skills/tools degrade gracefully when API keys are missing
- [ ] No breaking changes to existing API routes (or discussed in issue)
- [ ] Code follows existing patterns (see `CONTRIBUTING.md`)
- [ ] Relevant documentation updated (README / `.env.example` / docstrings)

## OSS Compatibility

- [ ] Does NOT introduce a strict dependency on a proprietary paid-only service
- [ ] Can be developed and tested locally without cloud accounts

## Screenshots / Logs (if applicable)

<!-- Add screenshots, terminal output, or GIFs to help reviewers understand the change. -->
