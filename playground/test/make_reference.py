"""Write test/reference.json with the Python front end (run next to frontend.py and sinhala.py).

    python make_reference.py sentences.txt reference.json
"""
import json, sys
import frontend

out = []
for text in open(sys.argv[1], encoding="utf-8").read().split("\n"):
    record = {"text": text}
    try:
        record["sentences"] = frontend.sentences(frontend.finished(text))
        record["phon"] = []
        for sentence in record["sentences"]:
            try:
                p = frontend.phonemize(sentence)
                record["phon"].append({"ids": list(p.ids), "stress": list(p.stress)})
            except frontend.NothingToPronounce:
                record["phon"].append({"error": "NothingToPronounce"})
    except Exception as error:
        record["error"] = type(error).__name__
    out.append(record)
json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
