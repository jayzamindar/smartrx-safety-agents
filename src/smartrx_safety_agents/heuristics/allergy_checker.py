"""Deterministic patient allergy and pharmacological cross-reactivity checker."""

from __future__ import annotations

from smartrx_safety_agents.heuristics.ddi_engine import DrugCatalog, resolve_canonical_rxcui
from smartrx_safety_agents.models.clinical import (
    ClinicalAlert,
    NormalizedMedication,
    RiskGrade,
    normalize_clinical_identifier,
)


class AllergyChecker:
    """Checks active/proposed medications against documented patient allergies."""

    def __init__(self, catalog: DrugCatalog) -> None:
        self._catalog = catalog

    def check(
        self,
        medications: tuple[NormalizedMedication, ...],
        allergies: tuple[str, ...],
    ) -> tuple[ClinicalAlert, ...]:
        """Return RED HOLD_PRESCRIPTION alerts for direct or cross-reactive allergies."""
        if not allergies or not medications:
            return ()

        normalized_allergies = {normalize_clinical_identifier(a) for a in allergies if a.strip()}
        alerts: list[ClinicalAlert] = []
        seen_keys: set[tuple[str, str]] = set()

        for med in medications:
            rx = resolve_canonical_rxcui(med, self._catalog)
            med_names = {
                normalize_clinical_identifier(med.scd_name),
                normalize_clinical_identifier(med.raw_name),
            }

            # Direct allergy match
            for allergy in sorted(normalized_allergies):
                if allergy in med_names or any(allergy in name for name in med_names):
                    key = (rx, allergy)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        alerts.append(
                            ClinicalAlert(
                                alert_id=f"allergy-direct-{rx}-{allergy}",
                                rule_category="ALLERGY",
                                severity="contraindicated",
                                risk_score=5,
                                risk_grade=RiskGrade.RED,
                                recommended_action="HOLD_PRESCRIPTION",
                                affected_rxcuis=(rx,),
                                rationale=(
                                    f"Direct allergy match: patient has documented "
                                    f"'{allergy}' allergy."
                                ),
                                citation=f"RxNorm:{rx} | NLM Clinical Allergy Guardrail",
                                requires_npi_attestation=True,
                            )
                        )

            # Cross-reactivity catalog match
            for rule in self._catalog.allergy_cross_reactivities:
                allergen_norm = normalize_clinical_identifier(rule.allergen)
                if not any(allergen_norm in a for a in normalized_allergies):
                    continue
                cross_rxcuis = {
                    normalize_clinical_identifier(c) for c in rule.cross_reactive_rxcuis
                }
                cross_names = {normalize_clinical_identifier(n) for n in rule.cross_reactive_names}
                name_hit = any(cn in name for cn in cross_names for name in med_names)
                if rx in cross_rxcuis or name_hit:
                    key = (rx, allergen_norm)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        alerts.append(
                            ClinicalAlert(
                                alert_id=f"allergy-xref-{rx}-{allergen_norm}",
                                rule_category="ALLERGY",
                                severity=rule.severity,
                                risk_score=5,
                                risk_grade=RiskGrade.RED,
                                recommended_action="HOLD_PRESCRIPTION",
                                affected_rxcuis=(rx,),
                                rationale=rule.rationale,
                                citation=rule.citation,
                                requires_npi_attestation=True,
                            )
                        )

        return tuple(alerts)
