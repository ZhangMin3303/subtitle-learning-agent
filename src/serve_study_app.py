"""Local-only HTTP service. Report approval only after an atomic CSV write."""
from __future__ import annotations
import argparse
import csv
import json
import os
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from ass_parser import PROJECT_ROOT
REVIEW_CSV=PROJECT_ROOT/"data/review/hardsub_ocr_review.csv"
class ReviewStore:
    def __init__(self,path: Path):
        self.path=path
        self.lock=threading.RLock()
    def read(self):
        with self.lock:
            if not self.path.is_file():
                return [],[]
            with self.path.open(encoding="utf-8-sig",newline="") as f:
                reader=csv.DictReader(f)
                return list(reader.fieldnames or []),list(reader)
    def update(self,payload: dict):
        index=payload.get("index")
        if isinstance(index,bool) or not isinstance(index,int) or index<1:
            raise ValueError("index must be a positive integer")
        if type(payload.get("approved")) is not bool:
            raise ValueError("approved must be a JSON boolean")
        text=payload.get("corrected_japanese_text")
        notes=payload.get("notes","")
        if not isinstance(text,str) or not isinstance(notes,str):
            raise ValueError("text and notes must be strings")
        text=text.strip()
        if payload["approved"] and not text:
            raise ValueError("Approval requires non-empty corrected text")
        if payload.get("review_state") not in ("","yes","problem",None):
            raise ValueError("Invalid review state")
        if payload["approved"] and payload.get("review_state")=="problem":
            raise ValueError("Problem status cannot be approved")
        with self.lock:
            fields,rows=self.read()
            row=next((r for r in rows if r.get("index")==str(index)),None)
            if row is None:
                raise KeyError(index)
            row.update(corrected_japanese_text=text,notes=notes,
                approved="yes" if payload["approved"] else ("problem" if payload.get("review_state")=="problem" else ""))
            fd,name=tempfile.mkstemp(prefix=".review-",suffix=".tmp",dir=self.path.parent)
            try:
                with os.fdopen(fd,"w",encoding="utf-8-sig",newline="") as f:
                    writer=csv.DictWriter(f,fieldnames=fields)
                    writer.writeheader();writer.writerows(rows);f.flush();os.fsync(f.fileno())
                os.replace(name,self.path)
            finally:
                Path(name).unlink(missing_ok=True)
            return dict(row)
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,store: ReviewStore,directory: str,**kwargs):
        self.store=store
        super().__init__(*args,directory=directory,**kwargs)
    def reply(self,status,value):
        body=json.dumps(value,ensure_ascii=False).encode("utf-8")
        self.send_response(status);self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(body)))
        self.end_headers();self.wfile.write(body)
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=="/api/hardsub-review":
            self.reply(200,{"rows":self.store.read()[1]})
        elif path=="/":
            self.send_response(302);self.send_header("Location","/web/");self.end_headers()
        elif path.startswith(("/web/","/data/")):
            super().do_GET()
        else:
            self.send_error(404)
    def do_POST(self):
        if urlsplit(self.path).path!="/api/hardsub-review":
            self.reply(404,{"error":"Unknown endpoint"});return
        origin=self.headers.get("Origin")
        if origin and origin!="http://"+self.headers.get("Host",""):
            self.reply(403,{"error":"Cross-origin write refused"});return
        try:
            length=int(self.headers.get("Content-Length","0"))
            if not 0<length<=65536:
                raise ValueError("Invalid request size")
            payload=json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload,dict):
                raise ValueError("Expected a JSON object")
            row=self.store.update(payload)
            self.reply(200,{"row":row,"saved_to_csv":True})
        except KeyError:
            self.reply(404,{"error":"Review index not found"})
        except (ValueError,UnicodeError) as exc:
            self.reply(400,{"error":str(exc)})
        except OSError:
            self.reply(500,{"error":"CSV save failed; approval was not committed"})
def make_server(port=8765,review_csv=REVIEW_CSV,root=PROJECT_ROOT):
    return ThreadingHTTPServer(("127.0.0.1",port),partial(Handler,store=ReviewStore(Path(review_csv)),directory=str(root)))
def main():
    p=argparse.ArgumentParser(description="Serve the local learning prototype.")
    p.add_argument("--port",type=int,default=8765)
    p.add_argument("--review-csv",type=Path,default=REVIEW_CSV)
    a=p.parse_args();server=make_server(a.port,a.review_csv)
    print(f"Local prototype: http://127.0.0.1:{server.server_port}/web/",flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
if __name__=="__main__":
    main()
