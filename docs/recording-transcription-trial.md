# D-123: the end-to-end trial of recording transcription on real audio, 11 November 2026

The trial ran recording transcription on a real recording, from the page to a cited answer: the
browser decodes the recording, the server transcribes it with Whisper on FLM, a person reviews the
draft, FR-09 adds it, and FR-12 answers from it.

- **Who:** Benjamin Morovan drove his own browser. The building session confirmed each step on the
  server, reading only, from the server log and the database.
- **The code:** branch `feat/FR-09-recording-transcription` at `fddbcb9`, served by
  `manage.py runserver 127.0.0.1:8010` from its worktree. That serves the page, built with
  `npm run build`, and the API from one origin.
  - **Why port 8010:** a Waitress the user had started on port 8000 was serving code without this
    branch. Windows let both servers bind 8000, and every request went to Waitress, which answered
    404 for `/api/transcriptions/status`. So the trial moved to 8010 and left that server alone.
- **The configuration:**
  - database `kmp_anthropic`;
  - `AI_PROVIDER=anthropic` (Claude Haiku 5.5 and Voyage `voyage-4`, D-122);
  - `TRANSCRIPTION_PROVIDER=flm`.
- **FLM:** v0.9.39, one process, started by the user with
  `flm serve gemma3:4b --embed 1 --asr 1`. Exactly one `flm.exe` was running and listening on 8625
  before the trial began.

## Before the trial: the server path alone

A 13.8 s sentence spoken by Windows' own speech synthesizer was sent through `apps/ingestion/audio.py`
and the AI service, with no browser and no database.

- **The route through the providers:** `AnthropicService.transcribe` handed it to FLM. FLM accepted
  the request as `apps/ai/transcription.py` builds it (`language=en`, `response_format=json`).
- **The level:** −17.1 dBFS at its loudest half second, well above the −45 dBFS threshold.
- **The speed:** transcribed in 7.1 s (0.52× real time). A short segment pays a fixed cost per call.
- **The text:** right except "the 1st of March 20 27" for "the first of March 2027" and "Sagraka" for
  "Sagarika". "$12,000" was right.

## The trial

1. **Sign-in.** The user registered a new Employee account on `kmp_anthropic` at 09:25:44 and signed
   in with it. That account is still in the database.
2. **Availability.** The status route answered `enabled` and `available` at 09:26:05.
3. **The recording.** The user chose a narrated tour of the platform, which the page decoded in his
   browser. The file's name and format were not recorded.
4. **Transcription.** 28 segments were posted, the first at 09:26:29 and the last at 09:29:14.
   - **Outcomes:** every one was answered 200.
   - **Silence:** one was answered `silent`, without a provider call. No invented text appears anywhere
     in the draft.
   - **Speed:** about 7 s per segment, 2 min 45 s from the first reply to the last.
   - **Length:** segments are cut at 20 to 31 s, so the recording was between 9.3 and 14.5 minutes,
     which puts the whole run at 0.19 to 0.30× real time. The 6 November measurement was
     0.24 to 0.31×.
5. **The draft.** 1,100 words in 26 paragraphs, one per transcribed segment. The gist is right; the
   details are not:
   - **meaning inverted:** "we can up reach our previous page because that session has been expired",
     where the speaker said the page cannot be reached after logout;
   - **figures and formats wrong:** "PDF, .x, .xlx, .txt" for PDF, DOCX, XLSX, TXT; "maximum 50
     gigabits" and "50 megabits" for 50 MB;
   - **terms garbled:** "mission-aware retrieval scoping" for permission-aware, "Regent Atlas",
     "EGOL organization", "Filed file not supported", "we should give it a total" for a title, and "it's a
     click answer to secure by cache";
   - **cut sentences:** some paragraphs stop mid-sentence where a segment was cut ("…sign in or create
     an" / "I'll create an account…"). A word at a cut can be lost, because Whisper hears each segment
     on its own.
6. **The review and the add.** The user ticked "I have reviewed and corrected this transcript" and
   added it.
   - **What was stored:** the draft exactly as transcribed, every error above included. It is meeting
     `fdd8cfa2-0872-494c-a924-37e0ae545e77`, titled "Tour of the platform", 1,100 words, `Indexed`,
     visible to both roles, with one attendee.
   - **Its chunks:** 3, each embedded by `voyage-4` at 1024 and stamped for both roles.
7. **The answer.** Asked "How long is an account locked after five wrong passwords?", the platform
   answered "If a user enters the wrong password five times, they will be locked out for 15 minutes".
   It cited passage [1], which is chunk 0 of the new meeting and contains "15 minutes". The Sources
   panel also listed three sources consulted and not cited.

## What it shows

- **The path works end to end on real audio:**
  - decoding in a real browser;
  - cutting at quiet points;
  - the server's checks;
  - Whisper on FLM under the `anthropic` provider;
  - the draft;
  - FR-09's ingestion unchanged;
  - a cited FR-12 answer from the new meeting.
- **The speed matches the 6 November measurement:** about a quarter of real time.
- **The silence rule did its job on this recording:** the one quiet segment was not sent, and nothing
  was invented.
- **The review step is the weak point, and in this trial it did not stop errors reaching the
  index.** The tick was given and nothing was corrected, so an inverted "cannot" and a wrong upload
  limit are now searchable, cited text.
  - D-123 concedes this in its own words: "The tick box proves a person was asked; it cannot prove
    they read". This trial is that limitation observed rather than predicted.
  - The answer that was asked happened to come from a sentence Whisper got right.

## What it did not measure

- **The per-segment levels.** The trial ran in the user's own browser, not the session's, so the
  `loudest_dbfs` each reply carried was not read. `TRANSCRIPTION_SILENCE_DBFS` (−45) is checked only
  in the sense above: one quiet segment skipped and nothing invented. Its margin is not measured.
- **The recording's exact length, name and format.** So the speed is a range, and whether this was
  an MP4 is not confirmed. A browser-made MP4 decoded short on 11 November (D-123, "What it does not
  cover").
- **Word error rate.** No reference transcript of the tour exists. The errors above are the ones a
  reader can see without the recording.

## What it left behind in `kmp_anthropic`

- **The meeting:** "Tour of the platform" (`fdd8cfa2-0872-494c-a924-37e0ae545e77`), with its
  uncorrected transcript and its chunks. An Administrator can delete it on its detail page (D-99).
  Meetings have no edit, so a corrected version would be a fresh add.
- **The Employee account** registered at 09:25:44.
- **The query log row** for the question.
