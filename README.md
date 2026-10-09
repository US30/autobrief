# AutoBrief — meeting transcript to follow-ups

After a client meeting someone has to write up the decisions, turn the commitments into tasks and send a follow-up email.
AutoBrief does that from the transcript, and holds back anything it cannot verify for a human to confirm.

**Design rule:** the LLM (OpenAI) only extracts. Deterministic code checks each item, creates the tasks and composes the
email, so nothing reaches a task tracker or an inbox unless it passed the checks or a person approved it.

```
POST /webhook/transcript -> LangGraph: extract -> check -> save -> create tasks -> [notify reviewers] -> draft email
                                         |                              |                 |
                                   OpenAI, JSON schema            GitHub Issues     Slack webhook        SQLite + event log
```

| Step | What it does |
|---|---|
| extract | One structured OpenAI call returns summary, decisions and action items (task, owner, due date, evidence quote) as a validated Pydantic object |
| check | Each item must quote a sentence that is really in the transcript, name an attendee as owner, and have a due date on or after the meeting. The model can also mark an item uncertain. Any failure sends the item to review |
| create tasks | Items that passed become GitHub Issues over REST, or a local reference if GitHub is not configured |
| notify | Runs only if something needs review (conditional edge). Posts the items and reasons to a Slack webhook |
| draft email | Built from a template using the checked data, so the email cannot contain anything the checks did not see |
| review | `GET /review` lists waiting items. `POST /review/{id}` approves (optionally fixing owner or due date) or rejects. Approval creates the task and refreshes the email |

If the OpenAI call fails, a regex fallback runs and **every** item it finds goes to review. It never creates tasks on its own.

## Run (conda)

```bash
conda create -n autobrief python=3.11 && conda activate autobrief && pip install -r requirements.txt
cp .env.example .env                       # add OPENAI_API_KEY; GitHub and Slack settings are optional
                                           # any OpenAI-compatible API works: set OPENAI_BASE_URL and OPENAI_MODEL
uvicorn autobrief.api:app                  # API docs at http://localhost:8000/docs
pytest -q                                  # 16 tests, offline: OpenAI, GitHub and Slack are mocked
python eval/run_eval.py --no-llm           # regex baseline only; drop --no-llm to score the OpenAI model
```

```bash
curl -X POST localhost:8000/webhook/transcript -H 'content-type: application/json' -d '{
  "title": "Weekly project sync", "date": "2026-09-14",
  "transcript": "Priya: Meera, can you pull the receivables ageing report by tomorrow?\nMeera: Yes, will do."}'
```

## Results (seed 7, first 23 of 40 synthetic meetings, 84 gold action items; see eval/report.md)

| | Regex baseline | `gemini-3.5-flash-lite` |
|---|---|---|
| Precision / recall / F1 | 0.60 / 0.29 / 0.39 | 1.00 / 0.99 / **0.99** |
| Due-date accuracy on correct items | 1.00 | 0.99 |
| Meetings needing no edit | 0/23 | **21/23** |

- The model was called through Google's OpenAI-compatible endpoint (same `langchain-openai` client, `OPENAI_BASE_URL` changed),
  because the OpenAI account had no credits. **No OpenAI model has been run.** The free tier stopped answering after
  23 meetings (429), so 17 meetings are unscored.
- The model made no wrong items in this run, so the review step was not exercised by the eval (0 wrong items to catch).
  It is covered only by unit tests with invented evidence, unknown owners and bad dates.
- At an assumed 12 minutes of manual write-up per meeting, 21 clean meetings is about 4 hours. The 12 minutes is an assumption.

A predicted item is correct when its task text matches a gold item and the owner is the same.

## Limitations

- Transcripts are template-generated: six ways of making a commitment and four look-alikes (cancelled, already done,
  parked, vague). Real meetings have interruptions, speech-to-text errors and commitments spread over several turns.
  The eval shows the pipeline works, not how accurate it is on real calls. An F1 of 0.99 here says the data is easy.
- I wrote the generator and the prompt, so the prompt's rules line up with the look-alike cases.
- The evidence check is a fuzzy string match. It catches invented quotes, not a real quote attached to the wrong task.
- GitHub and Slack calls are tested with mocked HTTP. They have not been run against live accounts.
- The email is drafted and stored, not sent. Storage is SQLite. The webhook is protected only by an optional shared secret.
- The webhook runs the pipeline inside the request; a production version would queue it.
