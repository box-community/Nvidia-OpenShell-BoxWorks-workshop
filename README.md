# Context-Aware Agents with NVIDIA Nemotron

> **For the cleaner, step-by-step view, open [`docs/workshop-walkthrough.html`](docs/workshop-walkthrough.html) in your browser.**
> It has the same steps as this README, with copy buttons on every command and a progress tracker.
> On a Mac: `open docs/workshop-walkthrough.html`. Or download the repo and double-click the file.

Build an agent that answers questions from Box content, cites its sources, and only uses files the person asking is allowed to see. You run one stage at a time and see exactly what each one does.

Box files → Parse → Chunk → Embed → Search → Rerank → Answer → Agent

---

# Get set up

## Step 0: Before you start

You need Python 3.10 or newer and a copy of the workshop repo. No GPU, and nothing to install for the core steps. Run every command from the repo folder.

*Run:*

```bash
cd boxworks-workshop
PYTHONPATH=src python3 -m unittest discover -s tests
```

The last line should say `OK`.

### Get your NVIDIA API key

Several steps compare a local stand-in with the real NVIDIA model. To use the real ones, you need a free NVIDIA API key:

1. Go to [build.nvidia.com](https://build.nvidia.com/) and sign in, or create an NVIDIA account if you don't have one.
2. Open any model page and choose **Get API Key**, then generate a key.
3. Copy the key. It starts with `nvapi-`. Store it somewhere safe, because you may not be able to see it again.

Then set it in the same terminal you run the commands in. Without it, everything still runs offline.

*Run:*

```bash
export NVIDIA_API_KEY="nvapi-..."   # your key from build.nvidia.com
export NVIDIA_USE_REMOTE=1
```

> Keep keys in your terminal only. Don't paste them into chat, documents or code. Every command prints `mode: REMOTE` or `mode: OFFLINE` so you always know which models ran.

---

## Step 1: Connect to Box

**Concepts**

- **Service account**: A Box app signs in as its own user, an `AutomationUser_…@boxdevedition.com` account. The code sees only what that account owns or has been invited to.
- **Client Credentials Grant**: How the app signs in: a client ID, a client secret and your Box enterprise ID buy a short-lived access token.

Your workshop host gives you these values, or you create your own Box Platform app (see the README's Setup). Set them in your terminal:

*Run:*

```bash
export BOX_CLIENT_ID="..."
export BOX_CLIENT_SECRET="..."
export BOX_ENTERPRISE_ID="..."
```

**Using your own Box?** Create the workshop folder once. It uploads five sample files and sets up two Box groups. Skip this if your host already gave you a folder ID.

*Run once:*

```bash
PYTHONPATH=src python3 -m akf_workshop.box_source.setup_box
```

*What it creates:*

```text
Context-Aware Agents Workshop/
  docs/           shared with group workshop-attendees
  data/           shared with group workshop-attendees
  support-leads/  shared with group support-leads
    enterprise-support-policy.md
    support_cases.csv

Done. Use this folder:
  export BOX_FOLDER_ID=429759160477
```

Point the workshop at the folder. From now on, every step reads from Box.

*Run:*

```bash
export BOX_FOLDER_ID=429759160477   # or the ID printed for your folder
```

> To go back to the local sample files at any point, run `unset BOX_FOLDER_ID`. Every step works either way.

---

# Ingest

## Step 2: See the files and who can read them

**Concepts**

- **Collaboration**: An invitation to a Box file or folder, for a user or a group. It's how Box decides who can read what.
- **Inheritance**: Box permissions flow down: anyone invited to a folder can read everything inside it. That's why the two restricted files live in their own `support-leads/` folder.
- **ACL**: Access control list: the users and groups allowed to read one file. The code builds it from Box's collaborations and attaches it to the file.

*Run:*

```bash
PYTHONPATH=src python3 -m akf_workshop.walkthrough files
```

*You'll see (shortened):*

```text
source: Box folder 429759160477 (live Box API)

box-ai-retrieval.md  (text/markdown)
   file_id: box-2541404399963   version: v2820326649563   labels: ['docs']
   allowed: user AutomationUser_…, …, group workshop-attendees  ->  you can see it
enterprise-support-policy.md  (text/markdown)
   file_id: box-2541403348737   version: v2820325281537   labels: ['support-leads']
   allowed: user AutomationUser_…, …, group support-leads  ->  hidden from you
```

### What to look for

- `source:` says *live Box API*. The IDs and versions are Box's own.
- You're `dev@example.com` in the group `workshop-attendees`. Two files say *hidden from you*, because only the `support-leads` group was invited to their folder.
- The permissions are attached to each file now, and they travel with it through every later step.

Code: `src/akf_workshop/box_source/box_api.py`

---

## Step 3: Parse files into sections

**Concepts**

- **Section**: A heading plus the text under it. Search works on pieces like this, not on whole files.
- **Layout model**: Text files can be split by their headings. A PDF page or an image is only pixels, so a model has to find the title, paragraphs and tables. That's what **Nemotron Parse** does.

*Run:*

```bash
PYTHONPATH=src python3 -m akf_workshop.walkthrough parse
```

The 5 files become 11 sections in total. Markdown splits at each `#` heading, and each CSV becomes one summary:

| File | Sections | Why |
|---|---|---|
| `box-ai-retrieval.md` | 3 | 3 headings |
| `supply-chain-risk-playbook.md` | 3 | 3 headings |
| `enterprise-support-policy.md` | 3 | 3 headings |
| `accounts.csv` | 1 | one summary per CSV |
| `support_cases.csv` | 1 | one summary per CSV |
| **All files** | **11** |  |

### Now parse an image with Nemotron Parse hosted

Needs the API key from Step 0 and two small libraries:

*Run:*

```bash
pip install "pypdfium2>=5" "Pillow>=10"
PYTHONPATH=src python3 -m akf_workshop.walkthrough parse --file tests/fixtures/response_targets.png
```

*You'll see:*

```text
response_targets.png   [text]   22 words  heading: p1: Support Response Targets
response_targets.png   [table]  41 words  heading: p1: Support Response Targets

--- [table] p1: Support Response Targets
| **Priority** | **Initial response** | **Escalate to lead after** |
|---|---|---|
| P1 | 15 minutes | 30 minutes |
| P2 | 2 hours | 4 hours |
| P3 | 1 business day | 2 business days |
```

See where the model found each part. `--show` draws its boxes onto a *copy* of the image:

*Run:*

```bash
PYTHONPATH=src python3 -m akf_workshop.walkthrough parse --file tests/fixtures/response_targets.png --show boxes.png
open boxes.png
```

- The table comes back as a real table, every row and column in place, not a jumble of words.
- Your original image never changes. The boxes go into `boxes.png`.
- If you see a "busy" message, NVIDIA's endpoint had a hiccup. Wait a minute and run it again.

---

## Step 4: Cut sections into chunks

**Concepts**

- **Chunk**: A piece of at most 120 words. Small pieces make search precise. Each chunk keeps its file, Box version and permissions. A table is never split, so a row is never separated from its header.

*Run:*

```bash
PYTHONPATH=src python3 -m akf_workshop.walkthrough chunk
```

*You'll see (shortened):*

```text
box-2541404399963:0001   69 words  box-ai-retrieval.md            Box AI Retrieval Evaluation
box-2541404399963:0002   48 words  box-ai-retrieval.md            Chunking Guidance
box-2541403348737:0008   47 words  enterprise-support-policy.md   Escalation

11 sections -> 11 chunks.   (totals across all 5 files)
```

Each line is one chunk:

| Part | Example | Meaning |
|---|---|---|
| Chunk ID | `box-2541404399963:0001` | The Box file ID, then the chunk's position in the list |
| Length | 69 words | How long the chunk is. The limit is 120, so this one wasn't split. |
| File | `box-ai-retrieval.md` | The Box file it came from |
| Heading | Box AI Retrieval Evaluation | The section it came from |

- In Step 3 the same section was 65 words. Each chunk starts with its section's heading, so it carries that context into search: 65 + 4 heading words = 69.
- A section longer than 120 words would become several chunks. Every section here is short, which is why 11 sections give 11 chunks.
- A chunk ID is the Box file ID plus a position. Answers cite these IDs later.
- Restricted chunks are in the list too. Permissions are checked when someone searches, not here.

---

## Step 5: Turn text into vectors

**Concepts**

- **Embedding**: A list of numbers (a vector) that captures what a piece of text means. Texts with similar meanings get similar vectors.
- **Cosine similarity**: How close two vectors point: 1.0 is the same direction, near 0 is unrelated.
- **Model**: **Nemotron 3 Embed 1B** (`nvidia/nemotron-3-embed-1b`), hosted by NVIDIA. Offline, a simple word-hashing stand-in is used.

*Run:*

```bash
PYTHONPATH=src python3 -m akf_workshop.walkthrough embed
```

It compares three sentences. 1 and 2 mean the same thing in different words, and 3 is unrelated:

| Pair | Offline (word hashing) | Nemotron Embed |
|---|---|---|
| 1 vs 2, same meaning | +0.18 | **+0.59** |
| 1 vs 3, unrelated | −0.14 | +0.06 |
| 2 vs 3, unrelated | +0.10 | +0.03 |
| Numbers per vector | 64 | 2,048 |

- Offline only shared words count, so the paraphrase barely stands out. The real model recognises it.
- Try your own: `... walkthrough embed "first sentence" "second sentence"`

---

# Answer a question

## Step 6: Search, with permissions first

**Concepts**

- **Vector search**: Embed the question, then find the chunks whose vectors are closest. Fast, but only roughly right.
- **Filter before ranking**: Chunks you can't see are removed *before* anything is scored, so restricted text can never leak into results.

With no question given, the default is *"How should the workshop evaluate retrieval quality?"*. To ask your own, put it in quotes at the end.

*Run:*

```bash
PYTHONPATH=src python3 -m akf_workshop.walkthrough search
PYTHONPATH=src python3 -m akf_workshop.walkthrough search "When should enterprise incidents be escalated?"
```

*Offline (word hashing):*

```text
mode: OFFLINE (local fallbacks; no network)
permission filter: 7 of 11 chunks are visible to you; the rest are never scored.

 1. vector +0.352  supply-chain-risk-playbook.md   Recommended Action      <- wrong document
 2. vector +0.207  supply-chain-risk-playbook.md   Workshop Scope
 3. vector +0.184  accounts.csv                    CSV table
 4. vector +0.086  box-ai-retrieval.md             Citation Contract
 5. vector +0.049  box-ai-retrieval.md             Box AI Retrieval Evaluation
 ...
```

Now run the same command with the NVIDIA key from Step 0 set:

*Online (Nemotron Embed):*

```text
mode: REMOTE (hosted NVIDIA models are used where available)
permission filter: 7 of 11 chunks are visible to you; the rest are never scored.

 1. vector +0.432  box-ai-retrieval.md             Box AI Retrieval Evaluation   <- right document
 2. vector +0.235  supply-chain-risk-playbook.md   Workshop Scope
 3. vector +0.155  box-ai-retrieval.md             Chunking Guidance
 4. vector +0.075  box-ai-retrieval.md             Citation Contract
 5. vector +0.039  supply-chain-risk-playbook.md   Support Risk Playbook
 ...
```

- Offline, the top hit is the playbook, which is the wrong document: it just shares a few words with the question. With Nemotron Embed, `box-ai-retrieval.md`, the document that actually answers it, comes first.
- The permission filter is the same in both: 7 of 11. Better models change the ranking, never what you're allowed to see.
- Without quotes around your question you'll get `unrecognized arguments`.

---

## Step 7: Rerank the candidates

**Concepts**

- **Reranker**: Reads the question *together with* each candidate and scores how well it answers. Slower than vector search, so it only runs on the few candidates search found.
- **Logit**: The reranker's raw score. It can be negative; higher is better.
- **Model**: **Nemotron 3.5 Rerank 8B** (`nvidia/nemotron-3.5-rerank-8b`), hosted. Offline, a word-overlap stand-in is used.

*Run:*

```bash
PYTHONPATH=src python3 -m akf_workshop.walkthrough rerank
```

*You'll see (online):*

```text
AFTER (reranked, top 4 kept):
 1. rerank  -2.36 (hosted)  box-ai-retrieval.md            Box AI Retrieval Evaluation
 2. rerank  -3.28 (hosted)  supply-chain-risk-playbook.md  Workshop Scope
 3. rerank  -3.35 (hosted)  box-ai-retrieval.md            Citation Contract
 4. rerank  -3.58 (hosted)  box-ai-retrieval.md            Chunking Guidance
```

- Compare BEFORE and AFTER: the right document moves to the top.
- The right chunk leads the next one by about 0.9. That lead, and whether the top score clears the threshold, decide the next step.

---

## Step 8: Answer, or refuse

**Concepts**

- **Threshold**: If the best chunk's rerank score is below `-3.1` (online), the evidence is too weak and the status is `insufficient_context`: the agent refuses instead of guessing.
- **Citation**: Each chunk used comes with its Box file, path, version and chunk ID, so every answer can be traced to a real file.

*Run:*

```bash
PYTHONPATH=src python3 -m akf_workshop.walkthrough answer "What must every answer include?"
PYTHONPATH=src python3 -m akf_workshop.walkthrough answer "When should enterprise incidents be escalated?"
```

|  | What must every answer include? | When should incidents be escalated? |
|---|---|---|
| status | `ok` | `insufficient_context` |
| top score | −1.95, above −3.1 | −3.30, below −3.1 |
| gap to 2nd | 1.13, a clear winner | 0.10, all equally weak |

- The escalation answer lives in the support policy, which you can't see. So you're refused. That's correct.
- Each citation's `score` is vector plus rerank. The threshold uses `top score`, the rerank alone.
- Where −3.1 comes from: every golden question that should be answered scored −2.87 or higher, and every one that should be refused scored −3.31 or lower. −3.1 sits between them. Change the documents or the reranker and you need to measure again.

---

## Step 9: Same question, two people

Ask the escalation question again, this time as a member of the Box group `support-leads`:

*Run:*

```bash
PYTHONPATH=src python3 -m akf_workshop.walkthrough --user support-lead@example.com --groups support-leads answer "When should enterprise incidents be escalated?"
```

*You'll see:*

```text
status:          ok
citations:
  enterprise-support-policy.md   box-2541403348737:0008

[box-2541403348737:0008] Escalation
Enterprise incidents with customer impact should be escalated to the support lead within 30 minutes. ...
```

| Who | Top rerank score (online) | Result |
|---|---|---|
| Attendee | −3.30 | Refused: the policy is never searched |
| Support lead | **−1.22** | Answered from the policy, with a citation |

- Nothing in the code knows about "support leads". Box's group on the `support-leads/` folder decides.
- Try it: in Box, invite another group to that folder, then run Step 2 again. The change shows up immediately, because permissions are read live every time.

---

# Agents

## Step 10: Predict who needs help, then cite the policy

The question for this step: **"Which customer is most likely to need help, and what does our policy say to do?"** It needs two kinds of evidence. A *prediction* from tables says who is at risk. A *rule* from a document says what to do. The agent combines both.

**Concepts**

- **Skill**: A tool the agent can run. This agent has two: *retrieval* (Steps 6 to 8) and *prediction*.
- **Kumo Relational**: NVIDIA's hosted model for predictions over database tables. A normal ML model has to be trained for each task. Kumo is pretrained: you send your tables, a few rows already labelled with the answer, and the row you want predicted. It returns a prediction and a probability, with no training step.
- **Rule-based agent**: This agent decides which skills to run by keyword. A question with "predict", "risk", "forecast" or "likely" runs prediction *and* retrieval. No language model is involved (Step 11 adds one).

### The data: two tables in Box

| Account | Tier | Days to renewal | Open cases | Oldest open case |
|---|---|---|---|---|
| Acme Motors (100) | enterprise | 21 | 1 | 4 days |
| **Beacon Health (101)** | enterprise | **8** | **3** (one P1, two P2) | **16 days** |
| Cobalt Retail (102) | business | 45 | 1 | 3 days |
| Delta Finance (103) | enterprise | 14 | 3 | 18 days |

From `data/accounts.csv` (everyone) and `support-leads/support_cases.csv` (support leads only).

### What happens when a support lead asks

*Run:*

```bash
PYTHONPATH=src python3 -m akf_workshop.agent.cli --user support-lead@example.com --groups support-leads ask "Predict support risk and cite the policy."
```

|  | What happens |
|---|---|
| 1 | **Pick skills.** The question says "predict", so the agent runs prediction and retrieval. |
| 2 | **Check permission.** Prediction needs `support_cases.csv`. In Box only the `support-leads` group can read it, so a support lead may continue. |
| 3 | **Predict.** Offline: a simple formula scores each account. Online: the tables go to Kumo. |
| 4 | **Find the policy.** Retrieval finds the *Escalation* section of the support policy. |
| 5 | **Combine.** The answer gives the at-risk account, then the policy text, with citations. |

*You'll see (online):*

```text
"answer": "Kumo Relational predicts high support risk for Beacon Health (account 101),
  probability 0.9998. Policy context: Based on permitted Box context, Enterprise
  incidents with customer impact should be escalated to the support lead within
  30 minutes. If a customer has more than three open priority cases or an unresolved
  case older than 14 days, the account should be marked as elevated risk ...",
"status": "ok"
```

### Offline vs online prediction

| Account | Offline formula score | Risk |
|---|---|---|
| Beacon Health | **1.67** | high, the top one |
| Delta Finance | 1.51 | high |
| Acme Motors | 0.73 | medium |
| Cobalt Retail | 0.21 | low |

The offline formula adds points for open cases, priority cases, case age, enterprise tier and a renewal within 21 days. Online, Kumo returns *high risk for Beacon Health, probability 0.9998*.

### Now ask as an attendee

*Run:*

```bash
PYTHONPATH=src python3 -m akf_workshop.agent.cli ask "Predict support risk and cite the policy."
```

*You'll see:*

```text
"answer": "The prediction data is restricted to support leads.",
"status": "denied"
```

Same question, but you can't read `support_cases.csv` in Box, so no prediction is made. Predictions follow the same permissions as documents.

> This is a demo of *how* to call Kumo, not a real forecast. The labelled examples it receives come from a simple rule (3 or more open cases, or renewal within 14 days), and the account it predicts is always Beacon Health, which those examples already mark as risky. A real version would label examples from history, such as "did this account escalate within 30 days?", and score every account.

- In the JSON, `skill_evidence` shows the data behind the prediction, and `trace` lists the two skills that ran.
- Ask a question without those keywords, like `ask "How should the workshop evaluate retrieval quality?"`, and the trace shows only retrieval ran.

---

## Step 11: A Nemotron agent that chooses its own tools

**Concepts**

- **Tool calling**: The model is told which tools exist. It decides which to call, reads the results, can search again with different words, then writes the answer.
- **Model**: **Nemotron 3.5 Super** (`nvidia/nemotron-3.5-super-vl-120b-a12b`), hosted. Needs the API key from Step 0.
- **Guardrails in code**: Tools run as the person asking, so permissions can't be bypassed. Weak searches return nothing. An answer only counts if it cites a chunk the tools returned.

*Run:*

```bash
PYTHONPATH=src python3 -m akf_workshop.agent.cli --agent nemotron --user support-lead@example.com --groups support-leads ask "Which account is most at risk, and what does our policy say we should do?"
```

*You'll see (wording varies):*

```text
"answer": "Beacon Health (account 101) is predicted to have the highest support risk,
  with a probability of 0.9998. Per the enterprise support policy, enterprise incidents
  with customer impact should be escalated to the support lead within 30 minutes
  [box-2541403348737:0008]. ...",
"status": "ok",
"agent": "nemotron"
```

- In the `trace`, find the turn where the model called **both** tools at once. No rule told it to.
- Now ask the same question without `--user` and `--groups`. The prediction is denied by the code, and the model explains that and answers from what you *can* see.
- Each model turn takes about 1 to 8 seconds. If the trace shows `llm_retry` or `"agent": "rule-based-fallback"`, NVIDIA's endpoint was busy and the safety net kicked in.

---

## Step 12: Measure it, then change one thing

So far you've judged answers by eye. An **eval** checks many questions at once, so you can change something and see what got better or worse. Each experiment below is one command. Have the NVIDIA key from Step 0 set.

**Concepts**

- **Golden question**: A question with a known right outcome: which file should be found, and whether the agent should answer or refuse. The set used here is in `src/akf_workshop/evals/golden_questions_search.json`.
- **PASS / FAIL**: Did the agent answer when it should, and refuse when it should?
- **recall@3**: Was the right file in the top 3 results? 1.00 means yes.

### Run the eval

*Run:*

```bash
PYTHONPATH=src python3 -m akf_workshop.evals.run_eval --summary \
  --golden src/akf_workshop/evals/golden_questions_search.json
```

*You'll see (shortened):*

```text
PASS  recall@3 1.00  ok                     support-lead  How fast must a priority one ticket get a first reply?
PASS  recall@3 1.00  ok                     dev           How big should chunks be?
PASS  recall@3 0.00  insufficient_context   dev           What is the warranty on the HX-9000 curing light?

10 of 10 status checks passed · average recall@3 0.90
```

One line per question: the result, recall, what the agent did, who asked, and the question. The HX-9000 line shows recall 0.00 even though refusing is right: no document mentions it, so there's no right file to find.

### Try 1: make the agent stricter

Raise the refusal threshold from −3.1 to −2.0. The agent now needs a stronger match before it answers.

*Run:*

```bash
AKF_RERANK_MIN_LOGIT=-2.0 PYTHONPATH=src python3 -m akf_workshop.evals.run_eval --summary \
  --golden src/akf_workshop/evals/golden_questions_search.json
```

*You'll see:*

```text
FAIL  recall@3 1.00  insufficient_context (expected ok)   support-lead  How fast must a priority one ticket get a first reply?
FAIL  recall@3 1.00  insufficient_context (expected ok)   dev           Which account attributes does the model look at?
FAIL  recall@3 1.00  insufficient_context (expected ok)   dev           How big should chunks be?
FAIL  recall@3 1.00  insufficient_context (expected ok)   dev           What is Beacon Health's renewal date?

6 of 10 status checks passed
```

The right file was found every time (recall 1.00), but the agent refused anyway. Too strict, and it turns away questions it could answer.

### Try 2: make the agent looser

*Run:*

```bash
AKF_RERANK_MIN_LOGIT=-4.0 PYTHONPATH=src python3 -m akf_workshop.evals.run_eval --summary \
  --golden src/akf_workshop/evals/golden_questions_search.json
```

*You'll see:*

```text
FAIL  recall@3 0.00  ok (expected insufficient_context)   dev   What is the warranty on the HX-9000 curing light?

9 of 10 status checks passed
```

Now it answers a question no document covers, from unrelated text. Too loose, and it answers questions it can't. That's how confident wrong answers happen. −3.1 sits between the two.

### Try 3: add your own questions

Write a few questions with the outcome you expect. Copy this whole block; it creates `my_questions.json` in the repo folder:

*Run:*

```bash
cat > my_questions.json <<'JSON'
[
  {"question": "What is the response target for a P3 case?",
   "user": "support-lead@example.com", "groups": ["support-leads"],
   "expected_files": ["enterprise-support-policy.md"], "expect_status": "ok"},
  {"question": "What is our refund policy for cancelled subscriptions?",
   "user": "dev@example.com", "groups": ["workshop-attendees"],
   "expected_files": [], "expect_status": "insufficient_context"}
]
JSON
PYTHONPATH=src python3 -m akf_workshop.evals.run_eval --summary --golden my_questions.json
```

*You'll see:*

```text
PASS  recall@3 1.00  ok                     support-lead  What is the response target for a P3 case?
PASS  recall@3 0.00  insufficient_context   dev           What is our refund policy for cancelled subscriptions?

2 of 2 status checks passed
```

Now open `my_questions.json` in your editor and change it: reword a question, swap who asks (try the P3 question as `dev@example.com` with group `workshop-attendees`; it should become a refusal), or add a question you think will trip it up. Run the last command again after each change.

---

# Agent security

## Step 13: Why run agents in a secure runtime

Until now the agent only *read*. Real agents also act: they write reports, edit files and delete things. An agent that can delete can delete the wrong thing, because it misread a request, followed a malicious instruction hidden in a document, or simply made a mistake. These steps run the agent's actions inside **OpenShell**, a secure runtime with rules the agent can't change.

**Concepts**

- **OpenShell**: NVIDIA's secure runtime for agents. It runs each agent's work in its own isolated environment, a small virtual machine (MicroVM), and decides, request by request, what may leave it. The agent can't change those rules. OpenShell's commands call each environment a *sandbox*, which is why you'll see `openshell sandbox …` below.
- **Network policy**: Rules on outgoing HTTP requests: which program may call which host, with which method and path. A **deny** rule beats any allow. Here: "Box Mount may sync with Box, but no `DELETE /2.0/files/*`."
- **Credential placeholder**: The real Box token stays with OpenShell, outside the agent's environment. Inside, programs only see a placeholder that OpenShell swaps for the token on approved requests. The agent can't read or leak it.
- **Box Mount**: Keeps a local folder in sync with a Box folder. The agent edits ordinary files; Box Mount uploads changes and asks Box to delete removed files.

![Box Mount traffic through OpenShell. Left, the agent's Linux MicroVM: the Codex agent reads and writes the local workspace /sandbox/box; Box Mount syncs it and holds only a token placeholder; the OpenShell runtime intercepts its outbound traffic. Right, the trusted Mac host: the OpenShell gateway holds the operator-managed policy and the Box credentials; the OpenShell supervisor checks the executable and destination, enforces HTTP method and path, and injects the Box token only if permitted. Allowed requests reach the Box API over HTTPS, so the report upload succeeds. A DELETE is blocked with 403 policy_denied and never reaches Box, so the cloud copy is preserved.](docs/images/openshell-box-mount-flow.png)

*Shown with Codex as the agent. With the Nemotron agent (Step 15, option A), the model runs on your laptop and only its file actions run inside the MicroVM; everything to the right is the same.*

> Two separate controls. Inside OpenShell, the **filesystem** lets the agent delete its local copy. The **network policy** stops that deletion from reaching Box. This demo shows the second one.

---

## Step 14: Set up OpenShell, Box Mount and the deletion guard

A one-time setup on your Mac (Apple silicon), following [NVIDIA's OpenShell docs](https://docs.nvidia.com/openshell/latest/about/overview). Run every command from the workshop repo folder. The files it uses are in the repo's `openshell/` folder.

### 14a · Install OpenShell

**Before you start:** the installer uses [Homebrew](https://brew.sh), and Homebrew needs current Apple Command Line Tools. Update them first in System Settings → General → Software Update.

*Mac terminal:*

```bash
curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh
```

The installer uses Homebrew to install the `openshell` command and the **gateway**, OpenShell's background service on your Mac. The gateway holds the policies and credentials and runs the agent environments. It registers the gateway as `openshell` at `https://localhost:17670`.

On a Mac without Docker, the installer ends with `local gateway listener did not become reachable`, and its log says `no compute driver configured`. That's expected: the gateway doesn't know how to run agent environments yet. The next step fixes it.

> If the installer stops with `Error: Your Command Line Tools are too outdated`, OpenShell wasn't installed. Update the tools and run the installer again. If Software Update shows nothing, reinstall them, then click **Install** in the window that opens and wait for it to finish:
>
> *Mac terminal:*
>
> ```bash
> sudo rm -rf /Library/Developer/CommandLineTools
> sudo xcode-select --install
> ```
>
> Homebrew may also print "tap trust" warnings about other taps you have installed. Those are unrelated and safe to ignore.

### 14b · Run agent environments as MicroVMs

Each agent environment should be its own small Linux virtual machine with no network device of its own, so every request goes through OpenShell. That's the MicroVM runtime. OpenShell never turns it on by itself, so you set it in the gateway's settings and restart the gateway.

*Mac terminal · Set it up · run once:*

```bash
mkdir -p ~/.config/openshell
cp openshell/gateway.toml ~/.config/openshell/gateway.toml
brew services restart openshell
```

The gateway takes about 10 seconds to start after a restart. Then check it:

*Mac terminal · Check · safe to repeat:*

```bash
openshell gateway info
```

*You'll see:*

```text
Gateway: openshell
Server: https://localhost:17670
Status: healthy
Version: 0.1.5
Compute drivers:
  vm
    Driver name: openshell-driver-vm
```

> **Seeing `Connection refused`?** The gateway is still starting. Wait 10 seconds and run only the check again. Don't re-run the set-up block: each run restarts the gateway, so the check will always be too early.

If `openshell --version` shows an older version than 0.1.5, another copy of `openshell` comes first on your PATH. Run Homebrew's directly as `/opt/homebrew/bin/openshell`.

### 14c · Create the agent's environment

OpenShell calls each agent environment a *sandbox*. Create one called `box-agent`; it starts from a standard Ubuntu 24.04 image.

*Mac terminal:*

```bash
openshell sandbox create --name box-agent --detach
openshell sandbox get box-agent
```

Wait until the phase is `Ready`.

### 14d · Give OpenShell the Box token

The token stays with OpenShell on your Mac. The *provider profile* says which program may use it (`/sandbox/box-mount`) and for which hosts (`api.box.com`, `upload.box.com`). Inside the environment, programs only ever see a placeholder.

*Mac terminal:*

```bash
openshell profile lint -f openshell/box-provider.yaml
openshell profile import -f openshell/box-provider.yaml

# needs BOX_CLIENT_ID, BOX_CLIENT_SECRET and BOX_ENTERPRISE_ID from Step 1
PYTHONPATH=src python3 -m akf_workshop.box_source.openshell_token --sandbox box-agent
```

The script gets a token from Box on your Mac, stores it in an OpenShell provider called `box-token`, and attaches it to `box-agent`. Tokens last about an hour: run it again to refresh, then restart Box Mount.

### 14e · Install and start Box Mount

Box Mount isn't included in this repo: get the build from your workshop host (or Box) and put its folder, `Box Mount Build 2026-09-14/`, in the repo folder. It's a Linux program, so it runs inside the environment. Use the `aarch64` build on Apple silicon.

*Mac terminal · Install:*

```bash
tar -xzf "Box Mount Build 2026-09-14/box-mount-0.6.0-linux-aarch64.tar.gz" -C /tmp
openshell sandbox upload box-agent /tmp/box-mount /sandbox/box-mount --no-git-ignore
openshell sandbox upload box-agent openshell/configure-box-mount.sh /sandbox/configure-box-mount.sh --no-git-ignore
openshell sandbox exec -n box-agent --no-login-shell -- chmod +x /sandbox/box-mount
openshell sandbox exec -n box-agent --no-login-shell -- /bin/sh /sandbox/configure-box-mount.sh
```

The last command should say *Configured Box Mount with an OpenShell placeholder, not a real token.* Box Mount also downloads files from Box's file servers, so allow those, read-only:

*Mac terminal · Allow downloads:*

```bash
openshell policy update box-agent --rule-name box-mount-downloads --binary /sandbox/box-mount \
  --add-endpoint public.boxcloud.com:443:read-only:rest:enforce --wait
openshell policy update box-agent --rule-name box-mount-version-check --binary /sandbox/box-mount \
  --add-endpoint cdn07.boxcdn.net:443:read-only:rest:enforce --wait
```

Now mount a Box folder that holds **only what the agent may change**. Create one from the command line: it makes *Agent Workspace* with a `Reviewed` folder inside, and prints its folder ID. Add `--invite` with your Box login email to see it in your own Box.

*Mac terminal · Create the folder:*

```bash
PYTHONPATH=src python3 -m akf_workshop.box_source.setup_box --agent-workspace --invite you@example.com
```

*You'll see:*

```text
folder   Agent Workspace  (id 429885139067)
folder   Agent Workspace/Reviewed  (id 429882316313)
invite   you@example.com as editor: accepted

Done. Mount this folder with Box Mount:
  export AGENT_FOLDER_ID=429885139067
  https://app.box.com/folder/429885139067
```

Copy the `export AGENT_FOLDER_ID=…` line it printed and run it, then mount that folder:

*Mac terminal · Mount:*

```bash
export AGENT_FOLDER_ID=429885139067   # use the ID printed for you
openshell sandbox exec -n box-agent --no-login-shell -- /sandbox/box-mount mount /sandbox/box "$AGENT_FOLDER_ID"
openshell sandbox exec -n box-agent --no-login-shell -- /sandbox/box-mount status
```

Running the create command again is safe: it reuses the folder and the invitation instead of making new ones.

> Box Mount syncs everything its account can see, with no per-person permissions. If you mounted the whole workshop folder, the agent could read the support-leads policy no matter who asked. Keep knowledge in the folder the agent *searches* (Steps 2 to 9, permissions enforced) and give it a separate folder to *change*.

### 14f · Add the deletion guard

Two updates: create the rule, then add the deny to it. A deny beats any allow, including the provider's read-write access.

*Mac terminal:*

```bash
openshell policy update box-agent --rule-name box-delete-guard --binary /sandbox/box-mount \
  --add-endpoint api.box.com:443:read-only:rest:enforce --wait

openshell policy update box-agent --rule-name box-delete-guard --binary /sandbox/box-mount \
  --add-deny 'api.box.com:443:DELETE:/2.0/files/*' --wait

openshell sandbox get box-agent --policy-only
```

*Look for this rule:*

```text
box-delete-guard:
  endpoints:
    - host: api.box.com
      port: 443
      protocol: rest
      enforcement: enforce
      access: read-only
      deny_rules:
        - method: DELETE
          path: /2.0/files/*
  binaries:
    - path: /sandbox/box-mount
```

- The rule names one program, one host, one method and one path pattern. Everything else Box Mount does, like uploads, still works.
- It's the explicit `DELETE` deny that blocks deletion. `access: read-only` alone doesn't, because the provider still grants read-write.
- The agent has no way to change this policy. Only someone with the `openshell` command on the Mac can.

---

## Step 15: Let the agent work

Pick your agent. Both act on the same folder inside OpenShell, so the same policy applies to both.

### Option A: the Nemotron agent from Step 11

Its brain stays on your laptop. Add `--sandbox` and `--workspace` and it gets four file tools (list, read, write, delete), and every one runs *inside* OpenShell through `openshell sandbox exec`. It never sees the Box token.

*Mac terminal:*

```bash
PYTHONPATH=src python3 -m akf_workshop.agent.cli --agent nemotron \
  --user support-lead@example.com --groups support-leads \
  --sandbox box-agent --workspace /sandbox/box \
  ask "Find which account is most at risk and what our policy says to do, then write a short review to Reviewed/beacon-risk-review-YOURNAME.md with citations. Don't touch other files."
```

*What we saw:*

```text
tool predict_support_risk                          ok
tool search_documents  "account at risk support policy what to do"   ok
tool write_workspace_file  Reviewed/beacon-risk-review.md  <985 characters>  ok
  "Written to the local workspace. Box Mount uploads it to Box; delivery is not verified by this tool."
```

- One model turn chose prediction and search, then wrote a cited review. Use your own filename: the tool refuses to overwrite.
- The tool says what it knows (the local write) and what it doesn't (whether Box received it). You check Box yourself.
- Paths are confined to the workspace: `../`, absolute paths and hidden files like Box Mount's config are refused.

### Option B: Codex inside OpenShell

> **Where each command runs.** Blocks labelled *Mac terminal* go in a terminal on your Mac, in the workshop repo folder. Blocks labelled *Paste into Codex* go into Codex, which runs inside OpenShell. Codex can't run the Mac commands: inside OpenShell there's no Python, no Box token and no network access to Box, on purpose.

Codex runs entirely inside the MicroVM, with its own approval prompts on top of OpenShell's rules. Set it up once:

*Mac terminal · 1 · Install Codex in the environment:*

```bash
curl -L -o /tmp/codex-package.tar.gz \
  https://github.com/openai/codex/releases/download/rust-v0.162.1/codex-package-aarch64-unknown-linux-musl.tar.gz
openshell sandbox upload box-agent /tmp/codex-package.tar.gz /sandbox/codex-package.tar.gz --no-git-ignore
openshell sandbox exec -n box-agent --no-login-shell -- tar -xzf /sandbox/codex-package.tar.gz -C /sandbox
openshell sandbox exec -n box-agent --no-login-shell -- /sandbox/bin/codex --version
```

That's OpenAI's official Codex package for Linux on arm64. It should print `codex-cli 0.162.1`.

*Mac terminal · 2 · Let Codex, and only Codex, reach OpenAI:*

```bash
for host in api.openai.com auth.openai.com chatgpt.com ab.chatgpt.com; do
  openshell policy update box-agent --rule-name "codex_${host//./_}" --binary /sandbox/bin/codex \
    --add-endpoint "$host:443:read-write:rest:enforce" --wait
done
```

Each rule names `/sandbox/bin/codex`, so no other program in the environment can use these hosts. Box Mount's rules, and the deletion guard, are unchanged.

*Mac terminal · 3 · Sign in to Codex:*

```bash
openshell sandbox exec -n box-agent --tty --no-login-shell -- /sandbox/bin/codex login --device-auth
```

Open the link it prints in your browser and enter the one-time code. Your Codex account and your Box account don't need to match. The Box token is never given to Codex.

*Mac terminal · 4 · Start Codex in the workspace:*

```bash
openshell sandbox exec -n box-agent --tty --no-login-shell --workdir /sandbox/box/Reviewed -- \
  /sandbox/bin/codex --no-daemon --sandbox workspace-write --ask-for-approval on-request --cd /sandbox/box/Reviewed
```

Paste into Codex:

*Paste into Codex:*

```bash
List the files in /sandbox/box/Reviewed.

Write a short note to /sandbox/box/Reviewed/codex-note-YOURNAME.md that describes
each file you found in one sentence. If a risk review is there, add a three-step
action plan based on it.
If this output already exists, stop; do not overwrite it.

Do not change or delete any other file.
Do not inspect credentials, change policy, install tools, or contact people.
Report when the local write completes. Do not claim delivery to Box without verification.
```

Codex asks before running commands. Approve only the ones that read the folder and write your note.

When you quit, Codex suggests `codex resume <id>`. Codex lives inside OpenShell, not on your Mac, so typing that on your Mac gives `command not found`. Resume through OpenShell instead:

*Mac terminal · Resume a Codex session:*

```bash
openshell sandbox exec -n box-agent --tty --no-login-shell --workdir /sandbox/box/Reviewed -- \
  /sandbox/bin/codex --no-daemon --sandbox workspace-write --ask-for-approval on-request \
  --cd /sandbox/box/Reviewed resume   # add the session ID, or pick from the list
```

**Then check Box.** Open your Agent Workspace folder in Box (the link `setup_box` printed) and refresh. The new report is in `Reviewed`: the upload was allowed by the policy.

---

## Step 16: Watch the policy hold

Now ask the agent to delete something. Use a **disposable** file that exists both in the workspace and in Box.

### 16a · Make a disposable file

Create it inside OpenShell. Box Mount uploads it to Box within a few seconds, so it exists in both places.

*Mac terminal:*

```bash
openshell sandbox exec -n box-agent --no-login-shell -- /bin/sh -c \
  'echo "Disposable file for the deletion test." > /sandbox/box/Reviewed/delete-me-demo.txt'
```

Open `Reviewed` in your Agent Workspace folder in Box and refresh: the file appears within a few seconds. Open it and note its **file ID**, the number at the end of its URL, `https://app.box.com/file/FILE_ID`.

Create the file this way rather than uploading it through Box. Box Mount picks up new files from Box only every couple of minutes, and may skip files added by its own account.

### 16b · Ask the agent to delete it

*Mac terminal · Nemotron agent:*

```bash
PYTHONPATH=src python3 -m akf_workshop.agent.cli --agent nemotron \
  --sandbox box-agent --workspace /sandbox/box \
  ask "Delete only Reviewed/delete-me-demo.txt. Report the local result separately from Box."
```

*What we saw:*

```text
tool list_workspace                                       ok
tool delete_workspace_file  Reviewed/delete-me-demo.txt   ok

"Local result: Reviewed/delete-me-demo.txt was deleted from the local workspace successfully.
 Box result: Unknown. Box Mount will request deletion from Box, but policy may block it;
 the tool does not have knowledge of the Box-side outcome."
```

*Or paste into Codex:*

```bash
Delete only the disposable local file
/sandbox/box/Reviewed/delete-me-demo.txt.

Do not touch any other file, change policy, or try another deletion method.
Report the local deletion result separately from whether Box Mount can
propagate the deletion to Box. Do not claim a remote result without evidence.
```

### 16c · Check all three pieces of evidence

Give Box Mount up to a couple of minutes to try the deletion, then:

*Mac terminal · 1 · The local copy is gone:*

```bash
openshell sandbox exec -n box-agent --no-login-shell -- ls /sandbox/box/Reviewed
```

*Mac terminal · 2 · OpenShell denied Box Mount's DELETE:*

```bash
openshell sandbox exec -n box-agent --no-login-shell -- /bin/sh -c \
  'tail -n 3000 /sandbox/.box-mount/logs/box-mount-sync.stderr.log | grep -E "DELETE https:|^Status:|^Code:|^Method:" | tail -4'
```

*You'll see:*

```text
"DELETE https://api.box.com/2.0/files/2542159113336" 403
Status: 403
Code: policy_denied
Method: DELETE
```

**3 · The file is still in Box.** Refresh the folder in Box: `delete-me-demo.txt` is still there, with the same file ID.

| Evidence | Where | What we saw |
|---|---|---|
| Local copy | inside OpenShell | gone: the agent's deletion worked |
| Remote DELETE | Box Mount's log | `403 policy_denied` from OpenShell, for file `2542159113336` |
| Cloud file | Box, in the browser | still there: same file ID, same size |

- The file ID in the DELETE line must match the one from 16a. That's what ties the denial to *this* file.
- A `403` from Box itself about permissions isn't this proof. It must say `policy_denied`.
- A `401` or `credential_unavailable` means the Box token expired: run the token script from 14d again. That's authentication, not the policy.
- If the agent reports `llm_rate_limited` or `status: error`, NVIDIA's endpoint was busy. Check the trace for what was done, wait a moment and ask again.
- **Leave the guard on afterwards.** Box Mount keeps retrying a pending deletion, and removing the rule would let it through.

> **What this shows, precisely.** The agent was allowed to create and sync its report and to delete its local copy, but not to delete anything in Box. The model never held the Box token and couldn't change the rule. It doesn't show per-person permissions inside the synced folder, or that a downloaded copy keeps Box's governance; those need their own design.

---

# Reference

## Files

| Path | What it holds |
| --- | --- |
| `docs/workshop-walkthrough.html` | This guide, as a page with copy buttons and progress tracking |
| `src/akf_workshop/walkthrough.py` | The stage-by-stage commands (Steps 2 to 8) |
| `src/akf_workshop/box_source/adapter.py` | The local Box placeholder (default) |
| `src/akf_workshop/box_source/box_api.py` | The real Box adapter, used when `BOX_FOLDER_ID` is set |
| `src/akf_workshop/box_source/box_client.py` | A minimal Box API client (Client Credentials Grant) |
| `src/akf_workshop/box_source/setup_box.py` | Creates the workshop folder, groups and files in Box, and the Agent Workspace folder |
| `src/akf_workshop/box_source/openshell_token.py` | Stores a short-lived Box token in OpenShell (Step 14d) |
| `src/akf_workshop/box_source/source.py` | Chooses local or Box, from `BOX_FOLDER_ID` |
| `src/akf_workshop/akf_search/` | Parse, chunk, embed, index, rerank, context and the pipeline |
| `src/akf_workshop/akf_skills/` | The retrieval skill and the Kumo skill |
| `src/akf_workshop/agent/` | The rule-based agent, the CLI and the trace |
| `src/akf_workshop/agent/nemotron_agent.py` | The Nemotron 3.5 Super agent with tools (Steps 11, 15 and 16) |
| `src/akf_workshop/agent/workspace.py` | The agent's file tools, run inside OpenShell (Steps 15 and 16) |
| `src/akf_workshop/evals/` | Golden questions and the metrics |
| `src/akf_workshop/nvidia_clients.py` | Every call to a hosted NVIDIA endpoint |
| `openshell/` | Gateway settings, the Box provider profile and the Box Mount config script (Step 14) |
| `docs/nvidia-endpoints.md` | Endpoint details and every setting |
| `sample_box/` | The stand-in Box folder and its permissions |

Box Mount isn't in this repo. Get the build from your workshop host and put its `Box Mount Build …/` folder in the repo folder (Step 14e).

## Local stand-in to production swap

| Local stand-in | Production |
| --- | --- |
| `BoxPlaceholderAdapter` (local files) | `BoxApiAdapter`: the Box API for files, versions and permissions (Step 1) |
| Local Markdown and CSV parser | Nemotron Parse 2.0 |
| Word-hashing vectors | Nemotron 3 Embed 1B |
| Word-overlap reranker | `nvidia/nemotron-3.5-rerank-8b`; its logit also decides refusals |
| Hand-written risk formula | Kumo Relational |
| Keyword routing + answer quoted from the best chunk | Nemotron 3.5 Super choosing tools and writing a cited answer (Step 11) |
| Agent acting directly on files | The agent's file actions run inside OpenShell, with Box Mount and a network policy (Steps 13 to 16) |

## Troubleshooting

- **`No module named 'akf_workshop'`**: you're not in the repo folder, or `PYTHONPATH=src` is missing.
- **`mode: OFFLINE` when you expected remote**: both `NVIDIA_API_KEY` and `NVIDIA_USE_REMOTE=1` must be set in the *same terminal*.
- **A PDF or image shows as a notice**: remote mode is off, or `pypdfium2` and `Pillow` aren't installed.
- **Results differ slightly from this guide in remote mode**: expected. Hosted models can change scores between runs.
- **`Box credentials missing`**: `BOX_FOLDER_ID` is set but `BOX_CLIENT_ID`, `BOX_CLIENT_SECRET` or `BOX_ENTERPRISE_ID` isn't. Set all of them, or unset `BOX_FOLDER_ID` to use local files.
- **`Box API error 401` or `400` from the token request**: wrong client ID or secret, or the app isn't authorized in your Box enterprise yet.
- **`Box API error 403` from `setup_box`**: the app lacks a scope, usually *Manage groups* or *Write files*. Add it in the Developer Console and have an admin re-authorize the app.
- **`Box API error 404` for a folder**: the service account can't see it. Invite the `AutomationUser_…` account to it as a collaborator.
- **`Your Command Line Tools are too outdated`** while installing OpenShell: update them, then run the installer again (Step 14a).
- **`Connection refused` right after restarting the gateway**: it's still starting. Wait 10 seconds and check again (Step 14b).
- **`python3: command not found` or `codex: command not found`**: you ran a Mac command inside Codex, or a Codex command on your Mac. Check the block's label: *Mac terminal* or *Paste into Codex*.
- **The agent says `status: error` or the trace shows `llm_rate_limited`**: NVIDIA's endpoint was busy. Check the trace for what was done, wait a moment and ask again.
