# Early design sessions

Pre-commit conversations recovered from public chat-share links. These
predate the first git commit (`486b51e Initial commit`,
2026-02-06 19:40 UTC) and the first VSCode + Copilot Chat session
(2026-02-05 19:49 UTC) on the development host. Together with the git
log, they are the primary-source backing for `papers/JOURNEY.md`
Phase 0.

**Note on dates**: the timestamps embedded in the ChatGPT share-page
metadata (`create_time`) reflect when the share *link* was generated
(mostly 2026-05-02, when the recovery was performed), not when the
original conversation happened. The mammouth.ai JSONs preserve original
per-message timestamps. The conversations themselves predate the
AISL→Sigil rename (2026-02-11) — they refer to the project as either
"AISL" or "CANON".

## mammouth.ai sessions (2026-02-05 — earliest known activity)

Two shared mammouth.ai chat sessions from the afternoon and evening
of 2026-02-05 — the earliest known activity on the project, ~3.5
hours before the first VSCode Copilot session opened on the dev
host. The earlier session is named verbatim in the data with the
working title **"CANON Grammar (AI-Focused)"** — primary-source
confirmation that CANON was the project's original name before it
became AISL (codebase name from 2026-02-06) and then Sigil
(2026-02-11).

| File | Source | Date (UTC) | Messages | Model |
|---|---|---|---|---|
| [`mammouth/228580f7-52a4-4fec-9b8a-89ab298d37ac.json`](./mammouth/228580f7-52a4-4fec-9b8a-89ab298d37ac.json) | https://mammouth.ai/shared/228580f7-52a4-4fec-9b8a-89ab298d37ac | 2026-02-05 16:11 → 16:31 | 30 | mistral-large-latest |
| [`mammouth/6fbdb0c8-a06c-4075-9fd9-80ed21791700.json`](./mammouth/6fbdb0c8-a06c-4075-9fd9-80ed21791700.json) | https://mammouth.ai/shared/6fbdb0c8-a06c-4075-9fd9-80ed21791700 | 2026-02-05 16:34 → 21:06 | 32 | anthropic-claude-sonnet-4-5-20250929 |

The `*.md` files in `mammouth/` are human-readable transcripts of the
same content. Mistral-large drove the initial CANON typed-AST sketch
(Int / Float / Bool / String / Array / Result, FunctionNode contract,
Pure / IORead / IOWrite / Network effect annotations). Claude Sonnet
4.5 took over for the EBNF refinement (BigDecimal, Future, Channel,
spawn/await/send concurrency, lambda exprs, path-restricted IO) over
the rest of the afternoon and into the evening.

## ChatGPT sessions (pre-AISL design brainstorming)

Four public ChatGPT shared conversations from the same pre-commit
brainstorming window. Among other things they contain the
OCaml-vs-alternatives evaluation that lands on *"OCaml is the best
long-term choice; … C should only remain as a minimal execution
core"* — the exact pivot that shows up in the codebase as commit
`e1ba0aa` on 2026-02-11 ("Add OCaml tree-walking interpreter") plus
`30761c5` ("Remove C bytecode compiler").

| Title | File | Share ID |
|---|---|---|
| AI Language Optimization Tips | [`chatgpt/69f5e8c2_ai_language_optimization_tips.md`](./chatgpt/69f5e8c2_ai_language_optimization_tips.md) | `69f5e8c2-c8b4-83eb-8aab-3921de5c6cff` |
| Meaning of AISL | [`chatgpt/69f5e8e8_meaning_of_aisl.md`](./chatgpt/69f5e8e8_meaning_of_aisl.md) | `69f5e8e8-f0b0-83eb-b7ea-c2eafe29e022` |
| Ultimate Programming Language Design | [`chatgpt/69f5e905_ultimate_programming_language_design.md`](./chatgpt/69f5e905_ultimate_programming_language_design.md) | `69f5e905-b1bc-83eb-827f-10deace79d0c` |
| Fine-tuning Small LLMs | [`chatgpt/69f5e951_fine-tuning_small_llms.md`](./chatgpt/69f5e951_fine-tuning_small_llms.md) | `69f5e951-9790-83eb-9bd4-81daf65e5154` |

## Why these matter

Together with the git log, these conversations are everything that
survives from the pre-commit / pre-fine-tune design phase. They
contain: the CANON → AISL → Sigil naming lineage, the typed-AST and
effect-annotation sketches that shaped the Core/Agent split, the
OCaml-vs-alternatives evaluation that drove the C-bytecode → OCaml
interpreter rewrite, and early thoughts on fine-tuning small LLMs
that motivated the local-LoRA work in Phases 1+ of
`papers/JOURNEY.md`.

See `papers/JOURNEY.md` for the synthesised narrative; this
directory is the unprocessed source.
