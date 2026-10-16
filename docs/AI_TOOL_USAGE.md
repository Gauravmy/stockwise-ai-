# AI tool usage and evidence

Edvexa weighs **CodeZero development efficiency at 30%**. This file separates what has actually happened from what you still need to do. **Do not submit until every `[TO BE COLLECTED]` placeholder is filled with genuine material, or the item is removed.**

## 1. Claude Code (used)

Claude Code (desktop app, Claude Opus 5.5) was the primary coding agent for this build. It did the following:

- **Workspace and toolchain:** inspected the empty workspace and the available tools, then created the monorepo, the Python virtual environment and the Next.js scaffold.
- **Backend:** implemented the services, ML engine, inventory policy, API, Alembic migration and seed scripts.
- **Frontend:** implemented the five pages, typed API client, forms and charts.
- **Tests:** wrote 94 backend tests and 11 frontend tests, ran them, and fixed the failures (see `DEVELOPMENT_WORKFLOW.md` §"Real defects").
- **End-to-end checks:** used the in-app browser to drive the real UI: invalid CSV report, sample load, batch forecast, inventory edit, low-confidence forecast, and 375 px layout checks. It saved genuine screenshots to `screenshots/agent-verification/`.
- **Documentation:** wrote this documentation, with numbers copied from real command output.

Two of the bugs were caught by verification, not by writing code:

- The pandas `NaT` comparison crash was caught by the automated tests.
- The forecast starting a day early was caught by **visually inspecting the dashboard chart** and then tracing the API data.

## 2. CodeZero (not yet used)

**Status: not used.** The agent did not access CodeZero. A read-only look at <https://frigga.cloud/codezero> (2026-10-16) showed that:

- CodeZero (Code0) is an **AI-native extension for VS Code** that indexes your repositories into a code graph. It "works with Claude Code, Codex, GitHub Copilot".
- It has a **free Trial plan** (no credit card), but you need to **sign up** and install the extension. The agent may not create accounts or sign in for you.

No CodeZero prompts, logs, screenshots or outputs exist yet. None have been invented here.

## 3. How to use CodeZero genuinely (steps for you)

1. Go to <https://frigga.cloud/codezero>, choose **Trial → Sign up**, and create your account yourself. Read the cookie choices and terms; choose "Allow essential" if you prefer.
2. Install the CodeZero extension in VS Code, following the site's **Docs → Get started**, and sign in.
3. Open `C:\Users\hp\Desktop\stockwise-ai` in VS Code and **connect or index the repository** in CodeZero. Commit first, so its Git Tree view shows history.
4. Carry out **at least two real tasks** with CodeZero, from the list in §4. For each one:
   1. Write the task prompt.
   2. Let CodeZero draft its execution plan.
   3. Review and approve the plan.
   4. Let it make the change.
   5. Review the diff yourself. Accept or reject it, and write down why.
   6. Run the tests:

      ```bash
      python -m pytest
      ```

      ```bash
      npm test
      ```

      ```bash
      npm run build
      ```

   7. Commit with a message such as `feat: … (CodeZero-assisted)`.
5. Take screenshots **while you work**: the prompt, the generated plan, the task breakdown, the diff, and the test results.
6. Fill in the evidence log in §5.

## 4. Suggested real tasks for CodeZero

Each task is genuinely useful, has a clear verification step, and touches code CodeZero can index.

| # | Task | Files | How to verify |
|---|---|---|---|
| A | **Code review:** ask CodeZero to review `backend/app/services/inventory_policy.py` and `forecasting.py` for edge-case bugs, then judge each finding yourself | ML and inventory modules | Accept only findings you can reproduce with a new failing test |
| B | **Test generation:** "Add pytest cases for `apply_order_constraints` with fractional pack sizes (e.g. 0.5) and for `days_until_stockout` when demand is zero on the first days" | `backend/tests/test_inventory_policy.py` | Run `python -m pytest tests/test_inventory_policy.py`; the new tests must pass, and must fail if you break the function |
| C | **Feature:** "Persist recommendation snapshots: add a `recommendations` table with an Alembic migration 0002, a `POST /api/v1/inventory/recommendations/snapshot` endpoint and tests" | `db/models.py`, `alembic/versions/`, `services/inventory.py`, `api/routes/inventory.py`, tests | `alembic upgrade head` on a fresh DB; a new API test passes |
| D | **Refactor:** "Extract the duplicated latest-forecast lookup used in `analytics.py`, `inventory.py` and `products.py` into one repository function" | services | Full test suite still passes with no behaviour change |
| E | **Cross-stack impact analysis:** "If `horizon_days` max changes from 90 to 120, list every backend and frontend location affected", then make the change | `ml/forecasting.py`, `schemas.py`, `forecasting/page.tsx`, docs | Grep confirms every location; tests pass |
| F | **Debugging replay:** give CodeZero the symptom of bug #2 in `DEVELOPMENT_WORKFLOW.md` on a scratch branch where you revert the fix, and see whether it finds the root cause | `ml/forecasting.py` | The regression tests turn red, then green |

Task B is a safe first task, and task C shows the most efficiency gain. Task D shows judgment.

## 5. Evidence log (fill in with genuine material only)

Copy this block once per task.

```
### CodeZero task <n>: <title>
- Date/time: [TO BE COLLECTED]
- CodeZero plan/mode used (Auto / Planned / Normal): [TO BE COLLECTED]
- Prompt (verbatim): [TO BE COLLECTED]
- Files changed: [TO BE COLLECTED]
- What CodeZero proposed: [TO BE COLLECTED]
- What I accepted / rejected and why: [TO BE COLLECTED]
- Verification command(s) and actual output: [TO BE COLLECTED]
- Commit hash: [TO BE COLLECTED]
- Screenshots: screenshots/codezero/<n>-*.png [TO BE COLLECTED]
- Time taken vs. estimate without CodeZero (honest): [TO BE COLLECTED]
```

## 6. Evidence checklist

- [ ] CodeZero account created and extension installed (screenshot of the signed-in extension)
- [ ] Repository indexed in CodeZero (screenshot of the Git Tree or Context Graph)
- [ ] At least 2 task prompts with CodeZero's plan (screenshots)
- [ ] Before/after diffs for each CodeZero change (`git show <hash>`)
- [ ] One genuine debugging example. Either use bug #2 above with Claude Code as the tool, or a new one found with CodeZero
- [ ] Test output after each change (`python -m pytest`, `npm test`)
- [ ] Build verification (`npm run build` output)
- [ ] Final application screenshots (see `screenshots/README.md`)
- [ ] §5 log completed with no placeholders left

## 7. Demonstrating development efficiency (evaluation guide)

Show verified outcomes, not volume of generated code. A 5–7 minute segment could run:

1. **The task (30 s):** state the task and why it matters. For example, recommendation history was an optional requirement that was not yet implemented.
2. **AI-assisted implementation (2 min):** show the CodeZero prompt, its plan, and the code context it attached automatically. Point out what you corrected in the plan before approving it.
3. **Code review and judgment (1 min):** show a piece of generated code you **rejected or changed**, and why. For example, it computed safety stock from the training mean instead of the forecast, or it used a random split.
4. **Iterative debugging (1 min):** show a failing test, the fix, then the passing test. Bug #2 in `DEVELOPMENT_WORKFLOW.md`, with its before/after screenshots, is a real example.
5. **Test-based verification (1 min):** run `python -m pytest` and `npm run build` live.
6. **Final decision (30 s):** say what you merged, what you deferred, and what you would do next.

Be explicit about which tool did what. Edvexa is evaluating your engineering judgment in using the tools, not the tools themselves.
