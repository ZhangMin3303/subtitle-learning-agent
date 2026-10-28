from __future__ import annotations
import csv
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from ass_parser import parse_ass_file,make_learning_records,normalize_ass_text,classify_content
from media_utils import ass_time_to_ms,project_path
from review_policy import apply_asr,apply_ocr
from build_asr_draft import build_draft_records
from build_asr_learning_dataset import build_learning_dataset
from serve_study_app import ReviewStore,make_server
from hardsub_ocr_extract import parse_regions,parse_sample_ratios,make_record

def draft():
    return [{"index":7,"start":"0:00:00.00","end":"0:00:04.50","japanese_text_asr":"原文です。",
        "chinese_text":"原文","source_type":"asr","audio_file_name":"clip_0007.wav"}]
def write_csv(path,rows):
    fields=["index","corrected_japanese_text","approved","notes"]
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

class PipelineTests(unittest.TestCase):
    def test_authored_ass_and_heuristics(self):
        raw=parse_ass_file(ROOT/"examples/self_authored.ass")
        merged=make_learning_records(raw)
        self.assertEqual((len(raw),len(merged)),(6,3))
        self.assertTrue(all(r["language_type"]=="bilingual" for r in merged))
        self.assertEqual(normalize_ass_text(r"{\i1}はい\Nいいえ"),"はい いいえ")
        self.assertEqual(classify_content(["OPJP"],"歌です","japanese")[0],"lyrics")
        self.assertEqual(classify_content(["screen"],"入口","chinese")[0],"screen_text")
    def test_times_and_crop_configuration(self):
        self.assertEqual(ass_time_to_ms("1:02:03.45"),3723450)
        for bad in ("0:90:00.00","-1:00:00.00","oops"):
            with self.assertRaises(ValueError):ass_time_to_ms(bad)
        with self.assertRaises(ValueError):project_path(ROOT.parent/"outside.mp4")
        for bad in ("box=0.8,0.9,0.1,0.2","box=-1,0,1,1"):
            with self.assertRaises(ValueError):parse_regions(bad)
        with self.assertRaises(ValueError):parse_sample_ratios("")
    def test_asr_approval_gate(self):
        for status,text,expected in [("pending","変更です。","原文です。"),("approved","","原文です。"),
                                     ("approved","変更です。","変更です。")]:
            row={"review_status":status,"japanese_text_corrected":text}
            out=apply_asr(draft(),{7:row})[0]
            self.assertEqual(out["japanese_text_final"],expected)
            self.assertEqual(out["needs_human_review"],not(status=="approved" and bool(text)))
            self.assertEqual(out["index"],7)
    def test_ocr_gate_and_revocation(self):
        base=apply_asr(draft(),{})
        for flag,text in [("","OCRです。"),("yes","")]:
            out=apply_ocr(base,{7:{"approved":flag,"corrected_japanese_text":text}})[0]
            self.assertEqual(out["japanese_text_final"],"原文です。")
            self.assertTrue(out["needs_human_review"])
        rows={7:{"approved":"yes","corrected_japanese_text":"OCRです。"}}
        out=apply_ocr(base,rows)
        self.assertEqual(out[0]["source_type"],"hardsub_ocr_reviewed")
        self.assertEqual(build_learning_dataset(out)[0]["source_quality"],"human_reviewed")
        rows[7]["approved"]=""
        # Rebuild from draft + current CSVs, not from a previous reviewed artifact.
        revoked=apply_ocr(apply_asr(draft(),{}),rows)[0]
        self.assertEqual(revoked["japanese_text_final"],"原文です。")
        self.assertTrue(revoked["needs_human_review"])
    def test_model_status_does_not_approve_text(self):
        record=make_record(index=7,clip={},learning={},frame_path=ROOT/"data/frame.jpg",
            crop_path=ROOT/"data/crop.png",processed_path=ROOT/"data/processed.png",
            backend="easyocr",ocr_text="はい。",confidence=1.0,raw_ocr=[],status="ok")
        self.assertTrue(record["needs_human_review"])

    def test_report_shapes_and_stable_indices(self):
        result={"source_index":7,"start":"0:00:00.00","end":"0:00:04.50","duration_ms":4500,
                "asr_text":"はい。","chinese_text":"是的","audio_file_name":"clip_0007.wav"}
        report={"model":"tiny","results":[result]}
        self.assertEqual(build_draft_records(report,None)[0]["index"],7)
        self.assertEqual(build_draft_records({"model_reports":[report]},"tiny")[0]["index"],7)
        fixture=apply_asr([{**draft()[0],"source_type":"demo_fixture"}],{})
        item=build_learning_dataset(fixture)[0]
        self.assertEqual((item["index"],item["source_quality"]),(7,"demo_fixture"))

class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"review.csv"
        write_csv(self.path,[{"index":str(i),"corrected_japanese_text":"","approved":"","notes":""} for i in (7,11)])
        self.store=ReviewStore(self.path)
    def tearDown(self):self.temp.cleanup()
    def payload(self,index=7,**updates):
        return {"index":index,"corrected_japanese_text":"はい。","approved":True,"notes":"test",**updates}
    def test_atomic_failure_and_parallel_updates(self):
        before=self.path.read_bytes()
        with patch("serve_study_app.os.replace",side_effect=OSError("simulated disk failure")):
            with self.assertRaises(OSError):self.store.update(self.payload())
        self.assertEqual(self.path.read_bytes(),before)
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(self.store.update,[self.payload(7),self.payload(11)]))
        self.assertTrue(all(r["approved"]=="yes" for r in self.store.read()[1]))
    def test_http_validation_and_save(self):
        server=make_server(0,self.path,Path(self.temp.name))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f"http://127.0.0.1:{server.server_port}/api/hardsub-review"
        def post(payload,origin=None):
            req=Request(url,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json",**({"Origin":origin} if origin else {})})
            try:
                with urlopen(req,timeout=5) as r:return r.status,json.load(r)
            except HTTPError as e:return e.code,json.load(e)
        try:
            self.assertEqual(post(self.payload(approved="false"))[0],400)
            self.assertEqual(post(self.payload(corrected_japanese_text=" "))[0],400)
            self.assertEqual(post(self.payload(99))[0],404)
            self.assertEqual(post(self.payload(),origin="https://example.invalid")[0],403)
            self.assertEqual(post([])[0],400)
            code,result=post(self.payload())
            self.assertEqual(code,200);self.assertTrue(result["saved_to_csv"])
            self.assertEqual(result["row"]["approved"],"yes")
            self.assertEqual(post(self.payload(approved=False))[0],200)
            self.assertEqual(self.store.read()[1][0]["approved"],"")
        finally:server.shutdown();server.server_close();thread.join()
if __name__=="__main__":
    unittest.main()
