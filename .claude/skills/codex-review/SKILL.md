---
name: codex-review
description: >-
  Dual-model peer review using Codex CLI (codex review).
  Use after implementation to get external AI review from GPT.
  Runs iterative review loop until all issues are addressed or MAX_ITERATIONS (3).
---

# Codex Review

External peer review via `codex review` CLI. Gets a second opinion from a different model.

## Usage

### Review current branch changes vs main
```
/codex-review
```

### Review specific commit
```
/codex-review commit <sha>
```

### Review uncommitted changes only
```
/codex-review uncommitted
```

## Workflow

### Step 1: Determine what to review

- **No arguments**: review current branch vs `master` (default)
- **`uncommitted`**: review only staged/unstaged/untracked changes
- **`commit <sha>`**: review a specific commit

### Step 2: Run codex review

Execute the appropriate command:

```bash
# Branch review (default) — compare current branch against master
codex review --base master

# Uncommitted changes only
codex review --uncommitted

# Specific commit
codex review --commit <sha>
```

You can add custom instructions to focus the review:

```bash
codex review --base master "Focus on SSL handling and error logging"
```

### Step 3: Read and present the review

1. Read the codex review output carefully
2. Present the findings to the user, organized by severity:
   - **Critical**: Bugs, security issues, data loss risks
   - **Warning**: Logic errors, edge cases, performance issues
   - **Suggestion**: Style, readability, minor improvements
3. For each finding, include the file and line reference

### Step 4: Iterative fix loop (if requested)

If the user wants to address the findings:

1. Fix the issues identified by codex
2. Run `codex review --uncommitted` to verify the fixes
3. Repeat until codex has no more critical/warning findings or 3 iterations reached
4. After 3 iterations with unresolved issues, present remaining items to the user for manual decision

## Notes

- Codex CLI must be installed (`codex --version` to verify)
- The project must be trusted in `~/.codex/config.toml`
- Review output goes to stdout — capture and parse it
- This gives a genuinely independent review since it's a different model (GPT) with no shared context
