# LetsPlanIt — Full Audit Report

Generated: 2026-02-26

---

## 1. Project Map

```
server/
  main.py                   — FastAPI app; /webhook handler; /state GET/DELETE/reset
                              endpoints; routes to extract_and_merge and run_agent
  config.py                 — THINKING_MODEL and SMALL_MODEL loaded from env; defaults
                              to "openai/gpt-oss-120b" and "llama-3.1-8b-instant"
  __init__.py               — empty

  agent/
    orchestrator.py         — run_agent, execute_tool, run_tool_loop; SYSTEM_PROMPT_STATIC
                              (Planxiety persona); SYSTEM_PROMPT_DYNAMIC (context block);
                              TOOLS schema list; FALLBACK_REPLY constant
    context.py              — extract_and_merge; parse_extraction; _build_user_prompt;
                              silent XML-based preference extraction via SMALL_MODEL
    resolver.py             — resolve_full_state; _parse_response; _apply_snapshot;
                              full-history reconciliation via THINKING_MODEL
    session_utils.py        — session_to_xml; build_history; _member_to_xml; serializes
                              session state into XML for LLM context
    triggers.py             — is_agent_mentioned; strip_trigger; AGENT_TRIGGERS list
    __init__.py             — empty

  state/
    models.py               — GroupSession, MemberPreference, LocationConstraint,
                              VenueOption, SearchResult; MAX_MESSAGE_HISTORY=20
    session.py              — get_or_create, save, get, get_all, delete, clear;
                              _sessions dict (pure in-memory, no persistence)
    preferences.py          — upsert_member, get_unconfirmed, all_confirmed, merge_dietary
    __init__.py             — empty

  tools/
    __init__.py             — re-exports: create_group_event, estimate_uber_fare,
                              geocode_location, get_travel_times, find_venues
    search_coordinator.py   — find_venues; _normalize_constraints; chains Yelp then Maps;
                              trims results to top 5
    yelp_tool.py            — search_yelp_candidates; Yelp Fusion REST API via httpx;
                              _build_attributes maps dietary filters to Yelp attributes
    maps_tool.py            — geocode_location; get_travel_times; validate_and_rank_venues;
                              estimate_uber_fare; Google Maps REST APIs via httpx
    calendar_tool.py        — create_group_event; stub only — always returns error dict
                              with event_id=None

  llm/
    groq_client.py          — complete(); Groq SDK singleton; asyncio.to_thread wrapper;
                              token usage logging to token_usage.log
    __init__.py             — empty

  imessage/
    photon_client.py        — send_message; HTTP POST to Photon/BlueBubbles bridge;
                              silent logging on failure; supports 3 env var name variants
    __init__.py             — empty

imessage/
  photon_client.py          — legacy standalone photon client (error-raising variant);
                              NOT imported by server/; leftover from prior codebase

scripts/
  reset_state.py            — CLI helper; POST /state/reset via httpx; argparse interface

tests/
  __init__.py               — empty
  test_state.py             — unit tests: session store, preferences, message history cap
  test_extraction.py        — unit tests: XML parsing, extract_and_merge, trigger helpers
  test_orchestrator.py      — unit tests: session_to_xml, run_agent, webhook routing
  test_resolver.py          — unit tests: _parse_response, _apply_snapshot, can_book
  test_tools.py             — unit tests: yelp_tool, maps_tool, search_coordinator,
                              execute_tool, run_tool_loop
  test_api_state.py         — FastAPI TestClient tests for /state endpoints

test.py                     — root-level integration demo script; seeds session manually
                              and runs real @Agent calls; requires live API keys
```

---

## 2. Data Flow — Message Lifecycle

### Silent message (no @Agent)

```
1.  Photon watcher POST /webhook  →  main.py:webhook()  (line 26)
2.  payload.is_self check → False  (line 29)
3.  session_store.get_or_create(payload.group_id)  →  session.py:11
4.  session.append_message({"sender": ..., "text": ...})  →  models.py:89
    State change: session.message_history grows (capped at 20)
5.  triggers.strip_trigger(payload.text)  →  triggers.py:17
    Returns text unchanged (no @Agent present)
6.  context.extract_and_merge({"sender":..., "text": clean_text}, session)
    →  context.py:161
    a. groq_client.complete(model=SMALL_MODEL, messages=[system, user], temp=0, max_tokens=1024)
    b. parse_extraction(raw_response)  →  context.py:94  (XML → dict)
    c. preferences.upsert_member(session, sender, updates)  →  preferences.py:9
       State change: session.members[sender] created or merged
    d. Cuisine tally: if 3+ members share a cuisine_like → session.cuisine set
    e. session.time updated if extracted
    f. session.location_constraints updated/appended if extracted
    g. session.uber_budget_cap updated if extracted
    h. session.dietary_filters = preferences.merge_dietary(session)
       State change: session.dietary_filters recomputed
7.  session_store.save(session)  →  session.py:22
    State change: session.last_updated advanced
8.  triggers.is_agent_mentioned(payload.text) → False → no reply
9.  return {"status": "ok"}
```

### @Agent message with no tool calls

```
Steps 1–7 identical to silent path.
8.  triggers.is_agent_mentioned(payload.text) → True  (main.py:42)
9.  orchestrator.run_agent(payload.text, session)  →  orchestrator.py:348
    a. user_text = strip_trigger(text).strip()
    b. resolver.resolve_full_state(session)  →  resolver.py:240
       - groq_client.complete(model=THINKING_MODEL, temp=0.2, max_tokens=1024)
       - _parse_response(raw) → _apply_snapshot(session, snapshot)
         State change: session fields may be reconciled from full history
       - session_store.save(session)
    c. session_to_xml(session)  →  session_utils.py:28
    d. build_history(session.message_history)  →  session_utils.py:91
    e. messages = [
         {"role": "system", "content": SYSTEM_PROMPT_STATIC},   # persona/rules
         {"role": "system", "content": context_block},           # session XML + history
         {"role": "user",   "content": user_text},
       ]
    f. groq_client.complete(model=THINKING_MODEL, temp=0.3, max_tokens=1024,
                             tools=TOOLS, tool_choice="auto", return_response=True)
    g. run_tool_loop(initial_response, messages, session)  →  orchestrator.py:297
       finish_reason != "tool_calls" → returns (content_string, session)
10. photon_client.send_message(payload.group_id, reply)  →  imessage/photon_client.py:19
11. return {"status": "ok"}
```

### @Agent message triggering find_venues

```
Steps 1–9e identical to @Agent path.
9f. complete() returns finish_reason="tool_calls"
9g. run_tool_loop enters loop (max 5 iterations):
    i.   Appends assistant tool_call message to messages list
    ii.  execute_tool("find_venues", args_json, session)  →  orchestrator.py:253
         - filters args to {cuisine, location_constraints, dietary_filters}
         - find_venues(**filtered_args)  →  search_coordinator.py:34
           a. _normalize_constraints(location_constraints)
           b. anchor = normalized_constraints[0].location
           c. yelp_tool.search_yelp_candidates(cuisine, anchor, dietary_filters, limit=20)
              → Yelp Fusion API call; returns list[dict]
           d. maps_tool.validate_and_rank_venues(candidates, constraints)
              - geocode_location() for each constraint location (Maps Geocode API)
              - Optional inter-constraint check: > 45 min apart → conflict
              - get_travel_times() from each constraint coords to all candidate addresses
                (Maps Distance Matrix API)
              - _filter_with_limits: keeps venues meeting all max_distance_mins
              - If no results: relaxes widest constraint +10 min and retries once
              - Sorts by rating, returns top 5 as list[VenueOption]
         State change: session.venue_options = result.venues
         State change: session.state = "awaiting_confirmation" (if venues found)
    iii. session_store.save(session)
    iv.  Appends tool result to messages
    v.   complete() again (temp=0.1, max_tokens=1024) → text reply
    vi.  finish_reason != "tool_calls" → returns (reply_text, session)
10. send_message(payload.group_id, reply)
11. return {"status": "ok"}
```

### @Agent message triggering create_group_event

```
Steps 1–9f same as above but with create_group_event tool call.
    execute_tool("create_group_event", args_json, session)  →  orchestrator.py:286
    - calendar_tool.create_group_event(**args)  →  calendar_tool.py:7
      Returns: {"event_id": None, "event_url": None, "summary": None,
                "error": "Calendar event creation is not yet implemented."}
    - result.get("event_id") is None → session.calendar_event_id NOT set
    - session.state stays at "awaiting_confirmation" (NOT set to "booked")
    State change: NONE (stub always fails)
    Tool result fed back to LLM; LLM receives error message and composes reply
    indicating calendar is unavailable.
```

---

## 3. State Model Inventory

### GroupSession

| Field | Type | Default | Written by | Read by | In session_to_xml | Status |
|---|---|---|---|---|---|---|
| `group_id` | `str` | required | `get_or_create` (session.py:18) | `save`, `send_message` | No (key only) | Working |
| `members` | `Dict[str, MemberPreference]` | `{}` | `preferences.upsert_member` (preferences.py:9) | `all_confirmed`, `merge_dietary`, `get_unconfirmed`, `session_to_xml` | Yes (`<members>`) | Working |
| `state` | `Literal[...]` | `"idle"` | `execute_tool` (orchestrator.py:261, 291), `_apply_snapshot` (resolver.py:188) | `session_to_xml` (`<state>`) | Yes | Partial — "booked" unreachable (calendar stub) |
| `event_type` | `Optional[str]` | `None` | `_apply_snapshot` (resolver.py:188) | `session_to_xml` | Yes | Partial — only resolver sets it; extraction ignores it |
| `cuisine` | `Optional[str]` | `None` | `extract_and_merge` (context.py:214), `_apply_snapshot` (resolver.py:188) | `session_to_xml` | Yes | Working |
| `time` | `Optional[str]` | `None` | `extract_and_merge` (context.py:217) | `session_to_xml`, `create_group_event` args | Yes | Working |
| `location_anchor` | `Optional[str]` | `None` | `extract_and_merge` (context.py:241–249) | `session_to_xml` | Yes | Partial — `find_venues` uses `constraint[0].location` not this field |
| `max_distance_mins` | `int` | `30` | Never after init | Never | No | Dead — per-member `LocationConstraint` used instead |
| `location_constraints` | `list[LocationConstraint]` | `[]` | `extract_and_merge` (context.py:234–239), `_apply_snapshot` (resolver.py:200–221) | `session_to_xml`, `find_venues` (via tool args) | Yes | Working |
| `dietary_filters` | `list[str]` | `[]` | `extract_and_merge` (context.py:251), `_apply_snapshot` (resolver.py:236) | `session_to_xml`, `find_venues` (via tool args) | Yes | Working |
| `venue_options` | `list[VenueOption]` | `[]` | `execute_tool` after `find_venues` (orchestrator.py:259) | `session_to_xml` (`<venue_options>`) | Yes | Working |
| `selected_venue` | `Optional[Dict]` | `None` | `_apply_snapshot` (resolver.py:189–191) | `session_to_xml`, `can_book` calc | Yes (`<selected_venue>`) | Partial — relies on resolver detecting venue name from chat |
| `uber_budget_cap` | `Optional[int]` | `None` | `extract_and_merge` (context.py:246), `_apply_snapshot` (resolver.py:193–196) | `execute_tool` get_uber_estimate (orchestrator.py:271) | No | Partial — not in XML, LLM cannot see it |
| `calendar_event_id` | `Optional[str]` | `None` | `execute_tool` after `create_group_event` (orchestrator.py:289) | Nothing | No | Dead — calendar stub always returns `event_id=None` |
| `calendar_event_url` | `Optional[str]` | `None` | `execute_tool` after `create_group_event` (orchestrator.py:290) | `session_to_xml` | Yes | Dead — calendar stub always returns `None` |
| `message_history` | `list[Dict]` | `[]` | `main.py:session.append_message` (main.py:35) | `build_history`, `resolve_full_state`, `session_to_xml` (party_size calc) | No (separate `<history>` block) | Working |
| `last_updated` | `datetime` | `datetime.now(UTC)` | `session.touch()` via `save()` (session.py:28) | Nothing | No | Working but never read |

### MemberPreference

| Field | Type | Default | Written by | Read by | In session_to_xml | Status |
|---|---|---|---|---|---|---|
| `name` | `str` | required | `upsert_member` (preferences.py:16) | `session_to_xml` | Yes (`<name>`) | Working |
| `dietary` | `list[str]` | `[]` | `upsert_member` — merged (preferences.py:28) | `merge_dietary`, `session_to_xml` | Yes (`<dietary>`) | Working |
| `cuisine_likes` | `list[str]` | `[]` | `upsert_member` — merged (preferences.py:28) | `extract_and_merge` cuisine tally (context.py:207–213), `session_to_xml` | Yes (`<cuisine_likes>`) | Working |
| `cuisine_dislikes` | `list[str]` | `[]` | `upsert_member` — merged (preferences.py:28) | `session_to_xml` | Yes (`<cuisine_dislikes>`) | Working — LLM sees it but `find_venues` does not filter on it |
| `location` | `Optional[str]` | `None` | `upsert_member` (preferences.py:31) | Nothing | No | Dead — captured but not serialized to XML; LLM cannot see it |
| `venue_confirmed` | `bool` | `False` | `upsert_member` (preferences.py:31) | `all_confirmed`, `get_unconfirmed`, `session_to_xml` | Yes (`<venue_confirmed>`) | Working |

### LocationConstraint

| Field | Type | Default | Written by | Read by | In session_to_xml | Status |
|---|---|---|---|---|---|---|
| `member` | `str` | required | `extract_and_merge` (context.py:234), `_apply_snapshot` (resolver.py:215) | `session_to_xml`, `validate_and_rank_venues` | Yes | Working |
| `location` | `str` | required | same as above | `geocode_location` (via `validate_and_rank_venues`), `find_venues` anchor (search_coordinator.py:45) | Yes | Working |
| `max_distance_mins` | `int` | `30` | same as above | `validate_and_rank_venues` (maps_tool.py:244) | Yes | Working |

### VenueOption

| Field | Type | Default | Written by | Read by | In session_to_xml | Status |
|---|---|---|---|---|---|---|
| `name` | `str` | required | `validate_and_rank_venues` (maps_tool.py:217) | `session_to_xml` option_text | Yes | Working |
| `address` | `str` | required | same | `validate_and_rank_venues` destination_addresses | No (not in option_text) | Partial |
| `rating` | `float` | required | same | sort key, `session_to_xml` option_text | Yes | Working |
| `price` | `str` | required | same | `session_to_xml` option_text | Yes | Working |
| `distance_mins` | `int` | required | same (primary constraint duration) | `session_to_xml` option_text | Yes | Working |
| `yelp_url` | `str` | required | same | Nothing in current code | No | Dead — stored but never presented to LLM or user |
| `coordinates` | `Dict[str, float]` | required | same | Nothing | No | Dead — stored but never used |
| `vegetarian_friendly` | `bool` | `False` | `_has_category(candidate, "vegetarian")` (maps_tool.py:224) | `session_to_xml` veg_tag | Yes | Partial — based on Yelp category tag, not Yelp attribute filter |
| `vegan_friendly` | `bool` | `False` | `_has_category(candidate, "vegan")` (maps_tool.py:225) | Nothing | No | Dead — stored but never surfaced |

---

## 4. Tool Inventory

### `find_venues`

| Property | Value |
|---|---|
| Groq schema name | `"find_venues"` (orchestrator.py:31) |
| Implements | `search_coordinator.find_venues()` (search_coordinator.py:34) |
| External APIs | Yelp Fusion `https://api.yelp.com/v3/businesses/search`; Google Maps Geocode + Distance Matrix |
| Writes to session | `session.venue_options`, `session.state = "awaiting_confirmation"` (if venues found) |
| Returns | `SearchResult.model_dump()` — `{venues, constraints_met, conflict_reason, compromised_constraints}` |
| Failure modes | `YELP_API_KEY` not set → returns `[]` silently; Maps API unavailable → `conflict_reason="Maps API unavailable"`; all candidates exceed distance → relaxes widest constraint +10 min; inter-constraint distance > 45 min → hard conflict returned |

### `get_uber_estimate`

| Property | Value |
|---|---|
| Groq schema name | `"get_uber_estimate"` (orchestrator.py:56) |
| Implements | `maps_tool.geocode_location` + `get_travel_times` + `estimate_uber_fare` (orchestrator.py:266–283) |
| External APIs | Google Maps Geocode API; Google Maps Distance Matrix API |
| Writes to session | Nothing |
| Returns | `{low, high, currency, within_budget, budget_cap, message, note}` |
| Failure modes | `geocode_location` returns `None` → `{"message": "Could not estimate fare — location not found", "error": True}`; distance conversion is rough approximation (`duration_mins * 60 * 8` meters at orchestrator.py:280); `GOOGLE_MAPS_API_KEY` not set → geocode returns `None` → same failure |

### `create_group_event`

| Property | Value |
|---|---|
| Groq schema name | `"create_group_event"` (orchestrator.py:76) |
| Implements | `calendar_tool.create_group_event()` (calendar_tool.py:7) — **stub** |
| External APIs | None (stub) |
| Writes to session | Nothing — `event_id` is always `None` so neither `calendar_event_id` nor `state = "booked"` is ever set |
| Returns | `{"event_id": None, "event_url": None, "summary": None, "error": "Calendar event creation is not yet implemented."}` |
| Failure modes | Always fails by design |

---

## 5. Prompt Inventory

### Call 1 — Silent Extraction

- **Model:** `SMALL_MODEL` = `"llama-3.1-8b-instant"` (via `config.py:4`, `context.py:15`)
- **System prompt:** `EXTRACTION_SYSTEM_PROMPT` (context.py:17–30)
  - Instructs: return only XML, no prose
  - Defines `<dietary>` (food restrictions only)
  - Defines `<cuisine_dislikes>` (cuisines to avoid, not restrictions)
  - Defines `<venue_confirmed>` (explicit venue agreement only)
  - Defines `<location_constraint>` with 30-min default
  - Defines `<uber_budget>` (integer dollars only)
- **User message:** `_build_user_prompt(sender, text)` (context.py:49–73)
  - One inline example (Alisha, vegetarian, no Indian)
  - Then: `Sender: "..."`, `Message: "..."`, filled `XML_TEMPLATE`
- **`max_tokens`:** 1024
- **`temperature`:** 0
- **Known issues:** SMALL_MODEL is a fast extraction model but the prompt's field disambiguation ("never put cuisine names into `<dietary>`") relies on instruction-following quality of `llama-3.1-8b-instant`; kitchen-sink system prompt may be noisy for edge cases.

### Call 2 — State Resolver

- **Model:** `THINKING_MODEL` = `"openai/gpt-oss-120b"` by default (config.py:3, resolver.py:15)
  - **This default is invalid for the Groq SDK** (see Section 7, Bug #1)
- **System prompt:** `SYSTEM_MESSAGE` (resolver.py:18–19)
  - Single line: "Return only the requested XML snapshot with no extra text."
- **User message:** `PROMPT_TEMPLATE.format(...)` (resolver.py:21–82)
  - `<session>` current session XML
  - `<history>` full `message_history`
  - Instructions: resolve venue references, pronoun resolution, implicit agreements
  - One inline example (Johi/Alisha confirming La Scala)
  - Rules block: what counts as `venue_confirmed`, when to set `selected_venue`, cuisine consensus rule (3+ members), dietary always included even if temporary
  - Returns `<resolved_state>` XML with session fields + members
- **`max_tokens`:** 1024
- **`temperature`:** 0.2
- **Known issues:** 1024 `max_tokens` may truncate response for groups with many members or long history, causing XML parse failure and silent fallback to pre-resolution state; `max_tokens` is the same for both 5-member and 2-member groups.

### Call 3 — Active Agent

- **Model:** `THINKING_MODEL` = `"openai/gpt-oss-120b"` by default (config.py:3, orchestrator.py:24)
- **System message 1:** `SYSTEM_PROMPT_STATIC` (orchestrator.py:143–230) — Planxiety persona, vibe rules, format templates, tool usage rules. Contains literal `{session_xml}` and `{history}` placeholders that are **never filled** — these appear verbatim in the system message (see Section 7, Bug #5).
- **System message 2:** `SYSTEM_PROMPT_DYNAMIC.format(session_xml=..., history=...)` (orchestrator.py:232–242, 360) — actual `<group>` XML + formatted message history.
- **User message:** `strip_trigger(text).strip()` — raw user request without `@Agent`.
- **`max_tokens`:** 1024 (initial call, orchestrator.py:374); 1024 (tool loop follow-up, orchestrator.py:340)
- **`temperature`:** 0.3 (initial), 0.1 (tool loop)
- **Known issues:** two system messages with duplicate `<session>` / `<history>` labels; first system message sends literal `{session_xml}` string; 1024 `max_tokens` may truncate venue-listing replies for 5 venues with vibe descriptions; old `SYSTEM_PROMPT_STATIC` is commented out but left in file (lines 97–141).

---

## 6. Test Coverage Matrix

**test_state.py**
```
test_get_or_create_returns_same_instance       Layer 2 — session.py ✓
test_session_get_delete_clear_helpers          Layer 2 — session.py ✓
test_upsert_member_creates_and_merges          Layer 2 — preferences.py ✓
test_all_confirmed_false_when_no_members       Layer 2 — preferences.py ✓
test_merge_dietary_returns_deduplicated_union  Layer 2 — preferences.py ✓
test_message_history_capped_at_twenty          Layer 2 — models.py ✓
```

**test_extraction.py**
```
test_valid_dietary_updates_member_and_filters  Layer 3 — context.py ✓
test_cuisine_and_time_updates                  Layer 3 — context.py ✓
test_confirmed_true_updates_member             Layer 3 — context.py ✓
test_malformed_xml_returns_empty               Layer 3 — context.py ✓
test_partial_xml_only_updates_present_fields   Layer 3 — context.py ✓
test_trigger_detection_and_stripping           Layer 3 — triggers.py ✓
test_dietary_and_dislikes_split                Layer 3 — context.py ✓
test_recent_meal_goes_to_cuisine_dislikes      Layer 3 — context.py ✓
test_venue_confirmed_tag_sets_flag             Layer 3 — context.py ✓
```

**test_orchestrator.py**
```
test_session_to_xml_contains_members_and_can_book_false  Layer 4 — session_utils.py ✓
test_session_to_xml_can_book_true_when_ready             Layer 4 — session_utils.py ✓
test_session_to_xml_handles_empty_members                Layer 4 — session_utils.py ✓
test_run_agent_strips_trigger                            Layer 4 — orchestrator.py ✓
test_run_agent_returns_reply_text                        Layer 4 — orchestrator.py ✓
test_run_agent_handles_exception                         Layer 4 — orchestrator.py ✓
test_webhook_sends_reply_when_agent_mentioned            Layer 4 — main.py ✓
test_webhook_no_send_without_trigger                     Layer 4 — main.py ✓
```

**test_resolver.py**
```
test_selected_venue_and_option_confirmation     Layer 4 — resolver._parse_response + _apply_snapshot ✓
test_no_venue_keeps_fields_empty                Layer 4 — resolver ✓
test_dietary_statement_updates_filters          Layer 4 — resolver ✓
test_two_member_cuisine_not_set                 Layer 4 — resolver ✓
test_majority_cuisine_sets_session_cuisine      Layer 4 — resolver ✓
test_dietary_merges_across_messages             Layer 4 — resolver ✓
test_all_confirmed_helper                       Layer 4 — preferences.py ✓
test_can_book_when_selected_and_all_confirmed   Layer 4 — session_utils.py ✓
```

**test_tools.py**
```
test_search_yelp_adds_vegetarian_attribute          Layer 5 — yelp_tool.py ✓
test_find_venues_handles_empty_yelp_results         Layer 5 — search_coordinator.py ✗ BROKEN
test_find_venues_accepts_dict_constraints           Layer 5 — search_coordinator.py ✗ BROKEN
test_validate_and_rank_returns_top_five             Layer 5 — maps_tool.py ✓
test_validate_and_rank_with_multiple_constraints    Layer 5 — maps_tool.py ✓
test_validate_and_rank_detects_conflict             Layer 5 — maps_tool.py ✓
test_validate_and_rank_relaxes_constraint_once      Layer 5 — maps_tool.py ✓
test_estimate_uber_no_budget                        Layer 5 — maps_tool.py ✓
test_estimate_uber_budget_exceeded                  Layer 5 — maps_tool.py ✓
test_execute_tool_updates_session_after_find        Layer 5 — orchestrator.execute_tool ✓
test_execute_tool_updates_calendar_fields           Layer 5 — orchestrator.execute_tool (mocked) ✓
test_execute_tool_handles_calendar_failure          Layer 5 — orchestrator.execute_tool ✓
test_tool_loop_limits_iterations                    Layer 5 — orchestrator.run_tool_loop ✓
test_execute_tool_handles_geocode_failure           Layer 5 — orchestrator.execute_tool ✓
```

**test_api_state.py**
```
test_list_sessions_endpoint         main.py /state GET ✓
test_get_session_endpoint_not_found main.py /state/{id} 404 ✓
test_reset_state_endpoint           main.py /state/reset ✓
test_delete_specific_session        main.py /state/{id} DELETE ✓
```

**Untested components:**
```
- calendar_tool.create_group_event  — only tested through mocked execute_tool; never called directly
- groq_client._log_usage            — token logging path
- groq_client._get_client           — GROQ_API_KEY missing error path
- photon_client.send_message        — only mocked; real HTTP path untested
- context.py cuisine majority tally — 3-member threshold logic (context.py:206–214)
- context.py uber_budget extraction — full path through extract_and_merge
- context.py location_constraint    — update vs create branch (context.py:222–239)
- resolver.resolve_full_state()     — tests call _parse_response + _apply_snapshot directly,
                                       bypassing the actual Groq call
- maps_tool.geocode_location        — HTTP Exception path
- maps_tool.get_travel_times        — non-default mode parameter
- yelp_tool.search_yelp_candidates  — YELP_API_KEY not set early return (yelp_tool.py:31)
- yelp_tool._build_attributes       — kosher, gluten-free, nut-free, dairy-free inputs
                                       (not in mapping; silently dropped)
- main.py is_self=True early return (main.py:29)
- search_coordinator                — no location_constraints at all (empty list path)
```

---

## 7. Known Bugs and Gaps

**Bug 1 — Invalid THINKING_MODEL default**
```
File:   server/config.py
Line:   3
Issue:  THINKING_MODEL defaults to "openai/gpt-oss-120b". This is not a valid Groq SDK model ID.
        groq_client.complete() calls Groq's API; passing an OpenAI model name will cause
        a 404 or model-not-found error from the Groq endpoint.
        .env.example (line 1) also hardcodes this invalid default.
Status: Active — breaks resolver and active agent on a fresh clone unless .env overrides it.
```

**Bug 2 — find_venues called with party_size in tests (signature mismatch)**
```
File:   tests/test_tools.py
Lines:  50, 81
Issue:  find_venues("italian", constraints, [], party_size=4) — find_venues() in
        search_coordinator.py:34 has signature (cuisine, location_constraints, dietary_filters)
        and accepts no party_size. This raises TypeError at call time.
        test_find_venues_handles_empty_yelp_results and test_find_venues_accepts_dict_constraints
        both fail.
Status: Active — these two tests fail.
```

**Bug 3 — calendar_tool is a permanent stub**
```
File:   server/tools/calendar_tool.py
Lines:  1–23
Issue:  create_group_event() always returns event_id=None and error message.
        execute_tool() checks `if result.get("event_id")` before setting state="booked"
        (orchestrator.py:288). This condition is never true. session.state can never
        reach "booked". calendar_event_id and calendar_event_url are never written.
        The booking flow is entirely non-functional.
Status: Identified, stub intentional but unfixed. Docstring says "Temporary stub".
```

**Bug 4 — Literal {session_xml} in SYSTEM_PROMPT_STATIC sent to LLM**
```
File:   server/agent/orchestrator.py
Lines:  165–172
Issue:  SYSTEM_PROMPT_STATIC contains literal "{session_xml}" and "{history}" placeholders
        (format strings) that are never filled. run_agent() (line 363) passes
        SYSTEM_PROMPT_STATIC as-is. The LLM receives the literal string "{session_xml}"
        in the first system message and the actual data in the second system message.
        This double-label pattern is confusing and may cause the model to misroute
        attention or misunderstand the structure.
Status: Identified, unfixed. Data does reach the LLM via context_block (second system message).
```

**Bug 5 — silent exception swallowing in all HTTP tool calls**
```
File:   server/tools/yelp_tool.py:47, maps_tool.py:59, maps_tool.py:100, maps_tool.py:261
Lines:  47, 59, 100, 261
Issue:  All four external HTTP call sites catch bare Exception and return empty/None.
        No logging occurs at yelp_tool.py:47. No logging at maps_tool.py:59 or :100.
        The orchestrator receives empty results and the agent is told "no results" with
        no visibility into whether it was an API key error, timeout, or bad response.
Status: Identified, unfixed.
```

**Bug 6 — party_size in session_to_xml counts message senders, not members**
```
File:   server/agent/session_utils.py
Line:   68
Issue:  party_size = len({entry.get("sender") for entry in session.message_history ...})
        This counts unique senders in the rolling 20-message history. If a member has
        never spoken, they are excluded. If old messages have been evicted, the count
        drops. This value is passed to create_group_event and shown to the LLM as party size.
Status: Identified, unfixed.
```

**Bug 7 — uber_budget_cap not visible to LLM**
```
File:   server/agent/session_utils.py
Lines:  28–88
Issue:  session_to_xml() does not include uber_budget_cap in the output XML. The LLM
        cannot see what budget cap was captured from the chat. execute_tool falls back to
        session.uber_budget_cap (orchestrator.py:271) but only if the LLM omits it from
        the tool call.
Status: Identified, unfixed.
```

**Bug 8 — member.location not serialized to XML**
```
File:   server/agent/session_utils.py
Lines:  16–25 (_member_to_xml)
Issue:  MemberPreference.location is captured via extraction (preferences.upsert_member)
        but is not included in _member_to_xml output. The LLM cannot see individual member
        locations in the session XML. Only location_constraints (which require explicit
        distance statements) are visible.
Status: Identified, unfixed. Field is effectively dead.
```

**Bug 9 — cuisine_dislikes not used in Yelp search filtering**
```
File:   server/tools/yelp_tool.py, server/tools/search_coordinator.py
Issue:  Members' cuisine_dislikes are faithfully captured and shown to the LLM in session XML.
        However, find_venues() and search_yelp_candidates() have no parameter for
        excluded cuisines. The Yelp search is performed without any negative cuisine filter.
        The LLM must refuse results on its own.
Status: Identified, unfixed. Relies entirely on LLM judgment.
```

**Bug 10 — dietary filter mapping is incomplete in yelp_tool**
```
File:   server/tools/yelp_tool.py
Lines:  13–20
Issue:  _build_attributes() maps only "vegetarian" → "vegetarian_friendly", "vegan" →
        "vegan_friendly", "halal" → "halal". The EXTRACTION_SYSTEM_PROMPT (context.py:21)
        lists: vegetarian, vegan, halal, kosher, gluten-free, nut-free, dairy-free.
        Kosher, gluten-free, nut-free, and dairy-free are silently dropped from the
        Yelp attributes filter. No logging.
Status: Identified, unfixed.
```

**Bug 11 — vegetarian_friendly detection uses category tag, not Yelp attribute**
```
File:   server/tools/maps_tool.py
Lines:  224
Issue:  VenueOption.vegetarian_friendly is set by _has_category(candidate, "vegetarian")
        which checks Yelp business categories (alias/title). This is independent of
        whether the Yelp API was called with `attributes=vegetarian_friendly`.
        A restaurant can be labelled vegetarian_friendly in session_to_xml's veg_tag
        without having been filtered on that attribute, or vice versa.
Status: Identified, minor inconsistency.
```

**Bug 12 — test_execute_tool_updates_calendar_fields gives false confidence**
```
File:   tests/test_tools.py
Lines:  260–288
Issue:  This test mocks create_group_event to return {"event_id": "1", "event_url": "url"}
        and asserts session.state == "booked". The real calendar_tool always returns
        event_id=None and the booking flow never completes. The test passes only because
        the entire calendar tool is mocked out.
Status: Test passes but provides no assurance about the real booking path.
```

**Bug 13 — imessage/photon_client.py is a dead file**
```
File:   imessage/photon_client.py
Issue:  Duplicate photon client at the project root level. Not imported by the server.
        Has different error-handling behavior (raises PhotonClientError). Confusing
        for contributors.
Status: Dead code, not a runtime bug.
```

**Bug 14 — python-dotenv not in requirements.txt**
```
File:   test.py:1, server/requirements.txt
Issue:  test.py uses `from dotenv import load_dotenv` but `python-dotenv` is not listed
        in server/requirements.txt. Will fail on a clean install.
Status: Missing dependency.
```

**Bug 15 — max_distance_mins field on GroupSession is dead**
```
File:   server/state/models.py
Line:   69
Issue:  GroupSession.max_distance_mins = 30 exists as a session-level field.
        Nothing reads or writes it after initialization. All distance logic uses
        per-member LocationConstraint.max_distance_mins.
Status: Dead field.
```

**Bug 16 — Old SYSTEM_PROMPT_STATIC commented out in file**
```
File:   server/agent/orchestrator.py
Lines:  97–141
Issue:  The old "LetsPlanIt" system prompt is preserved as a large commented-out block.
        Creates confusion about which prompt is active and the persona name
        (README says "LetsPlanIt", active prompt says "Planxiety").
Status: Code smell, not a runtime bug.
```

---

## 8. Layer Completion Status

```
Layer 0  scaffold          ⚠️ partial — FastAPI boots, module structure complete,
                                        but /health endpoint from PLAN.md is absent

Layer 1  iMessage bridge   ✅ complete — /webhook receives, send_message sends,
                                         is_self filtering in place, strip_trigger called
                                         before extraction

Layer 2  state models      ✅ complete — GroupSession, MemberPreference, LocationConstraint,
                                         VenueOption, SearchResult all implemented;
                                         session.py and preferences.py complete;
                                         max_distance_mins on GroupSession is dead but minor

Layer 3  silent extraction ✅ complete — extract_and_merge, parse_extraction, triggers.py
                                         all implemented; strip_trigger called before
                                         extraction in main.py (poison bug avoided)

Layer 4  active agent      ✅ complete — run_agent, run_tool_loop, resolve_full_state,
                                         session_to_xml, SYSTEM_PROMPT_STATIC all implemented;
                                         THINKING_MODEL default is invalid (Bug #1)

Layer 5  tools             ⚠️ partial — find_venues (Yelp + Maps) working;
                                         estimate_uber_fare working;
                                         create_group_event is a stub (always fails);
                                         OpenTable not implemented;
                                         two tests broken due to signature mismatch (Bug #2)

Layer 6  persistence       ❌ not started — _sessions is a plain dict; no Redis; no SQLite;
                                            session lost on server restart

Layer 7  state machine     ❌ not started — no machine.py; no formal transition guards;
                                            state field updated ad-hoc by resolver and
                                            execute_tool with no validation

Layer 8  multi-group       ⚠️ partial — group_id as key is in place; /state endpoints
                                         exist; no GroupRegistry, no rate limiting,
                                         no /admin/sessions route, no per-group concurrency
                                         guards

Layer 9  hardening         ❌ not started — no retry/backoff on Groq timeouts; no webhook
                                            signature validation; no per-group request
                                            queueing; no non-English handling; token usage
                                            logging exists but no alerting
```

---

## 9. Dependency Map

### Python packages (server/requirements.txt)

| Package | Version | Purpose | Core/Optional | Fallback if unavailable |
|---|---|---|---|---|
| `fastapi` | unpinned | HTTP framework, /webhook, /state endpoints | Core | None |
| `uvicorn` | unpinned | ASGI server | Core | None |
| `groq` | unpinned | Groq SDK for LLM completions | Core | ImportError handled at import (groq_client.py:12–15); runtime RuntimeError on first call |
| `httpx` | unpinned | HTTP client for Yelp, Maps, Photon | Core | None |
| `pydantic` | unpinned | Data models, validation | Core | None |
| `fastmcp` | unpinned | Listed in requirements.txt but **not imported anywhere** in server/ | Dead | N/A |
| `sqlmodel` | unpinned | Listed in requirements.txt but **not imported anywhere** | Dead | N/A |
| `redis` | unpinned | Listed in requirements.txt but **not imported anywhere** | Dead | N/A |
| `rich` | unpinned | Listed in requirements.txt; not imported in server/ (README mentions demo only) | Optional | N/A |
| `python-dotenv` | not listed | Used in test.py (`from dotenv import load_dotenv`) | Dev | Missing from requirements.txt |

No packages are pinned to specific versions.

### External APIs

| API | Env var | Purpose | Required for | Fallback |
|---|---|---|---|---|
| Groq API | `GROQ_API_KEY` | All three LLM calls | Core agent functionality | FALLBACK_REPLY for active agent; silent pass-through for extraction |
| Yelp Fusion | `YELP_API_KEY` | Venue candidate search | find_venues | Returns `[]` silently (yelp_tool.py:31–32) |
| Google Maps Geocoding | `GOOGLE_MAPS_API_KEY` | Address → coords | validate_and_rank_venues, get_uber_estimate | Returns `None` → tool call fails with error message |
| Google Maps Distance Matrix | `GOOGLE_MAPS_API_KEY` | Travel time validation | validate_and_rank_venues, get_uber_estimate | Returns `[None, ...]` → all venues fail constraints |
| Photon / BlueBubbles bridge | `PHOTON_WATCHER_URL` or `IMESSAGE_BRIDGE_URL` or `BLUEBUBBLES_URL` | Outbound iMessage | Sending replies | LOGGER.warning, silently skipped (photon_client.py:26–27) |

---

## 10. Critical Path to Demo-Ready

The following are the minimum changes required to demonstrate the agent to someone outside the team. Ordered by impact. No nice-to-haves.

---

**P0 — Fix THINKING_MODEL default (breaks everything)**
```
File:  server/config.py line 3  AND  .env.example line 1
Fix:   Change default from "openai/gpt-oss-120b" to a valid Groq model ID, e.g.
       "llama-3.3-70b-versatile".
       Populate .env with GROQ_API_KEY, YELP_API_KEY, GOOGLE_MAPS_API_KEY,
       PHOTON_WATCHER_URL (or IMESSAGE_BRIDGE_URL).
       .env.example only has 2 of ~6 required keys — it is misleading to a first-time
       runner.
Impact: Without this, both the resolver and active agent fail on every invocation.
```

**P0 — Fix two broken tests (blocks CI/CD and test trust)**
```
File:  tests/test_tools.py lines 50 and 81
Fix:   Remove the `party_size=4` keyword argument from the two find_venues() calls.
       find_venues() does not accept party_size. Both tests raise TypeError and fail.
Impact: Two tests fail on every `pytest` run.
```

**P1 — Implement a working calendar stub (booking flow is dead)**
```
File:  server/tools/calendar_tool.py
Fix:   Make create_group_event return a non-None event_id (even a fake UUID) so that
       execute_tool (orchestrator.py:288) can set session.state = "booked" and the LLM
       can present a "booked" confirmation to the demo audience.
       The full Google Calendar MCP integration can come later; the stub just needs to
       return {"event_id": "demo-event-001", "event_url": "https://..."} to unlock
       the booking path for demo.
Impact: Without this, the agent can never complete the booking flow. session.state never
        reaches "booked". The demo ends with "Calendar event creation is not yet implemented."
```

**P1 — Remove or resolve unfilled {session_xml}/{history} in SYSTEM_PROMPT_STATIC**
```
File:  server/agent/orchestrator.py lines 165–172
Fix:   The first system message contains literal Python format strings that never get
       filled. Either (a) remove the "{session_xml}" and "{history}" labels from
       SYSTEM_PROMPT_STATIC so it is pure rules/persona, or (b) merge SYSTEM_PROMPT_STATIC
       and SYSTEM_PROMPT_DYNAMIC into one format call. The current split sends
       "{session_xml}" literally to the LLM which is confusing.
Impact: Reduces LLM prompt confusion; avoids model treating "{session_xml}" as an
        instruction rather than a data label.
```

**P2 — Add GROQ_API_KEY, YELP_API_KEY, GOOGLE_MAPS_API_KEY to .env.example**
```
File:  .env.example
Fix:   Add placeholder lines for all required environment variables so a first-time
       runner knows what to set. Currently only THINKING_MODEL and SMALL_MODEL are
       documented.
Impact: Operational — without this, a new person cannot run the project.
```

**P2 — Add error logging to silent exception catches in tool HTTP calls**
```
Files: server/tools/yelp_tool.py:47, maps_tool.py:59, 100, 261
Fix:   Add `LOGGER.exception(...)` or `LOGGER.warning(...)` inside each bare except
       block so that API failures are visible in logs rather than returning silent
       empty results.
Impact: Debugging — without this, an expired or wrong API key produces no feedback
        and the agent silently returns "no results found" to the group.
```
