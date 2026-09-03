"""Flame-graph workload: replicate P03 process_publish (10x fill + 10x render per round).

fill = 18 recipe fields (page-correct) via pypdf; render = pdftoppm -r 200 + PIL save cl=6.
ROUNDS env controls repetition (default 3) for enough perf samples.
"""
import glob
import os
import subprocess
import sys
import time

sys.path.insert(0, "/opt/document-bench/skills/pdf/scripts")
from extract_form_field_info import get_field_info  # noqa: E402

from pypdf import PdfReader, PdfWriter  # noqa: E402
from PIL import Image  # noqa: E402

TPL = "/opt/document-bench/pdf/input/of306_aug2023.pdf"
OUT = "/tmp/wl"
ROUNDS = int(os.environ.get("ROUNDS", "3"))
N = 10

WANT = {
    "Full Name": "Flame Graph Run",
    "PLACE OF BIRTH Include city and state or country": "Springfield, IL, United States",
    "Country of Citizenship": "United States",
    "Are you a U.S. Citizen?": "/Yes",
    "DATE OF BIRTH MM  DD  YYYY": "01 15 1990",
    "Day": "555-0100",
    "Other Names Used 2": "None",
    "Male": "/Male",
    "Have you registered with Selective Service": "/Yes",
    "Have you ever served in the U.S. Military": "/No",
    "Have you been convicted imprisoned probation or paroled last 7 years": "/No",
    "Have you been court martialed in the last 7 years": "/No",
    "Are you currently under charges": "/No",
    "Have you been fired or debarred or quit due to a specific problem or quit after being told you would be fired": "/No",
    "Are you delinquent on any Federal debt": "/No",
    "Do any of your relatives work for the agency or government organization for which you are submitting this form": "/No",
    "Have you applied or do you receive retirement or pension benefits from the military Federal or D.C. government": "/No",
    "Continuation of Space or Agency Specific Questions": "N/A",
}
PAGES = {"Continuation of Space or Agency Specific Questions": 2}
PAGE2_EXTRA = [
    "Do any of your relatives work for the agency or government organization for which you are submitting this form",
    "Have you applied or do you receive retirement or pension benefits from the military Federal or D.C. government",
]

infos = {i["field_id"]: i for i in get_field_info(PdfReader(TPL))}
assert set(WANT) <= set(infos), sorted(set(WANT) - set(infos))


def value_of(fid):
    info = infos[fid]
    want = WANT[fid]
    if info.get("type") == "radio_group":
        opts = [o["value"] for o in info.get("radio_options", [])]
        if want in opts:
            return want
        if "/Yes" in opts:
            return "/Yes"
        return opts[0] if opts else want
    return want


BY_PAGE = {1: {}, 2: {}}
for fid in WANT:
    page = PAGES.get(fid, 1)
    if page == 2 and fid not in PAGE2_EXTRA:
        page = 1
    BY_PAGE[page][fid] = value_of(fid)


def fill(i):
    reader = PdfReader(TPL)
    writer = PdfWriter(clone_from=reader)
    for pidx, values in BY_PAGE.items():
        writer.update_page_form_field_values(writer.pages[pidx], values, auto_regenerate=False)
    writer.set_need_appearances_writer(True)
    path = f"{OUT}/applicant_{i:02d}.pdf"
    with open(path, "wb") as f:
        writer.write(f)
    return path


def render(path, i):
    subprocess.run(["pdftoppm", "-r", "200", path, f"{OUT}/r{i}"], check=True)
    for n, ppm in enumerate(sorted(glob.glob(f"{OUT}/r{i}-*.ppm")), 1):
        Image.open(ppm).save(f"{OUT}/r{i}_{n}.png", compress_level=6)
        os.unlink(ppm)


os.makedirs(OUT, exist_ok=True)
t0 = time.time()
for r in range(ROUNDS):
    for i in range(1, N + 1):
        render(fill(i), i)
print(f"done {ROUNDS}x{N} fill+render in {time.time() - t0:.1f}s", flush=True)
