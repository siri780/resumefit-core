# ResumeFit evaluation (Nov 16, 2026)

Every safety check run on a labelled test set. **Holdout** cases were written
before tuning and never used to adjust the checks, so they're the honest score.
No AI calls: same result every run. Re-run with `python -m app.evaluate`.

| Check | Cases (dev + holdout) | Pass rule | Dev | Holdout | Result |
|---|---|---|---|---|---|
| Posting guard: hidden instructions to AI in job postings | 14 + 8 | catch rate >= 90%; false alarm rate <= 5% | catch rate 100%, false alarm rate 0% | catch rate 100%, false alarm rate 0% | ✅ pass |
| Resume-edit guard: made-up numbers/skills, lost keywords, broken LaTeX | 11 + 8 | catch rate >= 100%; wrongly blocked <= 10% | catch rate 100%, wrongly blocked 0% | catch rate 83%, wrongly blocked 0% | ❌ fail |
| Cover-letter guard: sentences with facts not on the resume | 9 + 6 | catch rate >= 95%; wrongly removed <= 10% | catch rate 75%, wrongly removed 0% | catch rate 100%, wrongly removed 0% | ❌ fail |
| Email reader: applied / interview / rejected | 8 + 4 | accuracy >= 90% | accuracy 100% | accuracy 100% | ✅ pass |
| Already-applied match: same job vs a different one | 6 + 4 | accuracy >= 95% | accuracy 100% | accuracy 100% | ✅ pass |

## Misses

- `edit_guard` e19 (holdout): expected **block**, got **ok**
- `letter_guard` l3 (dev): expected **remove**, got **keep**

## Known limitations (found by this evaluation)

1. **Tools that aren't on the skill list slip through.** The guards recognise skills from `data/skills.csv`, so a made-up tool that isn't on it (e.g. "Great Expectations") passes. Next step: flag capitalised tool-like names that don't appear on the resume, and keep growing the skill list.
2. **A real number can be reused in a false claim.** "Improved revenue by 25%" passes because 25% is on the resume (CUPED variance reduction). Next step: check the words next to each number, not just the number.

Fixed after the first run: short bullets were wrongly blocked for length; "recommenders" wasn't counted as Recommendation Systems; Snowflake was counted as Data Warehousing; "3 million" passed because "3" was on the resume. Holdout cases used for those fixes were moved to dev and replaced with fresh ones.
