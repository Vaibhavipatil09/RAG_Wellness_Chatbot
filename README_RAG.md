# WellBot - Strict RAG Mental Health Chatbot

## What changed in this build

- The chatbot now answers using **Strict Retrieval-Augmented Generation
  (RAG)**: it only generates an answer when the built-in Q&A dataset has
  a closely matching question. If nothing matches well enough, it says so
  honestly instead of guessing (see `ChatbotWebsite/chatbot/rag.py`,
  `STRICT_MIN_SCORE` and `FALLBACK_RESPONSE`).
- The dataset (`ChatbotWebsite/static/data/mental_health_qa.json`) is a
  ~100-row Q&A set covering common mental health topics (anxiety, sleep,
  low mood, stress, burnout, loneliness, self-esteem, grief, and more),
  each with several paraphrased user question variants pointing at the
  same answer, to help retrieval generalize across different phrasings.

**Important - about sourcing:** this dataset is general educational
content written to reflect widely-known, publicly available mental
health guidance. It is NOT a verbatim transcript from WHO or any other
single organization, and should be described that way in any report -
claiming direct WHO sourcing for text that wasn't pulled from an actual
WHO document would be inaccurate. If you need to cite a specific
organization, expand the dataset yourself using their public fact sheets
as a reference, writing the answers in your own words.

- Original features (login/register, journal, topics, tests,
  mindfulness, SOS page, password reset) are all unchanged and included.
- Also carried over from earlier fixes: database auto-creation on
  startup, password-reset error handling instead of crashing, and the
  chat page dropdown/theme fixes.

## One-time setup

1. Install Python 3.10 if you don't have it already.
2. Get an Anthropic API key:
   - Go to console.anthropic.com and create an account
   - Add a payment method under Billing (no free tier, but a student
     project's usage typically costs cents to a couple dollars)
   - Settings -> API Keys -> Create Key, copy it (starts with `sk-ant-`)
3. Open the `.env` file in this folder and replace
   `ANTHROPIC_API_KEY=sk-ant-your-real-key-here` with your real key.
   (The MAIL_USERNAME/MAIL_PASSWORD lines are already filled in from
   your earlier setup - update them if that ever changes.)

## Installing dependencies

From this folder in Command Prompt / Terminal:

```
py -m pip install -r requirements.txt
```

This is a bigger install than before (`sentence-transformers` pulls in
`torch`), so it can take a few minutes - let it finish fully.

## Testing before running the full app

```
py test_rag.py
```

This checks two things without needing the browser:
- A mental-health-related question should retrieve good matches and get
  a real generated answer.
- An unrelated question (like "best pizza topping") should show low
  scores and trigger the fixed fallback message, with NO API call made.

The first time you run this (or the app), `sentence-transformers` will
download the embedding model (~80MB) automatically - that needs internet
once, then it's cached on your machine.

## Running the app

```
py run.py
```

Then open the site in your browser as usual and try the Chat page.

## Growing the dataset

Edit `ChatbotWebsite/static/data/mental_health_qa.json` directly - it's a
plain JSON list:

```json
[
  {
    "question": "your question here",
    "answer": "your answer here",
    "category": "optional category label"
  }
]
```

No code changes needed - `rag.py` reads whatever is in that file each
time the app starts. Adding a few paraphrased versions of the same
question (as this dataset already does) generally improves retrieval
more than adding entirely new topics.

## If something breaks

- Delete all `__pycache__` folders in the project if you see confusing
  import errors (this project has previously hit stale-cache issues due
  to OneDrive sync).
- Run `py test_rag.py` first whenever chat responses seem wrong - it
  isolates the RAG pipeline from the rest of the Flask app.
