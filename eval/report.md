# AutoBrief evaluation (seed 7, 23 synthetic meetings)

|                             | regex baseline   | gemini-3.5-flash-lite   |
|:----------------------------|:-----------------|:------------------------|
| meetings                    | 23               | 23                      |
| gold_items                  | 84               | 84                      |
| predicted                   | 40               | 83                      |
| precision                   | 0.6              | 1.0                     |
| recall                      | 0.286            | 0.988                   |
| f1                          | 0.387            | 0.994                   |
| due_date_accuracy           | 1.0              | 0.988                   |
| meetings_needing_no_edit    | 0/23             | 21/23                   |
| wrong_items_sent_to_review  | 0/16             | 0/0                     |
| correct_items_auto_approved | 24/24            | 83/83                   |

A predicted item counts as correct when its task text matches a gold item and the owner is the same. Due-date accuracy is measured on correct items. A meeting needs no edit when every item, owner and due date is right and nothing is missing or extra.

Estimated time saved: 21 of 23 meetings needed no edit; at an assumed 12 minutes of manual write-up per meeting that is about 4.2 hours over this set. The minutes figure is an assumption, not a measurement. The API failed after 23 of 40 meetings (`OpenAIRateLimitError: Error code: 429 - [{'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Q`), so only those are scored.

Transcripts are template-generated, so they are cleaner than real meetings. Treat these numbers as a check that the pipeline works, not as accuracy on real calls.
