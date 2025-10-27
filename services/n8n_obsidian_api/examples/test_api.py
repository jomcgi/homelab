"""Example script to test the n8n-obsidian-api service."""

import asyncio

import httpx


async def main():
    """Test the API endpoints."""
    base_url = "http://localhost:8080"

    async with httpx.AsyncClient(base_url=base_url) as client:
        # Health check
        print("1. Health check...")
        response = await client.get("/")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}\n")

        # Create a note
        print("2. Creating a test note...")
        response = await client.post(
            "/notes/create",
            json={
                "path": "n8n/test/example.md",
                "content": "# Test Note\n\nCreated via API at test time.",
            },
        )
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}\n")

        # Read the note
        print("3. Reading the note...")
        response = await client.get("/notes/n8n/test/example.md")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Path: {data['note']['path']}")
            print(f"   Content preview: {data['note']['content'][:50]}...\n")

        # Append to the note
        print("4. Appending to the note...")
        response = await client.post(
            "/notes/append",
            json={
                "path": "n8n/test/example.md",
                "content": "\n## Section 2\n\nAppended content here.",
            },
        )
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}\n")

        # Update frontmatter
        print("5. Updating frontmatter...")
        response = await client.post(
            "/notes/update-frontmatter",
            json={
                "path": "n8n/test/example.md",
                "key": "status",
                "value": "completed",
            },
        )
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}\n")

        # Try to write outside n8n/ (should fail)
        print("6. Testing path restriction (should fail)...")
        response = await client.post(
            "/notes/create",
            json={
                "path": "personal/secret.md",
                "content": "This should not work",
            },
        )
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}\n")

        # Delete the test note
        print("7. Deleting the test note...")
        response = await client.delete("/notes/n8n/test/example.md")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}\n")

        print("All tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
