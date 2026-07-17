---
name: mud-player
description: Play the tbaMUD (CircleMUD-family) text adventure running on localhost:4000 by driving scripts/mud_client.py over Bash. Use this whenever the user asks to log into the MUD, play the MUD, explore the game world, fight monsters, check score/inventory, or otherwise issue in-game commands to the localhost:4000 server. Also use this whenever the user wants to pursue a longer-term goal that spans multiple sessions -- reaching a target level, hunting down and defeating a specific monster, mapping out the world, or just "keep playing/grinding" -- since this skill maintains persistent player and world memory files (data/player.md, data/world.md) across conversations so progress and goals aren't lost when a session ends. Test account is dummy/helloworld unless the user gives different credentials. Always use this skill instead of trying to open a raw telnet/nc connection by hand -- the server's telnet negotiation and login menu are finicky and this script already handles them correctly.
---

# Playing the tbaMUD on localhost:4000

`scripts/mud_client.py` manages the whole session: it opens a raw TCP
connection (there's no `telnet` binary on this machine and Python 3.13+
dropped `telnetlib`), filters out telnet IAC negotiation bytes and ANSI
color codes, and keeps the connection alive in a background daemon so
state (room, HP, inventory) persists across multiple tool calls.

## Workflow

```bash
SCRIPT=.claude/skills/mud-player/scripts/mud_client.py   # adjust path as needed

python3 "$SCRIPT" start                                   # open the connection
python3 "$SCRIPT" login --name dummy --password helloworld  # authenticate + enter game
python3 "$SCRIPT" send "look"                              # issue any in-game command
python3 "$SCRIPT" send "north"
python3 "$SCRIPT" send "score"
python3 "$SCRIPT" read --wait 2                            # check for unsolicited messages (tells, combat)
python3 "$SCRIPT" status                                   # who's logged in, is the link alive
python3 "$SCRIPT" stop                                     # ALWAYS do this when done
```

Each `send` call prints exactly what the server sent back for that
command (room descriptions, combat rounds, score sheet, etc.) as plain
text ending in the game's status prompt, e.g. `23H 100M 83V (news) (motd) > `
— HP / Mana / Movement points, which is worth reading before deciding the
next action.

## Why `stop` matters

If you kill the shell or just stop calling the script without running
`stop`, the character is left "linkless" on the server. The next `login`
will then hit a `Please type Yes or No` reconnect prompt instead of the
normal flow — `login` handles that automatically by answering "yes", but
it's slower and messier than just quitting properly. Always call `stop`
at the end of a play session (or before switching characters).

## Command reference

- `start [--host HOST] [--port PORT]` — opens the raw connection and prints the banner. Defaults to `localhost:4000`.
- `login --name NAME --password PASSWORD` — answers the name/password prompts, presses return through the MOTD, picks "1) Enter the game" from the menu, and confirms a reconnect if needed. Auto-runs `start` first if no connection is open yet.
- `send "<command>" [--wait SECONDS]` — sends one command line (e.g. `look`, `north`, `kill rat`, `get sword`, `wear armor`, `cast 'magic missile' rat`) and returns the response, waiting up to `--wait` seconds (default 6) for it to finish arriving.
- `read [--wait SECONDS]` — drains any output that arrived without you sending anything (combat rounds ticking, tells from other players). Useful to poll after a `kill` command since fights happen over multiple rounds.
- `status` — reports whether a session is active and who's logged in, without side effects.
- `stop` — sends `quit` in-game, waits for confirmation, and shuts the connection down cleanly. Safe to call even if nothing is connected.

If the daemon ever gets stuck (rare), `rm -rf /tmp/mud-skill` and start over — this force-abandons the connection without a graceful in-game quit, so prefer `stop` whenever possible.

## Multiple characters at once

Pass `--session-dir <path>` (before the subcommand) to any command to
keep sessions isolated, e.g. to run two characters concurrently:

```bash
python3 "$SCRIPT" --session-dir /tmp/mud-alice start
python3 "$SCRIPT" --session-dir /tmp/mud-alice login --name alice --password ...
python3 "$SCRIPT" --session-dir /tmp/mud-bob   start
python3 "$SCRIPT" --session-dir /tmp/mud-bob   login --name bob --password ...
```

Without `--session-dir`, state lives at `/tmp/mud-skill/<host>_<port>/`,
so a second `start` on the same host:port reuses the same session rather
than opening a duplicate connection.

## Long-term memory: player and world files

`mud_client.py`'s session state disappears the moment you `stop` — that's
fine for keeping one conversation's connection alive, but it means every
new session starts with no memory of what happened before. Without
something more durable, a goal like "get this character to level 7" or
"track down and kill the Ogre King" can't survive past the current
conversation, and you'd re-explore the same rooms over and over. Two plain
markdown files under `data/` fix that by acting as persistent notes, read
and written with the normal Read/Edit/Write tools (not through
`mud_client.py` — it only speaks to the game socket, not these files):

- **`data/player.md`** — the character's stats, active/completed goals,
  known skills, inventory, and a running session log. This is the file
  that lets "keep grinding toward level 7" mean something across separate
  conversations. It assumes a single character; if the user ever plays
  more than one at once (see "Multiple characters" above), split it into
  `data/player-<name>.md` per character instead.
- **`data/world.md`** — one shared file for the whole game world, not
  per-character, since the map and monsters are the same no matter who's
  playing. Holds rooms and how they connect, NPCs/guildmasters and what
  they offer, and monsters with location, rough difficulty, and whether
  they're still alive.

### Reading memory

Right after `login`, read both `data/player.md` and `data/world.md`, if
they exist. This surfaces the active goal, last known location, and
already-explored map before you send a single game command — so
exploration heads somewhere useful instead of blindly retracing old
ground. If the files don't exist yet, create them from the templates
below, and if no goal is recorded, ask the user what they want tracked
(e.g. a target level, a specific monster to hunt) rather than assuming.

### Writing memory

Update incrementally as things happen rather than saving it all up for
the end — an interrupted session (or a forgotten `stop`) shouldn't erase
everything learned along the way:

- A room seen for the first time → add it to `world.md`'s map with its exits.
- A new monster or NPC → add it to the relevant table in `world.md`.
- A monster's status changes (defeated, or turns out much tougher than
  expected) → update its row.
- `score` shows a level-up, or a goal's condition is met → check it off in
  `player.md` and add a one-line session log entry.
- A fight goes badly or HP drops dangerously low → note it, so a future
  session knows to avoid that monster until stronger.

And always do a final sync of both files immediately before `stop` — treat
it as part of the same checkpoint, since that's the last guaranteed moment
before the connection closes.

### Working toward goals

When a goal is active, let it steer what happens next instead of
exploring aimlessly:

- If under-leveled for the goal, check `world.md`'s monster table for
  something appropriately weak nearby to fight for experience, and use
  `practice` at a guildmaster when a practice session is available — free
  progress that's easy to forget about mid-adventure.
- If the goal names a specific monster whose location isn't in `world.md`
  yet, prioritize exploring unmapped exits until it turns up, logging the
  map as you go rather than wandering the same halls twice.
- Once the monster is both located and the character seems ready (weigh
  level/HP against whatever's noted about the monster), go engage it —
  but retreat if HP drops dangerously low, same as any other fight.
- Check `score` periodically to catch level-ups and update `player.md`
  accordingly, so progress toward the goal stays visible without the user
  needing to ask for a status update.

### File templates

`data/player.md`:
```markdown
# Player Memory

Last updated: <date>

## Character
- Name:
- Class:
- Level:
- HP/Mana/Move:
- Experience:
- Gold:
- Location:

## Active Goals
- [ ]

## Completed Goals

## Skills & Practice
-

## Inventory
-

## Session Log
- <date>:
```

`data/world.md`:
```markdown
# World Memory

Last updated: <date>

## Map
### <Zone name>
| Room | Exits | Notes |
|------|-------|-------|

## NPCs & Guilds
- <name/role> — location: — notes:

## Monsters
| Name | Location | Difficulty | Status | Notes |
|------|----------|-----------|--------|-------|

## Points of Interest
-
```

## Safety notes

- If `login` is given a character name the server doesn't recognize, it aborts instead of accidentally creating a new character (the server would otherwise walk into a "Did I get that right... give me a password..." creation flow). Create characters manually first if that's genuinely what's wanted.
- This connects to `localhost:4000` only unless told otherwise — don't point it at a remote/public MUD without the user explicitly asking.
