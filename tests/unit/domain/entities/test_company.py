"""Unit tests for company domain entities."""

import pytest
from pydantic import ValidationError

from src.domain.entities.company import (
    AnnualReportExtraction,
    BusinessConcept,
    CompanyBasicInfo,
    Metrics,
    Relations,
    Shareholder,
    Timeline,
)


class TestShareholder:
    """Test cases for Shareholder model."""

    def test_valid_shareholder_creation(self):
        """Test creating a valid shareholder."""
        shareholder = Shareholder(
            name="开山控股集团股份有限公司",
            holding_percentage=51.49,
        )
        assert shareholder.name == "开山控股集团股份有限公司"
        assert shareholder.holding_percentage == 51.49

    def test_shareholder_percentage_validation(self):
        """Test percentage validation bounds."""
        # Valid boundary values
        Shareholder(name="Test", holding_percentage=0.0)
        Shareholder(name="Test", holding_percentage=100.0)

        # Invalid values
        with pytest.raises(ValidationError):
            Shareholder(name="Test", holding_percentage=-0.1)

        with pytest.raises(ValidationError):
            Shareholder(name="Test", holding_percentage=100.1)

    def test_shareholder_required_fields(self):
        """Test that all required fields must be provided."""
        with pytest.raises(ValidationError):
            Shareholder(name="Test")  # Missing holding_percentage

        with pytest.raises(ValidationError):
            Shareholder(holding_percentage=50.0)  # Missing name


class TestCompanyBasicInfo:
    """Test cases for CompanyBasicInfo model."""

    def test_valid_company_basic_info(self):
        """Test creating valid company basic info."""
        shareholders = [
            Shareholder(name="Major Shareholder", holding_percentage=60.0),
            Shareholder(name="Minor Shareholder", holding_percentage=10.0),
        ]

        company = CompanyBasicInfo(
            company_name_full="浙江开山压缩机股份有限公司",
            company_name_short="开山股份",
            company_code="300257",
            exchange="深圳证券交易所创业板",
            top_shareholders=shareholders,
        )

        assert company.company_name_full == "浙江开山压缩机股份有限公司"
        assert company.company_name_short == "开山股份"
        assert company.company_code == "300257"
        assert company.exchange == "深圳证券交易所创业板"
        assert len(company.top_shareholders) == 2
        assert company.top_shareholders[0].name == "Major Shareholder"

    def test_empty_shareholders_list(self):
        """Test company with empty shareholders list."""
        company = CompanyBasicInfo(
            company_name_full="Test Company Ltd.",
            company_name_short="Test Co",
            company_code="000001",
            exchange="Test Exchange",
            top_shareholders=[],
        )
        assert company.top_shareholders == []

    def test_company_required_fields(self):
        """Test that all required fields must be provided."""
        with pytest.raises(ValidationError):
            CompanyBasicInfo(
                company_name_short="Test",
                company_code="000001",
                exchange="Test",
                top_shareholders=[],
            )  # Missing company_name_full


class TestTimeline:
    """Test cases for Timeline model."""

    def test_timeline_all_fields_none(self):
        """Test timeline with all optional fields as None."""
        timeline = Timeline(established=None, recent_event=None)
        assert timeline.established is None
        assert timeline.recent_event is None

    def test_timeline_with_values(self):
        """Test timeline with actual values."""
        timeline = Timeline(
            established="2010年1月1日",
            recent_event="2024年完成重大收购",
        )
        assert timeline.established == "2010年1月1日"
        assert timeline.recent_event == "2024年完成重大收购"

    def test_timeline_partial_values(self):
        """Test timeline with some fields None."""
        timeline = Timeline(established="2010年", recent_event=None)
        assert timeline.established == "2010年"
        assert timeline.recent_event is None


class TestMetrics:
    """Test cases for Metrics model."""

    def test_metrics_all_none(self):
        """Test metrics with all optional fields as None."""
        metrics = Metrics(
            revenue=None,
            revenue_growth_rate=None,
            market_share=None,
            gross_margin=None,
            capacity=None,
            sales_volume=None,
        )
        assert all(
            getattr(metrics, field) is None
            for field in [
                "revenue",
                "revenue_growth_rate",
                "market_share",
                "gross_margin",
                "capacity",
                "sales_volume",
            ]
        )

    def test_metrics_with_values(self):
        """Test metrics with actual values."""
        metrics = Metrics(
            revenue=3926653074.89,
            revenue_growth_rate=21.01,
            market_share=15.5,
            gross_margin=36.31,
            capacity=1000000.0,
            sales_volume=850000.0,
        )
        assert metrics.revenue == 3926653074.89
        assert metrics.revenue_growth_rate == 21.01
        assert metrics.market_share == 15.5
        assert metrics.gross_margin == 36.31
        assert metrics.capacity == 1000000.0
        assert metrics.sales_volume == 850000.0

    def test_metrics_partial_values(self):
        """Test metrics with partial values."""
        metrics = Metrics(revenue=1000000.0, gross_margin=25.5)
        assert metrics.revenue == 1000000.0
        assert metrics.gross_margin == 25.5
        assert metrics.revenue_growth_rate is None
        assert metrics.market_share is None


class TestRelations:
    """Test cases for Relations model."""

    def test_empty_relations(self):
        """Test relations with all empty lists."""
        relations = Relations()
        assert relations.customers == []
        assert relations.partners == []
        assert relations.subsidiaries_or_investees == []

    def test_relations_with_data(self):
        """Test relations with actual data."""
        relations = Relations(
            customers=["客户A", "客户B"],
            partners=["合作伙伴1", "合作伙伴2"],
            subsidiaries_or_investees=["子公司1", "被投资公司1"],
        )
        assert len(relations.customers) == 2
        assert "客户A" in relations.customers
        assert len(relations.partners) == 2
        assert len(relations.subsidiaries_or_investees) == 2

    def test_relations_default_factory(self):
        """Test that default factory creates new lists."""
        r1 = Relations()
        r2 = Relations()
        r1.customers.append("test")
        assert r2.customers == []  # Should not be affected


class TestBusinessConcept:
    """Test cases for BusinessConcept model."""

    def test_valid_business_concept(self):
        """Test creating a valid business concept."""
        concept = BusinessConcept(
            concept_name="压缩机业务",
            concept_category="核心业务",
            description="公司主营业务，涵盖螺杆式空气压缩机等产品",
            importance_score=0.95,
            development_stage="成熟期",
            timeline=Timeline(established="2010年"),
            metrics=Metrics(revenue=1000000.0),
            relations=Relations(customers=["客户A"]),
            source_sentences=["句子1", "句子2"],
        )

        assert concept.concept_name == "压缩机业务"
        assert concept.concept_category == "核心业务"
        assert concept.importance_score == 0.95
        assert concept.development_stage == "成熟期"
        assert len(concept.source_sentences) == 2

    def test_business_concept_category_validation(self):
        """Test category validation."""
        # Valid categories
        for category in ["核心业务", "新兴业务", "战略布局"]:
            BusinessConcept(
                concept_name="Test",
                concept_category=category,
                description="Test",
                importance_score=0.5,
                development_stage="成长期",
                timeline=Timeline(),
                relations=Relations(),
                source_sentences=["s1", "s2"],
            )

        # Invalid category
        with pytest.raises(ValidationError):
            BusinessConcept(
                concept_name="Test",
                concept_category="invalid_category",
                description="Test",
                importance_score=0.5,
                development_stage="成长期",
                timeline=Timeline(),
                relations=Relations(),
                source_sentences=["s1", "s2"],
            )

    def test_business_concept_stage_validation(self):
        """Test development stage validation."""
        # Valid stages
        for stage in ["成熟期", "成长期", "探索期", "并购整合期"]:
            BusinessConcept(
                concept_name="Test",
                concept_category="核心业务",
                description="Test",
                importance_score=0.5,
                development_stage=stage,
                timeline=Timeline(),
                relations=Relations(),
                source_sentences=["s1", "s2"],
            )

        # Invalid stage
        with pytest.raises(ValidationError):
            BusinessConcept(
                concept_name="Test",
                concept_category="核心业务",
                description="Test",
                importance_score=0.5,
                development_stage="invalid_stage",
                timeline=Timeline(),
                relations=Relations(),
                source_sentences=["s1", "s2"],
            )

    def test_importance_score_validation(self):
        """Test importance score bounds."""
        # Valid boundary values
        BusinessConcept(
            concept_name="Test",
            concept_category="核心业务",
            description="Test",
            importance_score=0.0,
            development_stage="成长期",
            timeline=Timeline(),
            relations=Relations(),
            source_sentences=["s1", "s2"],
        )

        BusinessConcept(
            concept_name="Test",
            concept_category="核心业务",
            description="Test",
            importance_score=1.0,
            development_stage="成长期",
            timeline=Timeline(),
            relations=Relations(),
            source_sentences=["s1", "s2"],
        )

        # Invalid values
        with pytest.raises(ValidationError):
            BusinessConcept(
                concept_name="Test",
                concept_category="核心业务",
                description="Test",
                importance_score=-0.1,
                development_stage="成长期",
                timeline=Timeline(),
                relations=Relations(),
                source_sentences=["s1", "s2"],
            )

        with pytest.raises(ValidationError):
            BusinessConcept(
                concept_name="Test",
                concept_category="核心业务",
                description="Test",
                importance_score=1.1,
                development_stage="成长期",
                timeline=Timeline(),
                relations=Relations(),
                source_sentences=["s1", "s2"],
            )

    def test_source_sentences_validation(self):
        """Test source sentences length validation."""
        # Valid: 2-3 sentences
        BusinessConcept(
            concept_name="Test",
            concept_category="核心业务",
            description="Test",
            importance_score=0.5,
            development_stage="成长期",
            timeline=Timeline(),
            relations=Relations(),
            source_sentences=["s1", "s2"],
        )

        BusinessConcept(
            concept_name="Test",
            concept_category="核心业务",
            description="Test",
            importance_score=0.5,
            development_stage="成长期",
            timeline=Timeline(),
            relations=Relations(),
            source_sentences=["s1", "s2", "s3"],
        )

        # Invalid: too few
        with pytest.raises(ValidationError):
            BusinessConcept(
                concept_name="Test",
                concept_category="核心业务",
                description="Test",
                importance_score=0.5,
                development_stage="成长期",
                timeline=Timeline(),
                relations=Relations(),
                source_sentences=["s1"],
            )

        # Invalid: too many
        with pytest.raises(ValidationError):
            BusinessConcept(
                concept_name="Test",
                concept_category="核心业务",
                description="Test",
                importance_score=0.5,
                development_stage="成长期",
                timeline=Timeline(),
                relations=Relations(),
                source_sentences=["s1", "s2", "s3", "s4"],
            )


class TestAnnualReportExtraction:
    """Test cases for AnnualReportExtraction model."""

    def test_valid_annual_report_extraction(self):
        """Test creating a valid annual report extraction."""
        shareholders = [Shareholder(name="Major Shareholder", holding_percentage=60.0)]

        business_concepts = [
            BusinessConcept(
                concept_name="主营业务",
                concept_category="核心业务",
                description="公司主要业务",
                importance_score=0.9,
                development_stage="成熟期",
                timeline=Timeline(),
                relations=Relations(),
                source_sentences=["句子1", "句子2"],
            )
        ]

        report = AnnualReportExtraction(
            company_name_full="测试公司有限公司",
            company_name_short="测试公司",
            company_code="000001",
            exchange="上海证券交易所",
            top_shareholders=shareholders,
            business_concepts=business_concepts,
        )

        assert report.company_name_full == "测试公司有限公司"
        assert report.company_name_short == "测试公司"
        assert report.company_code == "000001"
        assert report.exchange == "上海证券交易所"
        assert len(report.top_shareholders) == 1
        assert len(report.business_concepts) == 1
        assert report.business_concepts[0].concept_name == "主营业务"

    def test_annual_report_empty_lists(self):
        """Test annual report with empty lists."""
        report = AnnualReportExtraction(
            company_name_full="Test Company",
            company_name_short="Test",
            company_code="000001",
            exchange="Test Exchange",
            top_shareholders=[],
            business_concepts=[],
        )
        assert report.top_shareholders == []
        assert report.business_concepts == []

    def test_annual_report_model_export(self):
        """Test model export to dict."""
        report = AnnualReportExtraction(
            company_name_full="Test Company",
            company_name_short="Test",
            company_code="000001",
            exchange="Test Exchange",
            top_shareholders=[],
            business_concepts=[],
        )

        data = report.model_dump()
        assert data["company_name_full"] == "Test Company"
        assert data["company_code"] == "000001"
        assert "top_shareholders" in data
        assert "business_concepts" in data
