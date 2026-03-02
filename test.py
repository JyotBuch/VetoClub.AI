from dotenv import load_dotenv
load_dotenv()

import asyncio
from server.agent.orchestrator import run_agent
from server.agent.context import extract_and_merge
from server.state import session as session_store
from server.state.models import LocationConstraint, MemberPreference

async def main():
    import traceback

    async def say(sender: str, text: str):
        entry = {"sender": sender, "text": text}
        session.message_history.append(entry)

        # always run silent extraction — same as real webhook
        await extract_and_merge(entry, session)
        session_store.save(session)

        if "@Agent" in text:
            print(f"\n[{sender}]: {text}")
            try:
                reply = await run_agent(text, session)
                print(f"\n[Planxiety]: {reply}\n")
                confirmed = [n for n, m in session.members.items() if m.venue_confirmed]
                print(f"  state={session.state}")
                print(f"  selected_venue={session.selected_venue}")
                print(f"  venue_confirmed={confirmed}")
            except Exception:
                traceback.print_exc()
        else:
            print(f"[{sender}]: {text}  (silent)")
            # show extraction result for debug
            confirmed = [n for n, m in session.members.items() if m.venue_confirmed]
            if confirmed:
                print(f"  → venue_confirmed so far: {confirmed}")

    # ── Seed session ──────────────────────────────────────────
    session = session_store.get_or_create("demo3")
    session.cuisine = "italian"
    session.time = "8pm"
    session.dietary_filters = ["vegetarian"]
    session.location_anchor = "Chicago, IL"        # ← changed from Riverwalk
    session.location_constraints = [
        LocationConstraint(
            member="Johi",
            location="Chicago, IL",                # ← changed
            max_distance_mins=30
        )
    ]
    session.members = {
        "Jyot":  MemberPreference(name="Jyot"),
        "Nidhi": MemberPreference(name="Nidhi",  cuisine_likes=["italian"]),
        "Johi":  MemberPreference(name="Johi",   cuisine_likes=["italian"], location="Chicago"),
        "Alisha":MemberPreference(name="Alisha", dietary=["vegetarian"]),
    }
    session.message_history = [
        {"sender": "Jyot",   "text": "lets go out for dinner tonight"},
        {"sender": "Nidhi",  "text": "I want Italian"},
        {"sender": "Johi",   "text": "Italian sounds good to me"},
        {"sender": "Alisha", "text": "I am vegetarian"},
        {"sender": "Jyot",   "text": "lets go at 8pm"},
        {"sender": "Johi",   "text": "nothing more than 30 mins away please"},
    ]
    session_store.save(session)

    print("=" * 60)
    print("SCENE 1 — venue search")
    print("=" * 60)
    await say("Nidhi", "find us Italian places with a chill vibe @Agent")

    if not session.venue_options:
        print("  !! venue_options empty — Yelp/Maps issue, stopping here")
        return

    top = session.venue_options[0].name
    print(f"\n  top venue from Yelp: {top}")

    print("\n" + "=" * 60)
    print("SCENE 2 — group confirms")
    print("=" * 60)
    await say("Jyot",   f"{top} works for me")
    await say("Nidhi",  f"{top} is great")
    await say("Alisha", f"I am good with {top}")
    await say("Johi",   f"{top} works")

    print("\n" + "=" * 60)
    print("SCENE 3 — confirmation gate")
    print("=" * 60)
    await say("Jyot", "are we all good @Agent")

    print("\n" + "=" * 60)
    print("SCENE 4 — book it")
    print("=" * 60)
    await say("Jyot", "book it @Agent")

    print("\n" + "=" * 60)
    print("FINAL STATE")
    print("=" * 60)
    print(f"  state:              {session.state}")
    print(f"  selected_venue:     {session.selected_venue}")
    print(f"  calendar_event_id:  {session.calendar_event_id}")
    print(f"  calendar_event_url: {session.calendar_event_url}")
    for name, m in session.members.items():
        print(f"  {name}: venue_confirmed={m.venue_confirmed}")

asyncio.run(main())