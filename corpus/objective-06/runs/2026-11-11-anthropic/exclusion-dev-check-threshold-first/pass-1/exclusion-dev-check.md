# D-108's development check of FR-19's permission exclusion

Commit 462e8e9, database kmp_obj0506_anthropic_20261110, dump 3bf98403…, configuration {'ai_provider': 'anthropic', 'chat_model': 'claude-haiku-5-5', 'embedding_model': 'voyage-4'}, RELEVANCE_THRESHOLD 0.3; every question asked as the Employee.

- Scoped questions left out: 6 of 6
- No-answer questions kept: 9 of 9
- Ordinary questions kept (for information): 46 of 50
- **PASS**; misses: none

| Set | Id | Kind | Outcome | Expected | Admitted | Top score | Top readable by the Employee | Question |
|---|---|---|---|---|---|---|---|---|
| dev-set-v2.json | u01 | ordinary | kept | kept if unanswered | 5 | 0.4568 | True | I start next week, what should I expect in my first few days? |
| dev-set-v2.json | u02 | ordinary | kept | kept if unanswered | 14 | 0.5594 | True | new hire here - how does onboarding work? |
| dev-set-v2.json | u03 | ordinary | kept | kept if unanswered | 25 | 0.5416 | True | how long do we have to hang on to old invoices and finance paperwork? |
| dev-set-v2.json | u04 | ordinary | kept | kept if unanswered | 12 | 0.4582 | True | does my work laptop need anything special set up on it? |
| dev-set-v2.json | u05 | ordinary | kept | kept if unanswered | 5 | 0.4642 | True | how much holiday do I build up each month? |
| dev-set-v2.json | u06 | ordinary | kept | kept if unanswered | 1 | 0.3284 | True | im sick tmrw, do i need a drs note? |
| dev-set-v2.json | u07 | ordinary | left out | kept if unanswered | 4 | 0.431 | False | I think I clicked a dodgy link in an email, what now? |
| dev-set-v2.json | u08 | ordinary | kept | kept if unanswered | 1 | 0.517 | True | where are we meant to go if the fire alarm goes off? |
| dev-set-v2.json | u09 | ordinary | kept | kept if unanswered | 1 | 0.4011 | True | hw many quotes do i need to buy something for about 10k? |
| dev-set-v2.json | u10 | ordinary | kept | kept if unanswered | 5 | 0.5463 | True | a customer is really unhappy and I can't sort it out, who do I hand it to? |
| dev-set-v2.json | u11 | ordinary | kept | kept if unanswered | 8 | 0.508 | True | am I allowed to work from home a couple of days a week? |
| dev-set-v2.json | u12 | ordinary | kept | kept if unanswered | 17 | 0.5251 | True | wfh - what hours do I actually need to be online? |
| dev-set-v2.json | u13 | ordinary | kept | kept if unanswered | 1 | 0.4095 | True | how do I get my money back for a work lunch? |
| dev-set-v2.json | u14 | ordinary | kept | kept if unanswered | 1 | 0.47 | True | can I find out what personal info the company keeps about me? |
| dev-set-v2.json | u15 | ordinary | kept | kept if unanswered | 2 | 0.4157 | True | who do we order pens and paper from? |
| dev-set-v2.json | u16 | ordinary | kept | kept if unanswered | 6 | 0.5328 | True | any training on giving feedback coming up? |
| dev-set-v2.json | u17 | ordinary | kept | kept if unanswered | 7 | 0.6116 | True | is there a spare laptop lying around in the Melbourne office? |
| dev-set-v2.json | u18 | ordinary | kept | kept if unanswered | 9 | 0.6138 | True | how do i book one of the meeting rooms? |
| dev-set-v2.json | u19 | ordinary | kept | kept if unanswered | 1 | 0.4469 | True | forgot my pw, how do I get back in? |
| dev-set-v2.json | u20 | ordinary | kept | kept if unanswered | 4 | 0.4988 | True | how do I print something from my laptop? |
| dev-set-v2.json | u21 | ordinary | kept | kept if unanswered | 6 | 0.4482 | True | can I take the company car home over the weekend? |
| dev-set-v2.json | u22 | ordinary | kept | kept if unanswered | 6 | 0.5677 | True | when are we moving offices? |
| dev-set-v2.json | u23 | ordinary | kept | kept if unanswered | 1 | 0.4374 | True | what's the latest on the database migration? |
| dev-set-v2.json | u24 | ordinary | kept | kept if unanswered | 1 | 0.3565 | True | is the new mobile app design going out in the next release? |
| dev-set-v2.json | u25 | ordinary | kept | kept if unanswered | 1 | 0.3406 | True | why do customers end up cancelling? |
| dev-set-v2.json | u26 | ordinary | kept | kept if unanswered | 2 | 0.4591 | True | need a room for 30 ppl one evening, anything I should know? |
| dev-set-v2.json | u27 | ordinary | kept | kept if unanswered | 7 | 0.3816 | True | my back hurts from sitting at my desk all day, is there anything I can ask for? |
| dev-set-v2.json | u28 | ordinary | left out | kept if unanswered | 2 | 0.4816 | False | how much have we put aside in case projects go over budget? |
| dev-set-v2.json | u29 | ordinary | left out | kept if unanswered | 1 | 0.3703 | False | did the board flag any new big risks for us to watch? |
| dev-set-v2.json | u30 | scoped | left out | left out | 2 | 0.4579 | False | what's project atlas actually for? |
| dev-set-v2.json | u31 | scoped | left out | left out | 1 | 0.4331 | False | who in the team is strongest at crunching data? |
| dev-set-v2.json | u32 | scoped | left out | left out | 4 | 0.5586 | False | how did staff go in the last fake phishing test? |
| dev-set-v2.json | u33 | no-answer | kept | kept | 2 | 0.3706 | True | what's the guest wifi password? |
| dev-set-v2.json | u34 | no-answer | kept | kept | 0 | 0.24 | True | do we get paid extra for working overtime? |
| dev-set-v2.json | u35 | no-answer | kept | kept | 1 | 0.2875 | True | is there a staff discount at the gym next door? |
| dev-set-v2.json | u36 | no-answer | kept | kept | 0 | 0.2296 | False | how many people did we hire last year? |
| dev-set-v2.json | u37 | no-answer | kept | kept | 2 | 0.4975 | True | how do I apply for parental leave? |
| dev-set.json | d01 | ordinary | kept | kept if unanswered | 21 | 0.6085 | True | What is the onboarding process for new employees? |
| dev-set.json | d02 | ordinary | kept | kept if unanswered | 24 | 0.6193 | True | Summarise the onboarding process for new employees. |
| dev-set.json | d03 | ordinary | kept | kept if unanswered | 20 | 0.5124 | True | How are records managed and retained? |
| dev-set.json | d04 | ordinary | kept | kept if unanswered | 25 | 0.5742 | True | What are the rules for acceptable use of IT equipment? |
| dev-set.json | d05 | ordinary | kept | kept if unanswered | 15 | 0.5701 | True | What does the health and safety induction cover? |
| dev-set.json | d06 | ordinary | kept | kept if unanswered | 24 | 0.5754 | True | Give me an overview of the procurement guidelines. |
| dev-set.json | d07 | ordinary | kept | kept if unanswered | 5 | 0.6412 | True | How are customer complaints escalated when they cannot be resolved straight away? |
| dev-set.json | d08 | ordinary | kept | kept if unanswered | 10 | 0.5468 | True | What equipment and security rules apply when working from home? |
| dev-set.json | d09 | ordinary | kept | kept if unanswered | 25 | 0.6555 | True | Summarise what staff need to know about the office relocation. |
| dev-set.json | d10 | ordinary | kept | kept if unanswered | 7 | 0.6282 | True | How do I submit an expense claim? |
| dev-set.json | d11 | scoped | left out | left out | 1 | 0.4291 | False | What happened in the security incident debrief? |
| dev-set.json | d12 | ordinary | kept | kept if unanswered | 3 | 0.5424 | True | What was decided at the product planning workshop? |
| dev-set.json | d13 | ordinary | kept | kept if unanswered | 5 | 0.5918 | True | What actions were agreed at the customer success retrospective? |
| dev-set.json | d14 | ordinary | kept | kept if unanswered | 5 | 0.4728 | True | What were the main points of the weekly operations standup? |
| dev-set.json | d15 | ordinary | kept | kept if unanswered | 1 | 0.5066 | True | How is consent to use personal information recorded? |
| dev-set.json | d16 | ordinary | kept | kept if unanswered | 10 | 0.6305 | True | What etiquette is expected when using a meeting room? |
| dev-set.json | d17 | ordinary | kept | kept if unanswered | 3 | 0.5559 | True | What should I do if my laptop is running slowly? |
| dev-set.json | d18 | ordinary | kept | kept if unanswered | 6 | 0.5271 | True | How do I request leave, and how quickly does my manager respond? |
| dev-set.json | d19 | ordinary | kept | kept if unanswered | 3 | 0.4587 | True | When do I need a medical certificate for personal leave? |
| dev-set.json | d20 | ordinary | kept | kept if unanswered | 4 | 0.5328 | True | What does the fourth quarter training program cover? |
| dev-set.json | d21 | scoped | left out | left out | 3 | 0.4522 | False | Which team members are rated expert in customer service? |
| dev-set.json | d22 | scoped | left out | left out | 1 | 0.4805 | False | What did the risk committee decide about the contingency reserve? |
| dev-set.json | d23 | ordinary | left out | kept if unanswered | 6 | 0.5471 | False | How is Project Atlas delivered, and who reviews each phase? |
| dev-set.json | d24 | no-answer | kept | kept | 6 | 0.3098 | True | How much is the annual staff bonus? |
| dev-set.json | d25 | no-answer | kept | kept | 6 | 0.3887 | True | Is there staff parking at the new office building? |
| dev-set.json | d26 | no-answer | kept | kept | 6 | 0.3596 | True | What is the policy on smoking at work? |
| dev-set.json | d27 | no-answer | kept | kept | 0 | 0.238 | False | What salary does the head of digital services earn? |
| dev-set.json | d28 | ordinary | kept | kept if unanswered | 7 | 0.6418 | True | Summarise the rules for using a fleet vehicle. |
