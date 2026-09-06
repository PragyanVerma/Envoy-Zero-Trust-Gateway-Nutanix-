from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def index(path):
    return jsonify({"message": "You have been rate limited - routed to SANDBOX"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
