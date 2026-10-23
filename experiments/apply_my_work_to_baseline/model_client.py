"""Resumable, accounted Groq calls; quota failures never become SQL abstentions."""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from contextlib import closing
from groq import Groq, APIStatusError, APIConnectionError
from settings import MODEL


class RunBlocked(RuntimeError):
    pass


def duration_seconds(value):
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        units = {"h":3600, "m":60, "s":1, "ms":0.001}
        return sum(float(number)*units[unit] for number, unit in re.findall(r"([\d.]+)(ms|h|m|s)", value))


class ModelClient:
    def __init__(self, run_dir, model=MODEL, reasoning_effort="none", sql_tokens=900, rewrite_tokens=256):
        self.run_dir = Path(run_dir)
        self.model = model
        self.effort = reasoning_effort
        self.sql_tokens = sql_tokens
        self.rewrite_tokens = rewrite_tokens
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"), timeout=60, max_retries=0)
        self.cache = self.run_dir / "model_calls.sqlite"
        with closing(sqlite3.connect(self.cache)) as con:
            con.execute("CREATE TABLE IF NOT EXISTS calls (key TEXT PRIMARY KEY, response TEXT NOT NULL)")
            con.commit()
        self.headers = {}

    def _event(self, event):
        event["timestamp"] = time.time()
        with (self.run_dir / "api_events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event)+"\n")

    def call(self, messages, stage, question_id, max_tokens=900):
        params = {"model": self.model, "messages": messages, "temperature": 0,
                  "max_completion_tokens": max_tokens, "seed": 42,
                  "reasoning_effort": self.effort, "reasoning_format": "hidden"}
        key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
        with closing(sqlite3.connect(self.cache)) as con:
            row = con.execute("SELECT response FROM calls WHERE key=?", (key,)).fetchone()
        if row:
            return json.loads(row[0])
        print(f"API {stage}: {question_id} (reasoning={self.effort}, max_tokens={max_tokens})", flush=True)
        estimated = sum(len(m["content"]) for m in messages)//3+max_tokens
        if self.headers and estimated > int(self.headers.get("x-ratelimit-remaining-tokens", 99999999)):
            delay = min(60, duration_seconds(self.headers.get("x-ratelimit-reset-tokens"))+1)
            if delay > 1:
                print(f"Rate pacing: wait {delay:.1f}s before {stage}", flush=True)
                time.sleep(delay)
        for attempt in range(8):
            try:
                raw = self.client.chat.completions.with_raw_response.create(**params)
                response = raw.parse()
                choice = response.choices[0]
                self.headers = {k:v for k,v in raw.headers.items() if k.startswith("x-ratelimit") or k=="retry-after"}
                result = {"content": choice.message.content or "", "finish_reason": choice.finish_reason,
                          "usage": response.usage.model_dump(), "rate_limit_headers": self.headers,
                          "request_hash": key, "model": response.model}
                with closing(sqlite3.connect(self.cache)) as con:
                    con.execute("INSERT INTO calls VALUES (?,?)", (key, json.dumps(result)))
                    con.commit()
                self._event({"kind":"success", "stage":stage, "question_id":question_id,
                             "usage":result["usage"], "rate_limit_headers":self.headers, "request_hash":key})
                return result
            except APIStatusError as error:
                message = str(error)[:1400]
                headers = {k:v for k,v in error.response.headers.items() if k.startswith("x-ratelimit") or k=="retry-after"}
                self._event({"kind":"api_error", "stage":stage, "question_id":question_id,
                             "status":error.status_code, "message":message, "rate_limit_headers":headers})
                daily = bool(re.search(r"tokens per day|requests per day|\bTPD\b|\bRPD\b", message, re.I))
                delay = duration_seconds(headers.get("retry-after"))
                if error.status_code == 429 and re.search(r"request too large|expected output tokens exceed", message, re.I):
                    raise RunBlocked("Request exceeds account output/input limit; use a compatible profile or raise account quota. "+message) from error
                if error.status_code == 429 and (daily or delay > 120):
                    raise RunBlocked("Daily/account quota exhausted; checkpoints retained. "+message) from error
                if error.status_code == 429 and attempt < 7:
                    wait = min(60, max(delay, 5)+1)
                    print(f"Rate limit: wait {wait:.1f}s", flush=True)
                    time.sleep(wait)
                elif error.status_code >= 500 and attempt < 3:
                    time.sleep(2**attempt)
                else:
                    raise RunBlocked("API configuration/service failure; checkpoint retained. "+message) from error
            except APIConnectionError as error:
                if attempt >= 2:
                    raise RunBlocked("Network connection failed; checkpoint retained") from error
                time.sleep(2**attempt)
        raise RunBlocked("API retry budget exhausted; checkpoint retained")

