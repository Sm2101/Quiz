# data_store.py
import json
import os
from typing import Dict, List

QUIZ_STORE = "quizzes.json"
RESULT_STORE = "results.json"

def _read_json(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def save_quiz(quiz: Dict):
    quizzes = _read_json(QUIZ_STORE)
    # if exists replace, else append
    found = False
    for i, q in enumerate(quizzes):
        if q.get("id") == quiz.get("id"):
            quizzes[i] = quiz
            found = True
            break
    if not found:
        quizzes.append(quiz)
    _write_json(QUIZ_STORE, quizzes)

def load_quizzes() -> List[Dict]:
    return _read_json(QUIZ_STORE)

def save_result(quiz_id: str, quiz_title: str, score: int, total: int):
    results = _read_json(RESULT_STORE)
    results.append({
        "quiz_id": quiz_id,
        "quiz_title": quiz_title,
        "score": score,
        "total": total,
        "timestamp": __import__("time").time()
    })
    _write_json(RESULT_STORE, results)

def load_results():
    return _read_json(RESULT_STORE)
