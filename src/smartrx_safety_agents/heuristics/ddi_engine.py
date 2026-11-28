"""Deterministic Drug-Drug Interaction, therapeutic duplication, and fail-closed catalog loader."""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from smartrx_safety_agents.models.clinical import (
    ClinicalAlert,
    NormalizedMedication,
    RiskGrade,
    StrictClinicalModel,
    normalize_clinical_identifier,
)

DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parents[3] / "config" / "drug_interactions.json"
)


class CatalogNotFoundError(RuntimeError):
    """Raised when the static drug interaction catalog is missing, unreadable, or invalid."""


class DrugAliasEntry(StrictClinicalModel):
    """Canonical RxCUI and generic name mapping for a drug alias."""

    rxcui: str = Field(..., min_length=1)
    generic_name: str = Field(..., min_length=1)


class DDIPairRule(StrictClinicalModel):
    """Deterministic drug-drug interaction rule with severity and citation."""

    rxcui_a: str = Field(..., min_length=1)
    rxcui_b: str = Field(..., min_length=1)
    drug_a: str = Field(..., min_length=1)
    drug_b: str = Field(..., min_length=1)
    severity: Literal["contraindicated", "major", "moderate", "minor"]
    rationale: str = Field(..., min_length=1)
    citation: str = Field(..., min_length=1)


class TherapeuticClassRule(StrictClinicalModel):
    """Therapeutic class membership for duplication detection."""

    rxcuis: tuple[str, ...] = Field(..., min_length=1)
    citation: str = Field(..., min_length=1)


class AllergyCrossReactivityRule(StrictClinicalModel):
    """Pharmacological allergy and cross-reactivity rule."""

    allergen: str = Field(..., min_length=1)
    cross_reactive_rxcuis: tuple[str, ...] = Field(default_factory=tuple)
    cross_reactive_names: tuple[str, ...] = Field(default_factory=tuple)
    severity: Literal["contraindicated", "major"]
    rationale: str = Field(..., min_length=1)
    citation: str = Field(..., min_length=1)


class OrganDosingRule(StrictClinicalModel):
    """Renal and hepatic organ-function dosing rule."""

    rxcui: str = Field(..., min_length=1)
    drug_name: str = Field(..., min_length=1)
    requires_renal_lab: bool = Field(default=False)
    requires_hepatic_lab: bool = Field(default=False)
    min_egfr_ml_min: float | None = Field(default=None, ge=0.0)
    contraindicated_egfr_ml_min: float | None = Field(default=None, ge=0.0)
    hepatic_caution: bool = Field(default=False)
    hepatic_contraindicated: bool = Field(default=False)
    citation: str = Field(..., min_length=1)


class BeersCriteriaRule(StrictClinicalModel):
    """AGS Beer's Criteria geriatric medication rule."""

    rxcui: str = Field(..., min_length=1)
    drug_name: str = Field(..., min_length=1)
    min_age: int = Field(default=65, ge=0)
    rationale: str = Field(..., min_length=1)
    alternative: str = Field(..., min_length=1)
    citation: str = Field(..., min_length=1)


class CMSAlternativeEntry(StrictClinicalModel):
    """CMS default formulary alternative entry."""

    rxcui: str = Field(..., min_length=1)
    drug_name: str = Field(..., min_length=1)
    formulary_tier: int = Field(..., ge=1, le=5)
    estimated_copay_usd: float = Field(..., ge=0.0)
    requires_pa: bool = Field(default=False)


class CMSFormularyDrugEntry(StrictClinicalModel):
    """CMS default formulary tier entry for a specific RxCUI."""

    formulary_tier: int = Field(..., ge=1, le=5)
    estimated_copay_usd: float = Field(..., ge=0.0)
    requires_pa: bool = Field(default=False)
    alternatives: tuple[CMSAlternativeEntry, ...] = Field(default_factory=tuple)


class DrugCatalog(StrictClinicalModel):
    """Schema-validated static clinical safety and formulary catalog."""

    catalog_version: str = Field(..., min_length=1)
    drug_aliases: dict[str, DrugAliasEntry]
    nti_rxcuis: tuple[str, ...]
    ddi_pairs: tuple[DDIPairRule, ...]
    therapeutic_classes: dict[str, TherapeuticClassRule]
    allergy_cross_reactivities: tuple[AllergyCrossReactivityRule, ...]
    organ_dosing_rules: tuple[OrganDosingRule, ...]
    beers_criteria: tuple[BeersCriteriaRule, ...]
    cms_default_formulary: dict[str, CMSFormularyDrugEntry | int | float | bool]


def load_catalog(catalog_path: Path | None = None) -> DrugCatalog:
    """Load and validate the static drug catalog, raising CatalogNotFoundError on failure."""
    target = catalog_path if catalog_path is not None else DEFAULT_CATALOG_PATH
    if not target.is_file():
        raise CatalogNotFoundError(f"Clinical safety catalog not found at: {target}")
    try:
        raw_text = target.read_text(encoding="utf-8")
        raw_data = json.loads(raw_text)
        return DrugCatalog.model_validate(raw_data)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise CatalogNotFoundError(
            f"Failed to load valid clinical catalog from {target}: {exc}"
        ) from exc


def resolve_canonical_rxcui(med: NormalizedMedication, catalog: DrugCatalog) -> str:
    """Resolve canonical RxCUI using NFKC-normalized RxCUI or alias lookup."""
    rxcui_norm = normalize_clinical_identifier(med.rxcui)
    for alias_key in (med.scd_name, med.raw_name):
        key_norm = normalize_clinical_identifier(alias_key)
        for token in key_norm.split():
            if token in catalog.drug_aliases:
                return normalize_clinical_identifier(catalog.drug_aliases[token].rxcui)
        if key_norm in catalog.drug_aliases:
            return normalize_clinical_identifier(catalog.drug_aliases[key_norm].rxcui)
    return rxcui_norm


class DDIEngine:
    """Deterministic Drug-Drug Interaction and therapeutic duplication checker."""

    def __init__(self, catalog: DrugCatalog) -> None:
        self._catalog = catalog
        self._pair_index: dict[frozenset[str], DDIPairRule] = {
            frozenset(
                (
                    normalize_clinical_identifier(rule.rxcui_a),
                    normalize_clinical_identifier(rule.rxcui_b),
                )
            ): rule
            for rule in catalog.ddi_pairs
        }
        self._class_by_rxcui: dict[str, list[tuple[str, str]]] = {}
        for class_name, class_rule in catalog.therapeutic_classes.items():
            for rxcui in class_rule.rxcuis:
                norm_rx = normalize_clinical_identifier(rxcui)
                self._class_by_rxcui.setdefault(norm_rx, []).append(
                    (class_name, class_rule.citation)
                )

    def check(self, medications: tuple[NormalizedMedication, ...]) -> tuple[ClinicalAlert, ...]:
        """Evaluate all medication pairs for DDIs and therapeutic class duplications."""
        alerts: list[ClinicalAlert] = []
        seen_ddis: set[frozenset[str]] = set()
        seen_dups: set[tuple[str, str, str]] = set()

        resolved: list[tuple[NormalizedMedication, str]] = [
            (med, resolve_canonical_rxcui(med, self._catalog)) for med in medications
        ]

        for (med_a, rx_a), (med_b, rx_b) in combinations(resolved, 2):
            pair_key = frozenset((rx_a, rx_b))
            if len(pair_key) == 2 and pair_key in self._pair_index and pair_key not in seen_ddis:
                seen_ddis.add(pair_key)
                rule = self._pair_index[pair_key]
                is_high = rule.severity in ("contraindicated", "major")
                alerts.append(
                    ClinicalAlert(
                        alert_id=f"ddi-{rx_a}-{rx_b}",
                        rule_category="DDI",
                        severity=rule.severity,
                        risk_score=5
                        if rule.severity == "contraindicated"
                        else (4 if is_high else 3),
                        risk_grade=RiskGrade.RED if is_high else RiskGrade.YELLOW,
                        recommended_action="HOLD_PRESCRIPTION"
                        if is_high
                        else "FLAG_DRUG_INTERACTION",
                        affected_rxcuis=(rx_a, rx_b),
                        rationale=rule.rationale,
                        citation=rule.citation,
                        requires_npi_attestation=is_high,
                    )
                )

            # Check same-ingredient or same-therapeutic-class duplication across distinct entries
            same_drug_different_name = rx_a == rx_b and med_a.raw_name != med_b.raw_name
            if same_drug_different_name:
                dup_key = ("same_ingredient", rx_a, f"{med_a.raw_name}:{med_b.raw_name}")
                if dup_key not in seen_dups:
                    seen_dups.add(dup_key)
                    alerts.append(
                        ClinicalAlert(
                            alert_id=f"dup-{rx_a}-{med_a.raw_name}-{med_b.raw_name}",
                            rule_category="DUPLICATION",
                            severity="moderate",
                            risk_score=3,
                            risk_grade=RiskGrade.YELLOW,
                            recommended_action="FLAG_DRUG_INTERACTION",
                            affected_rxcuis=(rx_a,),
                            rationale=(
                                f"Duplicate active ingredient detected: '{med_a.raw_name}' "
                                f"and '{med_b.raw_name}' resolve to RxCUI {rx_a}."
                            ),
                            citation=f"RxNorm:{rx_a} | BPMH Therapeutic Duplication Rule",
                            requires_npi_attestation=False,
                        )
                    )
                continue

            classes_a = {c for c, _ in self._class_by_rxcui.get(rx_a, [])}
            classes_b = {c for c, _ in self._class_by_rxcui.get(rx_b, [])}
            for shared_class in sorted(classes_a & classes_b):
                class_citation = self._catalog.therapeutic_classes[shared_class].citation
                ordered_pair = tuple(sorted((rx_a, rx_b)))
                dup_key = (shared_class, ordered_pair[0], ordered_pair[1])
                if dup_key not in seen_dups:
                    seen_dups.add(dup_key)
                    alerts.append(
                        ClinicalAlert(
                            alert_id=f"dup-{shared_class}-{ordered_pair[0]}-{ordered_pair[1]}",
                            rule_category="DUPLICATION",
                            severity="moderate",
                            risk_score=3,
                            risk_grade=RiskGrade.YELLOW,
                            recommended_action="FLAG_DRUG_INTERACTION",
                            affected_rxcuis=ordered_pair,
                            rationale=(
                                f"Therapeutic class duplication ({shared_class}) between "
                                f"{med_a.scd_name} and {med_b.scd_name}."
                            ),
                            citation=class_citation,
                            requires_npi_attestation=False,
                        )
                    )

        return tuple(alerts)
