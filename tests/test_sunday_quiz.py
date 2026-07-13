from io import BytesIO


def _fill_and_publish_quiz(client, quiz):
    for question in quiz["questions"]:
        response = client.patch(
            f"/sunday-quizzes/{quiz['id']}/questions/{question['id']}",
            json={
                "question": f"Question {question['position']}?",
                "correct_answer": f"Correct {question['position']}",
                "incorrect_answers": [
                    f"Wrong {question['position']}A",
                    f"Wrong {question['position']}B",
                    f"Wrong {question['position']}C",
                ],
                "explanation": f"Explanation {question['position']}",
            },
        )
        assert response.status_code == 200
    response = client.patch(f"/sunday-quizzes/{quiz['id']}/publication", json={"is_published": True})
    assert response.status_code == 200
    assert response.json()["status"] == "published"


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

    _fill_and_publish_quiz(client, quiz)

    response = client.get("/public/sunday-quizzes")
    assert response.status_code == 200
    assert response.json()[0]["theme"] == "Space"

    response = client.get(f"/public/sunday-quizzes/{quiz['id']}")
    assert response.status_code == 200
    public_quiz = response.json()
    assert public_quiz["question_count"] == 10
    assert "correct_answer" not in public_quiz["questions"][0]
    assert "explanation" not in public_quiz["questions"][0]
    assert set(public_quiz["questions"][0]["options"][0]) == {"id", "text"}
    first_order = [option["text"] for option in public_quiz["questions"][0]["options"]]
    seen_orders = {tuple(first_order)}
    for _ in range(8):
        response = client.get(f"/public/sunday-quizzes/{quiz['id']}")
        assert response.status_code == 200
        seen_orders.add(tuple(option["text"] for option in response.json()["questions"][0]["options"]))
    assert len(seen_orders) > 1

    answers = {}
    for index, question in enumerate(public_quiz["questions"]):
        correct_option = next(option for option in question["options"] if option["text"] == f"Correct {question['position']}")
        if index == 0:
            wrong_option = next(option for option in question["options"] if option["id"] != correct_option["id"])
            answers[question["id"]] = wrong_option["id"]
        else:
            answers[question["id"]] = correct_option["id"]
    response = client.post(f"/public/sunday-quizzes/{quiz['id']}/attempts", json={"answers": answers})
    assert response.status_code == 200
    result = response.json()
    assert result["score"] == 9
    assert result["total"] == 10
    assert result["review"][0]["correct_option_text"] == "Correct 1"
    assert result["review"][0]["selected_option_text"] != "Correct 1"
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
