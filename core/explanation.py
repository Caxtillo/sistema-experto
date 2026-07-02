"""Explanation engine that generates human-readable summaries of fuzzy diagnoses.

For a given asset state, this engine:
1. Computes membership degrees for each sensor value in each linguistic term
2. Identifies which rules fired with significant strength
3. Generates a natural-language summary of the diagnosis
"""

import skfuzzy as fuzz


class ExplanationEngine:
    """Generates explanations for fuzzy inference results."""

    def __init__(self, inference_engine):
        self.engine = inference_engine

    def explain(self, asset, sensors, rules, values, score, status):
        """Generate a full explanation for the current asset state.

        Returns a dict containing:
        - asset: asset label
        - score: numeric score
        - status: status label
        - total_rules: total rule count
        - active_rules_count: rules with fire_strength > 0.05
        - top_rules: up to 5 strongest rules
        - membership_detail: per-sensor term memberships with degree > 0.01
        - summary: natural-language diagnosis text
        """
        built = self.engine.build_system(asset, sensors, rules)
        antecedents = built["antecedents"]

        membership_detail = []
        for s in sensors:
            if s.name not in values:
                continue
            val = max(s.min_val, min(s.max_val, values[s.name]))
            for mf in s.mf_config:
                term = mf["term"]
                if s.name in antecedents and term in antecedents[s.name].terms:
                    degree = float(fuzz.interp_membership(
                        antecedents[s.name].universe,
                        antecedents[s.name][term].mf,
                        val
                    ))
                    if degree > 0.01:
                        membership_detail.append({
                            "sensor": s.name,
                            "sensor_label": s.label,
                            "value": round(val, 2),
                            "term": term,
                            "degree": round(degree, 3),
                        })

        active_rules = self.engine.get_active_rules(asset, sensors, rules, values)
        top_rules = [r for r in active_rules if r["fire_strength"] > 0.05][:5]

        return {
            "asset": asset.label,
            "score": score,
            "status": status,
            "total_rules": len(rules),
            "active_rules_count": len(top_rules),
            "top_rules": top_rules,
            "membership_detail": membership_detail,
            "summary": self._generate_summary(status, top_rules, membership_detail),
        }

    def _generate_summary(self, status, rules, memberships):
        """Build a natural-language summary of the diagnosis.

        Includes the status description, detected sensor values with
        high membership, and the number of contributing rules.
        """
        if status == "none":
            return "Sistema operando en condiciones óptimas. Ninguna regla de alerta activa."

        status_text = {
            "low": "condición normal con monitoreo de rutina",
            "medium": "condición que requiere atención preventiva",
            "high": "condición que requiere acción correctiva urgente",
            "critical": "condición crítica que requiere intervención inmediata",
        }

        summary = f"El diagnóstico indica {status_text.get(status, 'estado ' + status)}."
        if memberships:
            high_mem = [m for m in memberships if m["degree"] > 0.5]
            if high_mem:
                terms = ", ".join(f"{m['sensor_label']}={m['term']}" for m in high_mem[:3])
                summary += f" Valores detectados: {terms}."

        if rules:
            summary += f" {len(rules)} regla(s) contribuyen a esta decisión."

        return summary
