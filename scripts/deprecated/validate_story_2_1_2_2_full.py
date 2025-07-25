#!/usr/bin/env python3
"""Full validation script for Stories 2.1-2.2 with specific companies

This script validates the full pipeline from API endpoint (2.1) through vector
database retrieval (2.2) using two specific companies:
- 开山股份 (Kaishan)
- 300257

It tests the complete data flow and actual results.
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.domain.value_objects import BusinessConceptQuery
from src.infrastructure.persistence.postgres import PostgresVectorStoreRepository

console = Console()


class FullPipelineValidator:
    """Validates the full 2.1-2.2 pipeline with specific companies."""

    def __init__(self):
        self.api_base_url = "http://localhost:8000"
        self.test_companies = [
            # {"identifier": "开山股份", "description": "Company short name"},
            # {"identifier": "开山集团股份有限公司", "description": "Company full name"},
            {"identifier": "002240", "description": "Stock code"},
        ]

    async def validate(self):
        """Run full pipeline validation."""
        console.print(
            "[bold blue]🔍 Full Pipeline Validation: Stories 2.1 → 2.2[/bold blue]\n"
        )

        # Test 1: API Health Check (Story 2.1)
        if not await self._test_api_health():
            console.print(
                "[red]❌ API is not running. Please start the API server first.[/red]"
            )
            console.print(
                "[yellow]Run: uvicorn src.interfaces.api.main:app --reload[/yellow]"
            )
            return

        # Test 2: Direct Vector Store Search (Story 2.2)
        console.print("\n[bold cyan]📊 Direct Vector Store Search Results[/bold cyan]")
        direct_results = await self._test_direct_vector_search()

        # Test 3: API Endpoint Search (Story 2.1 → 2.2)
        console.print("\n[bold cyan]🌐 API Endpoint Search Results[/bold cyan]")
        api_results = await self._test_api_search()

        # Test 4: Compare Results
        console.print("\n[bold cyan]🔄 Results Comparison[/bold cyan]")
        self._compare_results(direct_results, api_results)

        # Test 5: Performance Analysis
        console.print("\n[bold cyan]⚡ Performance Analysis[/bold cyan]")
        await self._analyze_performance()

    async def _test_api_health(self) -> bool:
        """Test if API is running."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_base_url}/health")
                return response.status_code == 200
        except Exception:
            return False

    async def _test_direct_vector_search(self) -> dict[str, Any]:
        """Test direct vector store search for both companies."""
        results = {}
        vector_store = PostgresVectorStoreRepository()

        try:
            for company in self.test_companies:
                identifier = company["identifier"]
                console.print(
                    f"\n[yellow]Testing: {identifier} ({company['description']})[/yellow]"
                )

                # Create query
                query = BusinessConceptQuery(
                    target_identifier=identifier, top_k=50, similarity_threshold=0.5
                )

                # Execute search
                try:
                    documents = await vector_store.search_similar_concepts(query)

                    # Display results
                    if documents:
                        table = Table(title=f"Similar Companies for {identifier}")
                        table.add_column("Company", style="cyan")
                        table.add_column("Code", style="magenta")
                        table.add_column("Concept", style="green")
                        table.add_column("Score", justify="right", style="yellow")

                        # Group by company
                        company_groups = {}
                        for doc in documents:  # Show top 10
                            display_name = doc.company_name_short or doc.company_name
                            key = (display_name, doc.company_code, doc.company_name)
                            if key not in company_groups:
                                company_groups[key] = []
                            company_groups[key].append(
                                {
                                    "concept": doc.concept_name,
                                    "score": doc.similarity_score,
                                }
                            )

                        for (
                            display_name,
                            code,
                            full_name,
                        ), concepts in company_groups.items():
                            # Show first concept for each company
                            first_concept = concepts[0]
                            table.add_row(
                                display_name,
                                code,
                                first_concept["concept"],
                                f"{first_concept['score']:.3f}",
                            )

                        console.print(table)

                        # Store results
                        results[identifier] = {
                            "total_found": len(documents),
                            "companies": company_groups,
                            "top_scores": [
                                doc.similarity_score for doc in documents[:5]
                            ],
                        }

                        # Show concept distribution
                        self._show_concept_distribution(documents)

                    else:
                        console.print(f"[red]No results found for {identifier}[/red]")
                        results[identifier] = {"total_found": 0, "companies": {}}

                except Exception as e:
                    console.print(f"[red]Error searching for {identifier}: {e}[/red]")
                    results[identifier] = {"error": str(e)}

        finally:
            await vector_store.close()

        return results

    async def _test_api_search(self) -> dict[str, Any]:
        """Test API endpoint search for both companies."""
        results = {}

        async with httpx.AsyncClient() as client:
            for company in self.test_companies:
                identifier = company["identifier"]
                console.print(
                    f"\n[yellow]API Testing: {identifier} ({company['description']})[/yellow]"
                )

                # Prepare request
                request_data = {
                    "query_identifier": identifier,
                    "top_k": 100,
                    "similarity_threshold": 0.5,
                }

                try:
                    # Make API call
                    response = await client.post(
                        f"{self.api_base_url}/api/v1/search/similar-companies",
                        json=request_data,
                        timeout=30.0,
                    )

                    if response.status_code == 200:
                        data = response.json()

                        # Display results
                        if data.get("results"):
                            table = Table(title=f"API Results for {identifier}")
                            table.add_column("Company", style="cyan")
                            table.add_column("Code", style="magenta")
                            table.add_column("Score", justify="right", style="yellow")
                            table.add_column("Concepts", style="green")

                            for result in data["results"]:
                                concepts = ", ".join(
                                    [
                                        f"{c['name']} ({c['similarity_score']:.2f})"
                                        for c in result.get("matched_concepts", [])[:2]
                                    ]
                                )
                                table.add_row(
                                    result["company_name"],
                                    result["company_code"],
                                    f"{result['relevance_score']:.3f}",
                                    concepts,
                                )

                            console.print(table)

                            # Store results
                            results[identifier] = {
                                "status": "success",
                                "query_company": data.get("query_company"),
                                "total_results": len(data["results"]),
                                "results": data["results"],
                            }

                            # Save to Excel
                            self._save_to_excel(identifier, data)
                        else:
                            console.print(
                                f"[red]No results from API for {identifier}[/red]"
                            )
                            results[identifier] = {"status": "no_results"}

                    else:
                        console.print(f"[red]API Error: {response.status_code}[/red]")
                        console.print(response.text)
                        results[identifier] = {
                            "status": "error",
                            "code": response.status_code,
                            "message": response.text,
                        }

                except Exception as e:
                    console.print(f"[red]API Request Error: {e}[/red]")
                    results[identifier] = {"status": "exception", "error": str(e)}

        return results

    def _show_concept_distribution(self, documents: list[Any]):
        """Show distribution of matched concepts."""
        concept_counts = {}
        for doc in documents:
            concept = doc.concept_category or "Unknown"
            concept_counts[concept] = concept_counts.get(concept, 0) + 1

        if concept_counts:
            tree = Tree("Concept Distribution")
            for concept, count in sorted(
                concept_counts.items(), key=lambda x: x[1], reverse=True
            ):
                tree.add(f"{concept}: {count} matches")
            console.print(tree)

    def _compare_results(
        self, direct_results: dict[str, Any], api_results: dict[str, Any]
    ):
        """Compare direct vector search with API results."""
        for identifier in self.test_companies:
            ident = identifier["identifier"]
            console.print(f"\n[yellow]Comparison for {ident}:[/yellow]")

            direct = direct_results.get(ident, {})
            api = api_results.get(ident, {})

            if "error" in direct or api.get("status") == "error":
                console.print("[red]Cannot compare due to errors[/red]")
                continue

            # Compare counts
            direct_count = direct.get("total_found", 0)
            api_count = len(api.get("results", []))

            console.print(f"Direct search found: [cyan]{direct_count}[/cyan] documents")
            console.print(f"API search returned: [cyan]{api_count}[/cyan] companies")

            # Compare top companies
            if direct.get("companies") and api.get("results"):
                console.print("\n[bold]Top 5 Companies Comparison:[/bold]")

                # Get top 5 from direct search
                direct_companies = []
                for (display_name, code, full_name), concepts in direct[
                    "companies"
                ].items():
                    max_score = max(c["score"] for c in concepts)
                    direct_companies.append((display_name, code, max_score))
                direct_companies.sort(key=lambda x: x[2], reverse=True)

                # Compare with API results
                table = Table()
                table.add_column("Rank", justify="center")
                table.add_column("Direct Search", style="cyan")
                table.add_column("API Search", style="magenta")
                table.add_column("Match", justify="center")

                for i in range(min(5, len(direct_companies), len(api["results"]))):
                    direct_comp = (
                        direct_companies[i] if i < len(direct_companies) else None
                    )
                    api_comp = api["results"][i] if i < len(api["results"]) else None

                    if direct_comp and api_comp:
                        direct_str = f"{direct_comp[0]} ({direct_comp[1]})"
                        api_str = (
                            f"{api_comp['company_name']} ({api_comp['company_code']})"
                        )
                        match = (
                            "✅" if direct_comp[1] == api_comp["company_code"] else "❌"
                        )
                    else:
                        direct_str = direct_comp[0] if direct_comp else "-"
                        api_str = api_comp["company_name"] if api_comp else "-"
                        match = "❓"

                    table.add_row(str(i + 1), direct_str, api_str, match)

                console.print(table)

    def _save_to_excel(self, identifier: str, data: dict):
        """Save API results to Excel file."""
        from datetime import datetime

        import pandas as pd

        # Prepare data for DataFrame
        rows = []
        for result in data.get("results", []):
            # Extract concept names and scores
            concepts = []
            concept_scores = []
            for concept in result.get("matched_concepts", [])[:5]:  # Top 5 concepts
                concepts.append(concept["name"])
                concept_scores.append(concept["similarity_score"])

            # Pad lists to ensure consistent length
            while len(concepts) < 5:
                concepts.append("")
                concept_scores.append("")

            row = {
                "公司简称": result["company_name"],
                "股票代码": result["company_code"],
                "相关性得分": result["relevance_score"],
                "概念1": concepts[0] if len(concepts) > 0 else "",
                "概念1得分": concept_scores[0] if len(concept_scores) > 0 else "",
                "概念2": concepts[1] if len(concepts) > 1 else "",
                "概念2得分": concept_scores[1] if len(concept_scores) > 1 else "",
                "概念3": concepts[2] if len(concepts) > 2 else "",
                "概念3得分": concept_scores[2] if len(concept_scores) > 2 else "",
                "概念4": concepts[3] if len(concepts) > 3 else "",
                "概念4得分": concept_scores[3] if len(concept_scores) > 3 else "",
                "概念5": concepts[4] if len(concepts) > 4 else "",
                "概念5得分": concept_scores[4] if len(concept_scores) > 4 else "",
            }
            rows.append(row)

        # Create DataFrame
        df = pd.DataFrame(rows)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)

        filename = output_dir / f"similar_companies_{identifier}_{timestamp}.xlsx"

        # Save to Excel with formatting
        with pd.ExcelWriter(filename, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="相似公司", index=False)

            # Get the workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets["相似公司"]

            # Auto-adjust column widths
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width

        console.print(f"[green]Results saved to: {filename}[/green]")

    async def _analyze_performance(self):
        """Analyze search performance."""
        vector_store = PostgresVectorStoreRepository()

        try:
            for company in self.test_companies:
                identifier = company["identifier"]
                console.print(f"\n[yellow]Performance test for {identifier}:[/yellow]")

                # Test different similarity thresholds
                thresholds = [0.3, 0.5, 0.7, 0.9]
                table = Table(title="Performance vs Similarity Threshold")
                table.add_column("Threshold", justify="center")
                table.add_column("Results", justify="right")
                table.add_column("Time (ms)", justify="right")

                for threshold in thresholds:
                    query = BusinessConceptQuery(
                        target_identifier=identifier,
                        top_k=50,
                        similarity_threshold=threshold,
                    )

                    start = asyncio.get_event_loop().time()
                    documents = await vector_store.search_similar_concepts(query)
                    elapsed = (asyncio.get_event_loop().time() - start) * 1000

                    table.add_row(
                        f"{threshold:.1f}", str(len(documents)), f"{elapsed:.1f}"
                    )

                console.print(table)

                # Test cache effectiveness
                console.print("\n[bold]Cache Performance:[/bold]")
                query = BusinessConceptQuery(
                    target_identifier=identifier, top_k=20, similarity_threshold=0.5
                )

                # First call (cache miss)
                start1 = asyncio.get_event_loop().time()
                docs1 = await vector_store.search_similar_concepts(query)
                time1 = (asyncio.get_event_loop().time() - start1) * 1000

                # Second call (cache hit)
                start2 = asyncio.get_event_loop().time()
                docs2 = await vector_store.search_similar_concepts(query)
                time2 = (asyncio.get_event_loop().time() - start2) * 1000

                improvement = ((time1 - time2) / time1) * 100 if time1 > 0 else 0
                console.print(f"First call: [cyan]{time1:.1f}ms[/cyan]")
                console.print(f"Second call: [cyan]{time2:.1f}ms[/cyan]")
                console.print(f"Cache improvement: [green]{improvement:.1f}%[/green]")

        finally:
            await vector_store.close()


async def main():
    """Run the full pipeline validation."""
    validator = FullPipelineValidator()
    await validator.validate()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Validation interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Validation failed: {e}[/red]")
        import traceback

        traceback.print_exc()
