import uuid

import pytest

pytestmark = pytest.mark.integration


async def test_add_member(client):
    response = await client.post(
        "/api/members", json={"full_name": "  Maya Hassan ", "email": "Maya@Example.com"}
    )

    assert response.status_code == 201
    member = response.json()
    assert set(member) == {"id", "full_name", "email", "joined_on", "active_loans"}
    assert member["full_name"] == "Maya Hassan"
    assert member["email"] == "Maya@Example.com"
    assert member["active_loans"] == 0
    assert member["joined_on"]


async def test_email_is_optional(client):
    response = await client.post("/api/members", json={"full_name": "Youssef Adel", "email": ""})

    assert response.status_code == 201
    assert response.json()["email"] is None


async def test_email_is_unique_whatever_the_letter_case(make_member, client):
    await make_member(email="maya@example.com")

    response = await client.post(
        "/api/members", json={"full_name": "Maya H.", "email": "MAYA@example.com"}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "member_email_taken"


@pytest.mark.parametrize(
    ("body", "field", "error_type"),
    [
        ({"full_name": " "}, "full_name", "string_too_short"),
        ({"full_name": "Maya", "email": "not-an-email"}, "email", "email_format"),
        ({"full_name": "Maya", "email": "a@b"}, "email", "email_format"),
    ],
)
async def test_invalid_member_is_422(client, body, field, error_type):
    response = await client.post("/api/members", json=body)

    assert response.status_code == 422
    [error] = response.json()["error"]["details"]["errors"]
    assert error["location"] == ["body", field]
    assert error["type"] == error_type


async def test_search_members_by_partial_name_or_email(make_member, client):
    await make_member("Maya Hassan", "maya@example.com")
    await make_member("Omar Farouk", "omar@library.test")
    await make_member("Lina Haddad")

    by_name = (await client.get("/api/members", params={"q": "HAS"})).json()
    by_email = (await client.get("/api/members", params={"q": "library.test"})).json()
    everyone = (await client.get("/api/members")).json()

    assert [m["full_name"] for m in by_name["items"]] == ["Maya Hassan"]
    assert [m["full_name"] for m in by_email["items"]] == ["Omar Farouk"]
    assert everyone["total"] == 3
    assert [m["full_name"] for m in everyone["items"]] == [
        "Lina Haddad",
        "Maya Hassan",
        "Omar Farouk",
    ]


async def test_member_list_counts_active_loans(make_book, make_member, borrow, client):
    book = await make_book(copies=2)
    member = await make_member()
    await borrow(book["copies"][0]["id"], member["id"])
    loan = (await borrow(book["copies"][1]["id"], member["id"])).json()
    await client.post(f"/api/loans/{loan['id']}/return")

    [listed] = (await client.get("/api/members")).json()["items"]

    assert listed["active_loans"] == 1


# Member detail


async def test_member_detail_counts_loans_now_and_in_total(make_book, make_member, borrow, client):
    book = await make_book(copies=2)
    member = await make_member("Maya Hassan", "maya@example.com")
    await borrow(book["copies"][0]["id"], member["id"])
    loan = (await borrow(book["copies"][1]["id"], member["id"])).json()
    await client.post(f"/api/loans/{loan['id']}/return")
    await borrow(book["copies"][1]["id"], member["id"])

    response = await client.get(f"/api/members/{member['id']}")

    assert response.status_code == 200
    detail = response.json()
    assert set(detail) == {"id", "full_name", "email", "joined_on", "active_loans", "loans_total"}
    assert {key: detail[key] for key in member} == {**member, "active_loans": 2}
    assert detail["loans_total"] == 3


async def test_member_without_loans_has_zero_loans(make_member, client):
    member = await make_member()

    detail = (await client.get(f"/api/members/{member['id']}")).json()

    assert (detail["active_loans"], detail["loans_total"]) == (0, 0)


async def test_unknown_member_is_404(client):
    response = await client.get(f"/api/members/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_member_id_must_be_an_id(client):
    response = await client.get("/api/members/maya")

    assert response.status_code == 422
