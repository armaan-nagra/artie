# FrankensteinQueueMaxxinggg 🧟💪🗣🙏

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python server.py --priority        # terminal 1: priority FIFO on :8000
python client.py demo              # terminal 2: scripted walkthrough
```

The demo pushes 5 jobs (mixed priorities, one delayed) and drains them so you
can watch the ordering rules do their thing:

```
[11:34:40] processing: "URGENT: reset carol's password"    ← priority 5 jumps the line
[11:34:40] processing: 'send newsletter to alice'          ← then FIFO order
[11:34:40] processing: 'send newsletter to bob'
[11:34:40] processing: 'send newsletter to dave'
[11:34:40] queue empty, next delayed message in 3.0s — waiting
[11:34:43] worker 'demo' processing: 'reminder email (delayed 3.0s)'
```

To see durability live: push a few jobs with `python client.py produce "hi"`,
kill the server, restart it, then run
`python client.py work --exit-when-empty` — the jobs come back.

### Server flags

| Flag | Effect |
|---|---|
| `--mode fifo\|lifo` | Base ordering (default `fifo`) |
| `--priority` | Higher-priority messages pop first; mode breaks ties |
| `--log-path PATH` | Durable log location (default `queue.log`) |
| `--no-log` | In-memory only, no persistence |

### API

| Endpoint | Does |
|---|---|
| `POST /push` | Enqueue. Body: `{"item": ..., "priority": 0, "delay": 0}` → `{"seq": n}` |
| `POST /pop` | Dequeue next available message, `404` if none |
| `GET /size` | Messages in queue (ready + delayed) |
| `GET /next-available` | Timestamp when the next delayed message unlocks |
| `POST /compact` | Rewrite the log to only still-pending messages |
| `GET /health` | Liveness check |

```bash
curl -X POST localhost:8000/push -H 'Content-Type: application/json' \
     -d '{"item": "hello", "priority": 5, "delay": 2}'
curl -X POST localhost:8000/pop
```

`client.py` is a worker built on this API: `produce` pushes a job, `work`
polls in a loop (sleeping until the next delayed message instead of
busy-polling), and `demo` runs the scripted tour above.

## Design

- Ready messages live in one heap sorted by
  `(-priority if priority enabled else 0, seq if fifo else -seq)`. This single
  key handles every mode combination: priority first, then sequence number in
  FIFO or LIFO direction.
- Delayed messages wait in a second heap keyed by unlock time, and get moved
  to the ready heap on each operation once their time passes.
- Every push and pop is appended to `queue.log` and fsync'd before memory is
  updated. Startup replays the log to rebuild pending messages; a torn last
  line from a mid-write crash is truncated away, so later appends can't glue
  onto it and corrupt the log. `/compact` rewrites the log through a temp
  file and atomic rename.
- One lock guards the heaps and the log, so log order always matches memory
  order. The fsync is the throughput bottleneck, not the lock.

## Additional questions

**How do you handle replay messages?**
Server crashes are covered: the log is replayed on startup, so pending
messages survive.

**How would you refactor into a Pub/Sub?**
The log is already most of a topic. Add named topics (one log each) and
replace destructive pops with per-subscriber cursors, so every subscriber
sees every message and pop just advances your offset. Compaction then drops
records all cursors have passed.

**With more time, what would you add?**
Automatic compaction: right now the log grows until someone calls
`POST /compact`, so I'd have the server compact itself in the background once
the log passes a size threshold, removing the "someone must remember"
failure mode.

**Why choose this over SQS / RabbitMQ / Pulsar?**
For real production traffic, don't🫡 lol. This wins when those are overkill: it's a
few hundred lines of Python with no cloud account and no ops
burden, and it supports combinations the above don't (SQS has no
priorities or LIFO)

