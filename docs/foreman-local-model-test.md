# Foreman phase 6: local-model play test

Goal (plan section 11): a local model plays 2 cycles through the harness, guided only by Foreman briefings, and keeps **food days and water days at 3 or more through cycle 2**.

The driver is `foreman/local_model_driver.py`. It works with any OpenAI-compatible chat API that supports tool calling: Ollama, LM Studio, llama.cpp server or vLLM. It uses only the standard library, so run it with the harness venv, which also provides the harness imports for `--live`.

## Before you start

1. Start Foreman: `cd foreman && ../runtime/python -m foreman serve`, then open http://127.0.0.1:8097.
2. Start the model server and use a model that is good at tool calls. For example, with Ollama: `ollama serve`, then `ollama pull qwen3:14b`.
3. **Never use the stream save.**
   - For `--live`, start a **new game** (`new_game`) or load a throwaway save.
   - The driver never saves, but the game's own autosave does. A live run on a save you care about would change it.

## Dry run (default; safe on any save)

```
runtime/python foreman/local_model_driver.py --base-url http://127.0.0.1:11434/v1 --model qwen3:14b --turns 3
```

- The game is never changed, unpaused or saved.
- Every game action the model asks for is validated by Foreman, and the verdict goes back to the model as the tool result:
  - `NOT RUN` with the criticals, or
  - `DRY RUN` with the warnings.
- Use the dry run to check that the model reads the briefing, follows the NEXT calls and fixes criticals before it asks to place anything.

## Live run (new game or throwaway save only)

```
runtime/python foreman/local_model_driver.py --base-url http://127.0.0.1:11434/v1 --model qwen3:14b --live --test-save
```

Each turn:

1. The driver fetches `/api/briefing`.
2. The model works for up to `--rounds` tool-call rounds. It has:
   - the game actions: `place_building`, `place_line`, `place_area`, `safe_plant`, `mark_tree_cutting`, `clear_planting`, `building_action`, `set_priority`, `set_workers`, `set_paused`, `unlock_building` and `demolish`
   - the reads: `foreman_suggestions`, `foreman_where`, `foreman_plantable`, `foreman_findings` and `list_buildings`
3. The model ends the turn with `end_turn(thought)`.
4. Every action goes through `/api/validate` first. An action with a critical problem is **not run**, and the model gets the reason and the fix.
5. `watch.py <chunk> 3` then runs the game for `--chunk` seconds (110 by default).

The run stops at cycle 3 or after `--turns` turns (200 by default).

The driver never narrates on the overlay, never saves and never touches OBS or polls.

## Result

- Each turn is one line in `foreman/data/localtest-<time>.jsonl`. It holds:
  - the cycle and day
  - food and food days, water and water days
  - the number of adults and kits
  - the actions and their results
  - the model's thought
  - the `STOP`, `TIME` and `FOOD DAYS` lines from watch.py
- At the end the driver prints the lowest food days and water days.
- **PASS** means both stayed at 3 or more. Exit code 0 means pass and 1 means fail.
- A dry run gives no verdict, because the game did not move.

## Options

| Option | Default | What it does |
|---|---|---|
| `--base-url` | `$OPENAI_BASE_URL` or `http://127.0.0.1:11434/v1` | Chat completions endpoint (the `/v1` root) |
| `--model` | required | Model name |
| `--turns` | 3 dry, 200 live | Turns to play |
| `--rounds` | 12 | Tool-call rounds per turn |
| `--chunk` | 110 | watch.py seconds per turn (live) |
| `--timeout` | 300 | Model request timeout (s) |
| `FOREMAN_URL` | `http://127.0.0.1:8097` | Foreman service |
| `OPENAI_API_KEY` | unset | Sent as a bearer token if set; never printed |

## Tested

- The driver ran end to end in dry mode against the `late-game` fixture, using a scripted fake model.
- The fake model did four things, and each gave the expected result:

  | What the fake model did | Result |
  |---|---|
  | Placed a warehouse on the District Centre | Refused, with the critical |
  | Asked `foreman_where` for a clean spot | Got the spot and the calls |
  | Planted corn on mostly dry tiles | Validated, with the skipped tiles reported |
  | Called `end_turn` | Ended the turn |

- `--live` without `--test-save` is refused.
- **A real local-model live run has not been done yet.** It needs your model and a fresh game.
