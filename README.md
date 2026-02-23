# 🐶 DevBuddy

**DevBuddy** is your local AI coding companion.
It analyzes usage, tokens, and workflow patterns from local session data and shows insights in a lightweight browser dashboard — private and easy to run.

---

## ✨ Features

* 📊 Local AI usage analytics
* 💰 Token and cost insights
* 🧠 Session and workflow statistics
* 🔍 Prompt and activity patterns
* ⚡ Lightweight web dashboard
* 🔒 Privacy-first — runs entirely on your machine
* 🖥️ Cross-platform (Linux, Windows, macOS)
* 📦 Single executable distribution (no installation required)

---

## 🚀 Quick Start

### Option 1 — Run Binary (Recommended)

Download the latest release and start DevBuddy:

```bash
./devbuddy
```

Your browser will open automatically.

---

### Option 2 — Run from Source

Requirements:

* Python 3.10+

Install dependencies:

```bash
pip install -r requirements.txt
```

Run:

```bash
python run.py
```

Open:

```
http://127.0.0.1:8765
```

---

## 🏗️ Architecture

DevBuddy is designed to be simple and local-first:

* **Backend:** FastAPI
* **Database:** DuckDB (embedded analytics database)
* **Frontend:** Lightweight HTML + HTMX + Chart.js
* **Packaging:** PyInstaller single binary

No external services. No telemetry.

---

## 📂 Project Structure

```
devbuddy/
│
├── app/
│   ├── main.py
│   ├── routes.py
│   ├── parser/
│   ├── analytics/
│   ├── templates/
│   └── static/
│
├── data/
│   └── devbuddy.duckdb
│
├── run.py
├── requirements.txt
└── README.md
```

---

## 🔒 Privacy

DevBuddy runs completely locally:

* No cloud communication
* No data collection
* No tracking
* Your data stays on your machine

---

## 📦 Build Executable

Create a standalone binary:

```bash
pyinstaller --onefile run.py
```

The output will be available in:

```
dist/
```

---

## 🧠 Use Cases

* Understand AI coding usage
* Track token consumption and costs
* Improve prompting efficiency
* Analyze development workflows
* Personal productivity insights
* Team experimentation (optional future)

---

## 🤝 Contributing

Contributions are welcome!

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

Ideas, bug reports, and discussions are encouraged.

---

## 📜 License

MIT License — see [LICENSE](LICENSE).

---

## 🐕 About the Name

DevBuddy is inspired by the idea of a friendly developer companion — a small helper that watches your workflow and provides useful insights.

---

## ⭐ Support

If you find DevBuddy useful, consider giving the repository a star!
