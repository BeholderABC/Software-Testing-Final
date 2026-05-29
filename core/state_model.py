"""
state_model.py  --  White-box test design via state-transition coverage

Implements FR 4.0: model the system's behaviour as a finite state machine
and generate optimal test sequences against well-defined coverage criteria
(all states, all transitions).

The default model in [data/order_state_model.json](../data/order_state_model.json)
describes the Order status machine of the Mini-E-Commerce backend:

    pending ──complete──> completed
    pending ──cancel─────> cancelled

Both `completed` and `cancelled` are terminal states; any further attempt
to transition out is invalid and contributes a "guard" coverage item.

The output of `generate_state_test_cases(...)` is shaped exactly like the
black-box engine's output so the rest of the pipeline (optimiser,
exporter, in-UI runner) can consume it unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


TECHNIQUE = "State Transition Testing"


# ---------------------------------------------------------------------------
# Model dataclasses
# ---------------------------------------------------------------------------

@dataclass
class StateTransition:
    """Single state → state edge triggered by an event."""

    source: str
    event: str
    target: str
    description: str = ""
    valid: bool = True

    def label(self) -> str:
        prefix = "" if self.valid else "(invalid) "
        return f"{prefix}{self.source} --{self.event}--> {self.target}"


@dataclass
class StateModel:
    """Container for a labelled state machine + helpers."""

    name: str
    states: List[str]
    initial: str
    terminal: List[str]
    transitions: List[StateTransition]
    requirement_id: str = ""
    feature: str = ""

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "StateModel":
        transitions = [
            StateTransition(
                source=t["source"], event=t["event"], target=t["target"],
                description=t.get("description", ""),
                valid=t.get("valid", True),
            )
            for t in payload.get("transitions", [])
        ]
        return cls(
            name=payload.get("name", "unnamed"),
            states=list(payload.get("states", [])),
            initial=payload.get("initial", ""),
            terminal=list(payload.get("terminal", [])),
            transitions=transitions,
            requirement_id=payload.get("requirement_id", ""),
            feature=payload.get("feature", ""),
        )

    @classmethod
    def from_json(cls, path: Path) -> "StateModel":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def valid_transitions(self) -> List[StateTransition]:
        return [t for t in self.transitions if t.valid]

    def invalid_transitions(self) -> List[StateTransition]:
        return [t for t in self.transitions if not t.valid]


# ---------------------------------------------------------------------------
# Coverage algorithms
# ---------------------------------------------------------------------------

def all_states_sequences(model: StateModel) -> List[List[StateTransition]]:
    """Return BFS paths from `initial` that together visit every state.

    Greedy: extend the frontier until each state appears in at least one
    returned path. Each path is a list of transitions starting at
    `initial`.
    """
    visited = {model.initial}
    paths: List[List[StateTransition]] = []
    frontier: List[Tuple[str, List[StateTransition]]] = [(model.initial, [])]
    valid_edges = model.valid_transitions()

    while frontier and visited != set(model.states):
        state, path = frontier.pop(0)
        for tr in valid_edges:
            if tr.source != state:
                continue
            if tr.target in visited:
                continue
            new_path = path + [tr]
            visited.add(tr.target)
            paths.append(new_path)
            frontier.append((tr.target, new_path))

    if not paths:
        # Single-state machine: still emit an "observation" path.
        paths.append([])
    return paths


def all_transitions_sequences(model: StateModel
                              ) -> List[List[StateTransition]]:
    """Return one path per valid transition (each path: initial → … → that edge).

    Simple BFS shortest-path to the transition's source, then take the
    transition. Together the paths cover every valid edge at least once
    (FR 4.0 "all transitions" criterion).
    """
    valid_edges = model.valid_transitions()
    parents = _shortest_paths_from(model, model.initial)
    paths: List[List[StateTransition]] = []
    for tr in valid_edges:
        prefix = _reconstruct(parents, tr.source)
        paths.append(prefix + [tr])
    return paths


def invalid_transition_guards(model: StateModel
                              ) -> List[List[StateTransition]]:
    """Return one path per invalid transition for negative coverage.

    Negative cases ensure the implementation rejects undefined moves
    (terminal → anything else, or undeclared events). Each returned path
    walks to the invalid edge's source then attempts the bad move.
    """
    parents = _shortest_paths_from(model, model.initial)
    paths: List[List[StateTransition]] = []
    for tr in model.invalid_transitions():
        prefix = _reconstruct(parents, tr.source)
        paths.append(prefix + [tr])
    return paths


def _shortest_paths_from(model: StateModel,
                         start: str) -> Dict[str, Optional[StateTransition]]:
    """BFS parent map; parents[state] = the transition used to enter state."""
    parents: Dict[str, Optional[StateTransition]] = {start: None}
    queue: List[str] = [start]
    valid_edges = model.valid_transitions()
    while queue:
        node = queue.pop(0)
        for tr in valid_edges:
            if tr.source != node or tr.target in parents:
                continue
            parents[tr.target] = tr
            queue.append(tr.target)
    return parents


def _reconstruct(parents: Dict[str, Optional[StateTransition]],
                  state: str) -> List[StateTransition]:
    """Walk the parent map back to the initial state."""
    chain: List[StateTransition] = []
    cursor: Optional[str] = state
    while cursor is not None and parents.get(cursor) is not None:
        tr = parents[cursor]
        assert tr is not None
        chain.append(tr)
        cursor = tr.source
    return list(reversed(chain))


# ---------------------------------------------------------------------------
# Test-case rendering (same shape as the black-box engine)
# ---------------------------------------------------------------------------

def _format_steps(path: List[StateTransition], initial: str) -> List[str]:
    """Human-readable steps for the test case `steps` field."""
    if not path:
        return [f"Observe initial state '{initial}'"]
    steps = [f"Place the system in state '{initial}'"]
    for i, tr in enumerate(path, start=1):
        verb = "Trigger" if tr.valid else "Attempt"
        steps.append(
            f"Step {i}: {verb} event '{tr.event}' "
            f"(expected target: '{tr.target}')")
    return steps


def _format_title(model: StateModel, path: List[StateTransition],
                  kind: str) -> str:
    if not path:
        return f"Observe initial state of {model.feature}"
    last = path[-1]
    return (f"{kind.title()}: {last.source} --{last.event}--> {last.target} "
            f"({'invalid' if not last.valid else 'valid'})")


def _build_test_case(model: StateModel, path: List[StateTransition],
                     index: int, kind: str) -> Dict[str, Any]:
    """Convert one transition sequence into the project's test-case shape."""
    if path:
        last = path[-1]
        valid = last.valid
        coverage_type = "positive" if valid else "negative"
        expected = (
            f"After the sequence, the system is in state '{last.target}'."
            if valid else
            f"The system rejects event '{last.event}' from terminal "
            f"state '{last.source}' and stays in '{last.source}'."
        )
        covered_item = last.label()
    else:
        coverage_type = "positive"
        expected = (
            f"The system reports state '{model.initial}' on observation.")
        covered_item = f"initial state: {model.initial}"

    rid = model.requirement_id or "REQ-STATE"
    return {
        "test_case_id": f"TC-{rid}-S{index:03d}",
        "requirement_id": rid,
        "feature": model.feature,
        "title": _format_title(model, path, kind),
        "description": (
            f"State-coverage case ({kind}) derived from the {model.name} "
            "model."),
        "test_design_technique": TECHNIQUE,
        "coverage_item": covered_item,
        "coverage_type": coverage_type,
        "preconditions": [f"system in initial state '{model.initial}'"],
        "test_data": {"event_sequence": [tr.event for tr in path]},
        "steps": _format_steps(path, model.initial),
        "expected_result": expected,
        "priority": "Medium",
        "risk_level": "Medium",
        "risk_score": 5,
        "traceability": {
            "source_requirement": rid,
            "covered_item": covered_item,
            "coverage_strategy": f"state-transition coverage ({kind})",
        },
        "review_status": "generated",
        "need_manual_review": False,
    }


def generate_state_test_cases(model: StateModel,
                              strategy: str = "all_transitions"
                              ) -> Dict[str, Any]:
    """Produce the full test-suite payload for the given coverage strategy.

    Strategies:
      - "all_states"        — every state reached at least once
      - "all_transitions"   — every valid edge fired at least once
      - "all_transitions+guards" — also exercise declared invalid edges
    """
    strategy = strategy.lower().replace(" ", "")
    if strategy == "all_states":
        paths = all_states_sequences(model)
        kind = "all-states"
    elif strategy == "all_transitions":
        paths = all_transitions_sequences(model)
        kind = "all-transitions"
    elif strategy == "all_transitions+guards":
        paths = (all_transitions_sequences(model)
                 + invalid_transition_guards(model))
        kind = "all-transitions+guards"
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    test_cases = [_build_test_case(model, path, idx, kind)
                  for idx, path in enumerate(paths, start=1)]

    by_type: Dict[str, int] = {}
    for tc in test_cases:
        by_type[tc["coverage_type"]] = by_type.get(tc["coverage_type"], 0) + 1

    return {
        "test_cases": test_cases,
        "summary": {
            "total": len(test_cases),
            "strategy": kind,
            "by_technique": {TECHNIQUE: len(test_cases)},
            "by_coverage_type": by_type,
        },
    }


# ---------------------------------------------------------------------------
# Convenience loader
# ---------------------------------------------------------------------------

def load_default_order_model() -> StateModel:
    """Load the bundled Order status model used by the demo."""
    path = (Path(__file__).resolve().parent.parent
            / "data" / "order_state_model.json")
    return StateModel.from_json(path)


# Manual smoke test
if __name__ == "__main__":
    model = load_default_order_model()
    for strategy in ("all_states", "all_transitions",
                     "all_transitions+guards"):
        result = generate_state_test_cases(model, strategy=strategy)
        print(f"--- {strategy} ---")
        print(f"  {result['summary']}")
        for tc in result["test_cases"]:
            print(f"    {tc['test_case_id']}: {tc['title']}")
