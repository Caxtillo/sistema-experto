"""Fuzzy inference engine using scikit-fuzzy (Mamdani-type).

Builds a fuzzy control system for each asset using sensor membership
functions and rule definitions stored in the database. The system is
cached per asset for performance and rebuilt automatically when the
cache is cleared.

Key capabilities:
- Build antecedents from sensor membership function configurations
- Build consequent from default or custom output term configurations
- Evaluate sensor values through the fuzzy system -> defuzzified score
- Classify scores into status levels (none/low/medium/high/critical)
- Identify which rules fired and their fire strengths
"""

import skfuzzy as fuzz
import skfuzzy.control as ctrl
import numpy as np


class InferenceEngine:
    """Mamdani fuzzy inference engine with per-asset caching."""

    def __init__(self):
        self._cache = {}

    def build_system(self, asset, sensors, rules):
        """Build and cache a fuzzy control system for the given asset.

        Creates Antecedent objects for each sensor (with membership functions
        from mf_config), a Consequent for the asset's output variable,
        and ControlRules from the rule definitions.

        Returns a dict with the simulation, antecedents, consequent, and sensor map.
        The result is cached by asset.id and reused on subsequent calls.
        """
        cache_key = asset.id
        if cache_key in self._cache:
            return self._cache[cache_key]

        sensor_names_in_rules = set()
        for r in rules:
            for ant in r.antecedents:
                sensor_names_in_rules.add(ant["sensor"])

        antecedents = {}
        for s in sensors:
            if s.name not in sensor_names_in_rules:
                continue
            ante = ctrl.Antecedent(
                np.arange(s.min_val, s.max_val + 1, 1), s.name
            )
            for mf in s.mf_config:
                name = mf["term"]
                mf_type = mf.get("type", "trimf")
                params = mf["params"]
                if mf_type == "trimf" and len(params) >= 3:
                    ante[name] = fuzz.trimf(ante.universe, params[:3])
                elif mf_type == "trapmf" and len(params) >= 4:
                    ante[name] = fuzz.trapmf(ante.universe, params[:4])
                elif mf_type == "gaussmf" and len(params) >= 2:
                    ante[name] = fuzz.gaussmf(ante.universe, params[0], params[1])
            antecedents[s.name] = ante

        consequent = ctrl.Consequent(
            np.arange(asset.output_min, asset.output_max + 1, 1),
            asset.output_name
        )
        for r in rules:
            if r.enabled:
                ct = r.consequent
                term = ct["term"]
                if "mf_config" in ct:
                    cfg = ct["mf_config"]
                    t = cfg.get("type", "trimf")
                    p = cfg["params"]
                    if t == "trimf" and len(p) >= 3:
                        consequent[term] = fuzz.trimf(consequent.universe, p[:3])
                    elif t == "trapmf" and len(p) >= 4:
                        consequent[term] = fuzz.trapmf(consequent.universe, p[:4])
                else:
                    defaults = {
                        "none": fuzz.trimf(consequent.universe, [0, 0, 20]),
                        "low": fuzz.trimf(consequent.universe, [0, 0, 30]),
                        "medium": fuzz.trimf(consequent.universe, [20, 50, 80]),
                        "high": fuzz.trimf(consequent.universe, [60, 85, 100]),
                        "critical": fuzz.trimf(consequent.universe, [85, 100, 100]),
                    }
                    if term in defaults:
                        consequent[term] = defaults[term]

        ctrl_rules = []
        for r in rules:
            if not r.enabled:
                continue
            ant_conditions = []
            for ant in r.antecedents:
                sensor_name = ant["sensor"]
                term_name = ant["term"]
                if sensor_name in antecedents and term_name in antecedents[sensor_name].terms:
                    ant_conditions.append(antecedents[sensor_name][term_name])

            if not ant_conditions:
                continue

            if r.operator == "or":
                antecedent_expr = ant_conditions[0]
                for ac in ant_conditions[1:]:
                    antecedent_expr = antecedent_expr | ac
            else:
                antecedent_expr = ant_conditions[0]
                for ac in ant_conditions[1:]:
                    antecedent_expr = antecedent_expr & ac

            cons_name = r.consequent["term"]
            if cons_name in consequent.terms:
                ctrl_rules.append(ctrl.Rule(antecedent_expr, consequent[cons_name]))

        system = ctrl.ControlSystem(ctrl_rules)
        sim = ctrl.ControlSystemSimulation(system)

        self._cache[cache_key] = {
            "simulation": sim,
            "antecedents": antecedents,
            "consequent": consequent,
            "sensor_map": {s.name: s for s in sensors},
        }
        return self._cache[cache_key]

    def evaluate(self, asset, sensors, rules, values):
        """Run the fuzzy inference and return the defuzzified score (0-100).

        Sets each sensor's current value as input to the fuzzy system,
        computes the output, and returns the crisp result.
        """
        built = self.build_system(asset, sensors, rules)
        sim = built["simulation"]
        antecedents = built["antecedents"]

        for s in sensors:
            if s.name in values and s.name in antecedents:
                sim.input[s.name] = max(s.min_val, min(s.max_val, values[s.name]))

        sim.compute()
        score = 0.0
        if asset.output_name in sim.output:
            score = round(float(sim.output[asset.output_name]), 1)
        return score

    def get_status(self, score, output_max=100):
        """Convert a numeric score to a 3-state traffic light status.

        Thresholds (as percentage of output_max):
        - Rojo (high): >= 60
        - Amarillo (medium): >= 30
        - Verde (low): < 30
        """
        pct = (score / output_max) * 100 if output_max > 0 else score
        if pct >= 60:
            return "high"
        elif pct >= 30:
            return "medium"
        else:
            return "low"

    def get_active_rules(self, asset, sensors, rules, values):
        """Evaluate all rules and return those with fire_strength > 0.

        For each enabled rule, calculates the fire strength by evaluating
        membership degrees of each antecedent at the current sensor values,
        combined using the rule's AND/OR operator.

        Returns a list sorted by fire_strength descending, with action data.
        """
        built = self.build_system(asset, sensors, rules)
        antecedents = built["antecedents"]

        sensor_map = {s.name: s for s in sensors}

        results = []
        for r in rules:
            if not r.enabled:
                continue
            fire_strengths = []
            for ant in r.antecedents:
                s_name = ant["sensor"]
                term = ant["term"]
                if s_name in antecedents and term in antecedents[s_name].terms and s_name in sensor_map:
                    s_cfg = sensor_map[s_name]
                    val = max(s_cfg.min_val, min(s_cfg.max_val, values.get(s_name, 0)))
                    memberships = fuzz.interp_membership(
                        antecedents[s_name].universe,
                        antecedents[s_name][term].mf,
                        val
                    )
                    fire_strengths.append(memberships)

            if not fire_strengths:
                continue

            if r.operator == "or":
                strength = max(fire_strengths)
            else:
                strength = min(fire_strengths)

            results.append({
                "id": f"R{r.id}",
                "name": r.name,
                "description": r.description or self._rule_desc(r),
                "fire_strength": round(float(strength), 3),
                "enabled": True,
                "action": r.action,
            })

        results.sort(key=lambda x: x["fire_strength"], reverse=True)
        return results

    def _rule_desc(self, rule):
        """Generate a human-readable description of a rule."""
        op = " O " if rule.operator == "or" else " Y "
        ants = f" {op} ".join(
            f"{a['sensor']} es {a['term']}" for a in rule.antecedents
        )
        cons = f"{rule.consequent['sensor']}={rule.consequent['term']}"
        return f"SI {ants} ENTONCES {cons}"
