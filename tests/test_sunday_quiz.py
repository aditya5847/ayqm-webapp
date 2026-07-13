from io import BytesIO


def _fill_and_publish_quiz(client, quiz):
    answers = {}
    for question in quiz["questions"]:
        options = [f"Option {question['position']}{letter}" for letter in ["A", "B", "C", "D"]]
        response = client.patch(
            f"/sunday-quizzes/{quiz['id']}/questions/{question['id']}",
            json={
                "question": f"Question {question['position']}?",
                "options": options,
                "correct_option": 1,
                "explanation": f"Explanation {question['position']}",
            },
        )
        assert response.status_code == 200
        answers[question["id"]] = 1
    response = client.patch(f"/sunday-quizzes/{quiz['id']}/publication", json={"is_published": True})
    assert response.status_code == 200
    assert response.json()["status"] == "published"
    return answers


def test_sunday_quiz_admin_requires_auth(unauth_client):
    response = unauth_client.get("/sunday-quizzes")
    assert response.status_code == 401


def test_sunday_quiz_create_validate_publish_and_play(client):
    response = client.post("/sunday-quizzes", json={"quiz_date": "2026-01-04", "theme": "Space"})
    assert response.status_code == 201
    quiz = response.json()
    assert quiz["status"] == "draft"
    assert quiz["question_count"] == 10
    assert len(quiz["questions"]) == 10

    response = client.patch(f"/sunday-quizzes/{quiz['id']}/publication", json={"is_published": True})
    assert response.status_code == 422
    assert "publish_errors" in response.json()["detail"]

    answers = _fill_and_publish_quiz(client, quiz)

    response = client.get("/public/sunday-quizzes")
    assert response.status_code == 200
    assert response.json()[0]["theme"] == "Space"

    response = client.get(f"/public/sunday-quizzes/{quiz['id']}")
    assert response.status_code == 200
    public_quiz = response.json()
    assert public_quiz["question_count"] == 10
    assert "correct_option" not in public_quiz["questions"][0]
    assert "explanation" not in public_quiz["questions"][0]

    wrong_question_id = public_quiz["questions"][0]["id"]
    answers[wrong_question_id] = 0
    response = client.post(f"/public/sunday-quizzes/{quiz['id']}/attempts", json={"answers": answers})
    assert response.status_code == 200
    result = response.json()
    assert result["score"] == 9
    assert result["total"] == 10
    assert result["review"][0]["correct_option"] == 1
    assert result["review"][0]["explanation"] == "Explanation 1"


def test_sunday_quiz_assets_are_images_and_public_only_after_publish(client):
    response = client.post("/sunday-quizzes", json={"quiz_date": "2026-01-11", "theme": "Cinema"})
    assert response.status_code == 201
    quiz = response.json()

    response = client.post(
        f"/sunday-quizzes/{quiz['id']}/assets",
        data={"kind": "cover"},
        files={"file": ("cover.txt", BytesIO(b"not an image"), "text/plain")},
    )
    assert response.status_code == 422

    response = client.post(
        f"/sunday-quizzes/{quiz['id']}/assets",
        data={"kind": "cover"},
        files={"file": ("cover.png", BytesIO(b"fake png"), "image/png")},
    )
    assert response.status_code == 200
    admin_asset_path = response.json()["cover_image_url"]
    asset_id = admin_asset_path.rsplit("/", 1)[-1]
    public_asset_path = f"/public/sunday-quizzes/assets/{asset_id}"

    response = client.get(public_asset_path)
    assert response.status_code == 404

    response = client.get(admin_asset_path)
    assert response.status_code == 200
    assert response.content == b"fake png"

    _fill_and_publish_quiz(client, quiz)
    response = client.get(public_asset_path)
    assert response.status_code == 200
    assert response.content == b"fake png"
