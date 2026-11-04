# The 18 unclassified questions: software-engineering syllabus audit (v11)

Date: 2026-11-04. Question set: the 18 questions with no classification (the v10
taxonomy-gap set). Conclusion up front: **all 18 are historical software
engineering questions from 2011-2015, on a topic present in the pre-2016 CS&IT
syllabus and absent from the official 2026/2027 syllabi** (the exact removal
year, reportedly the 2016 revision, rests on a secondary source and stays
tentative). The gate-cs-2027 taxonomy correctly has no SE topic, so
the questions stay UNCLASSIFIED with their `taxonomy_gap` review flags. This
audit adds evidence and per-question subtopic determinations (agent analysis,
recorded in `review_events` as `syllabus_audit`), not new labels.

## Syllabus evidence

- **Current syllabus (primary sources)**: the official GATE 2027 CS syllabus
  (IIT Madras), GATE 2026 CS syllabus (IIT Guwahati) and GATE 2023 CS syllabus
  (IIT Kanpur) each list exactly Sections 1-10: Engineering Mathematics,
  Digital Logic, COA, Programming & Data Structures, Algorithms, TOC, Compiler
  Design, OS, Databases, Computer Networks. **No Software Engineering section.**
  Sources: https://gate2027.iitm.ac.in/static/doc/GATE2027_Syllabus/CS_GATE2027_Syllabus.pdf ,
  https://gate2026.iitg.ac.in/doc/GATE2026_Syllabus/CS_2026_Syllabus.pdf ,
  https://gate.iitk.ac.in/GATE2023/doc/Syllabus/cs.pdf
- **Historical syllabus**: the pre-2016 CS&IT syllabus carried a section
  "Information Systems and Software Engineering" (information gathering,
  feasibility, DFDs, process life cycle, project planning, design, coding,
  testing, implementation, maintenance). Verified from a 2014 copy of the
  official GATE 2015 CS&IT syllabus (secondary copy; the IIT Kanpur 2015 site
  is defunct): https://uptukhabar.net/wp-content/uploads/2014/09/GATE-syllabus-CS-and-IT.pdf
- **Removal date (TENTATIVE - secondary source only)**: an independent guide
  (updated Oct 2026) says SE, Web Technologies, Information Systems and
  Numerical Methods were removed in the 2016 syllabus revision:
  https://gateguide.co.in/articles/gate-cse-out-of-syllabus-topics/
  This is NOT an official source; treat the exact cutoff year as tentative.
  What is established: SE was in the CS&IT syllabus as of the 2015 copy above,
  and is absent from the official 2026 and 2027 syllabi. The dataset agrees
  with a mid-2010s removal: SE questions appear in 2011-2015 papers and never
  in 2016-2026 papers.

## Per-question determination (agent analysis of the question text)

| Question | SE subtopic |
| --- | --- |
| GATE-CS-2011-S1-Q05 | project cost estimation (development + maintenance trade-off) |
| GATE-CS-2011-S1-Q07 | basic COCOMO effort estimation |
| GATE-CS-2011-S1-Q10 | SRS document contents |
| GATE-CS-2011-S1-Q47 | black-box testing - equivalence class partitioning |
| GATE-CS-2013-S1-Q38 | cohesion and coupling |
| GATE-CS-2013-S2-Q35 | cohesion and coupling (same question, session copy) |
| GATE-CS-2013-S3-Q47 | cohesion and coupling (same question, session copy) |
| GATE-CS-2013-S4-Q27 | cohesion and coupling (same question, session copy) |
| GATE-CS-2014-S1-Q28 | software process models (waterfall/evolutionary/CBSE/spiral) |
| GATE-CS-2014-S2-Q29 | requirements engineering (SRS, prototyping, validation) |
| GATE-CS-2014-S3-Q29 | cohesion and coupling |
| GATE-CS-2015-S1-Q16 | testing techniques and levels |
| GATE-CS-2015-S2-Q25 | SRS document contents |
| GATE-CS-2015-S2-Q29 | basic COCOMO equations |
| GATE-CS-2015-S2-Q64 | code inspection vs walkthrough |
| GATE-CS-2015-S3-Q17 | function point analysis |
| GATE-CS-2015-S3-Q33 | fault seeding (estimating undetected faults) |
| GATE-CS-2015-S3-Q58 | cyclomatic complexity / control-flow analysis |

## Recommendation (no action taken)

For GATE 2027 preparation these 18 are out of syllabus and the "no topic"
state is the honest answer. If you ever want them browsable as a set, the
clean move is a deprecated taxonomy node (e.g. `LEGACY.SE` marked
deprecated/historical), not forcing them into PDS.C - the same reason they
were left unclassified in v10. That is a taxonomy decision for you; nothing
was changed.
