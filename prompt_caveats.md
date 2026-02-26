# Prompt Caveats — LetsPlanIt

Reference document for anyone editing the three Groq prompt phases.
Last audited: 2026-02-26.

---

## Phase map

| Phase | File | Function | Model | Trigger |
|---|---|---|---|---|
| Silent extraction | `server/agent/context.py` | `extract_and_merge` | `llama-3.1-8b-instant` | Every non-self inbound message |
| State resolver | `server/agent/resolver.py` | `resolve_full_state` | `llama-3.3-70b-versatile` | Only when `@Agent` is mentioned |
| Orchestrator | `server/agent/orchestrator.py` | `run_agent` | `llama-3.3-70b-versatile` | Only when `@Agent` is mentioned |

On an `@Agent` message all three phases run: extraction first (silently), then resolver, then orchestrator — two sequential 70b calls before any reply is sent.

---

## Phase 1 — Silent Extraction

**File:** `server/agent/context.py` · **Model:** `llama-3.1-8b-instant`

### What it does
Sends only the current sender and message text to the model. Returns a 6-field XML block. No conversation history is in context.

### Known gaps

**No dietary vs cuisine_dislikes distinction in the prompt.**
The template has both `<dietary>` and `<cuisine_dislikes>` fields but no instruction separating them. The model must guess from field names alone.
- `dietary` = dietary restrictions the person cannot eat (vegetarian, halal, gluten-free)
- `cuisine_dislikes` = cuisines they prefer to avoid but can eat (Indian, spicy food)

"I don't eat Indian food" risks landing in `dietary` instead of `cuisine_dislikes`.
"I'm vegan" risks landing in `cuisine_dislikes` instead of `dietary`.
Fix: add a one-sentence clarification and a worked example to the user prompt.

**No worked example.**
The prompt shows an empty XML template and nothing else. A single inline example (message → filled XML) would significantly reduce misclassification on the dietary/cuisine boundary and on the confirmed field.

**Implicit agreements cannot be resolved here.**
The model sees only the current message with no prior context. Phrases like "yeah works for me", "sounds good", "let's do it" will produce `<confirmed>true</confirmed>` but the model cannot know what the agreement refers to. This is structural — the resolver phase exists to fix it, but only when `@Agent` is called.

**Temporary dietary constraints are stored permanently.**
"I'm vegetarian today" or "no spicy food tonight" will write to `member.dietary` with no expiry mechanism. The word "today"/"tonight" is silently discarded.

**`<confirmed>` maps to `venue_confirmed`, not `cuisine_confirmed`.**
The tag name is ambiguous. A casual agreement about cuisine will set `venue_confirmed=True` on the member even though no venue exists yet. `cuisine_confirmed` is never set by this phase.

**`session.cuisine` and `session.state` are never set here.**
Extraction only updates member-level fields plus `session.time` and `session.location_anchor`. The group-level cuisine stays `null` and state stays `idle` until the resolver runs.

**`max_tokens` is not set.**
The expected output is ~60 tokens (filled XML). Without a cap the model may over-generate prose before or after the XML block, wasting latency. Recommended cap: 120.

---

## Phase 2 — State Resolver

**File:** `server/agent/resolver.py` · **Model:** `llama-3.3-70b-versatile`

### What it does
Receives the current `session_to_xml` snapshot plus the full stored message history. Re-reads everything, resolves pronoun/venue references, and returns a `<resolved_state>` XML block that updates the session.

### Known gaps

**The XML output template contains hardcoded field values.**
The resolver's output template (shown to the model as the format to follow) contains:
```xml
<cuisine_confirmed>true</cuisine_confirmed>
<venue_confirmed>false</venue_confirmed>
```
These are literal values in the template, not blanks. A model following the template may anchor `cuisine_confirmed` to `true` for all members or treat `venue_confirmed=false` as a default to preserve. Both tags should be empty in the template.

**No worked example.**
There is no demonstration of a sample conversation → expected XML output. A single 2-3 message example showing how "yeah that works for me" maps to `venue_confirmed=true` for the speaker is the highest-value addition here, given that reference resolution is the primary job of this phase.

**Instruction order is suboptimal.**
Current order: task description → output format → rules → session state → history. The model reads format instructions before it sees the data it needs to interpret. Preferred order: data (session + history) → task → output format → rules.

**No instruction for the no-venue-yet case.**
Rule 1 states `'that option', 'it', 'that place' ALWAYS refers to the most recently named venue`. If no venue has been named in the conversation yet, this rule has no referent. The model may hallucinate a venue name or leave things empty. Add an explicit "if no venue has been discussed, leave `venue_confirmed` empty for all members" instruction.

**`can_book` is sent to the resolver but it has no instruction to act on it.**
`session_to_xml` includes `<can_book>false</can_book>`. The resolver receives this in the session snapshot but has no rule that references `can_book`. It is noise in this call. Consider stripping it from the session XML passed to the resolver.

**`selected_venue` is not in the resolver's output template and is never parsed.**
`_parse_response` has no logic to extract a venue name or venue dict. If the conversation mentions "La Piazza works for me", the resolver will correctly set `venue_confirmed=true` for the speaker but will not record what venue was selected. `session.selected_venue` remains `null` forever, which permanently blocks `can_book`.

**`event_type` is in the output template but not in the input session XML.**
`session_to_xml` does not emit `event_type`. The resolver can set it from history (and `_parse_response` will extract it), but on the next call the orchestrator will never see it because `session_to_xml` does not include it.

**`max_tokens` is not set.**
The resolved XML output is bounded at roughly 200-400 tokens for any realistic group size. Recommended cap: 500.

---

## Phase 3 — Orchestrator

**File:** `server/agent/orchestrator.py` · **Model:** `llama-3.3-70b-versatile`

### What it does
Receives the post-resolver session XML plus history in the system prompt. The stripped `@Agent` message is the user turn. Returns a plain-text chat reply.

### Known gaps

**`selected_venue` is invisible to the orchestrator.**
`session_to_xml` does not emit a `<selected_venue>` field. The orchestrator system prompt therefore never shows which venue was proposed. Combined with `selected_venue` never being written anywhere in the codebase, `<can_book>` is always `false`, and the agent can never be told it is safe to proceed with booking.

**`can_book` rule references JSON-style syntax; XML is used in the prompt.**
Core Rule 3 says `unless can_book: true`. The session XML the model reads uses `<can_book>true</can_book>`. The model must bridge two notational styles for the same concept.

**`event_type` is never emitted in session XML.**
Defined in the model, settable by the resolver, but `session_to_xml` never includes it in the `<group>` block. The orchestrator cannot see it.

**8 rules with no priority ordering.**
Rules 1–8 are flat with no grouping. The most safety-critical rule (Rule 3, never book without `can_book`) is buried after generic behavioral rules. The booking safety rule should be first or visually separated.

**Typo in opening line.**
`"YYou are LetsPlanIt"` — double Y. Present in every active agent system prompt.

**The static and dynamic parts of the system prompt are concatenated into one string.**
~420 tokens of persona + rules + format instructions never change between calls. The dynamic `{session_xml}` and `{history}` sections change every call. They are currently formatted into one string via `.format()`, making future prompt caching structurally impossible without refactoring.

**No worked example of a complete state → reply.**
There is no demonstration of what a correct reply looks like for common scenarios (all confirmed, one person missing, no venue yet).

**`max_tokens` is not set.**
Rules say "max 3 sentences" but the model has no hard token cap. Recommended cap: 300.

---

## Cross-phase issues

### `upsert_member` replaces list fields, does not merge them
`preferences.upsert_member` uses `model_copy(update=payload)`. Any upsert that includes a list field fully replaces the prior list. If Alisha says "I'm vegetarian" in message 3 and then "no nuts please" in message 8, the extraction of message 8 with `{"dietary": ["nut-free"]}` will overwrite `["vegetarian"]` entirely. This affects extraction outputs for `dietary`, `cuisine_likes`, and `cuisine_dislikes` across all messages from the same sender.

### `session.dietary_filters` has two diverging write paths
- Extraction (`context.py`): calls `_merge_session_dietary`, an additive deduplicating append that does not rebuild from member data.
- Resolver (`resolver.py`): calls `preferences.merge_dietary(session)`, which rebuilds from scratch from all member dietary lists.

After a resolver pass, the two paths produce consistent results. But if only silent extraction has run (no `@Agent` yet), `dietary_filters` is built by the additive path. If a member's dietary list is later replaced (see `upsert_member` issue above), `dietary_filters` will contain stale entries that no member actually holds.

### `pending_confirmations` is a dead write field
`models.py` defines `pending_confirmations: list[str]`. `session_to_xml` reads it with an `or` fallback to `get_unconfirmed`. Nothing in the codebase ever writes to it. The fallback always fires, making the field functionally unused. Do not populate the prompt with this field expecting it to reflect intentional state.

### `time_confirmed_by` is entirely unused
Defined in `models.py`, never written, never read by any helper or prompt. Ignore or remove.

### `cuisine_confirmed` has no behavioral effect
Both `cuisine_confirmed` and `venue_confirmed` exist on `MemberPreference`. Both are serialized to XML in `session_to_xml`. Only `venue_confirmed` is read by `all_confirmed`, `get_unconfirmed`, and the `can_book` gate. `cuisine_confirmed` is stored and sent to the LLM but nothing acts on it.

### History entries contain unused fields in storage
`payload.model_dump()` stores five fields per history entry: `group_id`, `sender`, `text`, `timestamp`, `is_self`. `build_history` uses only `sender` and `text`. The other three fields live in RAM but are never sent to any model. They are noise in the stored session object.

### Debug `print()` in production extraction path
`context.py:127` has `print(f"[extract] processing message from {msg['sender']}: {msg['text']}")`. This runs on every non-self inbound message, logging sender and full message content to stdout. Remove before any production deployment.

---

## Token budget reference

| Phase | Current `max_tokens` | Typical output size | Recommended cap |
|---|---|---|---|
| Silent extraction | **Not set** | ~60 tokens (XML) | 120 |
| State resolver | **Not set** | ~200–400 tokens (XML) | 500 |
| Orchestrator | **Not set** | ~80–200 tokens (chat reply) | 300 |

No call site currently passes `max_tokens` to `groq_client.complete()`.

---

## Context window headroom

Neither the 8k (8b model) nor the 32k (70b model) context windows are at risk with current group sizes.

| Phase | Model context | Tokens at max (20 messages, 10 members) | Headroom |
|---|---|---|---|
| Silent extraction | 8k | ~165 (constant) | No concern |
| Resolver | 32k | ~1,400 | No concern |
| Orchestrator | 32k | ~1,700 | No concern |

The 20-message history cap (`models.py:MAX_MESSAGE_HISTORY`) is enforced at append time, before any prompt is built.

---

## Prompt editing checklist

Before modifying any prompt, verify:

- [ ] `<confirmed>` in extraction maps to `venue_confirmed`, never `cuisine_confirmed`
- [ ] Resolver output template has empty tags (no hardcoded `true`/`false` values)
- [ ] Any new session field added to `models.py` also needs to be added to `session_to_xml` in `session_utils.py` to be visible to the LLM
- [ ] Any new session field added to `session_to_xml` should have a corresponding parse rule in `resolver._parse_response` if the resolver should be able to set it
- [ ] `selected_venue` is currently never written — if you add venue search results, the write path must go through `resolver._apply_snapshot` or a direct assignment after the resolver call
- [ ] `max_tokens` should be set on any new `complete()` call
- [ ] `event_type` is parsed by the resolver but never emitted by `session_to_xml` — if you want the orchestrator to see it, add it to the `group_xml` list in `session_utils.py`
