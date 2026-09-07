import json
import hmac
import hashlib
from pathlib import Path
import random
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse

from ..auth import require_admin
from ..config import get_settings
from ..db import get_connection
from ..repositories import now_utc
from ..schemas import (
    PublicSundayQuizDetailOut,
    PublicSundayQuizSummaryOut,
    SundayQuizAttemptIn,
    SundayQuizAttemptOut,
    SundayQuizCreate,
    SundayQuizOut,
    SundayQuizPublicationUpdate,
    SundayQuizQuestionOut,
    SundayQuizQuestionUpdate,
    SundayQuizUpdate,
)
from ..storage import get_object_storage


admin_router = APIRouter(prefix="/sunday-quizzes", tags=["sunday-quizzes"], dependencies=[Depends(require_admin)])
public_router = APIRouter(prefix="/public/sunday-quizzes", tags=["public-sunday-quizzes"])


QUESTION_COUNT = 10
ADMIN_ASSET_CACHE_CONTROL = "private, no-store"
PUBLIC_ASSET_REDIRECT_CACHE_CONTROL = "public, max-age=300"
PUBLIC_ASSET_FILE_CACHE_CONTROL = "public, max-age=86400"


def _loads_json(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        return json.loads(value)
    return value


def _option_id(question_id: str, answer: str) -> str:
    secret = get_settings().session_secret or "ayqm-local-sunday-quiz-options"
    digest = hmac.new(secret.encode("utf-8"), f"{question_id}\0{answer}".encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:24]


def _answer_options(question: dict, *, shuffle: bool) -> list[dict]:
    options = [{"id": _option_id(question["id"], question["correct_answer"]), "text": question["correct_answer"]}]
    options.extend({"id": _option_id(question["id"], answer), "text": answer} for answer in question["incorrect_answers"])
    if shuffle:
        random.SystemRandom().shuffle(options)
    return options


def _asset_url(asset_id: str, public: bool) -> str:
    prefix = "/public/sunday-quizzes" if public else "/sunday-quizzes"
    return f"{prefix}/assets/{asset_id}"


def _asset_map(conn, quiz_id: str, *, public: bool) -> dict[tuple[str | None, str], dict]:
    rows = conn.execute(
        """
        SELECT id, question_id, kind, object_key, content_type, size_bytes
        FROM sunday_quiz_assets
        WHERE quiz_id = ?
        ORDER BY created_at
        """,
        [quiz_id],
    ).fetchall()
    assets: dict[tuple[str | None, str], dict] = {}
    for asset_id, question_id, kind, object_key, content_type, size_bytes in rows:
        assets[(question_id, kind)] = {
            "id": asset_id,
            "question_id": question_id,
            "kind": kind,
            "object_key": object_key,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "url": _asset_url(asset_id, public),
        }
    return assets


def _question_from_row(row, assets: dict[tuple[str | None, str], dict], *, include_answer: bool) -> dict:
    question_id = row[0]
    item = {
        "id": question_id,
        "position": row[2],
        "question": row[3],
        "correct_answer": row[7],
        "incorrect_answers": _loads_json(row[8], []),
        "question_image_url": (assets.get((question_id, "question")) or {}).get("url"),
    }
    if include_answer:
        item["explanation"] = row[6]
        item["answer_image_url"] = (assets.get((question_id, "answer")) or {}).get("url")
    return item


def _quiz_from_row(conn, row, *, public: bool, include_answer: bool = True) -> dict:
    assets = _asset_map(conn, row[0], public=public)
    questions = conn.execute(
        """
        SELECT id, quiz_id, position, question, options, correct_option, explanation, correct_answer, incorrect_answers
        FROM sunday_quiz_questions
        WHERE quiz_id = ?
        ORDER BY position
        """,
        [row[0]],
    ).fetchall()
    return {
        "id": row[0],
        "quiz_date": row[1],
        "theme": row[2],
        "status": row[3],
        "cover_image_url": (assets.get((None, "cover")) or {}).get("url"),
        "question_count": len(questions),
        "questions": [_question_from_row(item, assets, include_answer=include_answer) for item in questions],
        "created_at": row[4],
        "updated_at": row[5],
    }


def _get_quiz(conn, quiz_id: str, *, public: bool = False) -> dict | None:
    filters = ["id = ?"]
    params = [quiz_id]
    if public:
        filters.append("status = 'published'")
    row = conn.execute(
        f"""
        SELECT id, quiz_date, theme, status, created_at, updated_at
        FROM sunday_quizzes
        WHERE {' AND '.join(filters)}
        """,
        params,
    ).fetchone()
    if row is None:
        return None
    return _quiz_from_row(conn, row, public=public, include_answer=not public)


def _validate_publishable(quiz: dict) -> list[str]:
    errors: list[str] = []
    if not quiz["theme"].strip():
        errors.append("theme is required")
    if len(quiz["questions"]) != QUESTION_COUNT:
        errors.append("exactly 10 questions are required")
    for question in quiz["questions"]:
        prefix = f"question {question['position']}"
        if not (question.get("question") or "").strip():
            errors.append(f"{prefix} text is required")
        correct_answer = (question.get("correct_answer") or "").strip()
        incorrect_answers = [answer.strip() for answer in question.get("incorrect_answers", [])]
        if not correct_answer:
            errors.append(f"{prefix} correct answer is required")
        if len(incorrect_answers) != 3 or any(not answer for answer in incorrect_answers):
            errors.append(f"{prefix} needs 3 incorrect answers")
        answers = [correct_answer, *incorrect_answers]
        if len({answer.casefold() for answer in answers if answer}) != 4:
            errors.append(f"{prefix} answers must be unique")
    return errors


@admin_router.get("", response_model=list[SundayQuizOut])
def list_admin_sunday_quizzes() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, quiz_date, theme, status, created_at, updated_at
            FROM sunday_quizzes
            ORDER BY quiz_date DESC, created_at DESC
            """
        ).fetchall()
        return [_quiz_from_row(conn, row, public=False) for row in rows]


@admin_router.post("", response_model=SundayQuizOut, status_code=status.HTTP_201_CREATED)
def create_sunday_quiz(request: SundayQuizCreate) -> dict:
    quiz_id = str(uuid4())
    timestamp = now_utc()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sunday_quizzes VALUES (?, ?, ?, 'draft', ?, ?)",
            [quiz_id, request.quiz_date, request.theme.strip(), timestamp, timestamp],
        )
        for position in range(1, QUESTION_COUNT + 1):
            conn.execute(
                """
                INSERT INTO sunday_quiz_questions (
                    id, quiz_id, position, question, options, correct_option,
                    correct_answer, incorrect_answers, explanation, created_at, updated_at
                )
                VALUES (?, ?, ?, NULL, '[]'::JSON, NULL, NULL, '[]'::JSON, NULL, ?, ?)
                """,
                [str(uuid4()), quiz_id, position, timestamp, timestamp],
            )
        quiz = _get_quiz(conn, quiz_id)
    if quiz is None:
        raise RuntimeError(f"Sunday quiz was not created: {quiz_id}")
    return quiz


@admin_router.get("/{quiz_id}", response_model=SundayQuizOut)
def read_admin_sunday_quiz(quiz_id: str) -> dict:
    with get_connection() as conn:
        quiz = _get_quiz(conn, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Sunday quiz not found")
    return quiz


@admin_router.patch("/{quiz_id}", response_model=SundayQuizOut)
def update_sunday_quiz(quiz_id: str, request: SundayQuizUpdate) -> dict:
    changes = request.model_dump(exclude_unset=True)
    assignments = []
    values = []
    if "quiz_date" in changes:
        assignments.append("quiz_date = ?")
        values.append(changes["quiz_date"])
    if "theme" in changes:
        theme = changes["theme"].strip()
        if not theme:
            raise HTTPException(status_code=422, detail="theme is required")
        assignments.append("theme = ?")
        values.append(theme)
    if assignments:
        assignments.append("updated_at = ?")
        values.append(now_utc())
        with get_connection() as conn:
            conn.execute(f"UPDATE sunday_quizzes SET {', '.join(assignments)} WHERE id = ?", [*values, quiz_id])
            quiz = _get_quiz(conn, quiz_id)
    else:
        with get_connection() as conn:
            quiz = _get_quiz(conn, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Sunday quiz not found")
    return quiz


@admin_router.patch("/{quiz_id}/questions/{question_id}", response_model=SundayQuizQuestionOut)
def update_sunday_quiz_question(quiz_id: str, question_id: str, request: SundayQuizQuestionUpdate) -> dict:
    changes = request.model_dump(exclude_unset=True)
    assignments = []
    values = []
    if "question" in changes:
        assignments.append("question = ?")
        values.append(changes["question"].strip() if changes["question"] else None)
    if "correct_answer" in changes:
        assignments.append("correct_answer = ?")
        values.append(changes["correct_answer"].strip() if changes["correct_answer"] else None)
    if "incorrect_answers" in changes:
        incorrect_answers = [answer.strip() for answer in (changes["incorrect_answers"] or [])]
        assignments.append("incorrect_answers = ?::JSON")
        values.append(json.dumps(incorrect_answers))
    if "explanation" in changes:
        assignments.append("explanation = ?")
        values.append(changes["explanation"].strip() if changes["explanation"] else None)
    with get_connection() as conn:
        exists = conn.execute(
            "SELECT COUNT(*) FROM sunday_quiz_questions WHERE id = ? AND quiz_id = ?",
            [question_id, quiz_id],
        ).fetchone()[0]
        if not exists:
            raise HTTPException(status_code=404, detail="Sunday quiz question not found")
        if assignments:
            assignments.append("updated_at = ?")
            values.append(now_utc())
            conn.execute(
                f"UPDATE sunday_quiz_questions SET {', '.join(assignments)} WHERE id = ? AND quiz_id = ?",
                [*values, question_id, quiz_id],
            )
            conn.execute("UPDATE sunday_quizzes SET updated_at = ? WHERE id = ?", [now_utc(), quiz_id])
        quiz = _get_quiz(conn, quiz_id)
    return next(question for question in quiz["questions"] if question["id"] == question_id)


@admin_router.post("/{quiz_id}/assets", response_model=SundayQuizOut)
def upload_sunday_quiz_asset(
    quiz_id: str,
    kind: str = Form(...),
    file: UploadFile = File(...),
    question_id: str | None = Form(default=None),
) -> dict:
    if kind not in {"cover", "question", "answer"}:
        raise HTTPException(status_code=422, detail="kind must be cover, question, or answer")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=422, detail="Sunday quiz assets must be images")
    with get_connection() as conn:
        quiz = _get_quiz(conn, quiz_id)
        if quiz is None:
            raise HTTPException(status_code=404, detail="Sunday quiz not found")
        if kind in {"question", "answer"}:
            exists = conn.execute(
                "SELECT COUNT(*) FROM sunday_quiz_questions WHERE id = ? AND quiz_id = ?",
                [question_id, quiz_id],
            ).fetchone()[0]
            if not question_id or not exists:
                raise HTTPException(status_code=422, detail="question_id is required for question assets")

    suffix = Path(file.filename or "image").suffix.lower()
    suffix = suffix if suffix and len(suffix) <= 8 else ".image"
    asset_id = str(uuid4())
    object_key = f"sunday-quizzes/{quiz_id}/{asset_id}{suffix}"
    storage = get_object_storage(get_settings())
    stored = storage.put_stream(object_key, file.file, file.content_type)
    timestamp = now_utc()
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM sunday_quiz_assets WHERE quiz_id = ? AND kind = ? AND question_id IS NOT DISTINCT FROM ?",
            [quiz_id, kind, question_id],
        )
        conn.execute(
            """
            INSERT INTO sunday_quiz_assets
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                asset_id,
                quiz_id,
                question_id,
                kind,
                object_key,
                stored.get("content_type") or file.content_type,
                stored.get("size"),
                timestamp,
            ],
        )
        conn.execute("UPDATE sunday_quizzes SET updated_at = ? WHERE id = ?", [timestamp, quiz_id])
        quiz = _get_quiz(conn, quiz_id)
    return quiz


@admin_router.patch("/{quiz_id}/publication", response_model=SundayQuizOut)
def update_sunday_quiz_publication(quiz_id: str, request: SundayQuizPublicationUpdate) -> dict:
    with get_connection() as conn:
        quiz = _get_quiz(conn, quiz_id)
        if quiz is None:
            raise HTTPException(status_code=404, detail="Sunday quiz not found")
        if request.is_published:
            errors = _validate_publishable(quiz)
            if errors:
                raise HTTPException(status_code=422, detail={"publish_errors": errors})
        conn.execute(
            "UPDATE sunday_quizzes SET status = ?, updated_at = ? WHERE id = ?",
            ["published" if request.is_published else "draft", now_utc(), quiz_id],
        )
        return _get_quiz(conn, quiz_id)


@admin_router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sunday_quiz(quiz_id: str) -> None:
    settings = get_settings()
    storage = get_object_storage(settings)
    with get_connection() as conn:
        if _get_quiz(conn, quiz_id) is None:
            raise HTTPException(status_code=404, detail="Sunday quiz not found")
        keys = [row[0] for row in conn.execute("SELECT object_key FROM sunday_quiz_assets WHERE quiz_id = ?", [quiz_id]).fetchall()]
        for key in keys:
            storage.delete_object(key)
        conn.execute("DELETE FROM sunday_quiz_attempts WHERE quiz_id = ?", [quiz_id])
        conn.execute("DELETE FROM sunday_quiz_assets WHERE quiz_id = ?", [quiz_id])
        conn.execute("DELETE FROM sunday_quiz_questions WHERE quiz_id = ?", [quiz_id])
        conn.execute("DELETE FROM sunday_quizzes WHERE id = ?", [quiz_id])


@public_router.get("", response_model=list[PublicSundayQuizSummaryOut])
def list_public_sunday_quizzes() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, quiz_date, theme, status, created_at, updated_at
            FROM sunday_quizzes
            WHERE status = 'published'
            ORDER BY quiz_date DESC, created_at DESC
            """
        ).fetchall()
        return [
            {key: value for key, value in _quiz_from_row(conn, row, public=True, include_answer=False).items() if key in {"id", "quiz_date", "theme", "question_count", "cover_image_url"}}
            for row in rows
        ]


@public_router.get("/{quiz_id}", response_model=PublicSundayQuizDetailOut)
def read_public_sunday_quiz(quiz_id: str) -> dict:
    with get_connection() as conn:
        quiz = _get_quiz(conn, quiz_id, public=True)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Sunday quiz not found")
    return {
        "id": quiz["id"],
        "quiz_date": quiz["quiz_date"],
        "theme": quiz["theme"],
        "question_count": quiz["question_count"],
        "cover_image_url": quiz["cover_image_url"],
        "questions": [
            {
                "id": question["id"],
                "position": question["position"],
                "question": question["question"],
                "options": _answer_options(question, shuffle=True),
                "question_image_url": question["question_image_url"],
            }
            for question in quiz["questions"]
        ],
    }


@public_router.post("/{quiz_id}/attempts", response_model=SundayQuizAttemptOut)
def submit_sunday_quiz_attempt(quiz_id: str, request: SundayQuizAttemptIn) -> dict:
    with get_connection() as conn:
        quiz = _get_quiz(conn, quiz_id, public=True)
        if quiz is None:
            raise HTTPException(status_code=404, detail="Sunday quiz not found")
        assets = _asset_map(conn, quiz_id, public=True)
        rows = conn.execute(
            """
            SELECT id, quiz_id, position, question, options, correct_option, explanation, correct_answer, incorrect_answers
            FROM sunday_quiz_questions
            WHERE quiz_id = ?
            ORDER BY position
            """,
            [quiz_id],
        ).fetchall()
        score = 0
        review = []
        for row in rows:
            question_id = row[0]
            correct_answer = row[7]
            incorrect_answers = _loads_json(row[8], [])
            option_text_by_id = {
                _option_id(question_id, answer): answer
                for answer in [correct_answer, *incorrect_answers]
            }
            selected = request.answers.get(question_id)
            correct = _option_id(question_id, correct_answer)
            is_correct = selected == correct
            score += 1 if is_correct else 0
            review.append(
                {
                    "question_id": question_id,
                    "position": row[2],
                    "selected_option_id": selected,
                    "correct_option_id": correct,
                    "selected_option_text": option_text_by_id.get(selected),
                    "correct_option_text": correct_answer,
                    "correct": is_correct,
                    "explanation": row[6],
                    "answer_image_url": (assets.get((question_id, "answer")) or {}).get("url"),
                }
            )
        conn.execute(
            "INSERT INTO sunday_quiz_attempts VALUES (?, ?, ?, ?, ?::JSON, ?)",
            [str(uuid4()), quiz_id, score, len(rows), json.dumps(request.answers), now_utc()],
        )
    return {"score": score, "total": len(rows), "review": review}


def _asset_response(asset_id: str, *, public: bool):
    settings = get_settings()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT a.object_key, a.content_type, q.status
            FROM sunday_quiz_assets a
            JOIN sunday_quizzes q ON q.id = a.quiz_id
            WHERE a.id = ?
            """,
            [asset_id],
        ).fetchone()
    if row is None or (public and row[2] != "published"):
        raise HTTPException(status_code=404, detail="Sunday quiz asset not found")
    object_key, content_type, _status = row
    storage = get_object_storage(settings)
    signed_url = storage.presign_get(object_key)
    if signed_url:
        cache_control = PUBLIC_ASSET_REDIRECT_CACHE_CONTROL if public else ADMIN_ASSET_CACHE_CONTROL
        headers = {"Cache-Control": cache_control}
        return RedirectResponse(signed_url, status_code=307, headers=headers)
    root = settings.upload_root.resolve()
    path = (root / object_key).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Sunday quiz asset not found")
    cache_control = PUBLIC_ASSET_FILE_CACHE_CONTROL if public else ADMIN_ASSET_CACHE_CONTROL
    headers = {"Cache-Control": cache_control}
    return FileResponse(path, media_type=content_type or "application/octet-stream", headers=headers)


@admin_router.get("/assets/{asset_id}", response_model=None)
def read_admin_sunday_quiz_asset(asset_id: str):
    return _asset_response(asset_id, public=False)


@public_router.get("/assets/{asset_id}", response_model=None)
def read_public_sunday_quiz_asset(asset_id: str):
    return _asset_response(asset_id, public=True)
