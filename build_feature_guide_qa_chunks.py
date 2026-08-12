"""Build render-only QA chunks from the same Feature Testing Guide functions."""

from pathlib import Path

from docx import Document

import qa_master_catalog as qa
from build_feature_testing_guide import (
    configure_styles,
    configure_section,
    cover_page,
    front_matter,
    feature_chapter,
    cross_feature_section,
    impact_guide,
    repro_templates,
    risks_and_unknowns,
    closing,
)


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs" / "master_qa_documentation" / "_docx_chunks"


def new_doc():
    doc = Document()
    configure_styles(doc)
    for section in doc.sections:
        configure_section(section)
    return doc


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    groups = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 25), (25, 27)]
    for index, (start, end) in enumerate(groups, 1):
        doc = new_doc()
        if index == 1:
            cover_page(doc, qa.summary())
            front_matter(doc, qa.summary())
        for feature_index in range(start, end):
            feature_chapter(doc, feature_index + 1, qa.FEATURES[feature_index])
        if index == len(groups):
            cross_feature_section(doc)
            impact_guide(doc)
            repro_templates(doc)
            risks_and_unknowns(doc)
            closing(doc)
        output = OUT / f"guide_chunk_{index:02d}.docx"
        doc.save(output)
        print(output)


if __name__ == "__main__":
    build()

