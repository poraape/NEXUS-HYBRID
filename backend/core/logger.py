import json, sys, time
def log_event(agent:str, level:str, message:str, meta:dict|None=None):
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent": agent,
        "level": level,
        "message": message,
        "meta": meta or {}
    }
    sys.stdout.write(json.dumps(rec, ensure_ascii=False) + "\n")
    sys.stdout.flush()
