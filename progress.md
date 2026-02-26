# LetsPlanIt Progress

## Layer 2 — State & Preferences
- ✅ In-memory Pydantic models for `MemberPreference` and `GroupSession`
- ✅ Session store helpers (`get_or_create`, `save`, `get_all`, `get`, `delete`, `clear`)
- ✅ Preference utilities (`upsert_member`, `merge_dietary`, confirmation helpers)
- ✅ Test coverage via `tests/test_state.py`

## Layer 3 — Silent Extraction
- ✅ `extract_and_merge` processes every inbound message with Groq 8B
- ✅ XML parsing guards handle malformed responses safely
- ✅ Dietary filters and consensus cuisine inference kept in sync
- ✅ Trigger detection (`@Agent`) remains separate for Layer 4
- ✅ Tested in `tests/test_extraction.py`

## Layer 4 — Active Agent & State Resolution
- ✅ Active orchestrator uses Groq 70B with structured session XML
- ✅ Photon bridge client integrated for outbound replies
- ✅ Post-response `resolve_full_state` reconcilers preference/venue confirmations
- ✅ Unit coverage through `tests/test_orchestrator.py` and `tests/test_resolver.py`

## Operational Notes
- `.env` and Photon watcher configs aligned (`PHOTON_GROUP_CHAT_GUID`, `PHOTON_SHARED_SECRET` optional)
- `scripts/reset_state.py` clears in-memory sessions via FastAPI endpoint
- All tests run with `python3 -m unittest discover -s tests -p 'test_*.py'` once dependencies from `server/requirements.txt` are installed
