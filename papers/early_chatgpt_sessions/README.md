# Early ChatGPT design sessions

Conversations from the pre-corpus / pre-Claude design phase, recovered
from public ChatGPT share links. These are raw transcripts (light
cleanup only) — primary-source material for the project journey.

**Note on dates**: the timestamps embedded in the share-page metadata
(`create_time`) reflect when the share *link* was generated (2026-05-02),
not when the original conversation happened. The conversations themselves
predate the AISL→Sigil rename (2026-02-11) — they all reference the
project as "AISL" and discuss design decisions that landed in the
Feb 6-11 commit window in `git log`.

| Title | File | Share ID |
|---|---|---|
| AI Language Optimization Tips | [`69f5e8c2_ai_language_optimization_tips.md`](./69f5e8c2_ai_language_optimization_tips.md) | `69f5e8c2-c8b4-83eb-8aab-3921de5c6cff` |
| Meaning of AISL | [`69f5e8e8_meaning_of_aisl.md`](./69f5e8e8_meaning_of_aisl.md) | `69f5e8e8-f0b0-83eb-b7ea-c2eafe29e022` |
| Ultimate Programming Language Design | [`69f5e905_ultimate_programming_language_design.md`](./69f5e905_ultimate_programming_language_design.md) | `69f5e905-b1bc-83eb-827f-10deace79d0c` |
| Fine-tuning Small LLMs | [`69f5e951_fine-tuning_small_llms.md`](./69f5e951_fine-tuning_small_llms.md) | `69f5e951-9790-83eb-9bd4-81daf65e5154` |

## Why these matter

These predate the Claude Code logs (which start 2026-04-21) and the
opencode logs (no surviving Sigil sessions). They contain the
pre-fine-tune design decisions: AISL naming origin, programming-
language design discussions that shaped Sigil's grammar, the
OCaml-vs-alternatives evaluation that led to the OCaml interpreter
rewrite, and early thoughts on fine-tuning small LLMs that motivated
the local-LoRA work in Phases 1+ of `papers/JOURNEY.md`.

See `papers/JOURNEY.md` for the synthesised narrative; this directory
is the unprocessed source.