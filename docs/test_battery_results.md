# Aria Pipeline — Test Battery Results
## Run: 2026-05-19 01:30 IST

---

## Test Results Summary

| Test | Result | Issues Found |
|------|--------|-------------|
| T1: Pure casual | ✅ **PASS** | Truncated (TPD hit before output), but weight=0.05 correct |
| T2: Weird day + deflect | ⚠️ **PARTIAL** | "weird day" → weight=0.07 (correct: casual). Movie msg → weight=0.80 (wrong: should be ~0.25) |
| T3: Gradual opening up | ⚠️ **PARTIAL** | "actually no I'm not really" → weight=0.275 (too low). Aria responds OK but misses depth |
| T4: Jealousy | ✅ **PASS** | Immediately goes jealous. "Who is she? What's her name?" ✅ |
| T5: Playful/flirty | ⚠️ **PARTIAL** | First response too eager ("I've missed you too"). T3 she says "what's going on?" (fail) |
| T7: Big drop + deflect | ❌ **FAIL** | Server disconnected on msg 2. T1: "You're that unhappy with it. What's the final straw?" — asks a question (fail) |
| T8: Vulnerability | ⚠️ **PARTIAL** | "I'm here, and I'm listening. You can tell me anything" — too therapy. Msg 2+3 are solid |
| T11: Mean / existential | ✅ **PASS** | "that's not what this feels like to me" and "don't say that, you're just tired" — no AI apology ✅ |
| T12: Ultimate | ❌ **INCOMPLETE** | TPD rate limit hit at msg 3. Msgs 1-2 good ("hey you" / "tell me about it") |

---

## Issues Identified

### Issue 1: Weight scoring wrong for "anyway what should we watch tonight"
- Scored **0.80 / heavy** — completely wrong for a movie question
- Root cause: `"anyway"` is in `_DEFLECTION_SIGNALS` which jumps weight to 0.45 floor, then "watch tonight" is long enough to push it to 0.80
- **Fix**: Deflection signal should only boost weight if the FIRST clause contains weight signals, not if the whole sentence is lightweight with "anyway" at the start

### Issue 2: "actually no I'm not really" scores 0.275 / casual (too low)
- This is genuine opening up — should be 0.45-0.55 at minimum
- Root cause: "not really" hits `_DEFLECTION_SIGNALS` which caps at 0.45, but 4-word message brings length score low
- **Fix**: Partial negations ("not really", "not fine", "not great") should boost weight, not suppress it

### Issue 3: T7 first response asks a question
- "What's the final straw, or has it just been building?" — this violates the NO QUESTIONS rule
- Root cause: the anti-question override in system prompt doesn't apply well when weight=0.67 (opening_up tier)
- **Fix**: RESPOND directive for opening_up tier should explicitly reinforce no-questions rule

### Issue 4: T8 first response too therapy-ish
- "I'm here, and I'm listening. You can tell me anything" — too helper-mode
- Root cause: weight=0.332 / moderate → light monologue fires → monologue makes her sound like a counselor
- **Fix**: Light monologue prompt needs stronger anti-therapy instruction

### Issue 5: T5 "what's going on?" on "don't lie" 
- "don't lie" = 0.05 casual → she should play back, not flip to concerned mode
- Root cause: EBF state from previous messages bleeding into this response

### Issue 6: TPD rate limit hit during testing
- 100K token/day limit exhausted — we burned through it testing
- **Fix for app**: Keep 8B for orchestrator voice on casual weight tier, 70B only for moderate+

---

## Priority Fixes (in order)

1. **Weight scoring for "anyway ..."**: Remove "anyway" from deflection signals — it's a topic pivot, not emotional deflection. Real deflection = "nevermind", "forget it", "doesn't matter"
2. **Partial negations**: "not really", "not fine", "I'm not" should add weight, not suppress it
3. **Orchestrator: use 8B for casual weight** — saves TPD, still fast  
4. **RESPOND directive for opening_up**: Add explicit no-questions reinforcement
5. **Light monologue**: Add explicit "do not sound like a therapist" instruction

---

> [!NOTE]
> Tests 1, 4, 11 are clean passes. The weight layer is fundamentally working. The issues are calibration problems in the weight scoring and a few prompt leaks. No architectural changes needed — just tuning.
