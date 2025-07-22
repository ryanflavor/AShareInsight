#!/usr/bin/env python3
"""Detailed API test to diagnose issues."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import httpx


async def test_api():
    """Test the API with detailed error handling."""
    print("🔍 Testing API Endpoint\n")

    async with httpx.AsyncClient() as client:
        # Test 1: Health check
        print("1. Testing health endpoint...")
        try:
            response = await client.get("http://localhost:8000/health")
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.json()}")
        except Exception as e:
            print(f"   ❌ Health check failed: {e}")

        # Test 2: Search endpoint
        print("\n2. Testing search endpoint...")
        try:
            response = await client.post(
                "http://localhost:8000/api/v1/search/similar-companies",
                json={"query_identifier": "002170", "top_k": 5},
            )
            print(f"   Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Success! Found {len(data.get('results', []))} results")
                if data.get("results"):
                    result = data["results"][0]
                    print(
                        f"   First result: {result['company_name']} ({result['company_code']})"
                    )
            else:
                print(f"   ❌ Error response: {response.json()}")

        except Exception as e:
            print(f"   ❌ Request failed: {e}")
            import traceback

            traceback.print_exc()

        # Test 3: Check if it's an import issue by testing with mock data
        print("\n3. Testing with include_justification parameter...")
        try:
            response = await client.post(
                "http://localhost:8000/api/v1/search/similar-companies?include_justification=true",
                json={"query_identifier": "002170", "top_k": 3},
            )
            print(f"   Status: {response.status_code}")
            if response.status_code != 200:
                print(f"   Response: {response.json()}")
        except Exception as e:
            print(f"   ❌ Request failed: {e}")


async def main():
    """Run the API test."""
    await test_api()


if __name__ == "__main__":
    asyncio.run(main())
