from uuid import uuid4

import pytest
import test_auth
import test_storage
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from story_api import auth, main, saved_routes
from story_api.assign_legacy import assign
from story_api.auth import Identity, resolve_user
from story_api.database import migrate
from story_api.providers import DemoProvider
from story_api.storage import AppUser, MissingStory, StoryProject, StoryStore, WorkflowRun

token_signer = test_auth.signer
postgres_engine = test_storage.engine
REQUEST = test_storage.REQUEST


@pytest.fixture
def clients(postgres_engine, request, monkeypatch):
    engine, signer = postgres_engine, request.getfixturevalue("token_signer")
    monkeypatch.setattr(auth, "get_engine", lambda: engine)
    monkeypatch.setattr(saved_routes, "get_engine", lambda: engine)
    monkeypatch.setattr(main, "create_provider", DemoProvider)
    _, token, _ = signer
    with TestClient(main.app, headers={"Authorization": "Bearer " + token("alice")}) as alice:
        with TestClient(main.app, headers={"Authorization": "Bearer " + token("bob")}) as bob:
            yield alice, bob


def test_two_users_cannot_read_edit_or_regenerate_each_others_stories(clients, postgres_engine):
    engine = postgres_engine
    alice, bob = clients
    a = alice.post("/api/stories", json=REQUEST)
    b = bob.post("/api/stories", json=REQUEST)
    assert a.status_code == b.status_code == 202
    a_id, b_id = a.json()["id"], b.json()["id"]
    assert [s["id"] for s in alice.get("/api/stories").json()] == [a_id]
    assert [s["id"] for s in bob.get("/api/stories").json()] == [b_id]
    for client, foreign_id in [(alice, b_id), (bob, a_id)]:
        path = f"/api/stories/{foreign_id}"
        assert client.get(path).status_code == 404
        assert client.get(path + "/runs").status_code == 404
        assert client.post(path + "/runs").status_code == 404
        assert (
            client.patch(path, json={"expected_version": 1, "title": "Stolen"}).status_code == 404
        )
    assert alice.get(f"/api/stories/{a_id}/runs").status_code == 200
    assert (
        alice.patch(
            f"/api/stories/{a_id}", json={"expected_version": 1, "title": "Mine"}
        ).status_code
        == 200
    )
    with Session(engine) as session:
        assert len(session.scalars(select(WorkflowRun)).all()) == 2


def test_user_id_in_body_cannot_override_verified_identity(clients):
    alice, bob = clients
    bob_id = bob.get("/api/auth/me").json()["id"]
    assert alice.post("/api/stories", json={**REQUEST, "owner_id": bob_id}).status_code == 422
    created = alice.post("/api/stories", json=REQUEST).json()
    assert created["owner_id"] == alice.get("/api/auth/me").json()["id"]
    assert created["owner_id"] != bob_id
    assert (
        alice.patch(
            f"/api/stories/{created['id']}",
            json={
                "expected_version": 1,
                "owner_id": bob_id,
            },
        ).status_code
        == 422
    )


def test_local_identity_is_stable_and_issuer_scoped(postgres_engine):
    engine = postgres_engine
    first = resolve_user(engine, Identity("https://one.invalid", "same-subject"))
    again = resolve_user(engine, Identity("https://one.invalid", "same-subject"))
    other = resolve_user(engine, Identity("https://two.invalid", "same-subject"))
    assert first.id == again.id
    assert first.id != other.id


def test_legacy_stories_are_hidden_and_only_explicitly_assignable(clients, postgres_engine):
    engine = postgres_engine
    alice, bob = clients
    story_id = str(uuid4())
    with Session(engine) as session, session.begin():
        session.add(StoryProject(id=story_id, owner_id=None, title="Legacy", request=REQUEST))
    for client in (alice, bob):
        assert client.get(f"/api/stories/{story_id}").status_code == 404
        assert client.get("/api/stories").json() == []
    alice_id = alice.get("/api/auth/me").json()["id"]
    assign(engine, story_id, alice_id)
    assert alice.get(f"/api/stories/{story_id}").status_code == 200
    assert bob.get(f"/api/stories/{story_id}").status_code == 404
    with pytest.raises(ValueError, match="already has an owner"):
        assign(engine, story_id, bob.get("/api/auth/me").json()["id"])


def test_schema_v1_upgrade_preserves_ownerless_rows(postgres_engine):
    engine = postgres_engine
    # Reconstruct v1 only inside this test's unique disposable schema.
    story_id = str(uuid4())
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE story_projects DROP COLUMN owner_id"))
        connection.execute(text("DROP TABLE app_users"))
        connection.execute(text("DELETE FROM story_schema_version"))
        connection.execute(text("INSERT INTO story_schema_version VALUES (1)"))
        connection.execute(
            text(
                "INSERT INTO story_projects (id,title,request,version,created_at) "
                "VALUES (:id,'Legacy','{}',1,now())"
            ),
            {"id": story_id},
        )
    migrate(engine)
    migrate(engine)
    with Session(engine) as session:
        assert session.get(StoryProject, story_id).owner_id is None
        assert session.scalars(select(AppUser)).all() == []
    user = resolve_user(engine, Identity("https://test.invalid", "new-user"))
    with pytest.raises(MissingStory):
        StoryStore(engine, user.id).get(story_id)
