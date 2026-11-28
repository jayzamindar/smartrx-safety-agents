"""Deterministic organ-function dosing, NTI OCR confidence, and AGS Beer's Criteria validator."""

from __future__ import annotations

from smartrx_safety_agents.heuristics.ddi_engine import (
    BeersCriteriaRule,
    DrugCatalog,
    OrganDosingRule,
    resolve_canonical_rxcui,
)
from smartrx_safety_agents.models.clinical import (
    ClinicalAlert,
    ClinicalOutput,
    NormalizedMedication,
    RiskGrade,
    normalize_clinical_identifier,
)

_OCR_NTI_CONFIDENCE_THRESHOLD = 0.70


class DosingValidator:
    """Validates renal/hepatic dosing bounds, NTI OCR clarity, and AGS Beer's Criteria."""

    def __init__(self, catalog: DrugCatalog) -> None:
        self._catalog = catalog
        self._nti_rxcuis: frozenset[str] = frozenset(
            normalize_clinical_identifier(rx) for rx in catalog.nti_rxcuis
        )
        self._organ_rules: dict[str, OrganDosingRule] = {
            normalize_clinical_identifier(r.rxcui): r for r in catalog.organ_dosing_rules
        }
        self._beers_rules: dict[str, BeersCriteriaRule] = {
            normalize_clinical_identifier(r.rxcui): r for r in catalog.beers_criteria
        }

    def check(
        self,
        medications: tuple[NormalizedMedication, ...],
        clinical: ClinicalOutput,
        *,
        patient_age: int | None = None,
    ) -> tuple[ClinicalAlert, ...]:
        """Run OCR NTI, renal/hepatic lab bounds, and Beer's Criteria checks."""
        alerts: list[ClinicalAlert] = []
        seen_ids: set[str] = set()

        def _add(alert: ClinicalAlert) -> None:
            if alert.alert_id not in seen_ids:
                seen_ids.add(alert.alert_id)
                alerts.append(alert)

        has_hepatic_lab = any(
            any(k in lab.name for k in ("ast", "alt", "bilirubin", "hepatic", "liver"))
            and lab.value is not None
            for lab in clinical.labs
        )

        for med in medications:
            rx = resolve_canonical_rxcui(med, self._catalog)
            is_nti = med.is_nti or rx in self._nti_rxcuis

            if is_nti and med.ocr_confidence < _OCR_NTI_CONFIDENCE_THRESHOLD:
                _add(
                    ClinicalAlert(
                        alert_id=f"ocr-nti-{rx}",
                        rule_category="OCR_NTI",
                        severity="major",
                        risk_score=5,
                        risk_grade=RiskGrade.RED,
                        recommended_action="HOLD_PRESCRIPTION",
                        affected_rxcuis=(rx,),
                        rationale=(
                            f"Low OCR confidence ({med.ocr_confidence:.2f} < 0.70) on Narrow "
                            f"Therapeutic Index medication '{med.scd_name}'."
                        ),
                        citation=f"RxNorm:{rx} | ISMP High-Alert / NTI OCR Safeguard",
                        requires_npi_attestation=True,
                    )
                )

            organ_rule = self._organ_rules.get(rx)
            if organ_rule is not None:
                missing_renal = organ_rule.requires_renal_lab and clinical.egfr_ml_min is None
                missing_hepatic = (
                    organ_rule.requires_hepatic_lab
                    and not clinical.hepatic_impaired
                    and not has_hepatic_lab
                    and clinical.partial_ehr_record
                )
                if missing_renal or missing_hepatic:
                    _add(
                        ClinicalAlert(
                            alert_id=f"labs-missing-{rx}",
                            rule_category="DOSING",
                            severity="major",
                            risk_score=4,
                            risk_grade=RiskGrade.RED,
                            recommended_action="REQUEST_RENAL_HEPATIC_LABS",
                            affected_rxcuis=(rx,),
                            rationale=(
                                f"Missing required renal/hepatic lab observations for "
                                f"NTI/organ-cleared medication '{organ_rule.drug_name}'."
                            ),
                            citation=organ_rule.citation,
                            requires_npi_attestation=True,
                        )
                    )
                elif clinical.egfr_ml_min is not None:
                    egfr = clinical.egfr_ml_min
                    if (
                        organ_rule.contraindicated_egfr_ml_min is not None
                        and egfr < organ_rule.contraindicated_egfr_ml_min
                    ):
                        _add(
                            ClinicalAlert(
                                alert_id=f"renal-contra-{rx}",
                                rule_category="DOSING",
                                severity="contraindicated",
                                risk_score=5,
                                risk_grade=RiskGrade.RED,
                                recommended_action="HOLD_PRESCRIPTION",
                                affected_rxcuis=(rx,),
                                rationale=(
                                    f"eGFR {egfr:.1f} mL/min is below contraindication threshold "
                                    f"({organ_rule.contraindicated_egfr_ml_min:.1f} mL/min) for "
                                    f"'{organ_rule.drug_name}'."
                                ),
                                citation=organ_rule.citation,
                                requires_npi_attestation=True,
                            )
                        )
                    elif (
                        organ_rule.min_egfr_ml_min is not None and egfr < organ_rule.min_egfr_ml_min
                    ):
                        _add(
                            ClinicalAlert(
                                alert_id=f"renal-adjust-{rx}",
                                rule_category="DOSING",
                                severity="moderate",
                                risk_score=3,
                                risk_grade=RiskGrade.YELLOW,
                                recommended_action="PROPOSE_THERAPEUTIC_ALTERNATIVE",
                                affected_rxcuis=(rx,),
                                rationale=(
                                    f"eGFR {egfr:.1f} mL/min requires renal dose adjustment or "
                                    f"alternative for '{organ_rule.drug_name}'."
                                ),
                                citation=organ_rule.citation,
                                requires_npi_attestation=False,
                            )
                        )

                if clinical.hepatic_impaired:
                    if organ_rule.hepatic_contraindicated:
                        _add(
                            ClinicalAlert(
                                alert_id=f"hepatic-contra-{rx}",
                                rule_category="DOSING",
                                severity="contraindicated",
                                risk_score=5,
                                risk_grade=RiskGrade.RED,
                                recommended_action="HOLD_PRESCRIPTION",
                                affected_rxcuis=(rx,),
                                rationale=(
                                    f"Hepatic impairment contraindicates '{organ_rule.drug_name}'."
                                ),
                                citation=organ_rule.citation,
                                requires_npi_attestation=True,
                            )
                        )
                    elif organ_rule.hepatic_caution:
                        _add(
                            ClinicalAlert(
                                alert_id=f"hepatic-caution-{rx}",
                                rule_category="DOSING",
                                severity="moderate",
                                risk_score=3,
                                risk_grade=RiskGrade.YELLOW,
                                recommended_action="PROPOSE_THERAPEUTIC_ALTERNATIVE",
                                affected_rxcuis=(rx,),
                                rationale=(
                                    f"Hepatic impairment requires dose reduction or alternative "
                                    f"for '{organ_rule.drug_name}'."
                                ),
                                citation=organ_rule.citation,
                                requires_npi_attestation=False,
                            )
                        )

            beers_rule = self._beers_rules.get(rx)
            if (
                beers_rule is not None
                and patient_age is not None
                and patient_age >= beers_rule.min_age
            ):
                _add(
                    ClinicalAlert(
                        alert_id=f"beers-{rx}",
                        rule_category="BEERS_CRITERIA",
                        severity="moderate",
                        risk_score=3,
                        risk_grade=RiskGrade.YELLOW,
                        recommended_action="PROPOSE_THERAPEUTIC_ALTERNATIVE",
                        affected_rxcuis=(rx,),
                        rationale=(
                            f"AGS Beer's Criteria (age {patient_age} >= {beers_rule.min_age}): "
                            f"{beers_rule.rationale} Consider {beers_rule.alternative}."
                        ),
                        citation=beers_rule.citation,
                        requires_npi_attestation=False,
                    )
                )

        return tuple(alerts)
