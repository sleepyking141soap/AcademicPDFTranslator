"""Generate a deterministic native-text fixture; no external paper/download needed."""

import argparse
from pathlib import Path

from reportlab.pdfgen import canvas


def create_sample(path: Path) -> None:
    """Create a readable two-page paper covering single and double columns."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=(612, 792), invariant=1)
    pdf.setTitle("A Small Study of Reliable Translation")

    def text(x: float, y: float, lines: list[str], size: int = 11, bold: bool = False) -> None:
        obj = pdf.beginText(x, y)
        obj.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        obj.setLeading(size * 1.5)
        for line in lines:
            obj.textLine(line)
        pdf.drawText(obj)

    text(54, 742, ["A Small Study of Reliable Translation"], 21, True)
    text(54, 707, ["AcademicPDFTranslator contributors | Synthetic test paper"], 10)
    text(54, 650, ["Abstract"], 14, True)
    text(
        54,
        617,
        [
            "We study reliable translation of scientific documents.",
            "The method preserves measurements, references, and technical symbols.",
            "It achieves a recall of 0.873 at 5% coverage [23].",
        ],
    )
    text(54, 516, ["1 Introduction"], 14, True)
    text(
        54,
        481,
        [
            "Domain alignment alone cannot guarantee target-domain discriminability.",
            "This limitation motivates a separate check of numerical consistency.",
        ],
    )
    text(
        54,
        401,
        [
            "The FPGA operates at 300 MHz and uses 128 samples.",
            "Fig. 3 compares S21 with the baseline. Table IV reports the results.",
        ],
    )
    text(54, 305, ["Fig. 3. A synthetic caption for the translation pipeline."], 10)
    text(54, 255, ["2 Method"], 14, True)
    text(
        54,
        220,
        [
            "We protect each scientific token before requesting a translation.",
            "A deterministic checker then compares the restored values.",
        ],
    )
    text(303, 28, ["1"], 9)
    pdf.showPage()
    text(54, 741, ["3 Results"], 14, True)
    text(
        54,
        702,
        [
            "The left column starts here.",
            "Recall reaches 0.873 [12].",
            "The first experiment uses 128 samples.",
        ],
    )
    text(
        54,
        620,
        [
            "A second experiment tests the FPGA.",
            "It operates at 300 MHz.",
            "The measured coverage is 98.2%.",
        ],
    )
    text(54, 538, ["Table IV. Synthetic measurement results."], 10)
    text(
        326,
        702,
        [
            "The right column follows the left.",
            "Fig. 3 summarizes the experiment.",
            "The baseline uses 256 samples.",
        ],
    )
    text(
        326,
        620,
        [
            "A limitation is the small sample size.",
            "The checker does not verify meaning.",
            "Human review remains necessary.",
        ],
    )
    text(54, 411, ["4 Conclusion"], 14, True)
    text(
        54,
        375,
        [
            "Preserving scientific tokens makes translation errors easier to inspect.",
            "This fixture demonstrates extraction and checks, not model quality.",
        ],
    )
    text(54, 287, ["References"], 14, True)
    text(
        54,
        249,
        [
            "[12] Example A. A synthetic reference, 2024.",
            "[23] Example B. Another synthetic reference, 2025.",
        ],
        10,
    )
    text(303, 28, ["2"], 9)
    pdf.save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=Path("examples/sample_paper.pdf"))
    create_sample(parser.parse_args().path)
