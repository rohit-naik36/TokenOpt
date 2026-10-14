"""Local stand-in for POST /v1/messages, for exercising the n8n workflow without network or spend.

    python fake_anthropic.py --port 8765 --fail-nth 3 --fail-status 529

Returns Messages-shaped JSON with usage and a request-id. Fails the nth request once with --fail-status
(and retry-after 1). Never logs headers or the request body: the x-api-key header is only compared to
--expect-key, and the result is reported as a boolean.
"""
import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

ARGS = None
COUNT = {"n": 0}
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # keep stdout free of request details
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        with LOCK:
            COUNT["n"] += 1
            k = COUNT["n"]
        key_ok = self.headers.get("x-api-key") == ARGS.expect_key
        print(f"request {k}: key_ok={key_ok} cache_control={'cache_control' in json.dumps(body.get('system', ''))} "
              f"has_temperature={'temperature' in body} thinking={body.get('thinking')}", flush=True)
        if k == ARGS.fail_nth:
            self.send_response(ARGS.fail_status)
            self.send_header("content-type", "application/json")
            self.send_header("retry-after", "1")
            self.send_header("request-id", f"req_fake_fail_{k}")
            self.end_headers()
            self.wfile.write(json.dumps({"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}).encode())
            return
        cached = "cache_control" in json.dumps(body.get("system", ""))
        usage = {"input_tokens": 120, "output_tokens": 40,
                 "cache_creation_input_tokens": 300 if cached else 0, "cache_read_input_tokens": 0}
        out = {"id": f"msg_fake_{k}", "type": "message", "role": "assistant", "model": body.get("model"),
               "content": [{"type": "text", "text": json.dumps({"stub": True, "n": k})}],
               "stop_reason": "end_turn", "stop_sequence": None, "usage": usage}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("request-id", f"req_fake_{k}")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--fail-nth", type=int, default=0)
    ap.add_argument("--fail-status", type=int, default=529)
    ap.add_argument("--expect-key", default="fake-test-key")
    ARGS = ap.parse_args()
    HTTPServer(("0.0.0.0", ARGS.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
