"""Deterministic payer formulary, Prior Authorization, and CMS fallback checker."""

from __future__ import annotations

from typing import Any

from smartrx_safety_agents.heuristics.ddi_engine import (
    CMSFormularyDrugEntry,
    DrugCatalog,
    resolve_canonical_rxcui,
)
from smartrx_safety_agents.models.clinical import (
    FormularyAlternative,
    InsuranceOutput,
    NormalizedMedication,
)


class FormularyChecker:
    """Evaluates formulary tier, copay, and PA requirements with CMS tier fallback."""

    def __init__(self, catalog: DrugCatalog) -> None:
        self._catalog = catalog

    def check(
        self,
        medications: tuple[NormalizedMedication, ...],
        *,
        payer_formulary: dict[str, dict[str, Any]] | None = None,
    ) -> InsuranceOutput:
        """Evaluate coverage for medications, falling back to CMS defaults if plan unavailable."""
        if not medications:
            return InsuranceOutput(
                covered=True,
                formulary_tier=1,
                estimated_copay_usd=0.0,
                requires_pa=False,
                used_cms_fallback=payer_formulary is None,
            )

        highest_tier = 1
        max_copay = 0.0
        any_pa = False
        all_covered = True
        used_cms = False
        alternatives: list[FormularyAlternative] = []
        seen_alts: set[str] = set()

        for med in medications:
            rx = resolve_canonical_rxcui(med, self._catalog)
            if payer_formulary and rx in payer_formulary:
                entry = payer_formulary[rx]
                covered = bool(entry.get("covered", True))
                tier = int(entry.get("formulary_tier", 3))
                copay = float(entry.get("estimated_copay_usd", 45.0))
                req_pa = bool(entry.get("requires_pa", False))
            else:
                used_cms = True
                cms_entry = self._catalog.cms_default_formulary.get(rx)
                if isinstance(cms_entry, CMSFormularyDrugEntry):
                    covered = True
                    tier = cms_entry.formulary_tier
                    copay = cms_entry.estimated_copay_usd
                    req_pa = cms_entry.requires_pa
                    for alt in cms_entry.alternatives:
                        if alt.rxcui not in seen_alts:
                            seen_alts.add(alt.rxcui)
                            alternatives.append(
                                FormularyAlternative(
                                    rxcui=alt.rxcui,
                                    drug_name=alt.drug_name,
                                    formulary_tier=alt.formulary_tier,
                                    estimated_copay_usd=alt.estimated_copay_usd,
                                    requires_pa=alt.requires_pa,
                                )
                            )
                else:
                    covered = True
                    raw_tier = self._catalog.cms_default_formulary.get("default_tier", 3)
                    raw_copay = self._catalog.cms_default_formulary.get("default_copay_usd", 45.0)
                    tier = raw_tier if isinstance(raw_tier, int) else 3
                    copay = float(raw_copay) if isinstance(raw_copay, (int, float)) else 45.0
                    req_pa = bool(
                        self._catalog.cms_default_formulary.get("default_requires_pa", False)
                    )

            all_covered = all_covered and covered
            highest_tier = max(highest_tier, tier)
            max_copay = max(max_copay, copay)
            any_pa = any_pa or req_pa

        return InsuranceOutput(
            covered=all_covered,
            formulary_tier=highest_tier,
            estimated_copay_usd=max_copay,
            requires_pa=any_pa,
            used_cms_fallback=used_cms,
            alternatives=tuple(alternatives),
        )
