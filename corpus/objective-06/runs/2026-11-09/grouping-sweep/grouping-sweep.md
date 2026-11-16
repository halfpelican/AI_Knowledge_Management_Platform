# Development sweep for GAP_GROUPING_THRESHOLD (D-109)

Commit 4a1ed3d, FLM v0.9.39 (flm version), server v0.9.39, embedding model embed-gemma, 36 items, 36 positive and 594 negative pairs.

- Lowest within-subject similarity: 0.5322
- Highest cross-subject similarity: 0.5876
- Separates: False; gap -0.0555 against D-40's drift of 0.003
- **Threshold by D-109's rule (best pairwise F1): 0.5256**

## Hard pairs

| a | b | why | max similarity | above threshold |
|---|---|---|---|---|
| g01 | g02 | the same document, D01, two subjects | 0.4589 | False |
| g03 | g04 | both about passwords, different documents and subjects | 0.5876 | True |
| g04 | g07 | the same document, D18, two subjects | 0.3565 | False |
| g11 | g12 | the same document, D04, two subjects | 0.5788 | True |
| g06 | g11 | finance vocabulary, different subjects | 0.2680 | False |
| g08 | g09 | both about using shared facilities, different subjects | 0.2606 | False |

## Lowest within-subject pairs

- 0.5322: "For how many years must finance records be retained?" / "When can old accounting paperwork be destroyed?"
- 0.5377: "What has to be written in the logbook when I use a pool car?" / "Which details does the fleet logbook record for every trip?"
- 0.5401: "When can old accounting paperwork be destroyed?" / "financial records retention"
- 0.5687: "How do I set up printing from my laptop?" / "What do I do at the printer to release my print job?"
- 0.5898: "How far from the main office must copies of vital records be stored?" / "Where are the backups of our most important records kept?"

## Highest cross-subject pairs

- 0.5876: "password length" / "password reset window"
- 0.5788: "financial records retention" / "Where are the backups of our most important records kept?"
- 0.5191: "What is the minimum number of characters for a password?" / "password reset window"
- 0.5135: "financial records retention" / "vital records backup"
- 0.5026: "For how many years must finance records be retained?" / "Where are the backups of our most important records kept?"

## Centroid grouping simulated at 0.5256

12 entries for 12 subjects; 0 mixed; subjects not grouped as one entry of three: none.

| Entry subject | Count | Subjects |
|---|---|---|
| How quickly does annual leave build up for someone working full time? | 3 | g01 |
| After how many days off sick do I have to produce a doctor's certificate? | 3 | g02 |
| What is the minimum number of characters for a password? | 3 | g03 |
| During which hours can I reset my password on the self-service page? | 3 | g04 |
| Who does an unresolved customer complaint go to next? | 3 | g05 |
| How much can I claim for meals per day on a work trip? | 3 | g06 |
| How do I set up printing from my laptop? | 3 | g07 |
| Who has to approve a meeting room booking for a large group? | 3 | g08 |
| What has to be written in the logbook when I use a pool car? | 3 | g09 |
| Is every new employee given a buddy? | 3 | g10 |
| For how many years must finance records be retained? | 3 | g11 |
| How far from the main office must copies of vital records be stored? | 3 | g12 |
