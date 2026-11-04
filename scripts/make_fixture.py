"""Build a SYNTHETIC test paper + key. Clearly labelled: this is NOT a real
GATE paper and its content is invented for pipeline testing only. Real corpus
files never come from this script."""
from __future__ import annotations
import sys
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

def build(pdf_path: str, key_csv_path: str) -> None:
    c = canvas.Canvas(pdf_path, pagesize=A4)
    w, h = A4

    def header(text):
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, h - 60, text)

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, h - 40, "SYNTHETIC TEST FIXTURE - NOT A REAL GATE PAPER")
    c.setFont("Helvetica", 9)
    c.drawString(50, h - 55, "Invented content for pipeline testing only. Do not distribute as PYQ material.")

    header("General Aptitude - carry ONE mark each")
    y = h - 90
    c.setFont("Helvetica", 10)
    qs1 = [
        ("Q.1 Choose the word closest in meaning to CANDID.", ["(A) frank", "(B) secretive", "(C) vague", "(C) bold"]),
        ("Q.2 If a train travels 60 km in 45 minutes, its speed in km/h is", ["(A) 75", "(B) 80", "(C) 85", "(D) 90"]),
    ]
    # fix intentional label typo guard: rewrite options properly
    qs1[0] = ("Q.1 Choose the word closest in meaning to CANDID.", ["(A) frank", "(B) secretive", "(C) vague", "(D) bold"])
    for qtext, opts in qs1:
        c.drawString(50, y, qtext); y -= 18
        for o in opts:
            c.drawString(70, y, o); y -= 16
        y -= 8

    header("Computer Science and IT - carry ONE mark each")
    y -= 20
    qs2 = [
        ("Q.3 The worst-case time complexity of binary search on a sorted array of n elements is", ["(A) O(n)", "(B) O(log n)", "(C) O(n log n)", "(D) O(1)"]),
        ("Q.4 In a max-heap with n elements, the maximum element can be found in", ["(A) O(n)", "(B) O(log n)", "(C) O(1)", "(D) O(n log n)"]),
    ]
    for qtext, opts in qs2:
        c.drawString(50, y, qtext); y -= 18
        for o in opts:
            c.drawString(70, y, o); y -= 16
        y -= 8

    header("Computer Science and IT - carry TWO marks each")
    y -= 20
    c.drawString(50, y, "Q.5 Consider the tree diagram below. The number of leaf nodes in a full binary tree with 15 internal nodes is ________.")
    y -= 16
    c.drawString(50, y, "(NAT - no options; answer is an integer)")
    y -= 12
    c.rect(60, y - 90, 220, 90, stroke=1, fill=0)   # stand-in diagram asset (vector)
    c.drawString(70, y - 50, "[fixture diagram placeholder]")
    y -= 130
    c.drawString(50, y, "Q.6 Which of the following is/are context-free languages? (MSQ)")
    y -= 18
    for o in ["(A) {a^n b^n | n >= 0}", "(B) {a^n b^n c^n | n >= 0}", "(C) {w w^R | w in {a,b}*}", "(D) {a^n b^m c^n | n,m >= 0}"]:
        c.drawString(70, y, o); y -= 16
    c.showPage()
    c.save()

    with open(key_csv_path, "w") as f:
        f.write("qno,kind,answer,min,max,notes\n")
        f.write("1,mcq_single,A,,,\n")
        f.write("2,mcq_single,B,,,\n")
        f.write("3,mcq_single,B,,,\n")
        f.write("4,mcq_single,C,,,\n")
        f.write("5,nat_range,,16,16,NAT range key\n")
        f.write("6,msq_set,A;C,,,\n")

if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
    print("fixture written (SYNTHETIC - not a real GATE paper)")
