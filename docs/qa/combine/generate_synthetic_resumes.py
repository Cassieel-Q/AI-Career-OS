"""Generate fictional PDFs for local integration checks only."""

from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / ".runtime"
OUTPUT.mkdir(exist_ok=True)

RESUMES = {
    "combine-resume-a.pdf": (
        "Ada Lin\n"
        "AI Product Manager Intern\n"
        "Education: Example University, MSc in Computer Science, 2024-2026\n"
        "Experience: Product Research Intern, Acme Labs, 2025\n"
        "Built an AI evaluation dashboard for 120 labeled cases.\n"
        "Designed a rubric with quality and latency measures; reduced review cycle time by 17%.\n"
        "Project: Interview preparation assistant, 2024\n"
        "Compared retrieval approaches and documented failure cases.\n"
        "Skills: Python, SQL, Figma, product analytics."
    ),
    "combine-resume-b.pdf": (
        "Kai Chen\n"
        "Community Product Operations Intern\n"
        "Education: Example University, BA in Communication, 2023-2027\n"
        "Experience: Community Operations Intern, Northstar Media, 2025\n"
        "Analyzed 50 creator posts and tested a new onboarding checklist.\n"
        "Improved creator activation from 28% to 35% in a four-week pilot.\n"
        "Project: Content feedback study, 2024\n"
        "Interviewed 12 creators and summarized product pain points.\n"
        "Skills: Research interviews, spreadsheets, content operations."
    ),
}

for filename, content in RESUMES.items():
    document = fitz.open()
    page = document.new_page()
    page.insert_text((45, 55), content, fontsize=11, lineheight=1.45)
    document.save(OUTPUT / filename)
    document.close()
    print(OUTPUT / filename)
