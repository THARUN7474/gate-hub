# Proposed notation for the three flagged 2026 CS-1 questions (G5)

**Status: PROPOSAL ONLY. The database was not changed.** You decide whether to apply it.
Method: rendered each question's stored region from `data/raw/papers/2026/CS1_2026.pdf`, read the printed notation
(`'` = overbar / complement), then **evaluated every option by computer** and compared with the official key.
All three agree with the key, which is independent evidence that this reading of the overbars is the intended one.

| Q | Official key | Options that my reading makes true | Agrees? |
| --- | --- | --- | --- |
| Q21 | A;C | A, C | yes |
| Q37 | B | B (only) | yes |
| Q48 | B;D | B, D | yes |

## Q21 (id GATE-CS-2026-S1-Q21)
Stem: `F(P,Q) = (P' + Q) XOR (P'Q)`. Which expressions are equivalent to F?
- (A) `NOT( P XOR Q )`   <- the overbar spans the whole `P XOR Q`; the stored text attaches it ambiguously
- (B) `P XOR Q`
- (C) `P' XOR Q`
- (D) `P' XOR Q'`

(F is 1 when P = Q, i.e. XNOR; A and C are XNOR.)

## Q37 (GATE-CS-2026-S1-Q37)
Table (P, Q1, Q0 -> Q1+, Q0+): 000->01, 001->10, 010->11, 011->11, 100->00, 101->00, 110->01, 111->10 (the stored text keeps all 8 rows in order).
- (A) `D1 = P Q1 + P' Q0 + Q1 Q0 ;  D0 = P Q0 + P' Q1 + Q1 Q0'`
- (B) `D1 = P' Q1 + P' Q0 + Q1 Q0 ;  D0 = P' Q0' + P' Q1 + Q1 Q0'`
- (C) `D1 = P' Q1' + P' Q0 + Q1 Q0 ;  D0 = P' Q0 + P' Q1 + Q1 Q0'`
- (D) `D1 = P Q1' + P' Q0 + Q1 Q0 ;  D0 = P Q0' + P' Q1 + Q1 Q0'`

## Q48 (GATE-CS-2026-S1-Q48)
Stem: `F(P,Q,R,S) = Sum m(1,2,3,4,5,7,10,12,13,14)`; which are minimal sum-of-products expressions of F?
- (A) `P'S + QR' + P'Q'R + Q'RS'`
- (B) `P'S + QR' + P'Q'R + PRS'`
- (C) `P'S + QR' + PQS' + PRS'`
- (D) `P'S + QR' + PQS' + Q'RS'`

## G5 status in one line
The auditor's original artifact (52 exact / 10 normalized / 3 changed) was **not available**, so that discrepancy is still
unexplained. What I can say: on this machine (Python 3.12.9, PyMuPDF 1.28.2) re-extracting 2026 CS-1 matches the stored rows 65/65 exact,
and the same holds for 28 of 29 papers (see docs/15). If you can send the auditor's file, I will diff it row by row.
