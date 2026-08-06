"""
check_progress.py
==================
Compares the current baseline.csv against the known set of 117 IDs that
were unanswered BEFORE the Step 6 normalization fix (captured from the
run right after Steps 1-2). Reports:
  - which of those 117 are now fixed
  - which of the previously-117 are still unanswered
  - any REGRESSIONS: IDs that were previously answered but are now
    unanswered or now erroring (this is the important check — a
    normalization change touching sample/pesticide/neighborhood
    detection could plausibly break something that worked before)

Run from the same folder as baseline.csv:
    python check_progress.py baseline.csv
"""
import csv
import sys

# All 220 question IDs in the bank
ALL_IDS = (
    [f"A{i:03d}" for i in range(1, 61)]
    + [f"B{i:03d}" for i in range(1, 51)]
    + [f"C{i:03d}" for i in range(1, 31)]
    + [f"D{i:03d}" for i in range(1, 46)]
    + [f"E{i:03d}" for i in range(1, 36)]
)

# The 117 IDs confirmed unanswered right before the Step 6 normalization fix
PREV_UNANSWERED = set("""
A001,A002,A005,A013,A015,A016,A017,A018,A019,A020,A026,A027,A028,A040,A044,
A045,A048,A050,A052,A053,A054,A055,A056,A057,A058,A059,A060,B017,B018,B019,
B020,B021,B022,B023,B024,B028,B029,B031,B032,B033,B034,B036,B041,B045,B046,
B047,B049,B050,C005,C008,C009,C014,C016,C017,C019,C020,C021,C022,C024,C025,
C026,C027,C028,C029,C030,D003,D004,D007,D008,D010,D012,D013,D014,D015,D016,
D018,D020,D021,D022,D023,D024,D030,D032,D033,D035,D036,D037,D038,D039,D040,
D041,D042,D043,D044,D045,E001,E002,E003,E004,E005,E008,E009,E010,E011,E012,
E013,E014,E015,E022,E026,E029,E030,E031,E032,E033,E034,E035
""".replace("\n", "").split(","))

PREV_ANSWERED = set(ALL_IDS) - PREV_UNANSWERED


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "baseline.csv"
    with open(path, encoding="utf-8") as f:
        rows = {r["id"]: r for r in csv.DictReader(f)}

    fixed, still_unanswered, regressions, still_ok, missing = [], [], [], [], []

    for qid in ALL_IDS:
        if qid not in rows:
            missing.append(qid)
            continue
        status = rows[qid]["status"]
        was_unanswered = qid in PREV_UNANSWERED

        if was_unanswered:
            if status == "ok":
                fixed.append(qid)
            else:
                still_unanswered.append(qid)
        else:
            if status == "ok":
                still_ok.append(qid)
            else:
                regressions.append((qid, status, rows[qid].get("error", "")))

    print(f"Previously unanswered (117), now FIXED: {len(fixed)}")
    print(f"  {', '.join(fixed) if fixed else '(none)'}\n")

    print(f"Previously unanswered (117), STILL unanswered: {len(still_unanswered)}")
    print(f"  {', '.join(still_unanswered)}\n")

    print(f"Previously answered (103), still OK: {len(still_ok)}")

    print(f"\n*** REGRESSIONS (previously answered, now broken): {len(regressions)} ***")
    if regressions:
        for qid, status, err in regressions:
            print(f"  [{qid}] status={status} error={err}")
    else:
        print("  None. Good.")

    if missing:
        print(f"\nIDs missing from baseline.csv: {missing}")


if __name__ == "__main__":
    main()
