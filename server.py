import argparse
import atexit

from flask import Flask, jsonify, request

from frankenstein_queue import FrankensteinQueue


def create_app(queue):
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/push")
    def push():
        body = request.get_json(silent=True)
        if body is None:
            return jsonify({"error": "request body must be JSON"}), 400
        if body.get("item") is None:
            return jsonify({"error": "'item' is required"}), 400
        priority = body.get("priority", 0)
        delay = body.get("delay", 0)
        if not isinstance(priority, (int, float)):
            return jsonify({"error": "'priority' must be a number"}), 400
        if not isinstance(delay, (int, float)) or delay < 0:
            return jsonify({"error": "'delay' must be a non-negative number"}), 400
        seq = queue.push(body["item"], priority=priority, delay=delay)
        return jsonify({"seq": seq}), 201

    @app.post("/pop")
    def pop():
        item = queue.pop()
        if item is None:
            return jsonify({"error": "no message available"}), 404
        return jsonify({"item": item})

    @app.get("/size")
    def size():
        return jsonify({"size": queue.size()})

    @app.get("/next-available")
    def next_available():
        return jsonify({"next_available_at": queue.next_available_at()})

    @app.post("/compact")
    def compact():
        queue.compact()
        return jsonify({"status": "compacted"})

    return app


def main():
    parser = argparse.ArgumentParser(description="FrankensteinQueue HTTP server")
    parser.add_argument("--mode", choices=["fifo", "lifo"], default="fifo")
    parser.add_argument("--priority", action="store_true",
                        help="pop highest-priority messages first")
    parser.add_argument("--log-path", default="queue.log",
                        help="durable log file (use --no-log to disable)")
    parser.add_argument("--no-log", action="store_true",
                        help="run in-memory only, no persistence")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    log_path = None if args.no_log else args.log_path
    queue = FrankensteinQueue(mode=args.mode, use_priority=args.priority,
                              log_path=log_path)
    atexit.register(queue.close)

    app = create_app(queue)
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
