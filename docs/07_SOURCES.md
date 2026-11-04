# Source Registry (verification level stated per source, checked 3 Nov 2026)

| Source | URL | How verified |
| --- | --- | --- |
| GATE 2027 portal (IIT Madras) | https://gate2027.iitm.ac.in/ | page fetched |
| Test papers + syllabus page | https://gate2027.iitm.ac.in/exam_papers_and_syllabus | page fetched; states syllabi revised for 2027 |
| CS 2027 syllabus PDF | https://gate2027.iitm.ac.in/static/doc/GATE2027_Syllabus/CS_GATE2027_Syllabus.pdf | DOWNLOADED AND READ (2 pages). sha256 81b23f40417bc1c2069782db7ad5ea0182175c9acb4766ebfdeefbe071a70bc0. 10 sections transcribed verbatim into taxonomy.yaml |
| GA 2027 syllabus PDF | https://gate2027.iitm.ac.in/static/doc/GATE2027_Syllabus/GA_GATE2027_Syllabus.pdf | DOWNLOADED AND READ (1 page). sha256 3708769a165e5019d4fa0d2af95786dee8fbf239976d7d403d810bd54b9d7603 |
| 2027 paper pattern | https://gate2027.iitm.ac.in/question_paper_pattern | page fetched. 65 Q / 100 marks / MCQ-MSQ-NAT for 2027 ONLY - older years differ; per-year manifests decide |
| Downloads page (year-wise 2021-2026) | https://gate2027.iitm.ac.in/download | listing verified; CS-1+CS-2 sessions for 2025-2026, single CS 2021-2023 |
| Bulk archive (official Drive) | https://drive.google.com/drive/folders/1xUn7rGTzKlfvJDoo4SzCRi8jRlBD63ud | folder listing read: one ZIP per paper code 2007-2026, owned by helpdesk@gate.iitm.ac.in. CS.zip ~65.6 MB LISTED, NOT OPENED - contents are a Day-1 finding |
| NDLI mirror (IIT Kharagpur) | https://ndl.iitkgp.ac.in/cd_document/gate/gate/root | page fetched; papers + keys 2007-2025, open access |

Not inherited as fact: any claim from the pasted third-party plans that
contradicts the above (e.g. fixed 65/100 format for all years, guessed corpus
question counts, "cheap LLM" assumptions). The pipeline measures these.

Rights note: local personal analysis of official papers is low-risk but is a
risk assessment, not legal clearance. Phase 1 re-hosts nothing; reports link
out to official sources. Private books stay local.

## Added in v5 (2025 CS1 second-paper verification)

- GATE 2025 CS1 question paper (IIT Roorkee, official mirror on the IITG site):
  https://gate2026.iitg.ac.in/doc/download/2025/CS12025.pdf -> data/raw/papers/2025/CS1.pdf
- GATE 2025 CS1 final answer key (IIT Roorkee):
  https://gate2025.iitr.ac.in/doc/2025/2025_Key/CS1_Keys.pdf -> data/raw/keys/2025/CS1_Keys.pdf
  (parsed by scripts/keypdf_to_csv.py -> data/raw/keys/2025/CS1_key.csv)
