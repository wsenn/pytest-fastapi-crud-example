import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app import models
from app.database import Base, get_db

# Create test database
SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture()
def test_client():
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def setup_users(test_client):
    """Create test users for pagination and filtering tests"""
    users_data = [
        {"first_name": "Alice", "last_name": "Anderson", "address": "123 Main St", "activated": True},
        {"first_name": "Bob", "last_name": "Brown", "address": "456 Oak Ave", "activated": False},
        {"first_name": "Charlie", "last_name": "Clark", "address": "789 Pine Rd", "activated": True},
        {"first_name": "Diana", "last_name": "Davis", "address": "321 Elm St", "activated": False},
        {"first_name": "Eve", "last_name": "Evans", "address": "654 Main St", "activated": True},
        {"first_name": "Frank", "last_name": "Foster", "address": "987 Maple Ave", "activated": False},
    ]
    
    created_users = []
    for user_data in users_data:
        response = test_client.post("/api/users/", json=user_data)
        created_users.append(response.json()["User"])
    
    return created_users


def test_pagination_basic(test_client, setup_users):
    """Test basic pagination functionality"""
    # Test page 1 with limit 3
    response = test_client.get("/api/users/?page=1&limit=3")
    assert response.status_code == 200
    data = response.json()
    
    assert data["results"] == 3
    assert len(data["users"]) == 3
    assert data["pagination"]["page"] == 1
    assert data["pagination"]["limit"] == 3
    assert data["pagination"]["total"] == 6
    assert data["pagination"]["pages"] == 2


def test_pagination_second_page(test_client, setup_users):
    """Test second page of pagination"""
    response = test_client.get("/api/users/?page=2&limit=4")
    assert response.status_code == 200
    data = response.json()
    
    assert data["results"] == 2  # Only 2 items on second page
    assert len(data["users"]) == 2
    assert data["pagination"]["page"] == 2
    assert data["pagination"]["total"] == 6


def test_search_first_name(test_client, setup_users):
    """Test search functionality for first name"""
    response = test_client.get("/api/users/?search=alice")
    assert response.status_code == 200
    data = response.json()
    
    assert data["results"] == 1
    assert data["users"][0]["first_name"] == "Alice"
    assert data["pagination"]["total"] == 1


def test_search_last_name(test_client, setup_users):
    """Test search functionality for last name"""
    response = test_client.get("/api/users/?search=evans")
    assert response.status_code == 200
    data = response.json()
    
    assert data["results"] == 1
    assert data["users"][0]["last_name"] == "Evans"


def test_search_address(test_client, setup_users):
    """Test search functionality for address"""
    response = test_client.get("/api/users/?search=Main")
    assert response.status_code == 200
    data = response.json()
    
    assert data["results"] == 2  # Alice and Eve have "Main St" in address
    assert all("Main" in user["address"] for user in data["users"])


def test_filter_activated_true(test_client, setup_users):
    """Test filtering by activated status = true"""
    response = test_client.get("/api/users/?activated=true")
    assert response.status_code == 200
    data = response.json()
    
    assert data["results"] == 3  # Alice, Charlie, Eve
    assert all(user["activated"] is True for user in data["users"])


def test_filter_activated_false(test_client, setup_users):
    """Test filtering by activated status = false"""
    response = test_client.get("/api/users/?activated=false")
    assert response.status_code == 200
    data = response.json()
    
    assert data["results"] == 3  # Bob, Diana, Frank
    assert all(user["activated"] is False for user in data["users"])


def test_sort_by_first_name_asc(test_client, setup_users):
    """Test sorting by first name in ascending order"""
    response = test_client.get("/api/users/?sort_by=first_name&order=asc")
    assert response.status_code == 200
    data = response.json()
    
    first_names = [user["first_name"] for user in data["users"]]
    assert first_names == sorted(first_names)


def test_sort_by_first_name_desc(test_client, setup_users):
    """Test sorting by first name in descending order"""
    response = test_client.get("/api/users/?sort_by=first_name&order=desc")
    assert response.status_code == 200
    data = response.json()
    
    first_names = [user["first_name"] for user in data["users"]]
    assert first_names == sorted(first_names, reverse=True)


def test_combined_filters(test_client, setup_users):
    """Test combination of search, filter, and pagination"""
    # Search for "a" in names, filter activated=true, with pagination
    response = test_client.get("/api/users/?search=a&activated=true&page=1&limit=2")
    assert response.status_code == 200
    data = response.json()
    
    # Should match Alice, Charlie, Eve (all have 'a' and are activated)
    assert data["pagination"]["total"] == 3
    assert data["results"] == 2  # Limited to 2 per page
    assert all(user["activated"] is True for user in data["users"])


def test_invalid_page(test_client, setup_users):
    """Test pagination with page beyond available data"""
    response = test_client.get("/api/users/?page=10&limit=10")
    assert response.status_code == 200
    data = response.json()
    
    assert data["results"] == 0
    assert len(data["users"]) == 0
    assert data["pagination"]["page"] == 10


def test_pagination_limit_validation(test_client):
    """Test pagination limit validation (max 100)"""
    response = test_client.get("/api/users/?limit=101")
    assert response.status_code == 422  # Validation error


def test_default_pagination_params(test_client, setup_users):
    """Test default pagination parameters"""
    response = test_client.get("/api/users/")
    assert response.status_code == 200
    data = response.json()
    
    assert data["pagination"]["page"] == 1
    assert data["pagination"]["limit"] == 10