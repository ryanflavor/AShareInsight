"""Unit tests for research report domain entities."""

import pytest
from pydantic import ValidationError

from src.domain.entities.company import Metrics, Relations, Timeline
from src.domain.entities.research_report import (
    BusinessConceptWithBrands,
    ProfitForecast,
    ResearchReportExtraction,
    ValuationItem,
)


class TestProfitForecast:
    """Test cases for ProfitForecast model."""

    def test_valid_profit_forecast(self):
        """Test creating a valid profit forecast."""
        forecast = ProfitForecast(
            year=2024,
            metric="营业收入",
            value="50.5亿元",
            yoy_growth="15.2%",
        )
        assert forecast.year == 2024
        assert forecast.metric == "营业收入"
        assert forecast.value == "50.5亿元"
        assert forecast.yoy_growth == "15.2%"

    def test_profit_forecast_without_growth(self):
        """Test profit forecast without YoY growth."""
        forecast = ProfitForecast(
            year=2024,
            metric="净利润",
            value="5.2亿元",
            yoy_growth=None,
        )
        assert forecast.year == 2024
        assert forecast.metric == "净利润"
        assert forecast.value == "5.2亿元"
        assert forecast.yoy_growth is None

    def test_profit_forecast_required_fields(self):
        """Test that required fields must be provided."""
        with pytest.raises(ValidationError):
            ProfitForecast(
                year=2024,
                metric="营业收入",
                # Missing value
            )

        with pytest.raises(ValidationError):
            ProfitForecast(
                year=2024,
                value="50亿元",
                # Missing metric
            )

        with pytest.raises(ValidationError):
            ProfitForecast(
                metric="营业收入",
                value="50亿元",
                # Missing year
            )


class TestValuationItem:
    """Test cases for ValuationItem model."""

    def test_valid_valuation_item(self):
        """Test creating a valid valuation item."""
        item = ValuationItem(
            year=2024,
            metric="P/E",
            value=15.5,
        )
        assert item.year == 2024
        assert item.metric == "P/E"
        assert item.value == 15.5

    def test_valuation_with_different_metrics(self):
        """Test valuation with various metric types."""
        metrics_data = [
            (2024, "P/E", 15.5),
            (2025, "P/B", 2.8),
            (2024, "EV/EBITDA", 8.2),
            (2025, "P/S", 1.2),
        ]

        for year, metric, value in metrics_data:
            item = ValuationItem(year=year, metric=metric, value=value)
            assert item.year == year
            assert item.metric == metric
            assert item.value == value

    def test_valuation_negative_values(self):
        """Test that negative values are allowed (e.g., for loss-making companies)."""
        item = ValuationItem(
            year=2024,
            metric="P/E",
            value=-10.5,  # Negative P/E for loss-making company
        )
        assert item.value == -10.5


class TestBusinessConceptWithBrands:
    """Test cases for BusinessConceptWithBrands model."""

    def test_business_concept_with_brands(self):
        """Test creating business concept with brands."""
        concept = BusinessConceptWithBrands(
            concept_name="智能手机业务",
            concept_category="核心业务",
            description="公司智能手机产品线",
            importance_score=0.8,
            development_stage="成长期",
            timeline=Timeline(established="2020年"),
            metrics=Metrics(revenue=1000000000.0),
            relations=Relations(),
            source_sentences=["来源句子1", "来源句子2"],
            key_products_or_brands=["品牌A", "产品系列B", "型号C"],
        )

        assert concept.concept_name == "智能手机业务"
        assert len(concept.key_products_or_brands) == 3
        assert "品牌A" in concept.key_products_or_brands

    def test_business_concept_empty_brands(self):
        """Test business concept with empty brands list."""
        concept = BusinessConceptWithBrands(
            concept_name="测试业务",
            concept_category="核心业务",
            description="测试描述",
            importance_score=0.5,
            development_stage="成长期",
            timeline=Timeline(),
            metrics=None,
            relations=Relations(),
            source_sentences=["s1", "s2"],
            key_products_or_brands=[],
        )
        assert concept.key_products_or_brands == []

    def test_business_concept_inherits_validation(self):
        """Test that inherited validation rules still apply."""
        # Test invalid category
        with pytest.raises(ValidationError):
            BusinessConceptWithBrands(
                concept_name="Test",
                concept_category="invalid",  # Invalid category
                description="Test",
                importance_score=0.5,
                development_stage="成长期",
                timeline=Timeline(),
                relations=Relations(),
                source_sentences=["s1", "s2"],
                key_products_or_brands=[],
            )

        # Test invalid importance score
        with pytest.raises(ValidationError):
            BusinessConceptWithBrands(
                concept_name="Test",
                concept_category="核心业务",
                description="Test",
                importance_score=1.5,  # Out of range
                development_stage="成长期",
                timeline=Timeline(),
                relations=Relations(),
                source_sentences=["s1", "s2"],
                key_products_or_brands=[],
            )


class TestResearchReportExtraction:
    """Test cases for ResearchReportExtraction model."""

    def test_valid_research_report(self):
        """Test creating a valid research report extraction."""
        profit_forecasts = [
            ProfitForecast(
                year=2024,
                metric="营业收入",
                value="100亿元",
                yoy_growth="20%",
            ),
            ProfitForecast(
                year=2025,
                metric="营业收入",
                value="120亿元",
                yoy_growth="20%",
            ),
        ]

        valuations = [
            ValuationItem(year=2024, metric="P/E", value=15.0),
            ValuationItem(year=2025, metric="P/E", value=12.5),
        ]

        business_concepts = [
            BusinessConceptWithBrands(
                concept_name="主营业务",
                concept_category="核心业务",
                description="公司核心产品",
                importance_score=0.9,
                development_stage="成熟期",
                timeline=Timeline(),
                relations=Relations(),
                source_sentences=["s1", "s2"],
                key_products_or_brands=["产品A", "产品B"],
            )
        ]

        report = ResearchReportExtraction(
            company_name_short="测试公司",
            company_code="000001",
            report_title="测试公司深度研究报告",
            investment_rating="买入",
            core_thesis="公司具有强大的竞争优势和增长潜力",
            profit_forecast=profit_forecasts,
            valuation=valuations,
            comparable_companies=["公司A", "公司B"],
            risk_factors=["风险1", "风险2"],
            business_concepts=business_concepts,
        )

        assert report.company_name_short == "测试公司"
        assert report.company_code == "000001"
        assert report.investment_rating == "买入"
        assert len(report.profit_forecast) == 2
        assert len(report.valuation) == 2
        assert len(report.comparable_companies) == 2
        assert len(report.risk_factors) == 2
        assert len(report.business_concepts) == 1

    def test_research_report_empty_lists(self):
        """Test research report with empty optional lists."""
        report = ResearchReportExtraction(
            company_name_short="Test",
            company_code="000001",
            report_title="Test Report",
            investment_rating="中性",
            core_thesis="Test thesis",
            profit_forecast=[],
            valuation=[],
            comparable_companies=[],
            risk_factors=[],
            business_concepts=[],
        )

        assert report.comparable_companies == []
        assert report.risk_factors == []
        assert report.profit_forecast == []
        assert report.business_concepts == []

    def test_core_thesis_length_limit(self):
        """Test core thesis length validation."""
        # Valid: exactly 200 characters
        thesis = "x" * 200
        report = ResearchReportExtraction(
            company_name_short="Test",
            company_code="000001",
            report_title="Test Report",
            investment_rating="买入",
            core_thesis=thesis,
            profit_forecast=[],
            valuation=[],
            business_concepts=[],
        )
        assert len(report.core_thesis) == 200

        # Invalid: more than 200 characters
        with pytest.raises(ValidationError):
            ResearchReportExtraction(
                company_name_short="Test",
                company_code="000001",
                report_title="Test Report",
                investment_rating="买入",
                core_thesis="x" * 201,
                profit_forecast=[],
                valuation=[],
                business_concepts=[],
            )

    def test_research_report_required_fields(self):
        """Test that all required fields must be provided."""
        with pytest.raises(ValidationError):
            ResearchReportExtraction(
                # Missing company_name_short
                company_code="000001",
                report_title="Test",
                investment_rating="买入",
                core_thesis="Test",
                profit_forecast=[],
                valuation=[],
                business_concepts=[],
            )

        with pytest.raises(ValidationError):
            ResearchReportExtraction(
                company_name_short="Test",
                # Missing company_code
                report_title="Test",
                investment_rating="买入",
                core_thesis="Test",
                profit_forecast=[],
                valuation=[],
                business_concepts=[],
            )

    def test_research_report_model_export(self):
        """Test model export to dict."""
        report = ResearchReportExtraction(
            company_name_short="Test Company",
            company_code="000001",
            report_title="Test Report",
            investment_rating="买入",
            core_thesis="Strong growth potential",
            profit_forecast=[ProfitForecast(year=2024, metric="Revenue", value="100M")],
            valuation=[ValuationItem(year=2024, metric="P/E", value=15.0)],
            business_concepts=[],
        )

        data = report.model_dump()
        assert data["company_name_short"] == "Test Company"
        assert data["investment_rating"] == "买入"
        assert len(data["profit_forecast"]) == 1
        assert data["profit_forecast"][0]["year"] == 2024
