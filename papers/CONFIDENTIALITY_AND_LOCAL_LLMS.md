# Confidentiality Risk in Cloud-LLM Tooling Workflows, and the Local-DSL Mitigation

> **Status (2026-05-04): Sigil project closed.** This analysis was the
> motivating prose for the local-tooling thesis and remains correct on
> the confidentiality-risk argument. The mitigation it proposed —
> "local DSL with capability-restricted IO" — is exactly what the
> successor project (`post-sigil/PROJECT_PLAN.md` in a sibling repo)
> makes concrete with policy-enforced safety on a Starlark host. See
> [`SIGIL_RESULT.md`](./SIGIL_RESULT.md) for what the Sigil empirical
> work validated and refuted; this paper still holds as the
> *why*-the-project-exists framing.

**Status:** working draft, 2026-04-30
**Scope:** confidentiality risk specifically in *host-tooling-script
generation* workflows (file traversal, log filtering, text
transformation, output formatting), where an AI agent generates short
programs that are then executed locally against the user's filesystem
and data. Frontier-model use for general assistance, code review, or
multi-file refactoring is out of scope.

## 1. Why this analysis is necessary

The mainstream pattern for AI-driven host tooling today routes through
cloud LLMs: an agent (Claude Code, Cursor, Aider, custom agentic
workflows) sends a task description to a cloud model, receives a Python
or Bash script in response, then executes that script locally against
real files and data. The cloud round-trip is invisible from the user's
perspective — the agent feels local — but every call carries
substantial information about the host, the codebase, and the user's
intent across a network boundary into a third party's systems.

This pattern works well for accuracy and convenience. It works poorly
for any environment where the data being processed, the structure of
the codebase, or the user's intent is itself sensitive. The set of
such environments is large: regulated industries, classified work,
internal corporate IP, personal-data processing, security research,
incident response, journalistic source protection.

A defensible answer to "should I let an AI agent help with my tooling?"
in such environments cannot be "yes, just use Claude" without an
honest assessment of what crosses the network boundary.

## 2. Threat model

### 2.1 Information sent to a cloud LLM during tooling-script generation

When an agent asks "write me a Bash script that finds all PDFs
modified in the last 7 days under `~/Documents/Clients`, extracts
their text, and looks for the string 'confidential'," the LLM
provider receives, at minimum:

| Category | Specific items leaked |
|---|---|
| Filesystem layout | absolute and relative paths (`~/Documents/Clients`), implied directory hierarchy, file extensions, naming conventions |
| User intent | the task description in natural language, often containing keywords that imply business context ("Clients," "audit," "Q3 review") |
| Operational metadata | time references, sample sizes, environment hints (date, OS hints from path styles), tool versions if mentioned |
| Sample inputs | file content snippets the user pastes for context, error messages from prior failed runs, log excerpts |
| Code patterns | other code mentioned for context, internal function/variable names, library choices, architectural decisions implicit in the way the question is framed |
| Identifiers | environment variable names (and sometimes values), database table names, API endpoints, hostnames, usernames, project codenames |
| Iteration data | follow-up corrections that reveal what the first attempt got wrong, exposing what the user is actually trying to accomplish step by step |

This is not paranoia: every item above is content the LLM provider's
infrastructure must receive in order to respond. Whether they store
it, train on it, or share it varies by provider and tier; whether
they *receive* it does not.

### 2.2 What happens to the data after it arrives

Provider behaviour varies and changes. As of 2026-04 the published
positions of the three major providers are roughly:

| Provider | Default training use | Log retention | Encryption | Cross-border |
|---|---|---|---|---|
| Anthropic (Claude) | does not train on consumer API inputs by default; explicit opt-in for some products | 30 days for API, longer for safety review | TLS in transit, AES-256 at rest | data may transit US data centres |
| OpenAI (ChatGPT, API) | does not train on enterprise API; consumer ChatGPT can be opted out via settings | 30 days standard, longer for abuse review | TLS in transit, AES-256 at rest | US data centres primarily |
| Google (Gemini) | varies by product; some training uses by default for consumer; enterprise has stricter terms | varies | TLS + at-rest | global infrastructure |

Important nuances:
- "Does not train" usually means *automated training*. Manual review
  by safety teams, abuse review by trust and safety, and aggregate
  metrics (which can leak structural information) are typically
  retained.
- Logs persist longer than the documented retention periods in
  practice — backups, replication for fault tolerance, and abuse-
  investigation extensions all create durable copies.
- Encryption at rest does not protect against insider threat, lawful
  access requests, or breaches that compromise key management.
- Cross-border transfer creates jurisdictional exposure even when the
  provider's home country has strong privacy law: the data is now
  reachable by other governments under their own legal processes.

### 2.3 Threat actors of concern

For tooling workflows specifically, the threat actors are:

1. **The provider itself**, which has policy commitments but also
   commercial incentives that change over time and access to all
   uploaded data.
2. **Provider employees** with insider access for safety review,
   abuse investigation, or operational needs.
3. **Government legal process** (subpoenas, FISA, GDPR-recognised
   exceptions, equivalent foreign processes) that compels disclosure.
4. **Provider security incidents** — breaches, misconfigurations,
   key compromise. The 2024-2025 history of cloud incidents shows
   this is a non-trivial baseline risk.
5. **Other tenants** in the case of any shared-infrastructure
   misconfiguration.

For most consumer use, the realistic threat is (1) policy drift over
time and (4) security incident. For enterprise/regulated use, all
five matter and (3) government access has bitten organisations more
than once.

## 3. Documented incidents

The pattern this paper warns about has produced concrete incidents.

- **Samsung (2023):** engineers pasted proprietary chip-design code
  into ChatGPT for help; the company later discovered that fragments
  of internal IP were retrievable through the model. Samsung
  responded by banning ChatGPT use internally. Source: multiple
  press reports, Samsung internal memo to staff.
- **Law firms and ChatGPT (2023-2024):** several large firms
  prohibited ChatGPT use after instances of attorneys pasting client
  matter details. ABA ethics opinions have flagged this as a
  privilege concern requiring client consent.
- **Healthcare incidents:** multiple HIPAA covered entities have
  been required to file breach notifications after staff used
  consumer LLMs to draft documentation containing patient
  identifiers.
- **GitHub Copilot training-data lawsuits:** while focused on the
  training side rather than inference, these establish that code
  uploaded to inference services can become entangled with model
  training in ways the user cannot retract.
- **Italian data protection authority vs OpenAI (2023):** ChatGPT
  was temporarily banned in Italy over GDPR compliance issues
  including data minimisation and lawful basis for processing. The
  case ended with operational changes but established that
  data-protection regulators view LLM use as in scope.

These are illustrative, not comprehensive. The pattern is
consistent: organisations underestimate what employees paste into
LLM interfaces, regulators hold them accountable, providers offer
post-hoc fixes that don't undo the original disclosure.

## 4. Regulatory landscape (selected, 2026)

Without claiming legal exhaustiveness, the regulatory frameworks
that touch tooling-script generation workflows include:

- **GDPR (EU):** lawful basis required for processing personal data;
  cross-border transfer requires SCCs or adequacy; data minimisation
  principle ("only the data needed for the purpose") makes pasting
  whole files into an LLM legally risky if it includes identifiers;
  automated decision-making provisions when the LLM output drives
  consequential action.
- **HIPAA (US healthcare):** PHI cannot be disclosed to a
  non-covered third party without a Business Associate Agreement.
  The major LLM providers offer BAAs at higher tiers; consumer use
  generally does not have one.
- **SOX (US public companies):** internal control requirements over
  financial reporting; LLM use in scripts that touch financial data
  needs documented controls and data-handling agreements.
- **CMMC (US defence supply chain):** controlled unclassified
  information cannot leave authorised environments; LLM API calls
  generally violate this without special arrangements.
- **EU AI Act:** risk classification depends on use; LLM-as-tooling
  for regulated decisions can fall into limited-risk or high-risk
  categories with documentation and oversight obligations.
- **Sector-specific:** PCI DSS for cardholder data, FERPA for
  education records, GLBA for consumer financial data, and dozens
  of state and provincial laws each impose data-handling
  constraints that cloud LLM use can violate without obvious
  signs.

The common thread: most regulatory regimes were not written with
LLM-mediated workflows in mind, but their data-handling principles
clearly apply. "I just asked an AI to write a script" is not a
defence under any of them.

## 5. The local-LLM mitigation

### 5.1 What it changes about the threat model

Running a locally-hosted LLM (in our case, a fine-tuned 7B Sigil
writer running via ollama on the user's own hardware) eliminates
the network channel entirely for the inference itself. The threat
model collapses to the following local-only concerns:

- The local process can read files the user grants it
- The generated script can read/write files the user runs it on
- The local model weights and adapters are stored on disk

These are the same concerns the user already accepts when running
any local script. They do not extend to a third party.

What is *not* eliminated by local inference:

- The user might still copy data into a cloud service for other
  reasons (web searches, documentation lookup, version control
  pushes)
- The local model was itself trained on data that may have
  included internet-scraped sources; this is an upstream concern
  but not a present-tense leakage
- The local hardware is still subject to seizure, lawful search,
  or compromise — but these are local-process concerns, not
  data-in-transit concerns

### 5.2 What local inference does not solve

This paper is careful not to overclaim. Local inference does not:

- **Make the AI smarter.** A 7B local model is less capable than a
  cloud frontier model. The trade is correctness for confidentiality.
- **Eliminate provenance questions** about the model weights or
  training data
- **Substitute for governance.** A local pipeline still needs the
  same access controls, audit logs, and oversight as any other
  data-processing pipeline
- **Address every leakage vector.** If users still paste sensitive
  data into a cloud LLM elsewhere, the local-tool win evaporates

### 5.3 The specific mitigation in this work

The Sigil-fine-tuned 7B + RAG + interpreter-validate-and-retry
pipeline is a closed local loop:

1. The agent calls the local ollama HTTP endpoint with the task
   description. No network egress.
2. The local 7B writes a Sigil program. The RAG retrievals come
   from a local vector index. No network egress.
3. The Sigil program is validated by running it in the local
   interpreter with sample inputs. No network egress.
4. If validation fails, the retry loop sends the previous attempt
   plus the interpreter's error message back to the local model.
   No network egress.

Every step happens inside the host process boundary the user
already trusts. The information that previously leaked to a
cloud provider stays on the machine.

For the deployment study being prepared in Stream C of the
research plan, this mitigation will be measured against:

- The accuracy cost vs cloud LLM equivalents
- The latency cost vs cloud LLM equivalents
- The hardware cost amortised over expected workload

The hypothesis under test is that the accuracy and latency costs
are tolerable for many tooling workflows, and the confidentiality
benefit is decisive for the workflows that need it.

## 6. Where the local approach is necessary, where it is sufficient,
where it is neither

### 6.1 Necessary (cloud is unsafe)

- Healthcare workflows touching PHI without a BAA in place
- Financial workflows under SOX where audit trail of data
  handling matters
- Defence / national security work under CMMC or higher
- Legal work where attorney-client privilege might attach
- Personal data processing under GDPR where data minimisation
  cannot be satisfied with cloud calls
- Active incident response where the data being analysed is
  itself the incident

### 6.2 Sufficient (cloud is acceptable but local is better)

- Open-source contributor workflows where the code is public
  anyway — local saves cost and energy, but cloud doesn't risk
  much
- Personal scripting where the user accepts the cost / privacy
  trade-off consciously
- Educational / experimental work

### 6.3 Neither (local is not enough)

- Workflows that need frontier-model accuracy AND touch sensitive
  data — there is no clean answer; the user must choose between
  accuracy and confidentiality
- Multi-organisation collaborations where data sharing is
  required by the workflow (the cloud is just one of several
  exposures)
- Tasks that intrinsically need access to up-to-date external
  information (web search, API documentation lookup)

## 7. What the deployment study should measure

The Stream C deployment study should produce, for each task in
the test set:

- Whether local Sigil generates a correct program
- Whether the cloud equivalent generates a correct program
- The accuracy delta
- The information that *would have* been disclosed to a cloud
  provider under the cloud path (with concrete examples)
- The dollar cost saved
- The energy cost saved
- A categorical privacy assessment ("would this task description
  trigger HIPAA / GDPR / CMMC concerns if sent to a cloud
  provider?")

This makes the confidentiality argument concrete rather than
abstract: not "local is more private" in general, but "for these
specific 30-50 tasks pulled from your real shell history, the
cloud path would have leaked the following 47 distinct categories
of identifiable information."

## 8. Open questions

These remain unresolved and should be flagged in any deployment
recommendation:

1. **Trust in the model itself.** A locally-hosted model is not
   adversarial in the data-leakage sense, but it might generate
   code that does something other than what the user asked
   (e.g., a script that exfiltrates data through some indirect
   channel). Mitigation: human review of generated scripts before
   running on sensitive data.
2. **Supply chain of model weights.** The Qwen2.5-Coder-7B base
   was downloaded from Hugging Face. The provenance of the
   weights matters for high-assurance environments. Mitigation:
   reproducible builds, signed releases, in-house training for
   highest-assurance use.
3. **Adapter portability.** The fine-tuned LoRA is small (~100MB
   GGUF) and easily shared. Sharing the adapter without the
   training corpus is fine; sharing the corpus might leak the
   contents of the original task descriptions used to generate
   it. Audit the corpus before publication.
4. **Attack surface of ollama itself.** The local serving
   infrastructure is a process running on the host. It needs the
   same hardening as any other service: localhost-only binding,
   no exposed ports, periodic updates.

## 9. Summary

Cloud LLM use for host-tooling-script generation transmits
substantial information about the user's host, code, intent, and
data to a third party on every call. This is a defensible
trade-off in some contexts and an unacceptable one in others. The
contexts where it is unacceptable include several large regulated
industries and most workflows touching personal data, IP, or
classified material.

A locally-hosted LLM specialised for the target language —
demonstrated in this work by a fine-tuned 7B Qwen producing Sigil
on consumer AMD hardware — closes the network channel entirely
for the inference itself. This is not a free win: local accuracy
trails cloud frontier models by a measurable margin. The
deployment question is whether the accuracy gap is small enough,
and the confidentiality gap large enough, that the trade is
worth making for a given workflow.

The accompanying deployment study will measure both gaps
explicitly so the trade can be evaluated, not merely advocated.

## 10. References (provisional, to be expanded)

- Anthropic Privacy Policy and API Terms of Service (2025-2026
  versions)
- OpenAI Enterprise Privacy and API Data Usage policies
- Google Cloud AI / Gemini terms (consumer and enterprise variants)
- ABA Formal Opinion 512 (2024) on Generative AI use by lawyers
- HHS HIPAA Business Associate guidance for AI services
- EU AI Act, Regulation 2024/1689
- Italian Garante decision on ChatGPT, March 2023
- Samsung internal memo on ChatGPT use, May 2023 (as reported)
- NIST AI Risk Management Framework, AI RMF 1.0 (2023)

(Final paper version: each citation expanded with publication date,
URL, and the specific provision invoked.)
