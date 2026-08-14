import argparse
import sys
import time

import requests


def push(base_url, item, priority=0, delay=0):
    resp = requests.post(f"{base_url}/push",
                         json={"item": item, "priority": priority, "delay": delay})
    resp.raise_for_status()
    return resp.json()["seq"]


def pop(base_url):
    resp = requests.post(f"{base_url}/pop")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()["item"]


def get_size(base_url):
    resp = requests.get(f"{base_url}/size")
    resp.raise_for_status()
    return resp.json()["size"]


def next_available_at(base_url):
    resp = requests.get(f"{base_url}/next-available")
    resp.raise_for_status()
    return resp.json()["next_available_at"]


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def cmd_produce(args):
    seq = push(args.url, args.item, priority=args.priority, delay=args.delay)
    log(f"pushed seq={seq} item={args.item!r} "
        f"priority={args.priority} delay={args.delay}s")


def cmd_work(args):
    log(f"worker '{args.name}' started, polling {args.url}")
    while True:
        item = pop(args.url)
        if item is not None:
            log(f"worker '{args.name}' processing: {item!r}")
            time.sleep(args.work_time)  # pretend the job takes a moment
            continue
        unlock_time = next_available_at(args.url)
        if unlock_time is not None:
            wait = max(0, unlock_time - time.time())
            log(f"queue empty, next delayed message in {wait:.1f}s — waiting")
            time.sleep(wait + 0.05)
        elif args.exit_when_empty:
            log(f"worker '{args.name}' done: queue is empty")
            return
        else:
            time.sleep(args.poll_interval)


def cmd_demo(args):
    log("--- 1. producing jobs ---")
    push(args.url, "send newsletter to alice")
    push(args.url, "send newsletter to bob")
    push(args.url, "URGENT: reset carol's password", priority=5)
    push(args.url, "send newsletter to dave")
    push(args.url, f"reminder email (delayed {args.demo_delay}s)",
         delay=args.demo_delay)
    log(f"pushed 5 jobs, queue size is now {get_size(args.url)}")

    log("--- 2. draining ready jobs (watch the order) ---")
    while (item := pop(args.url)) is not None:
        log(f"processing: {item!r}")

    log("--- 3. waiting for the delayed job ---")
    args.exit_when_empty = True
    args.name = "demo"
    args.work_time = 0.0
    cmd_work(args)

    log("demo complete — restart the server and rerun step 2 style pops "
        "to see pending jobs survive (durability)")


def main():
    parser = argparse.ArgumentParser(
        description="Example client for the FrankensteinQueue HTTP server")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("produce", help="push a single job")
    p.add_argument("item")
    p.add_argument("--priority", type=int, default=0)
    p.add_argument("--delay", type=float, default=0)
    p.set_defaults(func=cmd_produce)

    w = sub.add_parser("work", help="pop and process jobs in a loop")
    w.add_argument("--name", default="worker-1")
    w.add_argument("--work-time", type=float, default=0.3,
                   help="seconds to 'process' each job")
    w.add_argument("--poll-interval", type=float, default=1.0,
                   help="seconds between polls when the queue is empty")
    w.add_argument("--exit-when-empty", action="store_true",
                   help="stop instead of polling once the queue is drained")
    w.set_defaults(func=cmd_work)

    d = sub.add_parser("demo", help="scripted end-to-end walkthrough")
    d.add_argument("--demo-delay", type=float, default=4,
                   help="delay in seconds for the delayed demo job")
    d.set_defaults(func=cmd_demo)

    args = parser.parse_args()
    try:
        requests.get(f"{args.url}/health", timeout=2).raise_for_status()
    except requests.RequestException:
        sys.exit(f"error: no server at {args.url} — start it with: "
                 "python server.py --priority")
    args.func(args)


if __name__ == "__main__":
    main()
